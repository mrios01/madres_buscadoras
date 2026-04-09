import tornado.escape
import tornado.web

from app.core.config import get_settings
from app.services.auth import (
    create_session,
    get_or_create_user_from_google,
    revoke_session,
    verify_google_id_token,
)


def _serialize_user(doc: dict) -> dict:
    collective = doc.get("collective_id")
    security = doc.get("security") or {}
    oauth = doc.get("google_oauth") or {}

    return {
        "id": str(doc["_id"]),
        "display_name": doc.get("display_name"),
        "role": doc.get("role"),
        "verification_status": doc.get("verification_status"),
        "collective_id": str(collective) if collective else None,
        "joined_at": doc.get("joined_at").isoformat()
        if doc.get("joined_at")
        else None,
        "last_active": doc.get("last_active").isoformat()
        if doc.get("last_active")
        else None,
        "security": {
            "force_logout": bool(security.get("force_logout")),
            "has_duress_pin": bool(security.get("duress_pin_hash")),
        },
        "google_oauth": {
            "email": oauth.get("email"),
            "email_verified": bool(oauth.get("email_verified", False)),
            "picture": oauth.get("picture"),
        },
    }


class RegisterHandler(tornado.web.RequestHandler):
    async def post(self):
        self.set_status(405)
        self.finish(
            {
                "error": "google_oauth_only",
                "message": "Use /auth/login with Google id_token",
            }
        )


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
