import json

import tornado.escape
import tornado.websocket

from app.api._auth import AuthenticatedHandler
from app.api._auth import SessionAwareHandler
from app.core.config import get_settings
from app.services.auth import get_user_by_session_token
from app.services.chat import create_chat_message
from app.services.chat import list_chat_messages
from app.services.chat import publish_chat_payload
from app.services.chat import serialize_chat_message
from app.services.media import upload_public_image


MAX_CHAT_IMAGE_BYTES = 8 * 1024 * 1024


class ChatPageHandler(SessionAwareHandler):
    async def get(self):
        if not self.current_user:
            self.redirect("/login")
            return

        settings = get_settings()
        self.render(
            "pizarra.html",
            is_authenticated=True,
            current_section="pizarra",
            static_version=(
                "20260409-7"
                if settings.app_env == "production"
                else "dev"
            ),
        )


class ChatMessagesHandler(AuthenticatedHandler):
    async def get(self):
        if self._finished:
            return

        db = self.application.settings["db"]
        channel = self.get_argument("channel", default="general")
        try:
            limit = min(max(int(self.get_argument("limit", "60")), 1), 150)
        except ValueError:
            self.set_status(400)
            self.finish({"error": "invalid_limit"})
            return

        docs = await list_chat_messages(db, channel=channel, limit=limit)
        self.finish(
            {
                "channel": channel,
                "items": [serialize_chat_message(doc) for doc in docs],
            }
        )


class ChatImageUploadHandler(AuthenticatedHandler):
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

        if len(file_bytes) > MAX_CHAT_IMAGE_BYTES:
            self.set_status(400)
            self.finish(
                {
                    "error": "image_too_large",
                    "max_bytes": MAX_CHAT_IMAGE_BYTES,
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

        object_key = str(uploaded.get("object_key") or "").strip()
        proxy_url = (
            f"/missing-persons/image-proxy?object_key={object_key}"
            if object_key
            else None
        )

        self.set_status(201)
        self.finish(
            {
                "object_key": object_key,
                "proxy_url": proxy_url,
            }
        )


class ChatSocketHandler(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin: str) -> bool:
        return True

    async def open(self):
        settings = get_settings()
        token = self.get_secure_cookie(settings.auth_cookie_name)
        if not token:
            self.close(code=4001, reason="not_authenticated")
            return

        db = self.application.settings["db"]
        user = await get_user_by_session_token(db, token.decode("utf-8"))
        if not user:
            self.close(code=4001, reason="invalid_session")
            return

        self.user_doc = user
        self.channel = (
            self.get_query_argument("channel", default="general")
            .strip()
            or "general"
        )
        hub = self.application.settings["chat_hub"]
        hub.join(self.channel, self)

        self.write_message(
            json.dumps(
                {
                    "type": "ready",
                    "channel": self.channel,
                    "user_display_name": str(
                        user.get("display_name") or "Busqueda"
                    ),
                }
            )
        )

    async def on_message(self, message: str):
        if not getattr(self, "user_doc", None):
            self.close(code=4001, reason="not_authenticated")
            return

        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            self.write_message(
                json.dumps({"type": "error", "error": "invalid_json"})
            )
            return

        if str(payload.get("type") or "message") != "message":
            self.write_message(
                json.dumps({"type": "error", "error": "invalid_type"})
            )
            return

        text = str(payload.get("text") or "")
        image_object_key = payload.get("image_object_key")
        reply_to_message_id = payload.get("reply_to_message_id")

        db = self.application.settings["db"]
        try:
            doc = await create_chat_message(
                db,
                channel=self.channel,
                text=text,
                user=self.user_doc,
                image_object_key=(
                    str(image_object_key)
                    if image_object_key is not None
                    else None
                ),
                reply_to_message_id=(
                    str(reply_to_message_id)
                    if reply_to_message_id is not None
                    else None
                ),
            )
        except ValueError as exc:
            self.write_message(
                json.dumps({"type": "error", "error": str(exc)})
            )
            return

        chat_payload = {
            "type": "message",
            "item": serialize_chat_message(doc),
        }

        publisher = self.application.settings.get("bulletin_publisher")
        topic_path = self.application.settings.get("bulletin_topic_path")

        if publisher and topic_path:
            try:
                publish_chat_payload(
                    publisher=publisher,
                    topic_path=topic_path,
                    channel=self.channel,
                    payload=chat_payload,
                )
            except Exception:
                self.write_message(
                    json.dumps(
                        {
                            "type": "error",
                            "error": "publish_failed",
                        }
                    )
                )
                return
        else:
            hub = self.application.settings["chat_hub"]
            hub.fan_out(self.channel, json.dumps(chat_payload))

    def on_close(self):
        channel = getattr(self, "channel", None)
        if not channel:
            return
        hub = self.application.settings.get("chat_hub")
        if hub:
            hub.leave(channel, self)
