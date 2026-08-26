import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from webhook_relay.models.delivery import Delivery, DeliveryAttempt, DeliveryStatus
from webhook_relay.models.event import Event


class DeliveryRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def create_many(
        self, event_id: uuid.UUID, subscription_ids: list[uuid.UUID]
    ) -> list[Delivery]:
        result = []
        for sub_id in subscription_ids:
            new_delivery = Delivery(
                event_id=event_id,
                subscription_id=sub_id,
                status=DeliveryStatus.PENDING,
            )
            result.append(new_delivery)
        self.session.add_all(result)
        await self.session.flush()
        return result

    async def get_by_id(self, delivery_id: uuid.UUID) -> Delivery | None:
        return await self.session.get(Delivery, delivery_id)

    async def claim_for_processing(self, delivery_id: uuid.UUID) -> Delivery | None:
        stmt = (
            select(Delivery)
            .where(
                Delivery.id == delivery_id,
                Delivery.status.not_in(
                    [DeliveryStatus.DELIVERED, DeliveryStatus.FAILED, DeliveryStatus.IN_PROGRESS]
                ),
            )
            .options(selectinload(Delivery.subscription), selectinload(Delivery.event))
            .with_for_update(skip_locked=True)
        )
        delivery = (await self.session.scalars(stmt)).first()
        if delivery is None:
            return None

        delivery.status = DeliveryStatus.IN_PROGRESS
        await self.session.flush()
        return delivery

    async def get_by_subscription_id(
        self, subscription_id: uuid.UUID, limit: int = 20, offset: int = 0
    ) -> list[Delivery]:
        stmt = (
            select(Delivery)
            .where(Delivery.subscription_id == subscription_id)
            .order_by(Delivery.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.scalars(stmt)
        return list(result.all())

    async def get_all(
        self,
        status: DeliveryStatus | None = None,
        event_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Delivery]:
        stmt = (
            select(Delivery)
            .options(selectinload(Delivery.subscription), selectinload(Delivery.event))
            .order_by(Delivery.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(Delivery.status == status)
        if event_type is not None:
            stmt = stmt.join(Event, Event.id == Delivery.event_id).where(
                Event.event_type == event_type
            )

        result = await self.session.scalars(stmt)
        return list(result.all())

    async def count(
        self,
        status: DeliveryStatus | None = None,
        event_type: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(Delivery)
        if status is not None:
            stmt = stmt.where(Delivery.status == status)
        if event_type is not None:
            stmt = stmt.join(Event, Event.id == Delivery.event_id).where(
                Event.event_type == event_type
            )

        return (await self.session.scalars(stmt)).one()

    async def get_with_attempts(self, delivery_id: uuid.UUID) -> Delivery | None:
        stmt = (
            select(Delivery)
            .where(Delivery.id == delivery_id)
            .options(
                selectinload(Delivery.subscription),
                selectinload(Delivery.event),
                selectinload(Delivery.attempts),
                selectinload(Delivery.dead_letter),
            )
        )
        return (await self.session.scalars(stmt)).first()

    async def stats_since(self, since: datetime) -> dict[DeliveryStatus, int]:
        stmt = (
            select(Delivery.status, func.count())
            .where(Delivery.created_at >= since)
            .group_by(Delivery.status)
        )
        result = await self.session.execute(stmt)
        return {status: count for status, count in result.all()}

    async def update_status(
        self,
        delivery_id: uuid.UUID,
        status: DeliveryStatus,
        last_error: str | None = None,
        next_attempt_at: datetime | None = None,
    ) -> Delivery | None:
        delivery = await self.get_by_id(delivery_id)
        if delivery is None:
            return None

        delivery.status = status
        delivery.attempt_count += 1
        delivery.last_error = last_error
        delivery.next_attempt_at = next_attempt_at

        await self.session.flush()
        return delivery

    async def add_attempt(
        self,
        delivery_id: uuid.UUID,
        attempt_number: int,
        http_status: int | None,
        duration_ms: int,
        error: str | None = None,
    ) -> DeliveryAttempt:
        new_attempt = DeliveryAttempt(
            delivery_id=delivery_id,
            attempt_number=attempt_number,
            http_status=http_status,
            duration_ms=duration_ms,
            error=error,
        )
        self.session.add(new_attempt)
        await self.session.flush()

        return new_attempt

    async def reset_for_retry(self, delivery_id: uuid.UUID) -> Delivery | None:
        delivery = await self.get_by_id(delivery_id)
        if delivery is None:
            return None

        delivery.status = DeliveryStatus.PENDING
        delivery.attempt_count = 0
        delivery.last_error = None
        delivery.next_attempt_at = None

        await self.session.flush()
        return delivery
