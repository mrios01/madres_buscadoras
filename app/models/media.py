from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Visibility = Literal["public", "private"]


class MediaIngestPlanRequest(BaseModel):
    filename: str = Field(min_length=3, max_length=255)
    visibility: Visibility = "private"


class PlaybackUrlRequest(BaseModel):
    object_key: str = Field(min_length=3, max_length=1024)
    visibility: Visibility = "private"


class MediaUploadTicketRequest(BaseModel):
    media_asset_id: str = Field(min_length=8)


class MediaFinalizeRequest(BaseModel):
    media_asset_id: str = Field(min_length=8)
    status: Literal["ready", "failed"] = "ready"


class MediaAsset(BaseModel):
    id: str
    owner_user_id: str
    backend: str
    object_prefix: str
    visibility: Visibility
    status: str
    created_at: datetime
