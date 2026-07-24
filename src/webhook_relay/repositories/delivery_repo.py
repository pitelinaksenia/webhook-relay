import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from webhook_relay.models.delivery import Delivery, DeliveryAttempt, DeliveryStatus


class DeliveryRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

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

    async def get_for_processing(self, delivery_id: uuid.UUID) -> Delivery | None:
        return await self.session.get(
            Delivery,
            delivery_id,
            options=[selectinload(Delivery.subscription), selectinload(Delivery.event)],
        )

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
