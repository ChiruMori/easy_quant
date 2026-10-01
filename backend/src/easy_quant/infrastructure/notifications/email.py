from __future__ import annotations

import smtplib
from email.message import EmailMessage

from easy_quant.application.ports.notifications import (
    PermanentDeliveryError,
    TemporaryDeliveryError,
)
from easy_quant.domain.notifications.entities import NotificationSubscription


class EmailChannel:
    def __init__(
        self,
        host: str,
        port: int,
        sender: str,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.host, self.port, self.sender, self.username, self.password = (
            host,
            port,
            sender,
            username,
            password,
        )

    def send(
        self, subscription: NotificationSubscription, title: str, body: str, idempotency_key: str
    ) -> None:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = subscription.destination
        message["Subject"] = title
        message["X-Idempotency-Key"] = idempotency_key
        message.set_content(body)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
                if self.username and self.password:
                    smtp.login(self.username, self.password)
                smtp.send_message(message)
        except smtplib.SMTPRecipientsRefused as error:
            raise PermanentDeliveryError("收件地址被拒绝") from error
        except (OSError, smtplib.SMTPException) as error:
            raise TemporaryDeliveryError("邮件服务暂时不可用") from error
