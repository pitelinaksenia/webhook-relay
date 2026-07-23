import uuid

from webhook_relay.exceptions import EventNotFoundError
from webhook_relay.models import Event
from webhook_relay.repositories.event_repo import EventRepo
from webhook_relay.schemas.event import EventCreate


class EventService:
    def __init__(self, event_repo: EventRepo):
        self.event_repo = event_repo

    async def create(self, event_data: EventCreate) -> Event:
        existing = await self.event_repo.get_by_idempotency_key(event_data.idempotency_key)
        if existing is not None:
            return existing
        event = await self.event_repo.create(event_data)
        return event

    async def get_by_id(self, event_id: uuid.UUID) -> Event:
        event = await self.event_repo.get_by_id(event_id)
        if event is None:
            raise EventNotFoundError(event_id)
        return event
