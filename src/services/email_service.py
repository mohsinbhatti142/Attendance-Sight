"""Gmail SMTP delivery for administrator verification and recovery codes."""
import asyncio
import base64
import hashlib
import json
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from src.core.config import get_settings

settings = get_settings()


class EmailSenderError(RuntimeError):
    """Raised when the local Gmail sender is missing or cannot be used."""


def _cipher() -> Fernet:
    if len(settings.secret_key) < 32 or settings.secret_key in {
        "your-secret-key-change-this",
        "replace-with-a-long-random-secret",
    }:
        raise EmailSenderError(
            "Set a private SECRET_KEY before configuring Gmail email delivery."
        )
    key = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _credentials_path() -> Path:
    return Path(settings.email_credentials_file)


def _load_credentials() -> tuple[str, str] | None:
    path = _credentials_path()
    if not path.exists():
        return None
    try:
        data = json.loads(_cipher().decrypt(path.read_bytes()))
        return data["sender_email"], data["app_password"]
    except (InvalidToken, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise EmailSenderError(
            "The saved Gmail sender settings cannot be decrypted. Configure them again."
        ) from exc


def _validate_gmail_login(sender_email: str, app_password: str) -> None:
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
        server.ehlo()
        server.login(sender_email, app_password)


def _save_credentials(sender_email: str, app_password: str) -> None:
    path = _credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    encrypted = _cipher().encrypt(
        json.dumps(
            {"sender_email": sender_email, "app_password": app_password}
        ).encode("utf-8")
    )
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_bytes(encrypted)
    temporary_path.replace(path)


async def configure_gmail_sender(sender_email: str, app_password: str) -> None:
    """Verify Gmail SMTP credentials before storing them encrypted on this device."""
    normalized_password = "".join(app_password.split())
    try:
        await asyncio.to_thread(
            _validate_gmail_login, sender_email, normalized_password
        )
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailSenderError(
            "Gmail could not verify these credentials. Check the sender address "
            "and its 16-character App Password."
        ) from exc
    await asyncio.to_thread(
        _save_credentials, sender_email, normalized_password
    )


def get_gmail_sender_status() -> dict[str, str | bool | None]:
    """Return whether a sender is configured without exposing its App Password."""
    credentials = _load_credentials()
    if credentials is None:
        return {"configured": False, "sender_email": None}
    return {"configured": True, "sender_email": credentials[0]}


def _send_email_code(sender_email: str, app_password: str, recipient: str, code: str, purpose: str) -> None:
    message = EmailMessage()
    message["Subject"] = "Your Attendance-Sight verification code"
    message["From"] = sender_email
    message["To"] = recipient
    action = "create your administrator account" if purpose == "register" else (
        "change your recovery email" if purpose == "change_email" else "reset your password"
    )
    message.set_content(
        f"Use this code to {action}: {code}\n\n"
        "This code expires in 10 minutes. If you did not request it, you can ignore this email."
    )
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
        server.ehlo()
        server.login(sender_email, app_password)
        server.send_message(message)


async def send_verification_code(recipient: str, code: str, purpose: str) -> None:
    """Send an account verification code through the configured Gmail sender."""
    credentials = _load_credentials()
    if credentials is None:
        raise EmailSenderError(
            "Set up Gmail email delivery before requesting a verification code."
        )
    sender_email, app_password = credentials
    try:
        await asyncio.to_thread(
            _send_email_code,
            sender_email,
            app_password,
            recipient,
            code,
            purpose,
        )
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailSenderError(
            "Gmail could not send the verification email. Check the sender's "
            "App Password and internet connection."
        ) from exc
