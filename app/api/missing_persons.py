from pydantic import ValidationError
import tornado.web

from app.api._auth import AuthenticatedHandler
from app.models.missing_person import MissingPersonCreate
from app.services.missing_persons import (
    can_view_private_dossier,
    create_missing_person,
    get_missing_person_by_id,
    list_public_missing_persons,
    serialize_private_missing_person,
    serialize_public_missing_person,
)


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
