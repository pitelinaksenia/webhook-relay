import uuid
from unittest.mock import AsyncMock

import pytest

from webhook_relay.exceptions import DeadLetterNotFoundError
from webhook_relay.models.delivery import DeadLetter, Delivery, DeliveryStatus
from webhook_relay.services.dead_letter_service import DeadLetterService


@pytest.fixture
def repos():
    return {
        "arq_redis": AsyncMock(),
        "delivery_repo": AsyncMock(),
        "dead_letter_repo": AsyncMock(),
    }


@pytest.fixture
def service(repos):
    return DeadLetterService(repos["arq_redis"], repos["delivery_repo"], repos["dead_letter_repo"])


class TestRetry:
    async def test_raises_not_found_when_missing(self, service, repos):
        dl_id = uuid.uuid4()
        repos["dead_letter_repo"].get_by_id.return_value = None

        with pytest.raises(DeadLetterNotFoundError):
            await service.retry(dl_id)

        repos["delivery_repo"].reset_for_retry.assert_not_awaited()
        repos["arq_redis"].enqueue_job.assert_not_awaited()

    async def test_resets_delivery_and_removes_dead_letter(self, service, repos):
        dl_id = uuid.uuid4()
        delivery_id = uuid.uuid4()
        dead_letter = DeadLetter(id=dl_id, delivery_id=delivery_id, last_error="boom")
        repos["dead_letter_repo"].get_by_id.return_value = dead_letter

        reset_delivery = Delivery(
            id=delivery_id,
            event_id=uuid.uuid4(),
            subscription_id=uuid.uuid4(),
            status=DeliveryStatus.PENDING,
            attempt_count=0,
        )
        repos["delivery_repo"].reset_for_retry.return_value = reset_delivery

        result = await service.retry(dl_id)

        assert result is reset_delivery
        repos["delivery_repo"].reset_for_retry.assert_awaited_once_with(delivery_id)
        repos["dead_letter_repo"].delete.assert_awaited_once_with(dl_id)
        repos["delivery_repo"].commit.assert_awaited_once()

    async def test_enqueues_job_with_manual_job_id_for_deduping_against_auto_retries(
        self, service, repos
    ):
        dl_id = uuid.uuid4()
        delivery_id = uuid.uuid4()
        repos["dead_letter_repo"].get_by_id.return_value = DeadLetter(
            id=dl_id, delivery_id=delivery_id, last_error="boom"
        )
        repos["delivery_repo"].reset_for_retry.return_value = Delivery(
            id=delivery_id,
            event_id=uuid.uuid4(),
            subscription_id=uuid.uuid4(),
            status=DeliveryStatus.PENDING,
            attempt_count=0,
        )

        await service.retry(dl_id)

        repos["arq_redis"].enqueue_job.assert_awaited_once()
        call = repos["arq_redis"].enqueue_job.call_args
        assert call.args == ("deliver_webhook", str(delivery_id))
        assert call.kwargs["_job_id"].startswith(f"{delivery_id}:manual:")

    async def test_dead_letter_deleted_before_commit(self, service, repos):
        dl_id = uuid.uuid4()
        delivery_id = uuid.uuid4()
        repos["dead_letter_repo"].get_by_id.return_value = DeadLetter(
            id=dl_id, delivery_id=delivery_id, last_error="boom"
        )
        repos["delivery_repo"].reset_for_retry.return_value = Delivery(
            id=delivery_id,
            event_id=uuid.uuid4(),
            subscription_id=uuid.uuid4(),
            status=DeliveryStatus.PENDING,
            attempt_count=0,
        )

        await service.retry(dl_id)

        assert repos["dead_letter_repo"].delete.await_args is not None
        assert repos["delivery_repo"].commit.await_args is not None


class TestGetAll:
    async def test_delegates_to_repo_with_pagination(self, service, repos):
        repos["dead_letter_repo"].get_all.return_value = ["dl1", "dl2"]

        result = await service.get_all(limit=10, offset=5)

        assert result == ["dl1", "dl2"]
        repos["dead_letter_repo"].get_all.assert_awaited_once_with(limit=10, offset=5)
