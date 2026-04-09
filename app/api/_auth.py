import tornado.web

from app.core.config import get_settings
from app.services.auth import get_user_by_session_token, revoke_session


class SessionAwareHandler(tornado.web.RequestHandler):
    current_user_doc: dict | None = None

    async def prepare(self):
        settings = get_settings()
        token = self.get_secure_cookie(settings.auth_cookie_name)
        if not token:
            return

        db = self.application.settings["db"]
        user = await get_user_by_session_token(db, token.decode("utf-8"))
        if not user:
            return

        security = user.get("security") or {}
        if bool(security.get("force_logout")):
            await revoke_session(db, token.decode("utf-8"))
            self.clear_cookie(settings.auth_cookie_name)
            return

        self.current_user_doc = user

    def get_current_user(self):
        return self.current_user_doc


class AuthenticatedHandler(SessionAwareHandler):
    async def prepare(self):
        await super().prepare()
        if self._finished:
            return

        if not self.current_user_doc:
            self.set_status(401)
            self.finish({"error": "not_authenticated"})
            return
