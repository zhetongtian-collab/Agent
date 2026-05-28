import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
import mimetypes

from app.core.config import settings


@dataclass(frozen=True)
class EmailAttachment:
    path: Path
    filename: str
    content_type: str | None = None


class EmailConfigurationError(RuntimeError):
    pass


class EmailSendError(RuntimeError):
    pass


def send_email_message(
    to: str,
    subject: str,
    content: str,
    attachments: list[EmailAttachment] | None = None,
) -> dict[str, object]:
    recipient = _clean_email(to)
    sender = _clean_email(settings.email_from or settings.email_smtp_username)
    username = settings.email_smtp_username.strip()
    password = settings.email_smtp_password.strip()

    if not sender or not username or not password:
        raise EmailConfigurationError(
            "email SMTP settings are incomplete; configure EMAIL_SMTP_USERNAME, "
            "EMAIL_SMTP_PASSWORD, and EMAIL_FROM"
        )
    if not recipient:
        raise EmailSendError("recipient email address is invalid")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject.strip() or "LongChain Office Agent"
    message.set_content(content)
    attached_files = _add_attachments(message, attachments or [])

    try:
        if settings.email_use_ssl:
            with smtplib.SMTP_SSL(settings.email_smtp_host, settings.email_smtp_port, timeout=30) as smtp:
                smtp.login(username, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings.email_smtp_host, settings.email_smtp_port, timeout=30) as smtp:
                smtp.starttls()
                smtp.login(username, password)
                smtp.send_message(message)
    except smtplib.SMTPException as exc:
        raise EmailSendError(str(exc)) from exc
    except OSError as exc:
        raise EmailSendError(str(exc)) from exc

    return {"to": recipient, "subject": message["Subject"], "attachments": attached_files}


def _clean_email(value: str) -> str:
    _, address = parseaddr(value.strip())
    if "@" not in address or address.startswith("@") or address.endswith("@"):
        return ""
    return address


def _add_attachments(message: EmailMessage, attachments: list[EmailAttachment]) -> list[dict[str, str]]:
    attached_files = []
    for attachment in attachments:
        path = attachment.path
        if not path.is_file():
            raise EmailSendError(f"attachment file not found: {path}")

        content_type = _resolve_content_type(attachment)
        maintype, subtype = content_type.split("/", 1)
        filename = attachment.filename or path.name

        message.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=filename)
        attached_files.append({"filename": filename, "content_type": content_type})
    return attached_files


def _resolve_content_type(attachment: EmailAttachment) -> str:
    content_type = attachment.content_type or mimetypes.guess_type(attachment.filename)[0]
    if content_type:
        content_type = content_type.split(";", 1)[0].strip().lower()
    if not content_type or "/" not in content_type:
        return "application/octet-stream"
    return content_type
