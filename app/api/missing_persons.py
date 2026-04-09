import mimetypes
from pathlib import Path

from pydantic import ValidationError
import tornado.web

from app.api._auth import AuthenticatedHandler
from app.models.missing_person import MissingPersonCreate
from app.core.config import get_settings
from app.services.missing_persons import (
    can_view_private_dossier,
    create_missing_person,
    get_missing_person_by_id,
    list_public_missing_persons,
    serialize_private_missing_person,
    serialize_public_missing_person,
)
from app.services.media import upload_public_image


MAX_IMAGE_BYTES = 8 * 1024 * 1024


class MissingPersonsPublicListHandler(tornado.web.RequestHandler):
    async def get(self):
        db = self.application.settings["db"]

        try:
            limit = min(max(int(self.get_argument("limit", "20")), 1), 100)
            offset = max(int(self.get_argument("offset", "0")), 0)
        except ValueError:
            self.set_status(400)
            self.finish({"error": "invalid_pagination"})
            return

        status = self.get_argument("status", default="").strip().upper()
        status_filter = status if status else None

        docs = await list_public_missing_persons(
            db,
            limit=limit,
            offset=offset,
            status=status_filter,
        )

        self.finish(
            {
                "items": [
                    serialize_public_missing_person(doc) for doc in docs
                ],
                "limit": limit,
                "offset": offset,
            }
        )


class MissingPersonPublicDetailHandler(tornado.web.RequestHandler):
    async def get(self, person_id: str):
        db = self.application.settings["db"]
        try:
            doc = await get_missing_person_by_id(db, person_id)
        except ValueError as exc:
            self.set_status(400)
            self.finish({"error": str(exc)})
            return

        if not doc:
            self.set_status(404)
            self.finish({"error": "missing_person_not_found"})
            return

        self.finish({"item": serialize_public_missing_person(doc)})


class MissingPersonCreateHandler(AuthenticatedHandler):
    async def post(self):
        if self._finished:
            return

        db = self.application.settings["db"]
        try:
            payload = MissingPersonCreate.model_validate_json(
                self.request.body
            )
        except ValidationError as exc:
            self.set_status(400)
            self.finish({"error": "invalid_payload", "details": exc.errors()})
            return

        try:
            doc = await create_missing_person(
                db,
                payload=payload,
                current_user=self.current_user_doc,
            )
        except ValueError as exc:
            self.set_status(400)
            self.finish({"error": str(exc)})
            return

        self.set_status(201)
        self.finish({"item": serialize_private_missing_person(doc)})


class MissingPersonImageUploadHandler(AuthenticatedHandler):
    async def post(self):
        if self._finished:
            return

        files = self.request.files.get("image") or []
        if not files:
            self.set_status(400)
            self.finish({"error": "missing_image_file"})
            return

        image = files[0]
        file_bytes = image.get("body") or b""
        if not file_bytes:
            self.set_status(400)
            self.finish({"error": "empty_image_file"})
            return

        if len(file_bytes) > MAX_IMAGE_BYTES:
            self.set_status(400)
            self.finish(
                {
                    "error": "image_too_large",
                    "max_bytes": MAX_IMAGE_BYTES,
                }
            )
            return

        filename = str(image.get("filename") or "upload.bin")
        content_type = str(
            image.get("content_type") or "application/octet-stream"
        )

        try:
            uploaded = await upload_public_image(
                file_bytes=file_bytes,
                filename=filename,
                content_type=content_type,
            )
        except ValueError as exc:
            self.set_status(400)
            self.finish({"error": str(exc)})
            return
        except Exception as exc:
            self.set_status(500)
            self.finish({"error": str(exc)})
            return

        self.set_status(201)
        self.finish(uploaded)


class MissingPersonImageProxyHandler(tornado.web.RequestHandler):
    async def get(self):
        object_key = str(self.get_argument("object_key", "")).strip()
        if not object_key:
            self.set_status(400)
            self.finish({"error": "missing_object_key"})
            return

        normalized = object_key.lstrip("/")
        if (
            not normalized.startswith("images/")
            or ".." in normalized
            or len(normalized) > 512
        ):
            self.set_status(400)
            self.finish({"error": "invalid_object_key"})
            return

        settings = get_settings()

        if settings.media_backend.lower() == "gcs":
            try:
                from google.cloud import storage
            except Exception:
                self.set_status(500)
                self.finish({"error": "google_cloud_storage_not_installed"})
                return

            if not settings.gcs_bucket:
                self.set_status(500)
                self.finish({"error": "missing_gcs_bucket"})
                return

            try:
                client = storage.Client(
                    project=settings.gcs_project_id or None
                )
                bucket = client.bucket(settings.gcs_bucket)
                blob = bucket.blob(normalized)
                if not blob.exists(client):
                    self.set_status(404)
                    self.finish({"error": "image_not_found"})
                    return
                content_type = blob.content_type or "application/octet-stream"
                body = blob.download_as_bytes()
            except Exception as exc:
                self.set_status(500)
                self.finish({"error": str(exc)})
                return

            self.set_header("Content-Type", content_type)
            self.set_header("Cache-Control", "public, max-age=300")
            self.finish(body)
            return

        target = Path(settings.media_local_root) / normalized
        if not target.exists() or not target.is_file():
            self.set_status(404)
            self.finish({"error": "image_not_found"})
            return

        content_type, _ = mimetypes.guess_type(str(target))
        self.set_header(
            "Content-Type",
            content_type or "application/octet-stream",
        )
        self.set_header("Cache-Control", "public, max-age=300")
        self.finish(target.read_bytes())


class MissingPersonPrivateDetailHandler(AuthenticatedHandler):
    async def get(self, person_id: str):
        if self._finished:
            return

        db = self.application.settings["db"]
        try:
            doc = await get_missing_person_by_id(db, person_id)
        except ValueError as exc:
            self.set_status(400)
            self.finish({"error": str(exc)})
            return

        if not doc:
            self.set_status(404)
            self.finish({"error": "missing_person_not_found"})
            return

        include_private = (
            self.get_argument("include_private", default="false")
            .strip()
            .lower()
            in {"1", "true", "yes"}
        )

        if include_private:
            if not can_view_private_dossier(self.current_user_doc, doc):
                self.set_status(403)
                self.finish({"error": "private_dossier_forbidden"})
                return
            self.finish({"item": serialize_private_missing_person(doc)})
            return

        self.finish({"item": serialize_public_missing_person(doc)})
