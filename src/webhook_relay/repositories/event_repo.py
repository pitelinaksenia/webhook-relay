import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from webhook_relay.models import Event
from webhook_relay.schemas.event import EventCreate


class EventRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def create(self, event_data: EventCreate) -> Event:
        event = Event(
            event_type=event_data.event_type,
            payload=event_data.payload,
            idempotency_key=event_data.idempotency_key,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_by_id(self, event_id: uuid.UUID) -> Event | None:
        return await self.session.get(Event, event_id)

    async def get_by_idempotency_key(self, idemp_key: str) -> Event | None:
        stmt = select(Event).where(Event.idempotency_key == idemp_key)
        return (await self.session.scalars(stmt)).first()
