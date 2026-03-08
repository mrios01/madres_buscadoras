from datetime import datetime

from pydantic import BaseModel, Field


class FollowAction(BaseModel):
    target_user_id: str = Field(min_length=8)


class PostCreate(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    media_type: str = "text"  # text | image | video
    media_href: str | None = None
    media_asset_id: str | None = None


class FeedItem(BaseModel):
    id: str
    user_id: str
    text: str
    media_type: str
    media_href: str | None = None
    created_at: datetime
