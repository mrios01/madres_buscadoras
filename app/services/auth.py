import hashlib
import hmac
import secrets
import re
from datetime import UTC, datetime, timedelta

from bson import ObjectId
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from pymongo import ASCENDING

from app.core.config import get_settings
from app.models.user import UserCreate


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _derive_hash(password: str, salt: str, pepper: str) -> str:
    raw = f"{password}:{salt}:{pepper}".encode("utf-8")
    digest = hashlib.pbkdf2_hmac("sha256", raw, salt.encode("utf-8"), 210_000)
    return digest.hex()


def _verify_password(password: str, salt: str, pepper: str, expected_hash: str) -> bool:
    candidate = _derive_hash(password, salt, pepper)
    return hmac.compare_digest(candidate, expected_hash)


def _hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def ensure_auth_indexes(db) -> None:
    await db.login.create_index([("email", ASCENDING)], unique=True, name="uniq_email")
    await db.login.create_index([("screen_name", ASCENDING)], unique=True, name="uniq_screen_name")
    await db.sessions.create_index([("token_hash", ASCENDING)], unique=True, name="uniq_token_hash")
    await db.sessions.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0, name="ttl_session")


async def create_user(db, payload: UserCreate) -> dict:
    settings = get_settings()
    now = _utcnow()
    email = _normalize_email(payload.email)

    salt = secrets.token_hex(16)
    pepper = settings.password_salt
    password_hash = _derive_hash(payload.password, salt, pepper)

    doc = {
        "email": email,
        "screen_name": payload.screen_name.strip(),
        "first_name": payload.first_name.strip(),
        "last_name": payload.last_name.strip(),
        "birth_date": payload.birth_date,
        "account": True,
        "opt_in": False,
        "password_hash": password_hash,
        "salt": salt,
        "pepper": pepper,
        "conf_code": None,
        "verifier": None,
        "country": None,
        "zipcode": None,
        "phone_number": None,
        "phone_verify_code": None,
        "dateCreated": now,
    }

    result = await db.login.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def authenticate_user(db, email: str, password: str) -> dict | None:
    normalized = _normalize_email(email)
    user = await db.login.find_one({"email": normalized})
    if not user:
        return None

    if not _verify_password(
        password=password,
        salt=user.get("salt", ""),
        pepper=user.get("pepper", ""),
        expected_hash=user.get("password_hash", ""),
    ):
        return None

    return user


def verify_google_id_token(token: str) -> dict:
    settings = get_settings()
    if not settings.google_client_id:
        raise ValueError("google_client_id_not_configured")

    payload = id_token.verify_oauth2_token(token, Request(), settings.google_client_id)
    if payload.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
        raise ValueError("invalid_google_issuer")

    if not payload.get("email"):
        raise ValueError("google_email_missing")

    return payload


def _slug_screen_name(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]", "", value).strip("._-")
    return slug[:30] or f"user{secrets.randbelow(999999):06d}"


async def _generate_unique_screen_name(db, base: str) -> str:
    candidate = _slug_screen_name(base)
    if not await db.login.find_one({"screen_name": candidate}):
        return candidate

    for _ in range(12):
        maybe = f"{candidate}{secrets.randbelow(9999):04d}"[:40]
        if not await db.login.find_one({"screen_name": maybe}):
            return maybe

    return f"user{secrets.token_hex(4)}"


async def get_or_create_user_from_google(db, claims: dict) -> dict:
    email = _normalize_email(claims["email"])
    existing = await db.login.find_one({"email": email})
    if existing:
        update = {
            "first_name": claims.get("given_name") or existing.get("first_name") or "",
            "last_name": claims.get("family_name") or existing.get("last_name") or "",
            "google_sub": claims.get("sub"),
            "google_picture": claims.get("picture"),
            "google_email_verified": bool(claims.get("email_verified", False)),
            "last_login_at": _utcnow(),
        }
        await db.login.update_one({"_id": existing["_id"]}, {"$set": update})
        existing.update(update)
        return existing

    base_name = email.split("@", 1)[0]
    screen_name = await _generate_unique_screen_name(db, base_name)

    now = _utcnow()
    doc = {
        "email": email,
        "screen_name": screen_name,
        "first_name": claims.get("given_name") or "",
        "last_name": claims.get("family_name") or "",
        "birth_date": None,
        "account": True,
        "opt_in": False,
        "password_hash": None,
        "salt": None,
        "pepper": None,
        "conf_code": None,
        "verifier": None,
        "country": None,
        "zipcode": None,
        "phone_number": None,
        "phone_verify_code": None,
        "google_sub": claims.get("sub"),
        "google_picture": claims.get("picture"),
        "google_email_verified": bool(claims.get("email_verified", False)),
        "dateCreated": now,
        "last_login_at": now,
    }

    result = await db.login.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def create_session(db, user_id: ObjectId, user_agent: str | None, ip: str | None) -> tuple[str, datetime]:
    settings = get_settings()
    token = secrets.token_urlsafe(48)
    expires_at = _utcnow() + timedelta(days=settings.auth_session_ttl_days)

    await db.sessions.insert_one(
        {
            "user_id": user_id,
            "token_hash": _hash_session_token(token),
            "created_at": _utcnow(),
            "expires_at": expires_at,
            "user_agent": user_agent,
            "ip": ip,
        }
    )

    return token, expires_at


async def revoke_session(db, token: str) -> None:
    await db.sessions.delete_one({"token_hash": _hash_session_token(token)})


async def get_user_by_session_token(db, token: str) -> dict | None:
    session = await db.sessions.find_one({"token_hash": _hash_session_token(token)})
    if not session:
        return None

    if session.get("expires_at") and session["expires_at"] < _utcnow():
        await db.sessions.delete_one({"_id": session["_id"]})
        return None

    user = await db.login.find_one({"_id": session["user_id"]})
    return user
