import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from webhook_relay.schemas.delivery import DeliveryResponse


class EventCreate(BaseModel):
    event_type: str
    payload: dict
    idempotency_key: str | None = None
    source: str | None = None


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    payload: dict
    idempotency_key: str
    source: str | None
    created_at: datetime
    deliveries: list[DeliveryResponse]
