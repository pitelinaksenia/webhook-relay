import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from webhook_relay.models.delivery import DeliveryStatus


class DeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subscription_id: uuid.UUID
    status: DeliveryStatus
    attempt_count: int
    created_at: datetime
