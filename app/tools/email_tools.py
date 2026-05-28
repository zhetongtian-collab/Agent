import html
import imaplib
import smtplib
from dataclasses import dataclass
from email import policy
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parseaddr
from pathlib import Path
import mimetypes
import re

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


class EmailReceiveError(RuntimeError):
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


def fetch_unread_email_messages(limit: int = 5, body_max_chars: int = 4000) -> dict[str, object]:
    username = (settings.email_imap_username or settings.email_smtp_username).strip()
    password = (settings.email_imap_password or settings.email_smtp_password).strip()

    if not username or not password:
        raise EmailConfigurationError(
            "email IMAP settings are incomplete; configure EMAIL_IMAP_USERNAME and EMAIL_IMAP_PASSWORD"
        )

    try:
        with imaplib.IMAP4_SSL(settings.email_imap_host, settings.email_imap_port) as imap:
            imap.login(username, password)
            _check_imap_status(imap.select("INBOX"), "select inbox")
            _, email_ids = _check_imap_status(imap.search(None, "UNSEEN"), "search unread emails")
            selected_ids = email_ids[0].split()[-limit:] if email_ids and email_ids[0] else []
            emails = []
            fetch_mode = "(RFC822)" if settings.email_mark_read_on_fetch else "(BODY.PEEK[])"
            for email_id in selected_ids:
                _, fetch_data = _check_imap_status(imap.fetch(email_id, fetch_mode), "fetch unread email")
                raw_message = _raw_message_from_fetch(fetch_data)
                if raw_message:
                    emails.append(_parse_email(raw_message, body_max_chars=body_max_chars))
            imap.logout()
    except imaplib.IMAP4.error as exc:
        raise EmailReceiveError(str(exc)) from exc
    except OSError as exc:
        raise EmailReceiveError(str(exc)) from exc

    return {"count": len(emails), "emails": emails}


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


def _check_imap_status(result: tuple[str, list[bytes]], action: str) -> tuple[str, list[bytes]]:
    status, data = result
    if status != "OK":
        raise EmailReceiveError(f"failed to {action}: {status}")
    return status, data


def _raw_message_from_fetch(fetch_data: list[object]) -> bytes | None:
    for item in fetch_data:
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
            return item[1]
    return None


def _parse_email(raw_message: bytes, body_max_chars: int) -> dict[str, object]:
    email_message = BytesParser(policy=policy.default).parsebytes(raw_message)
    body = _email_body(email_message)
    return {
        "from": _decode_header_value(email_message.get("From", "")),
        "to": _decode_header_value(email_message.get("To", "")),
        "subject": _decode_header_value(email_message.get("Subject", "")),
        "date": _decode_header_value(email_message.get("Date", "")),
        "body": body[:body_max_chars],
        "body_truncated": len(body) > body_max_chars,
        "attachments": _email_attachments(email_message, body_max_chars=body_max_chars),
    }


def _email_body(message: EmailMessage) -> str:
    plain_part = message.get_body(preferencelist=("plain",))
    if plain_part:
        return _part_text(plain_part).strip()
    html_part = message.get_body(preferencelist=("html",))
    if html_part:
        return _html_to_text(_part_text(html_part)).strip()
    if not message.is_multipart():
        return _part_text(message).strip()
    return ""


def _email_attachments(message: EmailMessage, body_max_chars: int) -> list[dict[str, object]]:
    attachments = []
    for part in message.iter_attachments():
        filename = _decode_header_value(part.get_filename() or "attachment")
        content_type = part.get_content_type()
        attachment: dict[str, object] = {"filename": filename, "content_type": content_type}
        if content_type.startswith("text/"):
            text = _part_text(part)
            attachment["content_preview"] = text[:body_max_chars]
            attachment["content_truncated"] = len(text) > body_max_chars
        attachments.append(attachment)
    return attachments


def _part_text(part: EmailMessage) -> str:
    try:
        content = part.get_content()
    except (LookupError, UnicodeDecodeError):
        payload = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    if isinstance(content, str):
        return content
    return str(content)


def _decode_header_value(value: str) -> str:
    if not value:
        return ""
    return str(make_header(decode_header(value)))


def _html_to_text(value: str) -> str:
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", value)
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</p\s*>", "\n", value)
    value = re.sub(r"<[^>]+>", "", value)
    return html.unescape(value)
