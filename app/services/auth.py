from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from app.core import config
from app.core.exceptions import AppError, BadRequestError, NotFoundError, UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    has_legacy_bootstrap_password,
    hash_password,
    hash_token,
    verify_password,
    verify_token_hash,
)
from app.models.enums import (
    AdminType,
    UserRole,
    UserStatus,
    VerificationChannel,
    VerificationPurpose,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.models.verification_otp import VerificationOtp
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.repositories.verification_otp import VerificationOtpRepository
from app.schemas.auth import (
    AdminRegisterRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    ResendEmailVerificationOtpRequest,
    ResetPasswordRequest,
    UserRead,
    UserRegisterRequest,
    VerifyEmailRequest,
)
from app.services.email import EmailService


class AuthService:
    def __init__(
        self,
        repository: UserRepository,
        refresh_token_repository: RefreshTokenRepository,
        verification_otp_repository: VerificationOtpRepository,
        email_service: EmailService,
    ) -> None:
        self.repository = repository
        self.refresh_token_repository = refresh_token_repository
        self.verification_otp_repository = verification_otp_repository
        self.email_service = email_service

    def register_user(self, payload: UserRegisterRequest) -> UserRead:
        email = payload.email.lower()
        if self.repository.get_by_email(email) is not None:
            raise BadRequestError(
                "A user with this email already exists",
                data={"email": email},
            )

        otp = self._generate_otp()
        try:
            user = self.repository.add(
                User(
                    email=email,
                    password_hash=hash_password(payload.password),
                    first_name=payload.first_name,
                    last_name=payload.last_name,
                    phone_number=payload.phone_number,
                    role=UserRole.USER,
                    admin_type=None,
                    is_superadmin=False,
                    is_verified=False,
                    status=UserStatus.UNVERIFIED,
                )
            )
            self._store_email_verification_otp_without_commit(user, otp)
            self.repository.db.commit()
            self.repository.db.refresh(user)
        except Exception:
            self.repository.db.rollback()
            raise

        self._send_email_verification_otp_to_user(user, otp)
        return self._to_schema(user)

    def register_admin(self, payload: AdminRegisterRequest) -> UserRead:
        admin_type = self._parse_admin_type(payload.admin_type)
        return self._create_user(
            email=payload.email,
            password=payload.password,
            first_name=payload.first_name,
            last_name=payload.last_name,
            role=UserRole.ADMIN,
            admin_type=admin_type,
            is_superadmin=admin_type == AdminType.SUPER_ADMIN,
        )

    def _create_user(
        self,
        *,
        email: str,
        password: str,
        first_name: str | None,
        last_name: str | None,
        role: UserRole,
        admin_type: AdminType | None,
        is_superadmin: bool,
    ) -> UserRead:
        if self.repository.get_by_email(email) is not None:
            raise BadRequestError(
                "A user with this email already exists",
                data={"email": email},
            )

        user = self.repository.create(
            User(
                email=email.lower(),
                password_hash=hash_password(password),
                first_name=first_name,
                last_name=last_name,
                role=role,
                admin_type=admin_type,
                is_superadmin=is_superadmin,
                is_verified=role == UserRole.ADMIN,
                status=UserStatus.ACTIVE if role == UserRole.ADMIN else UserStatus.UNVERIFIED,
            )
        )
        return self._to_schema(user)

    def login(self, payload: LoginRequest) -> LoginResponse:
        try:
            # Serialize password verification and token issuance with password resets.
            user = self.repository.get_by_email(payload.email, for_update=True)
            if user is None or not verify_password(payload.password, user.password_hash):
                raise UnauthorizedError("Invalid email or password")
            if not user.is_active:
                raise UnauthorizedError("User account is inactive")
            if not user.is_verified:
                raise UnauthorizedError("Please verify your email address before logging in")

            user = self.repository.mark_login(user, commit=False)
            access_token = self._build_access_token(user)
            refresh_token = self._issue_refresh_token(user, commit=False)
            self.repository.db.commit()
            return LoginResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                user=self._to_schema(user),
            )
        except Exception:
            self.repository.db.rollback()
            raise

    @staticmethod
    def _can_reset_password(user: User | None) -> bool:
        return (
            user is not None
            and user.is_active
            and user.status != UserStatus.SUSPENDED
            and not has_legacy_bootstrap_password(user.password_hash)
        )

    def forgot_password(self, payload: ForgotPasswordRequest) -> None:
        db = self.repository.db
        try:
            user = self.repository.get_by_email(payload.email, for_update=True)
            if not self._can_reset_password(user):
                db.commit()
                return
            latest = self.verification_otp_repository.get_latest_for_user(
                user.id,
                purpose=VerificationPurpose.PASSWORD_RESET,
                channel=VerificationChannel.EMAIL,
            )
            if latest is not None:
                created = latest.created_at
                created = created.replace(tzinfo=UTC) if created.tzinfo is None else created
                if (
                    datetime.now(UTC) - created
                ).total_seconds() < config.AUTH_OTP_RESEND_COOLDOWN_SECONDS:
                    db.commit()
                    return
            length = min(12, max(6, config.PASSWORD_RESET_OTP_LENGTH))
            otp = f"{secrets.randbelow(10**length):0{length}d}"
            self.verification_otp_repository.deactivate_active_for_user_without_commit(
                user.id,
                purpose=VerificationPurpose.PASSWORD_RESET,
                channel=VerificationChannel.EMAIL,
            )
            self.verification_otp_repository.add(
                VerificationOtp(
                    user_id=user.id,
                    otp_hash=hash_token(otp),
                    purpose=VerificationPurpose.PASSWORD_RESET,
                    channel=VerificationChannel.EMAIL,
                    target=user.email,
                    expires_at=datetime.now(UTC)
                    + timedelta(minutes=max(1, config.PASSWORD_RESET_OTP_EXPIRE_MINUTES)),
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        self.email_service.send_email(
            to_email=user.email,
            subject="Reset your Kompare password",
            body=(
                f"Your Kompare password reset code is {otp}.\n\n"
                f"This code expires in {max(1, config.PASSWORD_RESET_OTP_EXPIRE_MINUTES)} "
                "minutes.\n"
                "If you did not request this, you can ignore this email."
            ),
        )

    def reset_password(self, payload: ResetPasswordRequest) -> None:
        db = self.repository.db
        try:
            # All reset, resend, login and refresh operations lock the same parent first.
            user = self.repository.get_by_email(payload.email, for_update=True)
            if not self._can_reset_password(user):
                raise BadRequestError("Invalid or expired password reset code")
            active_otp = self.verification_otp_repository.get_active_for_user(
                user.id,
                purpose=VerificationPurpose.PASSWORD_RESET,
                channel=VerificationChannel.EMAIL,
                target=user.email,
                for_update=True,
            )
            if active_otp is None or active_otp.failed_attempts >= config.AUTH_OTP_MAX_ATTEMPTS:
                raise BadRequestError("Invalid or expired password reset code")
            if not verify_token_hash(payload.otp, active_otp.otp_hash):
                active_otp.failed_attempts += 1
                if active_otp.failed_attempts >= config.AUTH_OTP_MAX_ATTEMPTS:
                    active_otp.is_active = False
                db.commit()
                raise BadRequestError("Invalid or expired password reset code")
            user.password_hash = hash_password(payload.new_password)
            user.auth_version += 1
            self.verification_otp_repository.mark_used_without_commit(active_otp)
            self.verification_otp_repository.deactivate_active_for_user_without_commit(
                user.id,
                purpose=VerificationPurpose.PASSWORD_RESET,
                channel=VerificationChannel.EMAIL,
            )
            self.refresh_token_repository.revoke_all_for_user_without_commit(user.id)
            db.commit()
        except Exception:
            db.rollback()
            raise

    def refresh(self, payload: RefreshTokenRequest) -> LoginResponse:
        try:
            token_payload = decode_access_token(payload.refresh_token)
        except Exception as exc:
            raise UnauthorizedError("Invalid or expired refresh token") from exc

        if token_payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid refresh token type")

        token_id = token_payload.get("jti")
        subject = token_payload.get("sub")
        if not token_id or not subject:
            raise UnauthorizedError("Invalid refresh token payload")

        db = self.repository.db
        try:
            user = (
                db.query(User)
                .filter(User.id == int(subject))
                .with_for_update()
                .populate_existing()
                .one_or_none()
            )
            if (
                user is None
                or not user.is_active
                or not user.is_verified
                or has_legacy_bootstrap_password(user.password_hash)
            ):
                raise UnauthorizedError("User account is unavailable")
            consumed = self.refresh_token_repository.consume(
                token_id=str(token_id),
                token_hash=hash_token(payload.refresh_token),
                user_id=user.id,
                now=datetime.now(UTC),
            )
            if not consumed:
                raise UnauthorizedError("Refresh token is no longer valid")
            access_token = self._build_access_token(user)
            refresh_token = self._issue_refresh_token(user, commit=False)
            db.commit()
            return LoginResponse(
                access_token=access_token, refresh_token=refresh_token, user=self._to_schema(user)
            )
        except Exception:
            db.rollback()
            raise

    def logout(self, payload: RefreshTokenRequest) -> None:
        try:
            token_payload = decode_access_token(payload.refresh_token)
        except Exception as exc:
            raise UnauthorizedError("Invalid or expired refresh token") from exc

        if token_payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid refresh token type")

        token_id = token_payload.get("jti")
        if not token_id:
            raise UnauthorizedError("Invalid refresh token payload")

        stored_token = self.refresh_token_repository.get_active_by_token_id(str(token_id))
        if stored_token is None:
            return

        if verify_token_hash(payload.refresh_token, stored_token.token_hash):
            self.refresh_token_repository.revoke(stored_token)

    def verify_email(self, payload: VerifyEmailRequest) -> UserRead:
        try:
            # Stable parent lock serializes verification with OTP resends.
            user = self.repository.get_by_email(payload.email, for_update=True)
            if user is None or not user.is_active:
                raise BadRequestError("Invalid verification details")
            if user.is_verified:
                self.repository.db.commit()
                return self._to_schema(user)
            active_otp = self.verification_otp_repository.get_active_for_user(
                user.id,
                purpose=VerificationPurpose.EMAIL_VERIFICATION,
                channel=VerificationChannel.EMAIL,
                target=user.email,
                for_update=True,
            )
            if active_otp is None or active_otp.failed_attempts >= config.AUTH_OTP_MAX_ATTEMPTS:
                raise BadRequestError("Invalid or expired verification OTP")
            if not verify_token_hash(payload.otp, active_otp.otp_hash):
                active_otp.failed_attempts += 1
                if active_otp.failed_attempts >= config.AUTH_OTP_MAX_ATTEMPTS:
                    active_otp.is_active = False
                self.repository.db.commit()
                raise BadRequestError("Invalid or expired verification OTP")
            self.verification_otp_repository.mark_used_without_commit(active_otp)
            verified_user = self.repository.mark_verified_without_commit(user)
            self.repository.db.commit()
            self.repository.db.refresh(verified_user)
            return self._to_schema(verified_user)
        except Exception:
            self.repository.db.rollback()
            raise

    def resend_email_verification_otp(self, payload: ResendEmailVerificationOtpRequest) -> None:
        user = self.repository.get_by_email(payload.email)
        # Uniform public response avoids revealing account membership.
        if user is not None and user.is_active and not user.is_verified:
            try:
                self.send_email_verification_otp_for_user(user)
            except AppError as exc:
                # The public endpoint must not reveal whether an account has a recent code.
                if exc.error_code != "auth_rate_limited":
                    raise

    def _build_access_token(self, user: User) -> str:
        token = create_access_token(
            subject=str(user.id),
            email=user.email,
            role=user.role.value,
            admin_type=user.admin_type.value if user.admin_type else None,
            is_superadmin=user.is_superadmin,
            is_active=user.is_active,
            is_verified=user.is_verified,
            first_name=user.first_name,
            last_name=user.last_name,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
            updated_at=user.updated_at,
            auth_version=user.auth_version,
        )
        return token

    def _issue_refresh_token(self, user: User, *, commit: bool = True) -> str:
        token_id = secrets.token_urlsafe(32)
        refresh_token, expires_at = create_refresh_token(
            subject=str(user.id),
            token_id=token_id,
        )
        self.refresh_token_repository.create(
            RefreshToken(
                user_id=user.id,
                token_id=token_id,
                token_hash=hash_token(refresh_token),
                expires_at=expires_at,
            ),
            commit=commit,
        )
        return refresh_token

    def _send_email_verification_otp(self, email: str) -> None:
        user = self.repository.get_by_email(email)
        if user is None:
            raise NotFoundError("User not found", data={"email": email})

        self.send_email_verification_otp_for_user(user)

    def send_email_verification_otp_for_user(self, user: User) -> None:
        otp = self._generate_otp()
        try:
            user = self.repository.get_by_email(user.email, for_update=True)
            latest = (
                self.repository.db.query(VerificationOtp)
                .filter_by(
                    user_id=user.id,
                    purpose=VerificationPurpose.EMAIL_VERIFICATION,
                    channel=VerificationChannel.EMAIL,
                )
                .order_by(VerificationOtp.created_at.desc(), VerificationOtp.id.desc())
                .first()
            )
            if latest is not None:
                created = (
                    latest.created_at.replace(tzinfo=UTC)
                    if latest.created_at.tzinfo is None
                    else latest.created_at
                )
                remaining = (
                    config.AUTH_OTP_RESEND_COOLDOWN_SECONDS
                    - (datetime.now(UTC) - created).total_seconds()
                )
                if remaining > 0:
                    raise AppError(
                        "Please wait before requesting another code",
                        status_code=429,
                        error_code="auth_rate_limited",
                        data={"retry_after": max(1, int(remaining))},
                    )
            self._store_email_verification_otp_without_commit(user, otp)
            self.repository.db.commit()
        except Exception:
            self.repository.db.rollback()
            raise
        self._send_email_verification_otp_to_user(user, otp)

    def _store_email_verification_otp_without_commit(self, user: User, otp: str) -> VerificationOtp:
        self.verification_otp_repository.deactivate_active_for_user_without_commit(
            user.id,
            purpose=VerificationPurpose.EMAIL_VERIFICATION,
            channel=VerificationChannel.EMAIL,
            target=user.email,
        )
        return self.verification_otp_repository.add(
            VerificationOtp(
                user_id=user.id,
                otp_hash=hash_token(otp),
                purpose=VerificationPurpose.EMAIL_VERIFICATION,
                channel=VerificationChannel.EMAIL,
                target=user.email,
                expires_at=datetime.now(UTC)
                + timedelta(minutes=config.EMAIL_VERIFICATION_OTP_EXPIRE_MINUTES),
            )
        )

    def _send_email_verification_otp_to_user(self, user: User, otp: str) -> None:
        self.email_service.send_email(
            to_email=user.email,
            subject="Verify your Kompare email",
            body=(
                f"Your Kompare verification code is {otp}.\n\n"
                f"This code expires in {config.EMAIL_VERIFICATION_OTP_EXPIRE_MINUTES} minutes."
            ),
            html_body=(
                "<p>Your Kompare verification code is:</p>"
                f"<h2>{otp}</h2>"
                f"<p>This code expires in {config.EMAIL_VERIFICATION_OTP_EXPIRE_MINUTES} "
                "minutes.</p>"
            ),
        )

    @staticmethod
    def _generate_otp() -> str:
        length = max(config.EMAIL_VERIFICATION_OTP_LENGTH, 4)
        upper_bound = 10**length
        return f"{secrets.randbelow(upper_bound):0{length}d}"

    def get_user_by_id(self, user_id: int) -> User:
        user = self.repository.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found", data={"user_id": user_id})
        return user

    @staticmethod
    def _to_schema(user: User) -> UserRead:
        return UserRead(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            phone_number=user.phone_number,
            role=user.role.value,
            admin_type=user.admin_type.value if user.admin_type else None,
            is_superadmin=user.is_superadmin,
            is_active=user.is_active,
            is_verified=user.is_verified,
            is_phone_verified=user.is_phone_verified,
            status=user.status.value,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    @staticmethod
    def _parse_admin_type(admin_type: str) -> AdminType:
        try:
            parsed = AdminType(admin_type)
        except ValueError as exc:
            raise BadRequestError(
                "Invalid admin type",
                data={
                    "admin_type": admin_type,
                    "allowed_values": [value.value for value in AdminType],
                },
            ) from exc
        return parsed
