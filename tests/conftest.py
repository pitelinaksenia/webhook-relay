import uuid
from collections.abc import Callable

import pytest

from webhook_relay.models.delivery import Delivery, DeliveryStatus
from webhook_relay.models.event import Event
from webhook_relay.models.subscription import Subscription
from webhook_relay.security.hmac_signer import encrypt_secret

DeliveryFactory = Callable[..., Delivery]


@pytest.fixture
def make_delivery() -> DeliveryFactory:

    def _make(
        attempt_count: int = 0,
        status: DeliveryStatus = DeliveryStatus.PENDING,
        url: str = "http://mock-receiver/hook",
        plain_secret: str = "whsec_test_secret",
        event_type: str = "order.created",
        payload: dict | None = None,
        idempotency_key: str | None = None,
    ) -> Delivery:
        subscription = Subscription(
            id=uuid.uuid4(),
            url=url,
            event_types=[event_type],
            secret=encrypt_secret(plain_secret),
            is_active=True,
        )
        event = Event(
            id=uuid.uuid4(),
            event_type=event_type,
            payload=payload if payload is not None else {"foo": "bar"},
            idempotency_key=idempotency_key or str(uuid.uuid4()),
        )
        delivery = Delivery(
            id=uuid.uuid4(),
            event_id=event.id,
            subscription_id=subscription.id,
            status=status,
            attempt_count=attempt_count,
        )
        delivery.event = event
        delivery.subscription = subscription
        return delivery

    return _make
