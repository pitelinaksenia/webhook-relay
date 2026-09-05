import logging
import uuid

from arq import ArqRedis
from sqlalchemy.orm import attributes

from webhook_relay.exceptions import EventNotFoundError
from webhook_relay.models import Event
from webhook_relay.repositories.delivery_repo import DeliveryRepo
from webhook_relay.repositories.event_repo import EventRepo
from webhook_relay.repositories.subscription_repo import SubscriptionRepo
from webhook_relay.schemas.event import EventCreate

logger = logging.getLogger(__name__)


class EventService:
    def __init__(
        self,
        event_repo: EventRepo,
        subscription_repo: SubscriptionRepo,
        delivery_repo: DeliveryRepo,
        arq_pool: ArqRedis,
    ):
        self.event_repo = event_repo
        self.subscription_repo = subscription_repo
        self.delivery_repo = delivery_repo
        self.arq_pool = arq_pool

    async def create(self, event_data: EventCreate) -> Event:
        event = await self.event_repo.create(event_data)
        if event is None:
            return await self.event_repo.get_by_idempotency_key(event_data.idempotency_key)

        subscriptions = await self.subscription_repo.get_active_by_event_type(event.event_type)
        subscription_ids = [sub.id for sub in subscriptions]
        deliveries = await self.delivery_repo.create_many(event.id, subscription_ids)
        attributes.set_committed_value(event, "deliveries", deliveries)
        await self.event_repo.commit()

        failed_delivery_ids = []
        for delivery in deliveries:
            try:
                await self.arq_pool.enqueue_job(
                    "deliver_webhook", str(delivery.id), _job_id=f"{delivery.id}:1"
                )
            except Exception:
                logger.exception(
                    "failed to enqueue delivery %s for event %s", delivery.id, event.id
                )
                failed_delivery_ids.append(delivery.id)

        if failed_delivery_ids:
            raise RuntimeError(
                f"failed to enqueue {len(failed_delivery_ids)} of {len(deliveries)} "
                f"deliveries for event {event.id}: {failed_delivery_ids}"
            )

        return event

    async def get_by_id(self, event_id: uuid.UUID) -> Event:
        event = await self.event_repo.get_by_id(event_id)
        if event is None:
            raise EventNotFoundError(event_id)
        return event
