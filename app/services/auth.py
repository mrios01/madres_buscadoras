import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from bson import ObjectId
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from pymongo import ASCENDING

from app.core.config import get_settings


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _hash_phone_number(phone_number: str) -> str:
    settings = get_settings()
    raw = f"{settings.password_salt}:{phone_number}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _build_display_name(claims: dict) -> str:
    given = str(claims.get("given_name") or "").strip()
    family = str(claims.get("family_name") or "").strip()

    if given and family:
        return f"{given} {family[0]}."
    if given:
        return given

    email = _normalize_email(str(claims.get("email") or ""))
    base = email.split("@", 1)[0] if email else "Busqueda"
    return base[:40]


async def ensure_auth_indexes(db) -> None:
    await db.users.create_index(
        [("google_oauth.sub", ASCENDING)],
        unique=True,
        sparse=True,
        name="uniq_google_sub",
    )
    await db.users.create_index(
        [("google_oauth.email", ASCENDING)],
        unique=True,
        sparse=True,
        name="uniq_google_email",
    )
    await db.users.create_index(
        [("collective_id", ASCENDING)],
        name="idx_users_collective",
    )
    await db.users.create_index(
        [("verification_status", ASCENDING)],
        name="idx_users_verification_status",
    )

    await db.sessions.create_index(
        [("token_hash", ASCENDING)],
        unique=True,
        name="uniq_token_hash",
    )
    await db.sessions.create_index(
        [("user_id", ASCENDING)],
        name="idx_sessions_user_id",
    )
    await db.sessions.create_index(
        [("expires_at", ASCENDING)],
        expireAfterSeconds=0,
        name="ttl_session",
    )


def verify_google_id_token(token: str) -> dict:
    settings = get_settings()
    if not settings.google_client_id:
        raise ValueError("google_client_id_not_configured")

    payload = id_token.verify_oauth2_token(
        token,
        Request(),
        settings.google_client_id,
    )
    if payload.get("iss") not in {
        "accounts.google.com",
        "https://accounts.google.com",
    }:
        raise ValueError("invalid_google_issuer")

    if not payload.get("email"):
        raise ValueError("google_email_missing")

    if not payload.get("sub"):
        raise ValueError("google_sub_missing")

    return payload


async def get_or_create_user_from_google(db, claims: dict) -> dict:
    email = _normalize_email(str(claims["email"]))
    sub = str(claims["sub"])

    existing = await db.users.find_one({"google_oauth.sub": sub})
    if not existing:
        existing = await db.users.find_one({"google_oauth.email": email})

    if existing:
        update = {
            "display_name": _build_display_name(claims),
            "google_oauth": {
                "sub": sub,
                "email": email,
                "email_verified": bool(claims.get("email_verified", False)),
                "picture": claims.get("picture"),
            },
            "last_active": _utcnow(),
        }
        await db.users.update_one({"_id": existing["_id"]}, {"$set": update})
        existing.update(update)
        return existing

    now = _utcnow()
    doc = {
        "display_name": _build_display_name(claims),
        "collective_id": None,
        "role": "SEARCHER",
        "phone_number_hash": _hash_phone_number("pending"),
        "verification_status": "PENDING",
        "security": {
            "duress_pin_hash": None,
            "last_known_device_id": None,
            "force_logout": False,
        },
        "google_oauth": {
            "sub": sub,
            "email": email,
            "email_verified": bool(claims.get("email_verified", False)),
            "picture": claims.get("picture"),
        },
        "joined_at": now,
        "last_active": now,
    }

    result = await db.users.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def create_session(
    db,
    user_id: ObjectId,
    user_agent: str | None,
    ip: str | None,
) -> tuple[str, datetime]:
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
    session = await db.sessions.find_one(
        {"token_hash": _hash_session_token(token)}
    )
    if not session:
        return None

    if session.get("expires_at") and session["expires_at"] < _utcnow():
        await db.sessions.delete_one({"_id": session["_id"]})
        return None

    user = await db.users.find_one({"_id": session["user_id"]})
    return user
