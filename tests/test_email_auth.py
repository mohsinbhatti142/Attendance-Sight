import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

_test_data = Path(tempfile.mkdtemp(prefix="attendance-sight-auth-test-"))
atexit.register(shutil.rmtree, _test_data, ignore_errors=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(
    {
        "APP_ENV": "development",
        "LOCAL_DEMO_MODE": "true",
        "DATABASE_URL": f"sqlite+aiosqlite:///{(_test_data / 'attendance.db').as_posix()}",
        "SECRET_KEY": "test-secret-key-for-email-auth-tests-only",
        "EMAIL_CREDENTIALS_FILE": str(_test_data / "email_sender.enc"),
        "FACE_IMAGES_DIR": str(_test_data / "face_images"),
        "MODEL_WEIGHTS_DIR": str(_test_data / "models"),
        "FAISS_INDEX_DIR": str(_test_data / "faiss"),
        "LOG_FILE": str(_test_data / "app.log"),
    }
)

from src.api.routes import auth as auth_routes
from src.main import app


def test_gmail_sender_password_is_encrypted(monkeypatch):
    from src.services import email_service

    credentials_file = _test_data / "sender.enc"
    monkeypatch.setattr(email_service.settings, "email_credentials_file", str(credentials_file))
    monkeypatch.setattr(email_service, "_validate_gmail_login", lambda sender, password: None)

    import asyncio

    asyncio.run(
        email_service.configure_gmail_sender(
            "sender@gmail.com", "abcd efgh ijkl mnop"
        )
    )

    encrypted_contents = credentials_file.read_bytes()
    assert b"sender@gmail.com" not in encrypted_contents
    assert b"abcdefghijklmnop" not in encrypted_contents
    assert email_service.get_gmail_sender_status() == {
        "configured": True,
        "sender_email": "sender@gmail.com",
    }


def test_email_registration_reset_and_recovery_address(monkeypatch):
    sent_codes: list[tuple[str, str, str]] = []
    sender_configured = False

    def sender_status():
        return {"configured": sender_configured, "sender_email": "sender@gmail.com"}

    async def configure_sender(sender_email: str, app_password: str) -> None:
        nonlocal sender_configured
        assert sender_email == "sender@gmail.com"
        assert app_password == "abcdefghijklmnop"
        sender_configured = True

    async def send_code(email: str, code: str, purpose: str) -> None:
        sent_codes.append((email, code, purpose))

    monkeypatch.setattr(auth_routes, "get_gmail_sender_status", sender_status)
    monkeypatch.setattr(auth_routes, "configure_gmail_sender", configure_sender)
    monkeypatch.setattr(auth_routes, "send_verification_code", send_code)

    with TestClient(app) as client:
        setup = client.get("/api/v1/auth/setup-status").json()
        assert setup == {"setup_required": True, "email_configured": False}

        registered = client.post(
            "/api/v1/auth/register-first-admin",
            json={
                "email": "admin@gmail.com",
                "password": "CorrectHorseBattery1!",
            },
        )
        assert registered.status_code == 201
        assert registered.json()["email_verified"] is False
        assert registered.json()["username"] == "admin@gmail.com"
        assert sent_codes == []
        assert client.get("/api/v1/auth/me").json()["email"] == "admin@gmail.com"
        assert client.get("/api/v1/auth/setup-status").json()["setup_required"] is False
        assert client.post(
            "/api/v1/auth/send-password-reset-code",
            json={"email": "admin@gmail.com"},
        ).status_code == 503
        assert client.post("/api/v1/auth/register-first-admin", json={
            "email": "second@gmail.com",
            "password": "CorrectHorseBattery2!",
        }).status_code == 409

        configured = client.post(
            "/api/v1/auth/configure-email",
            json={
                "sender_email": "sender@gmail.com",
                "app_password": "abcd efgh ijkl mnop",
            },
        )
        assert configured.status_code == 200

        assert client.post(
            "/api/v1/auth/account/email/send-code",
            json={"email": "admin@gmail.com"},
        ).status_code == 200
        _, verification_code, purpose = sent_codes[-1]
        assert purpose == "change_email"
        verified_email = client.post(
            "/api/v1/auth/account/email/verify-code",
            json={"email": "admin@gmail.com", "code": verification_code},
        )
        assert verified_email.status_code == 200
        assert verified_email.json()["email_verified"] is True

        assert client.post(
            "/api/v1/auth/send-password-reset-code",
            json={"email": "admin@gmail.com"},
        ).status_code == 200
        _, reset_code, purpose = sent_codes[-1]
        assert purpose == "password_reset"
        reset = client.post(
            "/api/v1/auth/reset-password",
            json={
                "email": "admin@gmail.com",
                "code": reset_code,
                "new_password": "NewCorrectHorseBattery2!",
            },
        )
        assert reset.status_code == 200
        assert client.get("/api/v1/auth/me").status_code == 401
        assert client.post(
            "/api/v1/auth/login",
            json={"username": "admin@gmail.com", "password": "CorrectHorseBattery1!"},
        ).status_code == 401
        assert client.post(
            "/api/v1/auth/login",
            json={"username": "admin@gmail.com", "password": "NewCorrectHorseBattery2!"},
        ).status_code == 200

        assert client.post(
            "/api/v1/auth/account/email/send-code",
            json={"email": "new-admin@gmail.com"},
        ).status_code == 200
        _, change_code, purpose = sent_codes[-1]
        assert purpose == "change_email"
        updated_email = client.post(
            "/api/v1/auth/account/email/verify-code",
            json={"email": "new-admin@gmail.com", "code": change_code},
        )
        assert updated_email.status_code == 200
        assert updated_email.json() == {
            "email": "new-admin@gmail.com",
            "email_verified": True,
        }
        assert client.get("/api/v1/auth/me").json()["username"] == "new-admin@gmail.com"
        assert client.post(
            "/api/v1/auth/logout",
        ).status_code == 200
        assert client.post(
            "/api/v1/auth/login",
            json={"username": "new-admin@gmail.com", "password": "NewCorrectHorseBattery2!"},
        ).status_code == 200
        account_settings = client.put(
            "/api/v1/auth/account",
            json={
                "current_password": "NewCorrectHorseBattery2!",
                "new_password": None,
            },
        )
        assert account_settings.status_code == 200
