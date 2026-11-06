"""Explicit one-time local operator provisioning; passwords never enter argv or logs."""

import argparse
from getpass import getpass

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.enums import AdminType, UserRole, UserStatus
from app.models.user import User
from app.schemas.auth import AdminRegisterRequest


def provision(db, *, email, password):
    validated = AdminRegisterRequest(email=email, password=password)
    if db.query(User.id).filter(User.email == validated.email.lower()).first():
        raise ValueError("Account already exists; refusing to replace or promote it")
    user = User(
        email=validated.email.lower(),
        password_hash=hash_password(validated.password),
        role=UserRole.ADMIN,
        admin_type=AdminType.SUPER_ADMIN,
        is_superadmin=True,
        is_active=True,
        is_verified=True,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    return user.id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    password = getpass("New superadmin password: ")
    if password != getpass("Confirm password: "):
        raise SystemExit("Passwords do not match")
    try:
        with SessionLocal() as db:
            provision(db, email=args.email, password=password)
    except ValueError:
        # ValidationError contains supplied values; never print an operator password.
        raise SystemExit("Provisioning failed: invalid fields or an existing account") from None
    print("Superadmin provisioned")


if __name__ == "__main__":
    main()
