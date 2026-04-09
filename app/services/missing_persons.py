from datetime import UTC, datetime

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING

from app.models.missing_person import MissingPersonCreate


def _utcnow() -> datetime:
    return datetime.now(UTC)


def parse_object_id(value: str, field_name: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise ValueError(f"invalid_{field_name}")
    return ObjectId(value)


def _dedupe_object_ids(values: list[ObjectId]) -> list[ObjectId]:
    unique: dict[str, ObjectId] = {}
    for oid in values:
        unique[str(oid)] = oid
    return list(unique.values())


async def ensure_missing_person_indexes(db) -> None:
    await db.missing_persons.create_index(
        [("status", ASCENDING), ("updated_at", DESCENDING)],
        name="idx_missing_status_updated",
    )
    await db.missing_persons.create_index(
        [("public_ficha.date_missing", DESCENDING)],
        name="idx_missing_date",
    )
    await db.missing_persons.create_index(
        [("private_dossier.reporting_user_id", ASCENDING)],
        name="idx_missing_reporting_user",
    )
    await db.missing_persons.create_index(
        [("private_dossier.authorized_collective_ids", ASCENDING)],
        name="idx_missing_authorized_collectives",
    )


async def create_missing_person(
    db,
    payload: MissingPersonCreate,
    current_user: dict,
) -> dict:
    now = _utcnow()

    auth_ids: list[ObjectId] = []
    for raw_id in payload.private_dossier.authorized_collective_ids:
        auth_ids.append(parse_object_id(raw_id, "authorized_collective_id"))

    user_collective = current_user.get("collective_id")
    if isinstance(user_collective, ObjectId):
        auth_ids.append(user_collective)

    auth_ids = _dedupe_object_ids(auth_ids)

    doc = {
        "status": payload.status,
        "public_ficha": payload.public_ficha.model_dump(),
        "private_dossier": {
            "reporting_user_id": current_user["_id"],
            "authorized_collective_ids": auth_ids,
            "official_case_number": (
                payload.private_dossier.official_case_number
            ),
            "dna_sample_registered": (
                payload.private_dossier.dna_sample_registered
            ),
            "suspected_context": payload.private_dossier.suspected_context,
            "internal_notes": payload.private_dossier.internal_notes,
        },
        "created_at": now,
        "updated_at": now,
    }

    result = await db.missing_persons.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def list_public_missing_persons(
    db,
    *,
    limit: int,
    offset: int,
    status: str | None,
) -> list[dict]:
    query: dict = {}
    if status:
        query["status"] = status

    cursor = (
        db.missing_persons.find(query, {"private_dossier": 0})
        .sort("updated_at", DESCENDING)
        .skip(offset)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def get_missing_person_by_id(db, person_id: str) -> dict | None:
    oid = parse_object_id(person_id, "person_id")
    return await db.missing_persons.find_one({"_id": oid})


def can_view_private_dossier(user: dict, doc: dict) -> bool:
    role = str(user.get("role", ""))
    if role == "ADMIN":
        return True

    private = doc.get("private_dossier") or {}
    if private.get("reporting_user_id") == user.get("_id"):
        return True

    user_collective = user.get("collective_id")
    if not isinstance(user_collective, ObjectId):
        return False

    allowed = private.get("authorized_collective_ids") or []
    return any(oid == user_collective for oid in allowed)


def _serialize_dt(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC).isoformat()
        return value.isoformat()
    return value


def serialize_public_missing_person(doc: dict) -> dict:
    public = doc.get("public_ficha") or {}
    public["date_missing"] = _serialize_dt(public.get("date_missing"))

    return {
        "id": str(doc["_id"]),
        "status": doc.get("status"),
        "public_ficha": public,
        "created_at": _serialize_dt(doc.get("created_at")),
        "updated_at": _serialize_dt(doc.get("updated_at")),
    }


def serialize_private_missing_person(doc: dict) -> dict:
    result = serialize_public_missing_person(doc)
    private = doc.get("private_dossier") or {}

    result["private_dossier"] = {
        "reporting_user_id": str(private.get("reporting_user_id", "")),
        "authorized_collective_ids": [
            str(oid) for oid in private.get("authorized_collective_ids") or []
        ],
        "official_case_number": private.get("official_case_number"),
        "dna_sample_registered": bool(private.get("dna_sample_registered")),
        "suspected_context": private.get("suspected_context"),
        "internal_notes": private.get("internal_notes"),
    }
    return result
