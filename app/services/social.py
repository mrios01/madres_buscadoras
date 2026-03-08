from datetime import UTC, datetime

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def ensure_social_indexes(db) -> None:
    await db.follows.create_index([("follower_id", ASCENDING), ("target_id", ASCENDING)], unique=True, name="uniq_follow")
    await db.follows.create_index([("follower_id", ASCENDING)], name="idx_follow_follower")
    await db.posts.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)], name="idx_posts_user_created")
    await db.posts.create_index([("created_at", DESCENDING)], name="idx_posts_created")


async def follow_user(db, follower_id: ObjectId, target_id: ObjectId) -> None:
    if follower_id == target_id:
        raise ValueError("cannot_follow_self")

    await db.follows.update_one(
        {"follower_id": follower_id, "target_id": target_id},
        {"$setOnInsert": {"created_at": _utcnow()}},
        upsert=True,
    )


async def unfollow_user(db, follower_id: ObjectId, target_id: ObjectId) -> None:
    await db.follows.delete_one({"follower_id": follower_id, "target_id": target_id})


async def create_post(db, user_id: ObjectId, text: str, media_type: str, media_href: str | None) -> dict:
    doc = {
        "user_id": user_id,
        "text": text,
        "media_type": media_type,
        "media_href": media_href,
        "created_at": _utcnow(),
    }
    result = await db.posts.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def get_feed(db, user_id: ObjectId, limit: int = 20, offset: int = 0) -> list[dict]:
    follows = await db.follows.find({"follower_id": user_id}).to_list(length=2000)
    ids = [f["target_id"] for f in follows] + [user_id]

    cursor = (
        db.posts.find({"user_id": {"$in": ids}})
        .sort("created_at", DESCENDING)
        .skip(offset)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


def parse_object_id(value: str, field_name: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise ValueError(f"invalid_{field_name}")
    return ObjectId(value)
