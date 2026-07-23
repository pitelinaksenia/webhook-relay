import uuid
from datetime import datetime

from pydantic import BaseModel


class EventCreate(BaseModel):
    event_type: str
    payload: dict
    idempotency_key: str | None = None


class EventResponse(BaseModel):
    id: uuid.UUID
    event_type: str
    payload: dict
    idempotency_key: str
    source: str | None
    created_at: datetime
    deliveries: list
