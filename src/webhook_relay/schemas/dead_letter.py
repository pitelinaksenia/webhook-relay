import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DeadLetterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    delivery_id: uuid.UUID
    last_error: str
    failed_at: datetime
