import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import monotonic, time

import httpx
from arq import ArqRedis
from cryptography.fernet import InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession

from webhook_relay.config import settings
from webhook_relay.core.retry_policy import (
    DeliveryOutcome,
    classify_response,
    compute_backoff,
    parse_retry_after,
)
from webhook_relay.models.delivery import Delivery, DeliveryStatus
from webhook_relay.repositories.dead_letter_repo import DeadLetterRepo
from webhook_relay.repositories.delivery_repo import DeliveryRepo
from webhook_relay.security.hmac_signer import decrypt_secret, sign

logger = logging.getLogger(__name__)


@dataclass
class AttemptResult:
    status_code: int | None
    error: str | None
    is_timeout: bool
    is_connection_error: bool
    retry_after_header: str | None
    duration_ms: int


class WebhookDeliveryService:
    def __init__(
        self,
        session: AsyncSession,
        http_client: httpx.AsyncClient,
        arq_redis: ArqRedis,
        delivery_repo: DeliveryRepo,
        dead_letter_repo: DeadLetterRepo,
    ):
        self.session = session
        self.http_client = http_client
        self.arq_redis = arq_redis
        self.delivery_repo = delivery_repo
        self.dead_letter_repo = dead_letter_repo

    async def deliver(self, delivery_id: str) -> None:
        delivery = await self.delivery_repo.claim_for_processing(uuid.UUID(delivery_id))
        if delivery is None:
            return

        attempt_result = await self._send_request(delivery)

        await self.delivery_repo.add_attempt(
            delivery_id=delivery.id,
            attempt_number=delivery.attempt_count + 1,
            http_status=attempt_result.status_code,
            duration_ms=attempt_result.duration_ms,
            error=attempt_result.error,
        )

        await self._finalize(delivery, attempt_result)

    async def _send_request(self, delivery: Delivery) -> AttemptResult:
        event = delivery.event
        subscription = delivery.subscription

        timestamp = str(int(time()))
        raw_body = json.dumps(event.payload, separators=(",", ":")).encode()

        try:
            secret = decrypt_secret(subscription.secret)
            signature = sign(secret, timestamp, raw_body)
        except InvalidToken:
            logger.error(
                "delivery %s: failed to decrypt secret for subscription %s",
                delivery.id,
                subscription.id,
            )
            return AttemptResult(
                status_code=None,
                error="secret decryption failed",
                is_timeout=False,
                is_connection_error=False,
                retry_after_header=None,
                duration_ms=0,
            )

        headers = {
            "Content-Type": "application/json",
            "X-Signature": signature,
            "X-Timestamp": timestamp,
            "X-Idempotency-Key": event.idempotency_key,
        }

        status_code: int | None = None
        error: str | None = None
        is_timeout = False
        is_connection_error = False
        retry_after_header: str | None = None

        started_at = monotonic()
        try:
            response = await self.http_client.post(
                subscription.url, content=raw_body, headers=headers
            )
            status_code = response.status_code
            retry_after_header = response.headers.get("Retry-After")
            if not (200 <= status_code < 300):
                error = f"HTTP {status_code}"
        except httpx.TimeoutException as exc:
            is_timeout = True
            error = str(exc)
        except httpx.RequestError as exc:
            is_connection_error = True
            error = str(exc)

        duration_ms = int((monotonic() - started_at) * 1000)

        return AttemptResult(
            status_code=status_code,
            error=error,
            is_timeout=is_timeout,
            is_connection_error=is_connection_error,
            retry_after_header=retry_after_header,
            duration_ms=duration_ms,
        )

    async def _finalize(self, delivery: Delivery, attempt_result: AttemptResult) -> None:
        outcome = classify_response(
            attempt_result.status_code,
            is_timeout=attempt_result.is_timeout,
            is_connection_error=attempt_result.is_connection_error,
        )

        if outcome == DeliveryOutcome.DELIVERED:
            logger.info(
                "delivery %s delivered on attempt %s", delivery.id, delivery.attempt_count + 1
            )
            await self.delivery_repo.update_status(delivery.id, DeliveryStatus.DELIVERED)
            await self.session.commit()
            return

        attempt_number = delivery.attempt_count + 1
        limit_reached = attempt_number >= settings.retry_max_attempts

        if outcome == DeliveryOutcome.FAILED_FINAL or limit_reached:
            reason = attempt_result.error or (
                "final failure"
                if outcome == DeliveryOutcome.FAILED_FINAL
                else "max attempts exceeded"
            )
            logger.warning(
                "delivery %s failed permanently after %s attempt(s): %s",
                delivery.id,
                attempt_number,
                reason,
            )
            await self.delivery_repo.update_status(
                delivery.id, DeliveryStatus.FAILED, last_error=reason
            )
            await self.dead_letter_repo.create(delivery.id, reason)
            await self.session.commit()
            return

        await self._schedule_retry(delivery, attempt_result, attempt_number)

    async def _schedule_retry(
        self, delivery: Delivery, attempt_result: AttemptResult, attempt_number: int
    ) -> None:
        delay = parse_retry_after(attempt_result.retry_after_header)
        if delay is None:
            delay = compute_backoff(
                attempt_number,
                settings.retry_base_delay,
                settings.retry_max_delay,
                settings.retry_jitter,
            )
        else:
            delay = min(delay, settings.retry_max_delay)

        next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)

        logger.info(
            "delivery %s scheduled for retry #%s in %.1fs (reason: %s)",
            delivery.id,
            attempt_number + 1,
            delay,
            attempt_result.error,
        )

        await self.delivery_repo.update_status(
            delivery.id,
            DeliveryStatus.RETRYING,
            last_error=attempt_result.error,
            next_attempt_at=next_attempt_at,
        )
        await self.session.commit()

        try:
            job = await self.arq_redis.enqueue_job(
                "deliver_webhook",
                str(delivery.id),
                _defer_by=delay,
                _job_id=f"{delivery.id}:{attempt_number + 1}",
            )
            if job is None:
                logger.error(
                    "retry job for delivery %s (attempt #%s) was not enqueued: "
                    "a job with the same id already exists",
                    delivery.id,
                    attempt_number + 1,
                )
        except Exception:
            logger.exception("failed to enqueue retry for delivery %s", delivery.id)
            raise
