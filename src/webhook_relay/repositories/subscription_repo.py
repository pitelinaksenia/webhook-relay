import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from webhook_relay.models import Subscription
from webhook_relay.schemas.subscription import SubscriptionCreate


class SubscriptionRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def create(self, subscription_data: SubscriptionCreate) -> Subscription:
        subscription = Subscription(
            url=str(subscription_data.url),
            event_types=subscription_data.event_types,
            secret=subscription_data.secret,
        )
        self.session.add(subscription)
        await self.session.flush()
        return subscription

    async def get_all(self, limit: int, offset: int) -> list[Subscription]:
        stmt = select(Subscription).offset(offset).limit(limit)
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def get_by_id(self, subscription_id: uuid.UUID) -> Subscription | None:
        return await self.session.get(Subscription, subscription_id)

    async def delete_by_id(self, subscription_id: uuid.UUID) -> bool:
        subscription = await self.get_by_id(subscription_id)
        if subscription is None:
            return False

        await self.session.delete(subscription)
        await self.session.flush()
        return True

    async def get_active_by_event_type(self, event_type: str) -> list[Subscription]:
        stmt = select(Subscription).where(
            Subscription.is_active.is_(True),
            func.jsonb_exists(Subscription.event_types, event_type),
        )
        result = await self.session.scalars(stmt)
        return list(result.all())
