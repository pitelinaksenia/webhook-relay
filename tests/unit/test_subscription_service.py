import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from webhook_relay.exceptions import SubscriptionInUseError, SubscriptionNotFoundError
from webhook_relay.models.subscription import Subscription
from webhook_relay.schemas.subscription import SubscriptionCreate
from webhook_relay.security.hmac_signer import decrypt_secret
from webhook_relay.services.subscription_service import SubscriptionService


def make_subscription_create(**overrides) -> SubscriptionCreate:
    defaults = {
        "url": "http://mock-receiver/hook",
        "event_types": ["order.created"],
        "secret": "plain-secret",
    }
    defaults.update(overrides)
    return SubscriptionCreate(**defaults)


@pytest.fixture
def repos():
    return {"subscription_repo": AsyncMock(), "delivery_repo": AsyncMock()}


@pytest.fixture
def service(repos):
    return SubscriptionService(repos["subscription_repo"], repos["delivery_repo"])


class TestCreate:
    async def test_secret_is_encrypted_before_persisting(self, service, repos):
        repos["subscription_repo"].create.side_effect = lambda data: Subscription(
            id=uuid.uuid4(),
            url=str(data.url),
            event_types=data.event_types,
            secret=data.secret,
            is_active=True,
        )

        result = await service.create(make_subscription_create(secret="plain-secret"))

        persisted_data = repos["subscription_repo"].create.call_args.args[0]
        assert persisted_data.secret != "plain-secret"
        assert decrypt_secret(persisted_data.secret) == "plain-secret"
        assert decrypt_secret(result.secret) == "plain-secret"


class TestGet:
    async def test_returns_subscription_when_found(self, service, repos):
        sub_id = uuid.uuid4()
        subscription = Subscription(
            id=sub_id, url="http://x", event_types=["a"], secret="enc", is_active=True
        )
        repos["subscription_repo"].get_by_id.return_value = subscription

        result = await service.get(sub_id)

        assert result is subscription

    async def test_raises_not_found_when_missing(self, service, repos):
        sub_id = uuid.uuid4()
        repos["subscription_repo"].get_by_id.return_value = None

        with pytest.raises(SubscriptionNotFoundError):
            await service.get(sub_id)


class TestDelete:
    async def test_deletes_when_no_related_deliveries(self, service, repos):
        sub_id = uuid.uuid4()
        repos["subscription_repo"].delete_by_id.return_value = True

        await service.delete(sub_id)

        repos["subscription_repo"].delete_by_id.assert_awaited_once_with(sub_id)

    async def test_raises_not_found_when_nothing_deleted(self, service, repos):
        sub_id = uuid.uuid4()
        repos["subscription_repo"].delete_by_id.return_value = False

        with pytest.raises(SubscriptionNotFoundError):
            await service.delete(sub_id)

    async def test_raises_in_use_and_rolls_back_on_integrity_error(self, service, repos):
        sub_id = uuid.uuid4()
        repos["subscription_repo"].delete_by_id.side_effect = IntegrityError(
            "stmt", "params", Exception("fk violation")
        )

        with pytest.raises(SubscriptionInUseError):
            await service.delete(sub_id)

        repos["subscription_repo"].rollback.assert_awaited_once()


class TestGetDeliveries:
    async def test_raises_not_found_before_fetching_deliveries(self, service, repos):
        sub_id = uuid.uuid4()
        repos["subscription_repo"].get_by_id.return_value = None

        with pytest.raises(SubscriptionNotFoundError):
            await service.get_deliveries(sub_id, limit=20, offset=0)

        repos["delivery_repo"].get_by_subscription_id.assert_not_awaited()

    async def test_returns_deliveries_when_subscription_exists(self, service, repos):
        sub_id = uuid.uuid4()
        subscription = Subscription(
            id=sub_id, url="http://x", event_types=["a"], secret="enc", is_active=True
        )
        repos["subscription_repo"].get_by_id.return_value = subscription
        repos["delivery_repo"].get_by_subscription_id.return_value = ["d1", "d2"]

        result = await service.get_deliveries(sub_id, limit=20, offset=0)

        assert result == ["d1", "d2"]
        repos["delivery_repo"].get_by_subscription_id.assert_awaited_once_with(
            sub_id, limit=20, offset=0
        )
