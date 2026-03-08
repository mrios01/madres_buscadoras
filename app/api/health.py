import tornado.web


class HealthHandler(tornado.web.RequestHandler):
    async def get(self):
        self.write({"ok": True, "service": "marzlive_upgrade"})
