from datetime import UTC, datetime

import httpx
import respx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.conftest import seed_event, seed_subscription
from webhook_relay.config import settings
from webhook_relay.models import Event, Subscription
from webhook_relay.models.delivery import Delivery, DeliveryAttempt, DeliveryStatus
from webhook_relay.repositories.dead_letter_repo import DeadLetterRepo
from webhook_relay.repositories.delivery_repo import DeliveryRepo
from webhook_relay.services.dead_letter_service import DeadLetterService
from webhook_relay.services.webhook_delivery_service import WebhookDeliveryService

RECEIVER_URL = "http://mock-receiver/hook"


async def seed_delivery(db_session, attempt_count: int = 0) -> Delivery:
    subscription = await seed_subscription(db_session, url=RECEIVER_URL)
    event = await seed_event(db_session)
    delivery = Delivery(
        event_id=event.id,
        subscription_id=subscription.id,
        status=DeliveryStatus.PENDING,
        attempt_count=attempt_count,
    )
    db_session.add(delivery)
    await db_session.flush()
    db_session.expunge(delivery)
    return delivery


def make_service(db_session, arq_redis) -> WebhookDeliveryService:
    return WebhookDeliveryService(
        session=db_session,
        http_client=httpx.AsyncClient(),
        arq_redis=arq_redis,
        delivery_repo=DeliveryRepo(db_session),
        dead_letter_repo=DeadLetterRepo(db_session),
    )


class TestHappyPath:
    async def test_2xx_marks_delivered_and_logs_attempt(self, db_session, arq_redis):
        delivery = await seed_delivery(db_session)
        service = make_service(db_session, arq_redis)

        with respx.mock:
            respx.post(RECEIVER_URL).mock(return_value=httpx.Response(200))
            await service.deliver(str(delivery.id))

        refreshed = await DeliveryRepo(db_session).get_by_id(delivery.id)
        assert refreshed.status == DeliveryStatus.DELIVERED
        assert refreshed.attempt_count == 1

        attempts = (
            await db_session.scalars(
                select(DeliveryAttempt).where(DeliveryAttempt.delivery_id == delivery.id)
            )
        ).all()
        assert len(attempts) == 1
        assert attempts[0].http_status == 200


class TestRetryThenSuccess:
    async def test_two_failures_then_success_across_three_worker_runs(self, db_session, arq_redis):
        delivery = await seed_delivery(db_session)
        service = make_service(db_session, arq_redis)

        with respx.mock:
            route = respx.post(RECEIVER_URL)
            route.side_effect = [
                httpx.Response(500),
                httpx.Response(500),
                httpx.Response(200),
            ]

            await service.deliver(str(delivery.id))
            refreshed = await DeliveryRepo(db_session).get_by_id(delivery.id)
            assert refreshed.status == DeliveryStatus.RETRYING
            assert refreshed.attempt_count == 1
            db_session.expunge_all()

            await service.deliver(str(delivery.id))
            refreshed = await DeliveryRepo(db_session).get_by_id(delivery.id)
            assert refreshed.status == DeliveryStatus.RETRYING
            assert refreshed.attempt_count == 2
            db_session.expunge_all()

            await service.deliver(str(delivery.id))
            refreshed = await DeliveryRepo(db_session).get_by_id(delivery.id)
            assert refreshed.status == DeliveryStatus.DELIVERED
            assert refreshed.attempt_count == 3


class TestFinalFailure:
    async def test_4xx_marks_failed_and_writes_dead_letter(self, db_session, arq_redis):
        delivery = await seed_delivery(db_session)
        service = make_service(db_session, arq_redis)

        with respx.mock:
            respx.post(RECEIVER_URL).mock(return_value=httpx.Response(404))
            await service.deliver(str(delivery.id))

        refreshed = await DeliveryRepo(db_session).get_by_id(delivery.id)
        assert refreshed.status == DeliveryStatus.FAILED

        dead_letters = await DeadLetterRepo(db_session).get_all()
        assert len(dead_letters) == 1
        assert dead_letters[0].delivery_id == delivery.id


class TestRetryAfterHeader:
    async def test_429_schedules_next_attempt_from_retry_after_header(self, db_session, arq_redis):
        delivery = await seed_delivery(db_session)
        service = make_service(db_session, arq_redis)

        with respx.mock:
            respx.post(RECEIVER_URL).mock(
                return_value=httpx.Response(429, headers={"Retry-After": "5"})
            )
            await service.deliver(str(delivery.id))

        refreshed = await DeliveryRepo(db_session).get_by_id(delivery.id)
        assert refreshed.status == DeliveryStatus.RETRYING
        assert refreshed.next_attempt_at is not None

        delay = (refreshed.next_attempt_at - datetime.now(UTC)).total_seconds()
        assert 0 <= delay <= 5


class TestMaxAttemptsExhausted:
    async def test_last_allowed_attempt_failing_goes_to_dead_letter(self, db_session, arq_redis):
        delivery = await seed_delivery(db_session, attempt_count=settings.retry_max_attempts - 1)
        service = make_service(db_session, arq_redis)

        with respx.mock:
            respx.post(RECEIVER_URL).mock(return_value=httpx.Response(500))
            await service.deliver(str(delivery.id))

        refreshed = await DeliveryRepo(db_session).get_by_id(delivery.id)
        assert refreshed.status == DeliveryStatus.FAILED

        dead_letters = await DeadLetterRepo(db_session).get_all()
        assert len(dead_letters) == 1


class TestConcurrentClaim:
    async def test_second_worker_cannot_claim_a_locked_delivery(self, db_engine):
        # Seed on a committed, independent connection so a second connection can see it.
        async with AsyncSession(db_engine, expire_on_commit=False) as setup_session:
            subscription = await seed_subscription(setup_session, url=RECEIVER_URL)
            event = await seed_event(setup_session)
            delivery = Delivery(
                event_id=event.id,
                subscription_id=subscription.id,
                status=DeliveryStatus.PENDING,
            )
            setup_session.add(delivery)
            await setup_session.commit()
            delivery_id, event_id, subscription_id = delivery.id, event.id, subscription.id

        conn_a = await db_engine.connect()
        txn_a = await conn_a.begin()
        session_a = AsyncSession(bind=conn_a, expire_on_commit=False)

        conn_b = await db_engine.connect()
        txn_b = await conn_b.begin()
        session_b = AsyncSession(bind=conn_b, expire_on_commit=False)

        try:
            claimed_a = await DeliveryRepo(session_a).claim_for_processing(delivery_id)
            assert claimed_a is not None
            assert claimed_a.status == DeliveryStatus.IN_PROGRESS

            claimed_b = await DeliveryRepo(session_b).claim_for_processing(delivery_id)
            assert claimed_b is None
        finally:
            await session_a.close()
            await txn_a.rollback()
            await conn_a.close()

            await session_b.close()
            await txn_b.rollback()
            await conn_b.close()

            async with AsyncSession(db_engine, expire_on_commit=False) as cleanup:
                await cleanup.execute(delete(Delivery).where(Delivery.id == delivery_id))
                await cleanup.execute(delete(Event).where(Event.id == event_id))
                await cleanup.execute(
                    delete(Subscription).where(Subscription.id == subscription_id)
                )
                await cleanup.commit()


class TestManualRetryFromDeadLetter:
    async def test_retry_resets_delivery_and_enqueues_new_job(self, db_session, arq_redis):
        delivery = await seed_delivery(db_session, attempt_count=settings.retry_max_attempts - 1)
        service = make_service(db_session, arq_redis)

        with respx.mock:
            respx.post(RECEIVER_URL).mock(return_value=httpx.Response(500))
            await service.deliver(str(delivery.id))

        dead_letter_repo = DeadLetterRepo(db_session)
        delivery_repo = DeliveryRepo(db_session)
        dead_letters = await dead_letter_repo.get_all()
        assert len(dead_letters) == 1
        dead_letter_id = dead_letters[0].id

        dead_letter_service = DeadLetterService(arq_redis, delivery_repo, dead_letter_repo)
        result = await dead_letter_service.retry(dead_letter_id)

        assert result.status == DeliveryStatus.PENDING
        assert result.attempt_count == 0
        assert await dead_letter_repo.get_by_id(dead_letter_id) is None
