"""Local administrator sign-in and session endpoints."""
import asyncio
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from src.api.deps import require_admin
from src.core.config import get_settings
from src.core.security import SESSION_EXPIRE_DAYS, create_access_token, get_password_hash, verify_password
from src.db.database import get_db
from src.db.models import AdminUser, EmailVerificationCode
from src.services.email_service import (
    EmailSenderError,
    configure_gmail_sender,
    get_gmail_sender_status,
    send_verification_code,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()
COOKIE_NAME = "attendsight_session"
SESSION_MAX_AGE_SECONDS = SESSION_EXPIRE_DAYS * 24 * 60 * 60
initial_admin_lock = asyncio.Lock()
email_code_lock = asyncio.Lock()
CODE_LIFETIME = timedelta(minutes=10)
CODE_RESEND_DELAY = timedelta(seconds=60)
MAX_CODE_ATTEMPTS = 5
GENERIC_RESET_MESSAGE = (
    "If a verified administrator email matches, a password-reset code has been sent."
)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class InitialAdminRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class EmailAddressRequest(BaseModel):
    email: EmailStr


class EmailSenderRequest(BaseModel):
    sender_email: EmailStr
    app_password: str = Field(min_length=16, max_length=64)

    @field_validator("app_password")
    @classmethod
    def normalize_app_password(cls, value: str) -> str:
        normalized = "".join(value.split())
        if len(normalized) != 16:
            raise ValueError("A Gmail App Password must contain 16 characters.")
        return normalized


class EmailCodeRequest(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")


class PasswordResetRequest(EmailCodeRequest):
    new_password: str = Field(min_length=10, max_length=128)


class AccountUpdateRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str | None = Field(default=None, min_length=10, max_length=128)


def _set_session_cookie(response: Response, user: AdminUser) -> None:
    token = create_access_token(
        {"sub": str(user.id), "role": "admin", "ver": user.session_version},
        timedelta(days=SESSION_EXPIRE_DAYS),
    )
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.app_env.lower() not in {"development", "local"},
        samesite="strict",
        path="/",
    )


async def _has_admin(db: AsyncSession) -> bool:
    return bool(await db.scalar(select(func.count(AdminUser.id))))


def _normalize_email(email: str | EmailStr) -> str:
    return str(email).strip().casefold()


def _hash_verification_code(email: str, purpose: str, code: str) -> str:
    payload = f"{purpose}:{email}:{code}".encode("utf-8")
    return hmac.new(
        settings.secret_key.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def _issue_email_code(
    email: str,
    purpose: Literal["password_reset", "change_email"],
    db: AsyncSession,
    *,
    user: AdminUser | None = None,
) -> None:
    sender = get_gmail_sender_status()
    if not sender["configured"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Set up Gmail email delivery before requesting a verification code.",
        )

    email = _normalize_email(email)
    if purpose == "password_reset":
        account = await db.scalar(
            select(AdminUser).where(
                AdminUser.email == email,
                AdminUser.email_verified.is_(True),
            )
        )
        if account is None:
            return
    elif user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")

    if purpose == "change_email":
        existing_account = await db.scalar(
            select(AdminUser.id).where(
                AdminUser.email == email,
                AdminUser.id != user.id,
            )
        )
        if existing_account is not None:
            raise HTTPException(status_code=409, detail="That email is already in use.")

    async with email_code_lock:
        existing_code = await db.scalar(
            select(EmailVerificationCode).where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.purpose == purpose,
            )
        )
        now = datetime.now(timezone.utc)
        if (
            existing_code is not None
            and now - _as_utc(existing_code.created_at) < CODE_RESEND_DELAY
        ):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Please wait 60 seconds before requesting another code.",
            )
        if existing_code is not None:
            await db.delete(existing_code)

        code = f"{secrets.randbelow(1_000_000):06d}"
        verification = EmailVerificationCode(
            email=email,
            purpose=purpose,
            code_hash=_hash_verification_code(email, purpose, code),
            attempts=0,
            created_at=now,
            expires_at=now + CODE_LIFETIME,
        )
        db.add(verification)
        await db.commit()
        try:
            await send_verification_code(email, code, purpose)
        except EmailSenderError as exc:
            await db.delete(verification)
            await db.commit()
            raise HTTPException(status_code=502, detail=str(exc)) from exc


async def _consume_email_code(
    email: str,
    purpose: Literal["password_reset", "change_email"],
    code: str,
    db: AsyncSession,
) -> None:
    email = _normalize_email(email)
    verification = await db.scalar(
        select(EmailVerificationCode).where(
            EmailVerificationCode.email == email,
            EmailVerificationCode.purpose == purpose,
        )
    )
    if verification is None:
        raise HTTPException(
            status_code=400, detail="The code is invalid or has expired."
        )

    now = datetime.now(timezone.utc)
    if (
        verification.attempts >= MAX_CODE_ATTEMPTS
        or _as_utc(verification.expires_at) <= now
    ):
        await db.delete(verification)
        await db.commit()
        raise HTTPException(
            status_code=400, detail="The code is invalid or has expired."
        )

    expected_hash = _hash_verification_code(email, purpose, code)
    if not hmac.compare_digest(verification.code_hash, expected_hash):
        verification.attempts += 1
        await db.commit()
        raise HTTPException(
            status_code=400, detail="The code is invalid or has expired."
        )
    await db.delete(verification)
    await db.flush()


@router.get("/setup-status")
async def setup_status(db: AsyncSession = Depends(get_db)):
    """Report whether this local database still needs its first administrator."""
    return {
        "setup_required": not await _has_admin(db),
        "email_configured": bool(get_gmail_sender_status()["configured"]),
    }


@router.get("/email-status")
async def email_status():
    """Report whether local Gmail delivery is configured without exposing its secret."""
    sender = get_gmail_sender_status()
    return {"configured": sender["configured"]}


@router.post("/configure-email")
async def configure_email(
    body: EmailSenderRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Validate and save the local Gmail sender before registration or recovery."""
    if await _has_admin(db):
        await require_admin(request, db)
    sender_email = _normalize_email(body.sender_email)
    try:
        await configure_gmail_sender(sender_email, body.app_password)
    except EmailSenderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"configured": True, "sender_email": sender_email}


@router.post("/send-password-reset-code")
async def send_password_reset_code(
    body: EmailAddressRequest,
    db: AsyncSession = Depends(get_db),
):
    await _issue_email_code(_normalize_email(body.email), "password_reset", db)
    return {"message": GENERIC_RESET_MESSAGE}


@router.post("/register-first-admin", status_code=status.HTTP_201_CREATED)
async def register_first_admin(
    body: InitialAdminRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Create the single initial admin; email verification can be enabled later."""
    async with initial_admin_lock:
        if await _has_admin(db):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An administrator already exists. Please sign in.",
            )

        email = _normalize_email(body.email)
        username = email
        user = AdminUser(
            username=username,
            email=email,
            email_verified=False,
            hashed_password=get_password_hash(body.password),
            is_active=True,
            is_superuser=True,
        )
        db.add(user)
        try:
            await db.commit()
            await db.refresh(user)
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Initial account setup has already been completed. Please sign in.",
            ) from exc

    _set_session_cookie(response, user)
    return {
        "authenticated": True,
        "username": user.username,
        "email": user.email,
        "email_verified": user.email_verified,
    }


@router.post("/reset-password")
async def reset_password(
    body: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
):
    email = _normalize_email(body.email)
    user = await db.scalar(
        select(AdminUser).where(
            AdminUser.email == email,
            AdminUser.email_verified.is_(True),
        )
    )
    if user is None:
        raise HTTPException(
            status_code=400, detail="The code is invalid or has expired."
        )
    await _consume_email_code(email, "password_reset", body.code, db)
    user.hashed_password = get_password_hash(body.new_password)
    user.session_version += 1
    await db.commit()
    return {"message": "Your password was reset. You can now sign in."}


@router.post("/login")
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    login_id = str(body.username).strip()
    user = await db.scalar(
        select(AdminUser).where(
            (AdminUser.email == login_id.casefold())
            | (AdminUser.username == login_id)
        )
    )
    if not user or not user.is_active or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email or password is incorrect")
    _set_session_cookie(response, user)
    return {
        "authenticated": True,
        "username": user.username,
        "email": user.email,
        "email_verified": user.email_verified,
        "expires_in": SESSION_MAX_AGE_SECONDS,
    }


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=settings.app_env.lower() not in {"development", "local"}, samesite="strict")
    return {"authenticated": False}


@router.get("/me")
async def who_am_i(user: AdminUser = Depends(require_admin)):
    return {
        "authenticated": True,
        "username": user.username,
        "email": user.email,
        "email_verified": user.email_verified,
        "is_superuser": user.is_superuser,
    }


@router.post("/account/email/send-code")
async def send_account_email_code(
    body: EmailAddressRequest,
    user: AdminUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await _issue_email_code(
        _normalize_email(body.email), "change_email", db, user=user
    )
    return {"message": "A verification code was sent to the new email address."}


@router.post("/account/email/verify-code")
async def verify_account_email(
    body: EmailCodeRequest,
    user: AdminUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    email = _normalize_email(body.email)
    await _consume_email_code(email, "change_email", body.code, db)
    user.email = email
    user.username = email
    user.email_verified = True
    await db.commit()
    return {"email": user.email, "email_verified": True}


@router.put("/account")
async def update_account(
    body: AccountUpdateRequest,
    response: Response,
    user: AdminUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update the signed-in administrator's password."""
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    if body.new_password:
        user.hashed_password = get_password_hash(body.new_password)
        user.session_version += 1
    await db.commit()
    _set_session_cookie(response, user)
    return {
        "authenticated": True,
        "username": user.username,
        "email": user.email,
        "email_verified": user.email_verified,
    }
