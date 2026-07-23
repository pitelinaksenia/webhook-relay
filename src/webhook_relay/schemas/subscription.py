import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl


class SubscriptionCreate(BaseModel):
    url: HttpUrl
    event_types: list[str]
    secret: str


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: HttpUrl
    event_types: list[str]
    is_active: bool
    created_at: datetime
