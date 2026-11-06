from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.core import config
from app.core.logger import logger


class EmailService:
    def __init__(
        self,
        *,
        smtp_host: str | None = config.SMTP_HOST,
        smtp_port: int = config.SMTP_PORT,
        smtp_username: str | None = config.SMTP_USERNAME,
        smtp_password: str | None = config.SMTP_PASSWORD,
        smtp_use_tls: bool = config.SMTP_USE_TLS,
        smtp_use_ssl: bool = config.SMTP_USE_SSL,
        email_from: str | None = config.EMAIL_FROM,
        email_from_name: str = config.EMAIL_FROM_NAME,
    ) -> None:
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password
        self.smtp_use_tls = smtp_use_tls
        self.smtp_use_ssl = smtp_use_ssl
        self.email_from = email_from
        self.email_from_name = email_from_name

    def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        from_email: str | None = None,
        from_name: str | None = None,
    ) -> bool:
        if not self._is_configured(to_email=to_email, subject=subject):
            return False

        sender_email = from_email or self.email_from
        sender_name = from_name or self.email_from_name

        try:
            message = EmailMessage()
            message["From"] = formataddr((sender_name, sender_email))
            message["To"] = to_email
            message["Subject"] = subject
            message.set_content(body)
            if html_body is not None:
                message.add_alternative(html_body, subtype="html")

            smtp_class = smtplib.SMTP_SSL if self.smtp_use_ssl else smtplib.SMTP
            with smtp_class(self.smtp_host, self.smtp_port, timeout=30) as smtp:
                if self.smtp_use_tls and not self.smtp_use_ssl:
                    smtp.starttls()
                if self.smtp_username and self.smtp_password:
                    smtp.login(self.smtp_username, self.smtp_password)
                smtp.send_message(message)
            return True
        except Exception as exc:
            logger.exception(
                "Email delivery failed to=%s subject=%s smtp_host=%s smtp_port=%s error=%s",
                to_email,
                subject,
                self.smtp_host,
                self.smtp_port,
                exc,
            )
            return False

    def _is_configured(self, *, to_email: str, subject: str) -> bool:
        missing = []
        if not self.smtp_host:
            missing.append("SMTP_HOST")
        if not self.email_from:
            missing.append("EMAIL_FROM")
        if missing:
            logger.error(
                "Email delivery skipped to=%s subject=%s missing_config=%s",
                to_email,
                subject,
                ",".join(missing),
            )
            return False
        return True
