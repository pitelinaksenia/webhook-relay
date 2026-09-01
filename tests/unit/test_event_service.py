import uuid
from unittest.mock import AsyncMock

from webhook_relay.models import Event
from webhook_relay.schemas.event import EventCreate
from webhook_relay.services.event_service import EventService


def make_event_create(**overrides) -> EventCreate:
    defaults = {
        "event_type": "order.created",
        "payload": {"foo": "bar"},
        "idempotency_key": "idem-key-1",
    }
    defaults.update(overrides)
    return EventCreate(**defaults)


class TestEventServiceCreate:
    async def _make_service(self):
        event_repo = AsyncMock()
        subscription_repo = AsyncMock()
        delivery_repo = AsyncMock()
        arq_pool = AsyncMock()
        service = EventService(event_repo, subscription_repo, delivery_repo, arq_pool)
        return service, event_repo, subscription_repo, delivery_repo, arq_pool

    async def test_duplicate_idempotency_key_returns_existing_event_without_creating(self):
        service, event_repo, subscription_repo, delivery_repo, arq_pool = (
            await self._make_service()
        )
        existing_event = Event(
            id=uuid.uuid4(),
            event_type="order.created",
            payload={"foo": "bar"},
            idempotency_key="idem-key-1",
        )
        event_repo.create.return_value = None
        event_repo.get_by_idempotency_key.return_value = existing_event

        result = await service.create(make_event_create())

        assert result is existing_event
        event_repo.get_by_idempotency_key.assert_awaited_once_with("idem-key-1")
        subscription_repo.get_active_by_event_type.assert_not_awaited()
        delivery_repo.create_many.assert_not_awaited()
        arq_pool.enqueue_job.assert_not_awaited()

    async def test_new_event_creates_delivery_per_active_subscription(self):
        service, event_repo, subscription_repo, delivery_repo, arq_pool = (
            await self._make_service()
        )
        event_repo.get_by_idempotency_key.return_value = None
        new_event = Event(
            id=uuid.uuid4(),
            event_type="order.created",
            payload={"foo": "bar"},
            idempotency_key="idem-key-1",
        )
        event_repo.create.return_value = new_event

        sub_id_a, sub_id_b = uuid.uuid4(), uuid.uuid4()
        subscription_repo.get_active_by_event_type.return_value = [
            type("Sub", (), {"id": sub_id_a})(),
            type("Sub", (), {"id": sub_id_b})(),
        ]

        delivery_a = type("Delivery", (), {"id": uuid.uuid4()})()
        delivery_b = type("Delivery", (), {"id": uuid.uuid4()})()
        delivery_repo.create_many.return_value = [delivery_a, delivery_b]

        result = await service.create(make_event_create())

        assert result is new_event
        delivery_repo.create_many.assert_awaited_once_with(new_event.id, [sub_id_a, sub_id_b])
        event_repo.commit.assert_awaited_once()

        assert arq_pool.enqueue_job.await_count == 2
        enqueued_ids = {call.args[1] for call in arq_pool.enqueue_job.await_args_list}
        assert enqueued_ids == {str(delivery_a.id), str(delivery_b.id)}

        job_ids = {call.kwargs["_job_id"] for call in arq_pool.enqueue_job.await_args_list}
        assert job_ids == {f"{delivery_a.id}:1", f"{delivery_b.id}:1"}

    async def test_no_matching_subscriptions_creates_event_without_deliveries(self):
        service, event_repo, subscription_repo, delivery_repo, arq_pool = (
            await self._make_service()
        )
        event_repo.get_by_idempotency_key.return_value = None
        new_event = Event(
            id=uuid.uuid4(),
            event_type="order.created",
            payload={"foo": "bar"},
            idempotency_key="idem-key-1",
        )
        event_repo.create.return_value = new_event
        subscription_repo.get_active_by_event_type.return_value = []
        delivery_repo.create_many.return_value = []

        result = await service.create(make_event_create())

        assert result is new_event
        delivery_repo.create_many.assert_awaited_once_with(new_event.id, [])
        arq_pool.enqueue_job.assert_not_awaited()
