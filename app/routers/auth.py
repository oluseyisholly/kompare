from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies import get_auth_service
from app.dependencies.auth import get_current_user, require_superadmin
from app.dependencies.auth_limits import limit_auth_request
from app.schemas.auth import (
    AdminRegisterRequest,
    AuthenticatedUser,
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
from app.schemas.common import ApiResponse
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/forgot-password",
    response_model=ApiResponse[dict[str, str]],
    summary="Request a password reset code",
    description="Public and rate limited. Returns the same response for unknown and unavailable "
    "accounts. An eligible account receives an expiring code by email. Request again to resend; "
    "only the latest code is valid.",
)
def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[dict[str, str]]:
    limit_auth_request(request, db, action="forgot_password", account=payload.email)
    service.forgot_password(payload)
    return ApiResponse(
        responseCode=200,
        message="If the account is eligible, a password reset code will be sent to its email.",
        data={"status": "accepted"},
    )


@router.post(
    "/reset-password",
    response_model=ApiResponse[dict[str, str]],
    summary="Reset a password using an email code",
    description="Public and rate limited. Requires the email, a valid single-use password reset "
    "code and a new password (8–128 characters). Invalid attempts are limited per code. "
    "Success revokes existing access and refresh tokens; log in with the new password.",
)
def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[dict[str, str]]:
    limit_auth_request(request, db, action="reset_password", account=payload.email)
    service.reset_password(payload)
    return ApiResponse(
        responseCode=200,
        message="Password reset successfully. Please log in again.",
        data={"status": "password_reset"},
    )


@router.post("/register", response_model=ApiResponse[UserRead], status_code=201)
def register(
    request: Request,
    payload: UserRegisterRequest,
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[UserRead]:
    limit_auth_request(request, db, action="register", account=payload.email)
    return ApiResponse(
        responseCode=201,
        message="User onboarded successfully",
        data=service.register_user(payload),
    )


@router.post("/admins", response_model=ApiResponse[UserRead], status_code=201)
def register_admin(
    payload: AdminRegisterRequest,
    service: AuthService = Depends(get_auth_service),
    current_user: AuthenticatedUser = Depends(require_superadmin),
) -> ApiResponse[UserRead]:
    del current_user
    return ApiResponse(
        responseCode=201,
        message="Admin created successfully",
        data=service.register_admin(payload),
    )


@router.post("/login", response_model=ApiResponse[LoginResponse])
def login(
    request: Request,
    payload: LoginRequest,
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[LoginResponse]:
    limit_auth_request(request, db, action="login", account=payload.email)
    return ApiResponse(
        responseCode=200,
        message="Login successful",
        data=service.login(payload),
    )


@router.post("/verify-email", response_model=ApiResponse[UserRead])
def verify_email(
    request: Request,
    payload: VerifyEmailRequest,
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[UserRead]:
    limit_auth_request(request, db, action="verify", account=payload.email)
    return ApiResponse(
        responseCode=200,
        message="Email verified successfully",
        data=service.verify_email(payload),
    )


@router.post("/resend-verification-otp", response_model=ApiResponse[dict[str, str]])
def resend_verification_otp(
    request: Request,
    payload: ResendEmailVerificationOtpRequest,
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[dict[str, str]]:
    limit_auth_request(request, db, action="resend", account=payload.email)
    service.resend_email_verification_otp(payload)
    return ApiResponse(
        responseCode=200,
        message="Verification OTP sent successfully",
        data={"status": "sent"},
    )


@router.post("/refresh", response_model=ApiResponse[LoginResponse])
def refresh_token(
    payload: RefreshTokenRequest,
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[LoginResponse]:
    return ApiResponse(
        responseCode=200,
        message="Token refreshed successfully",
        data=service.refresh(payload),
    )


@router.post("/logout", response_model=ApiResponse[dict[str, str]])
def logout(
    payload: RefreshTokenRequest,
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[dict[str, str]]:
    service.logout(payload)
    return ApiResponse(
        responseCode=200,
        message="Logout successful",
        data={"status": "logged_out"},
    )


@router.get("/me", response_model=ApiResponse[UserRead])
def get_me(current_user: AuthenticatedUser = Depends(get_current_user)) -> ApiResponse[UserRead]:
    return ApiResponse(
        responseCode=200,
        message="Authenticated user retrieved successfully",
        data=UserRead(
            id=current_user.id,
            email=current_user.email,
            first_name=current_user.first_name,
            last_name=current_user.last_name,
            phone_number=current_user.phone_number,
            role=current_user.role,
            admin_type=current_user.admin_type,
            status=current_user.status,
            is_superadmin=current_user.is_superadmin,
            is_active=current_user.is_active,
            is_verified=current_user.is_verified,
            is_phone_verified=current_user.is_phone_verified,
            last_login_at=current_user.last_login_at,
            created_at=current_user.created_at,
            updated_at=current_user.updated_at,
        ),
    )
