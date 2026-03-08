from app.api._auth import AuthenticatedHandler
from app.services.social import get_feed


class FeedHandler(AuthenticatedHandler):
    async def get(self):
        if self._finished:
            return

        db = self.application.settings["db"]
        try:
            limit = min(max(int(self.get_argument("limit", "20")), 1), 100)
            offset = max(int(self.get_argument("offset", "0")), 0)
        except ValueError:
            self.set_status(400)
            self.finish({"error": "invalid_pagination"})
            return

        items = await get_feed(db, self.current_user_doc["_id"], limit=limit, offset=offset)
        self.finish(
            {
                "items": [
                    {
                        "id": str(item["_id"]),
                        "user_id": str(item["user_id"]),
                        "text": item["text"],
                        "media_type": item["media_type"],
                        "media_href": item.get("media_href"),
                        "created_at": item["created_at"].isoformat(),
                    }
                    for item in items
                ],
                "limit": limit,
                "offset": offset,
            }
        )
