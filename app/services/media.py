from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
import asyncio
from uuid import uuid4

from bson import ObjectId
from pymongo import ASCENDING, ReturnDocument

from app.core.config import Settings, get_settings

try:
    from google.cloud import storage
except Exception:  # pragma: no cover
    storage = None


@dataclass(slots=True)
class IngestPlan:
    media_id: str
    backend: str
    visibility: str
    object_prefix: str
    source_object_key: str
    source_upload_target: str
    hls_manifest_key: str
    ffmpeg_command: list[str]


class MediaStorage:
    async def playback_url(self, object_key: str, visibility: str) -> str:
        raise NotImplementedError


class LocalMediaStorage(MediaStorage):
    def __init__(self, settings: Settings):
        self.settings = settings
        self.public_base_url = settings.media_public_base_url.rstrip("/")

    async def playback_url(self, object_key: str, visibility: str) -> str:
        object_key = object_key.lstrip("/")
        return f"{self.public_base_url}/{object_key}"


class GCSMediaStorage(MediaStorage):
    def __init__(self, settings: Settings):
        if storage is None:
            raise RuntimeError("google_cloud_storage_not_installed")
        if not settings.gcs_bucket:
            raise RuntimeError("missing_gcs_bucket")

        self.bucket_name = settings.gcs_bucket
        self.ttl_seconds = settings.gcs_signed_url_ttl_seconds
        self.client = storage.Client(project=settings.gcs_project_id or None)

    async def playback_url(self, object_key: str, visibility: str) -> str:
        object_key = object_key.lstrip("/")
        bucket = self.client.bucket(self.bucket_name)
        blob = bucket.blob(object_key)

        if visibility == "public":
            return f"https://storage.googleapis.com/{self.bucket_name}/{object_key}"

        expiry = datetime.now(UTC) + timedelta(seconds=self.ttl_seconds)
        return blob.generate_signed_url(version="v4", expiration=expiry, method="GET")


def parse_object_id(value: str, field_name: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise ValueError(f"invalid_{field_name}")
    return ObjectId(value)


def get_media_storage(settings: Settings | None = None) -> MediaStorage:
    settings = settings or get_settings()
    backend = settings.media_backend.lower()
    if backend == "gcs":
        return GCSMediaStorage(settings)
    return LocalMediaStorage(settings)


def build_ingest_plan(*, filename: str, visibility: str, settings: Settings | None = None) -> IngestPlan:
    settings = settings or get_settings()

    ext = Path(filename).suffix.lower() or ".mp4"
    media_id = uuid4().hex
    object_prefix = f"videos/{media_id}"
    source_key = f"{object_prefix}/source{ext}"
    hls_manifest_key = f"{object_prefix}/hls/index.m3u8"

    if settings.media_backend == "gcs":
        source_upload_target = f"gs://{settings.gcs_bucket}/{source_key}"
        output_target = f"gs://{settings.gcs_bucket}/{object_prefix}/hls"
    else:
        source_upload_target = str(Path(settings.media_local_root) / source_key)
        output_target = str(Path(settings.media_local_root) / object_prefix / "hls")

    ffmpeg_command = [
        "ffmpeg",
        "-y",
        "-i",
        source_upload_target,
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-hls_time",
        "6",
        "-hls_playlist_type",
        "vod",
        "-f",
        "hls",
        str(Path(output_target) / "index.m3u8"),
    ]

    return IngestPlan(
        media_id=media_id,
        backend=settings.media_backend,
        visibility=visibility,
        object_prefix=object_prefix,
        source_object_key=source_key,
        source_upload_target=source_upload_target,
        hls_manifest_key=hls_manifest_key,
        ffmpeg_command=ffmpeg_command,
    )


async def ensure_media_indexes(db) -> None:
    await db.media_assets.create_index([("owner_user_id", ASCENDING), ("created_at", ASCENDING)], name="idx_media_owner_created")
    await db.media_assets.create_index([("object_prefix", ASCENDING)], unique=True, name="uniq_media_prefix")


async def create_media_asset(db, *, owner_user_id, plan: IngestPlan) -> dict:
    doc = {
        "owner_user_id": owner_user_id,
        "backend": plan.backend,
        "visibility": plan.visibility,
        "object_prefix": plan.object_prefix,
        "source_object_key": plan.source_object_key,
        "source_upload_target": plan.source_upload_target,
        "hls_manifest_key": plan.hls_manifest_key,
        "status": "planned",
        "created_at": datetime.now(UTC),
    }
    result = await db.media_assets.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def get_media_asset_for_owner(db, *, media_asset_id: str, owner_user_id) -> dict | None:
    oid = parse_object_id(media_asset_id, "media_asset_id")
    return await db.media_assets.find_one({"_id": oid, "owner_user_id": owner_user_id})


async def issue_upload_ticket(asset: dict, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()

    if asset["backend"] == "gcs":
        if storage is None:
            raise RuntimeError("google_cloud_storage_not_installed")
        if not settings.gcs_bucket:
            raise RuntimeError("missing_gcs_bucket")

        client = storage.Client(project=settings.gcs_project_id or None)
        bucket = client.bucket(settings.gcs_bucket)
        blob = bucket.blob(asset["source_object_key"])
        expiry = datetime.now(UTC) + timedelta(seconds=settings.gcs_signed_url_ttl_seconds)
        signed_put = blob.generate_signed_url(version="v4", expiration=expiry, method="PUT", content_type="video/mp4")

        return {
            "kind": "signed_put",
            "method": "PUT",
            "url": signed_put,
            "headers": {"Content-Type": "video/mp4"},
            "object_key": asset["source_object_key"],
            "expires_in_seconds": settings.gcs_signed_url_ttl_seconds,
        }

    target_path = Path(asset["source_upload_target"])
    target_path.parent.mkdir(parents=True, exist_ok=True)
    return {
        "kind": "local_path",
        "method": "PUT",
        "path": str(target_path),
        "object_key": asset["source_object_key"],
    }


async def set_media_status(db, *, media_asset_id: str, owner_user_id, status: str) -> dict | None:
    oid = parse_object_id(media_asset_id, "media_asset_id")
    result = await db.media_assets.find_one_and_update(
        {"_id": oid, "owner_user_id": owner_user_id},
        {"$set": {"status": status, "updated_at": datetime.now(UTC)}},
        return_document=ReturnDocument.AFTER,
    )
    return result


async def media_asset_playback_url(asset: dict, settings: Settings | None = None) -> str:
    storage_adapter = get_media_storage(settings)
    return await storage_adapter.playback_url(asset["hls_manifest_key"], asset.get("visibility", "private"))


async def claim_next_media_asset(db, *, backend: str | None = None) -> dict | None:
    query: dict = {"status": "planned"}
    if backend:
        query["backend"] = backend

    return await db.media_assets.find_one_and_update(
        query,
        {"$set": {"status": "processing", "processing_started_at": datetime.now(UTC)}},
        sort=[("created_at", ASCENDING)],
        return_document=ReturnDocument.AFTER,
    )


async def mark_media_asset_ready(db, *, asset_id: ObjectId) -> dict | None:
    return await db.media_assets.find_one_and_update(
        {"_id": asset_id},
        {"$set": {"status": "ready", "updated_at": datetime.now(UTC)}, "$unset": {"last_error": ""}},
        return_document=ReturnDocument.AFTER,
    )


async def mark_media_asset_failed(db, *, asset_id: ObjectId, reason: str) -> dict | None:
    return await db.media_assets.find_one_and_update(
        {"_id": asset_id},
        {
            "$set": {
                "status": "failed",
                "updated_at": datetime.now(UTC),
                "last_error": reason,
            }
        },
        return_document=ReturnDocument.AFTER,
    )


def _local_ffmpeg_command(asset: dict, settings: Settings) -> list[str]:
    source_path = Path(settings.media_local_root) / asset["source_object_key"]
    manifest_path = Path(settings.media_local_root) / asset["hls_manifest_key"]
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    return [
        "ffmpeg",
        "-y",
        "-i",
        str(source_path),
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-hls_time",
        "6",
        "-hls_playlist_type",
        "vod",
        "-f",
        "hls",
        str(manifest_path),
    ]


async def process_media_asset(db, *, asset: dict, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()

    if asset.get("backend") != "local":
        raise RuntimeError("worker_backend_not_supported_yet")

    cmd = _local_ffmpeg_command(asset, settings)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="ignore")[-1000:]
        raise RuntimeError(f"ffmpeg_failed:{err}")

    updated = await mark_media_asset_ready(db, asset_id=asset["_id"])
    if not updated:
        raise RuntimeError("media_asset_not_found_after_processing")
    return updated


async def process_next_media_asset(db, *, backend: str = "local", settings: Settings | None = None) -> dict | None:
    settings = settings or get_settings()
    asset = await claim_next_media_asset(db, backend=backend)
    if not asset:
        return None

    try:
        return await process_media_asset(db, asset=asset, settings=settings)
    except Exception as exc:
        await mark_media_asset_failed(db, asset_id=asset["_id"], reason=str(exc))
        raise
