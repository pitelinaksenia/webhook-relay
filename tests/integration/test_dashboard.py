import httpx
import respx

from tests.integration.conftest import seed_event, seed_subscription
from webhook_relay.models.delivery import Delivery, DeliveryStatus
from webhook_relay.repositories.dead_letter_repo import DeadLetterRepo
from webhook_relay.repositories.delivery_repo import DeliveryRepo
from webhook_relay.services.webhook_delivery_service import WebhookDeliveryService

RECEIVER_URL = "http://mock-receiver/hook"


async def seed_delivery(db_session, status: DeliveryStatus = DeliveryStatus.PENDING) -> Delivery:
    subscription = await seed_subscription(db_session, url=RECEIVER_URL)
    event = await seed_event(db_session)
    delivery = Delivery(
        event_id=event.id,
        subscription_id=subscription.id,
        status=status,
    )
    db_session.add(delivery)
    await db_session.flush()
    return delivery


class TestOverview:
    async def test_renders_delivery_from_db(self, client, db_session):
        delivery = await seed_delivery(db_session)

        response = await client.get("/dashboard/")

        assert response.status_code == 200
        assert str(delivery.id) in response.text

    async def test_filters_by_status(self, client, db_session):
        await seed_delivery(db_session, status=DeliveryStatus.PENDING)
        delivered = await seed_delivery(db_session, status=DeliveryStatus.DELIVERED)

        response = await client.get("/dashboard/deliveries", params={"status": "delivered"})

        assert response.status_code == 200
        assert str(delivered.id) in response.text


class TestDeliveryDetail:
    async def test_returns_delivery_with_attempts(self, client, db_session):
        delivery = await seed_delivery(db_session)

        response = await client.get(f"/dashboard/deliveries/{delivery.id}")

        assert response.status_code == 200
        assert str(delivery.id) in response.text

    async def test_unknown_delivery_returns_404(self, client):
        import uuid

        response = await client.get(f"/dashboard/deliveries/{uuid.uuid4()}")

        assert response.status_code == 404


class TestDeadLettersPage:
    async def test_retry_removes_dead_letter_and_resets_delivery(
        self, client, db_session, arq_redis
    ):
        delivery = await seed_delivery(db_session)
        service = WebhookDeliveryService(
            session=db_session,
            http_client=httpx.AsyncClient(),
            arq_redis=arq_redis,
            delivery_repo=DeliveryRepo(db_session),
            dead_letter_repo=DeadLetterRepo(db_session),
        )
        with respx.mock:
            respx.post(RECEIVER_URL).mock(return_value=httpx.Response(404))
            await service.deliver(str(delivery.id))

        dead_letters = await DeadLetterRepo(db_session).get_all()
        assert len(dead_letters) == 1
        dead_letter_id = dead_letters[0].id

        page = await client.get("/dashboard/dead-letters")
        assert str(dead_letter_id) in page.text or str(delivery.id) in page.text

        retry_response = await client.post(f"/dashboard/dead-letters/{dead_letter_id}/retry")
        assert retry_response.status_code == 200

        refreshed = await DeliveryRepo(db_session).get_by_id(delivery.id)
        assert refreshed.status == DeliveryStatus.PENDING
        assert await DeadLetterRepo(db_session).get_by_id(dead_letter_id) is None


class TestSubscriptionsPage:
    async def test_create_and_delete_subscription_via_form(self, client):
        create_response = await client.post(
            "/dashboard/subscriptions",
            data={
                "url": "http://mock-receiver/hook",
                "event_types": "order.created, order.updated",
                "secret": "top-secret",
            },
        )

        assert create_response.status_code == 200
        assert "http://mock-receiver/hook" in create_response.text

        list_response = await client.get("/dashboard/subscriptions")
        assert "http://mock-receiver/hook" in list_response.text

        api_response = await client.get("/subscriptions/")
        subscription_id = api_response.json()[0]["id"]

        delete_response = await client.post(f"/dashboard/subscriptions/{subscription_id}/delete")
        assert delete_response.status_code == 200

        list_after = await client.get("/dashboard/subscriptions")
        assert "http://mock-receiver/hook" not in list_after.text

    async def test_toggle_active(self, client, db_session):
        subscription = await seed_subscription(db_session)

        deactivate_response = await client.post(
            f"/dashboard/subscriptions/{subscription.id}/deactivate"
        )
        assert deactivate_response.status_code == 200
        assert ">Activate<" in deactivate_response.text

        activate_response = await client.post(
            f"/dashboard/subscriptions/{subscription.id}/activate"
        )
        assert activate_response.status_code == 200
        assert ">Deactivate<" in activate_response.text

    async def test_delete_with_deliveries_returns_row_with_error_instead_of_500(
        self, client, db_session
    ):
        subscription = await seed_subscription(db_session, event_types=["order.created"])
        await client.post("/events/", json={"event_type": "order.created", "payload": {}})

        response = await client.post(f"/dashboard/subscriptions/{subscription.id}/delete")

        assert response.status_code == 200
        assert "Deactivate it instead" in response.text
        assert f'id="sub-{subscription.id}"' in response.text
