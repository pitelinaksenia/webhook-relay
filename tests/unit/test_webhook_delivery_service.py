import uuid
from unittest.mock import AsyncMock

import httpx
import pytest

from webhook_relay.config import settings
from webhook_relay.models.delivery import DeliveryStatus
from webhook_relay.security.hmac_signer import verify
from webhook_relay.services.webhook_delivery_service import WebhookDeliveryService


def make_response(status_code: int, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code,
        headers=headers or {},
        request=httpx.Request("POST", "http://mock-receiver/hook"),
    )


@pytest.fixture
def mocks():
    return {
        "session": AsyncMock(),
        "http_client": AsyncMock(spec=httpx.AsyncClient),
        "arq_redis": AsyncMock(),
        "delivery_repo": AsyncMock(),
        "dead_letter_repo": AsyncMock(),
    }


@pytest.fixture
def service(mocks):
    return WebhookDeliveryService(
        session=mocks["session"],
        http_client=mocks["http_client"],
        arq_redis=mocks["arq_redis"],
        delivery_repo=mocks["delivery_repo"],
        dead_letter_repo=mocks["dead_letter_repo"],
    )


class TestDeliverShortCircuits:
    async def test_missing_delivery_does_nothing(self, service, mocks):
        mocks["delivery_repo"].claim_for_processing.return_value = None

        await service.deliver(str(uuid.uuid4()))

        mocks["http_client"].post.assert_not_awaited()

    async def test_unclaimable_delivery_is_skipped(self, service, mocks):
        mocks["delivery_repo"].claim_for_processing.return_value = None

        await service.deliver(str(uuid.uuid4()))

        mocks["http_client"].post.assert_not_awaited()


class TestSuccessfulDelivery:
    async def test_2xx_marks_delivered(self, service, mocks, make_delivery):
        delivery = make_delivery(attempt_count=0)
        mocks["delivery_repo"].claim_for_processing.return_value = delivery
        mocks["http_client"].post.return_value = make_response(200)

        await service.deliver(str(delivery.id))

        mocks["delivery_repo"].update_status.assert_awaited_once()
        args, kwargs = mocks["delivery_repo"].update_status.call_args
        assert args[0] == delivery.id
        assert args[1] == DeliveryStatus.DELIVERED
        mocks["dead_letter_repo"].create.assert_not_awaited()
        mocks["arq_redis"].enqueue_job.assert_not_awaited()
        mocks["session"].commit.assert_awaited_once()

    async def test_records_attempt_with_http_status(self, service, mocks, make_delivery):
        delivery = make_delivery(attempt_count=2)
        mocks["delivery_repo"].claim_for_processing.return_value = delivery
        mocks["http_client"].post.return_value = make_response(200)

        await service.deliver(str(delivery.id))

        mocks["delivery_repo"].add_attempt.assert_awaited_once()
        call_kwargs = mocks["delivery_repo"].add_attempt.call_args.kwargs
        assert call_kwargs["delivery_id"] == delivery.id
        assert call_kwargs["attempt_number"] == 3
        assert call_kwargs["http_status"] == 200
        assert call_kwargs["error"] is None
        assert call_kwargs["duration_ms"] >= 0

    async def test_request_is_signed_and_includes_idempotency_key(
        self, service, mocks, make_delivery
    ):
        delivery = make_delivery(plain_secret="top-secret")
        mocks["delivery_repo"].claim_for_processing.return_value = delivery
        mocks["http_client"].post.return_value = make_response(200)

        await service.deliver(str(delivery.id))

        call = mocks["http_client"].post.call_args
        url = call.args[0]
        raw_body = call.kwargs["content"]
        headers = call.kwargs["headers"]

        assert url == delivery.subscription.url
        assert headers["X-Idempotency-Key"] == delivery.event.idempotency_key
        assert verify("top-secret", headers["X-Timestamp"], raw_body, headers["X-Signature"])


class TestFinalFailure:
    async def test_4xx_marks_failed_without_retry(self, service, mocks, make_delivery):
        delivery = make_delivery(attempt_count=0)
        mocks["delivery_repo"].claim_for_processing.return_value = delivery
        mocks["http_client"].post.return_value = make_response(404)

        await service.deliver(str(delivery.id))

        args, kwargs = mocks["delivery_repo"].update_status.call_args
        assert args[1] == DeliveryStatus.FAILED
        mocks["dead_letter_repo"].create.assert_awaited_once()
        mocks["arq_redis"].enqueue_job.assert_not_awaited()

    async def test_3xx_marks_failed_with_status_in_error(self, service, mocks, make_delivery):
        delivery = make_delivery(attempt_count=0)
        mocks["delivery_repo"].claim_for_processing.return_value = delivery
        mocks["http_client"].post.return_value = make_response(301)

        await service.deliver(str(delivery.id))

        add_attempt_kwargs = mocks["delivery_repo"].add_attempt.call_args.kwargs
        assert add_attempt_kwargs["error"] == "HTTP 301"

        args, kwargs = mocks["delivery_repo"].update_status.call_args
        assert args[1] == DeliveryStatus.FAILED
        assert kwargs["last_error"] == "HTTP 301"
        mocks["dead_letter_repo"].create.assert_awaited_once_with(delivery.id, "HTTP 301")


class TestRetryScheduling:
    async def test_5xx_schedules_retry_with_backoff(self, service, mocks, make_delivery):
        delivery = make_delivery(attempt_count=0)
        mocks["delivery_repo"].claim_for_processing.return_value = delivery
        mocks["http_client"].post.return_value = make_response(500)

        await service.deliver(str(delivery.id))

        args, kwargs = mocks["delivery_repo"].update_status.call_args
        assert args[1] == DeliveryStatus.RETRYING
        mocks["dead_letter_repo"].create.assert_not_awaited()

        mocks["arq_redis"].enqueue_job.assert_awaited_once()
        job_args, job_kwargs = mocks["arq_redis"].enqueue_job.call_args
        assert job_args == ("deliver_webhook", str(delivery.id))
        assert job_kwargs["_job_id"] == f"{delivery.id}:2"
        max_expected = min(
            settings.retry_base_delay * 1 + settings.retry_jitter, settings.retry_max_delay
        )
        assert 0 <= job_kwargs["_defer_by"] <= max_expected

    async def test_429_uses_retry_after_header_over_backoff(self, service, mocks, make_delivery):
        delivery = make_delivery(attempt_count=0)
        mocks["delivery_repo"].claim_for_processing.return_value = delivery
        mocks["http_client"].post.return_value = make_response(429, headers={"Retry-After": "42"})

        await service.deliver(str(delivery.id))

        job_kwargs = mocks["arq_redis"].enqueue_job.call_args.kwargs
        assert job_kwargs["_defer_by"] == 42.0

    async def test_retry_after_header_is_clamped_to_max_delay(self, service, mocks, make_delivery):
        delivery = make_delivery(attempt_count=0)
        mocks["delivery_repo"].claim_for_processing.return_value = delivery
        mocks["http_client"].post.return_value = make_response(
            429, headers={"Retry-After": "999999"}
        )

        await service.deliver(str(delivery.id))

        job_kwargs = mocks["arq_redis"].enqueue_job.call_args.kwargs
        assert job_kwargs["_defer_by"] == settings.retry_max_delay

    async def test_timeout_is_retried(self, service, mocks, make_delivery):
        delivery = make_delivery(attempt_count=0)
        mocks["delivery_repo"].claim_for_processing.return_value = delivery
        mocks["http_client"].post.side_effect = httpx.ConnectTimeout("timed out")

        await service.deliver(str(delivery.id))

        args, kwargs = mocks["delivery_repo"].update_status.call_args
        assert args[1] == DeliveryStatus.RETRYING
        mocks["arq_redis"].enqueue_job.assert_awaited_once()

    async def test_connection_error_is_retried(self, service, mocks, make_delivery):
        delivery = make_delivery(attempt_count=0)
        mocks["delivery_repo"].claim_for_processing.return_value = delivery
        mocks["http_client"].post.side_effect = httpx.ConnectError("refused")

        await service.deliver(str(delivery.id))

        args, kwargs = mocks["delivery_repo"].update_status.call_args
        assert args[1] == DeliveryStatus.RETRYING


class TestMaxAttemptsExhausted:
    async def test_last_allowed_attempt_failing_goes_to_dead_letter(
        self, service, mocks, make_delivery
    ):
        delivery = make_delivery(attempt_count=settings.retry_max_attempts - 1)
        mocks["delivery_repo"].claim_for_processing.return_value = delivery
        mocks["http_client"].post.return_value = make_response(500)

        await service.deliver(str(delivery.id))

        args, kwargs = mocks["delivery_repo"].update_status.call_args
        assert args[1] == DeliveryStatus.FAILED
        mocks["dead_letter_repo"].create.assert_awaited_once()
        mocks["arq_redis"].enqueue_job.assert_not_awaited()

    async def test_attempt_below_limit_still_retries(self, service, mocks, make_delivery):
        delivery = make_delivery(attempt_count=settings.retry_max_attempts - 2)
        mocks["delivery_repo"].claim_for_processing.return_value = delivery
        mocks["http_client"].post.return_value = make_response(500)

        await service.deliver(str(delivery.id))

        args, kwargs = mocks["delivery_repo"].update_status.call_args
        assert args[1] == DeliveryStatus.RETRYING
        mocks["dead_letter_repo"].create.assert_not_awaited()
