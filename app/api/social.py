from app.api._auth import AuthenticatedHandler
from app.models.social import FollowAction, PostCreate
from app.services.media import get_media_asset_for_owner, media_asset_playback_url
from app.services.social import create_post, follow_user, parse_object_id, unfollow_user


class FollowHandler(AuthenticatedHandler):
    async def post(self):
        if self._finished:
            return

        db = self.application.settings["db"]
        try:
            payload = FollowAction.model_validate_json(self.request.body)
            target_id = parse_object_id(payload.target_user_id, "target_user_id")
        except Exception as exc:
            self.set_status(400)
            self.finish({"error": str(exc)})
            return

        try:
            await follow_user(db, self.current_user_doc["_id"], target_id)
        except ValueError as exc:
            self.set_status(400)
            self.finish({"error": str(exc)})
            return

        self.set_status(204)
        self.finish()


class UnfollowHandler(AuthenticatedHandler):
    async def post(self):
        if self._finished:
            return

        db = self.application.settings["db"]
        try:
            payload = FollowAction.model_validate_json(self.request.body)
            target_id = parse_object_id(payload.target_user_id, "target_user_id")
        except Exception as exc:
            self.set_status(400)
            self.finish({"error": str(exc)})
            return

        await unfollow_user(db, self.current_user_doc["_id"], target_id)
        self.set_status(204)
        self.finish()


class CreatePostHandler(AuthenticatedHandler):
    async def post(self):
        if self._finished:
            return

        db = self.application.settings["db"]
        try:
            payload = PostCreate.model_validate_json(self.request.body)
        except Exception as exc:
            self.set_status(400)
            self.finish({"error": str(exc)})
            return

        media_type = payload.media_type
        media_href = payload.media_href

        if payload.media_asset_id:
            try:
                asset = await get_media_asset_for_owner(
                    db,
                    media_asset_id=payload.media_asset_id,
                    owner_user_id=self.current_user_doc["_id"],
                )
            except ValueError as exc:
                self.set_status(400)
                self.finish({"error": str(exc)})
                return

            if not asset:
                self.set_status(404)
                self.finish({"error": "media_asset_not_found"})
                return
            if asset.get("status") != "ready":
                self.set_status(409)
                self.finish({"error": "media_asset_not_ready"})
                return

            media_type = "video"
            media_href = await media_asset_playback_url(asset)

        post = await create_post(
            db,
            user_id=self.current_user_doc["_id"],
            text=payload.text,
            media_type=media_type,
            media_href=media_href,
        )

        self.set_status(201)
        self.finish(
            {
                "id": str(post["_id"]),
                "user_id": str(post["user_id"]),
                "text": post["text"],
                "media_type": post["media_type"],
                "media_href": post.get("media_href"),
                "created_at": post["created_at"].isoformat(),
            }
        )
