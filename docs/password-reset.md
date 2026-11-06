# Password recovery

Two public, rate-limited endpoints are available in Swagger under Authentication.
They use the existing SMTP email service and `verification_otps` table. No logged-in
session or bearer token is required.

1. `POST /auth/forgot-password`

   ```json
   {"email": "user@example.com"}
   ```

   Always returns HTTP 200 with `data.status = "accepted"` for a valid, permitted request,
   whether the account exists or is eligible. Eligible users receive a numeric reset code.
   The response does not contain the code or a token. Disabled and suspended accounts
   cannot use password recovery. SMTP must be configured for delivery; delivery failures
   are logged by the existing email service and do not disclose account existence.

2. `POST /auth/reset-password`

   ```json
   {
     "email": "user@example.com",
     "otp": "123456",
     "new_password": "NewExamplePassword123!"
   }
   ```

   Use the real code from the reset email. The password follows the existing 8–128 character
   policy. Invalid, expired, exhausted or already-used codes return the same HTTP 400 error.
   Invalid payloads return 422 and throttled requests return 429 with `Retry-After`.
   Success returns HTTP 200 with `data.status = "password_reset"`. The user must log in
   again; all previously issued access and refresh tokens are invalidated. Resetting a
   password does not verify an email address, change roles or reactivate an account.

To resend, call forgot-password again after the cooldown. Each new code invalidates
earlier reset codes. Email verification codes and password reset codes are separate.
Only code hashes are stored. Password updates, code consumption and session revocation
commit atomically. User row locks serialize resets with resends, login and refresh.

Configuration (documented in `.env.example`):

- `PASSWORD_RESET_OTP_EXPIRE_MINUTES=10` (minimum one minute).
- `PASSWORD_RESET_OTP_LENGTH=6` (bounded to 6–12 digits).
- Existing `AUTH_OTP_MAX_ATTEMPTS=5`, `AUTH_OTP_RESEND_COOLDOWN_SECONDS=60`,
  `AUTH_EMAIL_*` and `AUTH_OTP_IP_LIMIT` controls apply.
- Existing `SMTP_*` and `EMAIL_FROM` settings deliver the email.

Apply migration `i5d6e7f8g9h0` before starting the updated API:

```sh
python -m alembic -c app/alembic.ini upgrade head
```

It adds `users.auth_version` with a default of zero for existing and new users. Access
tokens issued before this change remain usable until their expiry or the user's first
password reset. Tests use mocked email and disposable databases; no live emails are sent.
