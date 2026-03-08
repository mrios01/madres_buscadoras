from datetime import UTC

import pymongo.errors
import tornado.escape
import tornado.web
from pydantic import ValidationError

from app.core.config import get_settings
from app.models.user import UserCreate
from app.services.auth import (
    create_session,
    create_user,
    get_or_create_user_from_google,
    revoke_session,
    verify_google_id_token,
)


def _serialize_user(doc: dict) -> dict:
    created = doc.get("dateCreated")
    if created and created.tzinfo is None:
        created = created.replace(tzinfo=UTC)

    return {
        "id": str(doc["_id"]),
        "email": doc["email"],
        "screen_name": doc["screen_name"],
        "first_name": doc["first_name"],
        "last_name": doc["last_name"],
        "account": bool(doc.get("account", True)),
        "opt_in": bool(doc.get("opt_in", False)),
        "created_at": created.isoformat() if created else None,
    }


class RegisterHandler(tornado.web.RequestHandler):
    async def post(self):
        db = self.application.settings["db"]

        try:
            payload = UserCreate.model_validate_json(self.request.body)
        except ValidationError as exc:
            self.set_status(400)
            self.finish({"error": "invalid_payload", "details": exc.errors()})
            return

        try:
            user = await create_user(db, payload)
        except pymongo.errors.DuplicateKeyError:
            self.set_status(409)
            self.finish({"error": "email_or_screen_name_already_exists"})
            return

        token, expires_at = await create_session(
            db,
            user_id=user["_id"],
            user_agent=self.request.headers.get("User-Agent"),
            ip=self.request.remote_ip,
        )

        settings = get_settings()
        self.set_secure_cookie(
            settings.auth_cookie_name,
            token,
            httponly=True,
            secure=settings.auth_cookie_secure,
            samesite=settings.auth_cookie_samesite,
            expires=expires_at,
        )
        self.set_status(201)
        self.finish({"user": _serialize_user(user)})


class LoginHandler(tornado.web.RequestHandler):
    async def post(self):
        db = self.application.settings["db"]
        try:
            payload = tornado.escape.json_decode(self.request.body)
        except Exception:
            self.set_status(400)
            self.finish({"error": "invalid_json"})
            return

        google_id_token = payload.get("id_token", "")
        if not google_id_token:
            self.set_status(400)
            self.finish({"error": "id_token_required"})
            return

        try:
            claims = verify_google_id_token(google_id_token)
        except ValueError as exc:
            self.set_status(401)
            self.finish({"error": str(exc)})
            return
        except Exception:
            self.set_status(401)
            self.finish({"error": "invalid_google_token"})
            return

        user = await get_or_create_user_from_google(db, claims)

        token, expires_at = await create_session(
            db,
            user_id=user["_id"],
            user_agent=self.request.headers.get("User-Agent"),
            ip=self.request.remote_ip,
        )

        settings = get_settings()
        self.set_secure_cookie(
            settings.auth_cookie_name,
            token,
            httponly=True,
            secure=settings.auth_cookie_secure,
            samesite=settings.auth_cookie_samesite,
            expires=expires_at,
        )

        self.finish({"user": _serialize_user(user)})


class LogoutHandler(tornado.web.RequestHandler):
    async def post(self):
        db = self.application.settings["db"]
        settings = get_settings()
        token = self.get_secure_cookie(settings.auth_cookie_name)

        if token:
            await revoke_session(db, token.decode("utf-8"))

        self.clear_cookie(settings.auth_cookie_name)
        self.set_status(204)
        self.finish()
