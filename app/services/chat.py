from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
import json
import logging
from typing import Any
from typing import DefaultDict
from typing import Set

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING

from app.core.config import Settings

try:
    from google.cloud import pubsub_v1
except Exception:  # pragma: no cover
    pubsub_v1 = None


logger = logging.getLogger("madres_buscadoras.chat")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def encrypt_payload(plain_text: str) -> bytes:
    """Placeholder for AES-256 encryption before publishing to Pub/Sub."""
    return plain_text.encode("utf-8")


def decrypt_payload(cipher_bytes: bytes) -> str:
    """Placeholder for AES-256 decryption after receiving from Pub/Sub."""
    return cipher_bytes.decode("utf-8")


def _serialize_dt(value: Any) -> str | Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC).isoformat()
        return value.isoformat()
    return value


def serialize_chat_message(doc: dict) -> dict:
    image_object_key = str(doc.get("image_object_key") or "")
    image_url = doc.get("image_url")
    if not image_url and image_object_key:
        image_url = (
            "/missing-persons/image-proxy?object_key="
            f"{image_object_key}"
        )

    return {
        "id": str(doc.get("_id")),
        "channel": str(doc.get("channel") or "general"),
        "text": str(doc.get("text") or ""),
        "user_id": str(doc.get("user_id") or ""),
        "user_display_name": str(doc.get("user_display_name") or "Busqueda"),
        "image_object_key": image_object_key or None,
        "image_url": image_url,
        "reply_to_message_id": (
            str(doc.get("reply_to_message_id"))
            if doc.get("reply_to_message_id")
            else None
        ),
        "reply_to_preview": str(doc.get("reply_to_preview") or "") or None,
        "created_at": _serialize_dt(doc.get("created_at")),
    }


async def ensure_chat_indexes(db) -> None:
    await db.chat_messages.create_index(
        [("channel", ASCENDING), ("created_at", DESCENDING)],
        name="idx_chat_channel_created",
    )
    await db.chat_messages.create_index(
        [("user_id", ASCENDING), ("created_at", DESCENDING)],
        name="idx_chat_user_created",
    )


async def create_chat_message(
    db,
    *,
    channel: str,
    text: str,
    user: dict,
    image_object_key: str | None,
    reply_to_message_id: str | None,
) -> dict:
    clean_channel = channel.strip() or "general"
    clean_text = text.strip()
    clean_object_key = (image_object_key or "").strip() or None

    if not clean_text and not clean_object_key:
        raise ValueError("empty_chat_message")

    if clean_object_key:
        normalized = clean_object_key.lstrip("/")
        if not normalized.startswith("images/") or ".." in normalized:
            raise ValueError("invalid_image_object_key")
        clean_object_key = normalized

    reply_oid: ObjectId | None = None
    reply_preview: str | None = None
    if reply_to_message_id:
        if not ObjectId.is_valid(reply_to_message_id):
            raise ValueError("invalid_reply_to_message_id")
        reply_oid = ObjectId(reply_to_message_id)
        source = await db.chat_messages.find_one(
            {"_id": reply_oid, "channel": clean_channel}
        )
        if not source:
            raise ValueError("reply_message_not_found")
        source_text = str(source.get("text") or "").strip()
        if source_text:
            reply_preview = source_text[:140]

    doc = {
        "channel": clean_channel,
        "text": clean_text,
        "user_id": user.get("_id"),
        "user_display_name": str(user.get("display_name") or "Busqueda"),
        "image_object_key": clean_object_key,
        "reply_to_message_id": reply_oid,
        "reply_to_preview": reply_preview,
        "created_at": _utcnow(),
    }

    result = await db.chat_messages.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def list_chat_messages(
    db,
    *,
    channel: str,
    limit: int,
) -> list[dict]:
    clean_channel = channel.strip() or "general"
    cursor = (
        db.chat_messages.find({"channel": clean_channel})
        .sort("created_at", DESCENDING)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    docs.reverse()
    return docs


class BulletinHub:
    """Routes chat payloads to connected WebSocket clients by channel."""

    def __init__(self) -> None:
        self._clients: DefaultDict[str, Set[Any]] = defaultdict(set)

    def join(self, channel: str, client: Any) -> None:
        self._clients[channel].add(client)

    def leave(self, channel: str, client: Any) -> None:
        if channel not in self._clients:
            return
        self._clients[channel].discard(client)
        if not self._clients[channel]:
            self._clients.pop(channel, None)

    def fan_out(self, channel: str, payload: str) -> None:
        clients = list(self._clients.get(channel, set()))
        if not clients:
            return

        disconnected = []
        for client in clients:
            try:
                client.write_message(payload)
            except Exception:
                disconnected.append(client)

        for client in disconnected:
            self.leave(channel, client)


class AsyncPubSubListener:
    """Consumes Pub/Sub messages and relays them to Tornado loop."""

    def __init__(
        self,
        *,
        project_id: str,
        subscription_id: str,
        hub: BulletinHub,
        io_loop,
    ) -> None:
        if pubsub_v1 is None:
            raise RuntimeError("google_cloud_pubsub_not_installed")

        self.hub = hub
        self.io_loop = io_loop
        self.subscriber = pubsub_v1.SubscriberClient()
        self.subscription_path = self.subscriber.subscription_path(
            project_id,
            subscription_id,
        )
        self.streaming_future = None

    def start(self) -> None:
        self.streaming_future = self.subscriber.subscribe(
            self.subscription_path,
            callback=self.callback,
        )
        logger.info("Started Pub/Sub listener %s", self.subscription_path)

    def callback(self, message) -> None:
        try:
            channel = message.attributes.get("channel")
            if not channel:
                message.ack()
                return

            payload = decrypt_payload(message.data)
            self.io_loop.add_callback(self.hub.fan_out, channel, payload)
            message.ack()
        except Exception:
            logger.exception("Failed to process Pub/Sub chat message")
            message.nack()

    def stop(self, timeout: float = 10.0) -> None:
        if self.streaming_future is not None:
            self.streaming_future.cancel()
            try:
                self.streaming_future.result(timeout=timeout)
            except Exception:
                pass
        self.subscriber.close()


def build_pubsub_clients(settings: Settings):
    if not settings.bulletin_pubsub_enabled:
        return None, None
    if pubsub_v1 is None:
        raise RuntimeError("google_cloud_pubsub_not_installed")
    if not settings.bulletin_project_id:
        raise RuntimeError("bulletin_project_id_not_configured")
    if not settings.bulletin_topic_id:
        raise RuntimeError("bulletin_topic_id_not_configured")

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(
        settings.bulletin_project_id,
        settings.bulletin_topic_id,
    )
    return publisher, topic_path


def publish_chat_payload(
    *,
    publisher,
    topic_path: str,
    channel: str,
    payload: dict,
) -> None:
    if publisher is None:
        return
    body = json.dumps(payload, ensure_ascii=True)
    encrypted = encrypt_payload(body)
    publisher.publish(topic_path, encrypted, channel=channel)
