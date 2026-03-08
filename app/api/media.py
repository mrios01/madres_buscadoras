from app.api._auth import AuthenticatedHandler
from app.models.media import (
    MediaFinalizeRequest,
    MediaIngestPlanRequest,
    MediaUploadTicketRequest,
    PlaybackUrlRequest,
)
from app.services.media import (
    build_ingest_plan,
    create_media_asset,
    get_media_asset_for_owner,
    get_media_storage,
    issue_upload_ticket,
    set_media_status,
)


class MediaIngestPlanHandler(AuthenticatedHandler):
    async def post(self):
        if self._finished:
            return

        db = self.application.settings["db"]
        try:
            payload = MediaIngestPlanRequest.model_validate_json(self.request.body)
        except Exception as exc:
            self.set_status(400)
            self.finish({"error": str(exc)})
            return

        plan = build_ingest_plan(filename=payload.filename, visibility=payload.visibility)
        asset = await create_media_asset(db, owner_user_id=self.current_user_doc["_id"], plan=plan)

        self.set_status(201)
        self.finish(
            {
                "id": str(asset["_id"]),
                "backend": plan.backend,
                "visibility": plan.visibility,
                "status": asset["status"],
                "object_prefix": plan.object_prefix,
                "source_object_key": plan.source_object_key,
                "source_upload_target": plan.source_upload_target,
                "hls_manifest_key": plan.hls_manifest_key,
                "ffmpeg_command": plan.ffmpeg_command,
                "created_at": asset["created_at"].isoformat(),
            }
        )


class MediaUploadTicketHandler(AuthenticatedHandler):
    async def post(self):
        if self._finished:
            return

        db = self.application.settings["db"]
        try:
            payload = MediaUploadTicketRequest.model_validate_json(self.request.body)
            asset = await get_media_asset_for_owner(
                db,
                media_asset_id=payload.media_asset_id,
                owner_user_id=self.current_user_doc["_id"],
            )
            if not asset:
                self.set_status(404)
                self.finish({"error": "media_asset_not_found"})
                return

            ticket = await issue_upload_ticket(asset)
        except ValueError as exc:
            self.set_status(400)
            self.finish({"error": str(exc)})
            return
        except Exception as exc:
            self.set_status(400)
            self.finish({"error": str(exc)})
            return

        self.finish(
            {
                "media_asset_id": payload.media_asset_id,
                "status": asset.get("status"),
                "upload": ticket,
            }
        )


class MediaFinalizeHandler(AuthenticatedHandler):
    async def post(self):
        if self._finished:
            return

        db = self.application.settings["db"]
        try:
            payload = MediaFinalizeRequest.model_validate_json(self.request.body)
            updated = await set_media_status(
                db,
                media_asset_id=payload.media_asset_id,
                owner_user_id=self.current_user_doc["_id"],
                status=payload.status,
            )
            if not updated:
                self.set_status(404)
                self.finish({"error": "media_asset_not_found"})
                return
        except ValueError as exc:
            self.set_status(400)
            self.finish({"error": str(exc)})
            return

        self.finish(
            {
                "media_asset_id": payload.media_asset_id,
                "status": updated["status"],
                "updated_at": updated["updated_at"].isoformat(),
            }
        )


class MediaPlaybackUrlHandler(AuthenticatedHandler):
    async def post(self):
        if self._finished:
            return

        try:
            payload = PlaybackUrlRequest.model_validate_json(self.request.body)
        except Exception as exc:
            self.set_status(400)
            self.finish({"error": str(exc)})
            return

        try:
            storage = get_media_storage()
            url = await storage.playback_url(payload.object_key, payload.visibility)
        except Exception as exc:
            self.set_status(400)
            self.finish({"error": str(exc)})
            return

        self.finish(
            {
                "object_key": payload.object_key,
                "visibility": payload.visibility,
                "playback_url": url,
            }
        )
