# Kompare authentication in Postman

For the Provider Reviews collection with a simple login, see
[Provider Reviews in Postman](PROVIDER-REVIEWS.md).

For Providers, including category filtering and admin operations, see
[Providers API in Postman](PROVIDERS.md).

Import both files in this directory into Postman:

- `Kompare-Auth.postman_collection.json`
- `Kompare-Local.postman_environment.json`

Select **Kompare Auth - Local example** as the active environment. Set `base_url` to your
running backend URL, with no trailing slash or `/auth` suffix. The default is
`http://localhost:8000`. Set `email` to an inbox you own and choose `password`.
All provided accounts, passwords, OTPs and response tokens are fictional examples.
No server signing key, SMTP credentials or provider secrets are needed in Postman.

Each request has descriptions, a success example, relevant failure examples and a
post-response check. View saved response examples from the request's Examples menu.
Send requests individually: verification codes must be retrieved from email and
entered manually. Importing this collection does not send any requests or emails.

## Endpoints

| Method | Endpoint | Authentication | JSON fields |
| --- | --- | --- | --- |
| POST | `/auth/register` | Public | `email`, `password`; optional `first_name`, `last_name`, `phone_number` |
| POST | `/auth/verify-email` | Public | `email`, `otp` |
| POST | `/auth/resend-verification-otp` | Public | `email` |
| POST | `/auth/login` | Public | `email`, `password` |
| GET | `/auth/me` | Access token | No body |
| POST | `/auth/refresh` | Refresh token in body | `refresh_token` |
| POST | `/auth/logout` | Refresh token in body | `refresh_token` |
| POST | `/auth/forgot-password` | Public | `email` |
| POST | `/auth/reset-password` | Public | `email`, `otp`, `new_password` |
| POST | `/auth/admins` | Superadmin access token | `email`, `password`; optional `first_name`, `last_name`, `admin_type` |

## Onboarding and sessions

1. Send **Register user**. It returns HTTP 201 and an unverified user profile. SMTP must
   be configured on the backend for the verification email to arrive.
2. Copy the actual emailed code into `verification_otp`, keeping it a string so leading
   zeros survive. Send **Verify email**. Verification does not log the user in.
3. Send **Login**. Its script saves `access_token` and `refresh_token` in the selected
   environment. **Current user** uses the saved access token as a bearer token.
4. Use **Refresh session** when needed. Refresh rotates both tokens and the script
   replaces their saved values. Each refresh token works once.
5. **Logout** revokes the supplied refresh token and clears local user token variables.
   It does not immediately revoke an already-issued access token on the server.

Passwords must contain 8–128 characters. Defaults are six-digit verification codes,
ten-minute code expiry, five failed attempts per code, fifteen-minute access tokens
and seven-day refresh tokens. Server configuration can change these defaults.

## Password recovery

1. Send **Forgot password** with `email`. The HTTP 200 response is intentionally the
   same for unknown, inactive and eligible accounts. It does not guarantee email delivery.
2. Put the actual reset-email code into `password_reset_otp`; choose `new_password`.
   Email verification codes cannot be substituted for password reset codes.
3. On the frontend, compare the new password and confirmation before submitting.
   Send **Reset password** with `email`, `otp`, `new_password`. There is no separate
   reset-code verification endpoint and no `confirm_password` API field.
4. Successful reset consumes the code and invalidates all existing access/refresh
   sessions. Its Postman script clears user tokens, clears `password_reset_otp` and
   updates the `password` environment variable to `new_password`. Send **Login** again.

Request another code using the relevant resend/forgot endpoint after the default
sixty-second cooldown. A newly issued code replaces earlier codes of the same purpose.

## Admin creation

Set `superadmin_email` and `superadmin_password` to an existing provisioned superadmin
account, then send **Login as superadmin**. It uses `/auth/login` and saves separate
superadmin token variables, leaving the ordinary user's tokens unchanged.

Set `admin_email`, `admin_password` and the desired `admin_type`, then send **Create admin**.
Supported types: `super_admin`, `support_admin`, `content_moderator`, `ingestion_manager`,
`finance_admin`. Only a current superadmin may create admins. There is no default
superadmin password. Admin creation returns an active, verified account without the
normal registration verification email.

## Responses and errors

The response envelope is always `responseCode`, `message`, `data`. Examples are illustrative
and use the current response models; example tokens cannot authenticate requests.

- `400`: duplicate registration or invalid/expired/used OTP.
- `401`: missing/invalid access token, invalid login, unverified account or unusable refresh token.
- `403`: the current user lacks superadmin permission for admin creation.
- `422`: payload validation failed; field errors are in `data.details`.
- `429`: authentication rate limit or resend cooldown; honor the `Retry-After` header.

For local setup, [password recovery configuration](../password-reset.md) documents SMTP
and the required database migration. The collection follows the official
[Postman Collection v2.1 format](https://schema.postman.com/collection/json/v2.1.0/draft-07/collection.json).
