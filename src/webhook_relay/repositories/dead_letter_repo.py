import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from webhook_relay.models.delivery import DeadLetter


class DeadLetterRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, delivery_id: uuid.UUID, last_error: str) -> DeadLetter:
        dead_letter = DeadLetter(delivery_id=delivery_id, last_error=last_error)
        self.session.add(dead_letter)
        await self.session.flush()
        return dead_letter

    async def get_all(self, limit: int = 20, offset: int = 0) -> list[DeadLetter]:
        stmt = (
            select(DeadLetter)
            .options(selectinload(DeadLetter.delivery))
            .order_by(desc(DeadLetter.failed_at))
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.scalars(stmt)
        return list(result.all())

    async def get_by_id(self, dead_letter_id: uuid.UUID) -> DeadLetter | None:
        return await self.session.get(DeadLetter, dead_letter_id)

    async def delete(self, dead_letter_id: uuid.UUID) -> None:
        dead_letter = await self.get_by_id(dead_letter_id)
        if dead_letter is not None:
            await self.session.delete(dead_letter)
            await self.session.flush()
