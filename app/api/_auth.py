import tornado.web

from app.core.config import get_settings
from app.services.auth import get_user_by_session_token


class AuthenticatedHandler(tornado.web.RequestHandler):
    current_user_doc: dict | None = None

    async def prepare(self):
        settings = get_settings()
        token = self.get_secure_cookie(settings.auth_cookie_name)
        if not token:
            self.set_status(401)
            self.finish({"error": "not_authenticated"})
            return

        db = self.application.settings["db"]
        user = await get_user_by_session_token(db, token.decode("utf-8"))
        if not user:
            self.set_status(401)
            self.finish({"error": "invalid_session"})
            return

        self.current_user_doc = user
