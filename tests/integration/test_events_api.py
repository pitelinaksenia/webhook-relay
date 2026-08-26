import uuid

from tests.integration.conftest import seed_subscription


class TestCreateEvent:
    async def test_happy_path_creates_delivery_for_matching_subscription(self, client, db_session):
        await seed_subscription(db_session, event_types=["order.created"])

        response = await client.post(
            "/events/",
            json={"event_type": "order.created", "payload": {"amount": 10}},
        )

        assert response.status_code == 202
        body = response.json()
        assert body["event_type"] == "order.created"
        assert len(body["deliveries"]) == 1
        assert body["deliveries"][0]["status"] == "pending"

    async def test_no_matching_subscription_creates_event_without_deliveries(
        self, client, db_session
    ):
        await seed_subscription(db_session, event_types=["invoice.paid"])

        response = await client.post(
            "/events/",
            json={"event_type": "order.created", "payload": {}},
        )

        assert response.status_code == 202
        assert response.json()["deliveries"] == []

    async def test_inactive_subscription_is_not_delivered_to(self, client, db_session):
        await seed_subscription(
            db_session, event_types=["order.created"], is_active=False
        )

        response = await client.post(
            "/events/",
            json={"event_type": "order.created", "payload": {}},
        )

        assert response.status_code == 202
        assert response.json()["deliveries"] == []

    async def test_duplicate_idempotency_key_does_not_create_second_event(
        self, client, db_session
    ):
        await seed_subscription(db_session, event_types=["order.created"])
        idempotency_key = "same-key-123"

        first = await client.post(
            "/events/",
            json={
                "event_type": "order.created",
                "payload": {"n": 1},
                "idempotency_key": idempotency_key,
            },
        )
        second = await client.post(
            "/events/",
            json={
                "event_type": "order.created",
                "payload": {"n": 2},
                "idempotency_key": idempotency_key,
            },
        )

        assert first.status_code == 202
        assert second.status_code == 202
        assert first.json()["id"] == second.json()["id"]
        assert second.json()["payload"] == {"n": 1}


class TestGetEvent:
    async def test_returns_event_with_deliveries(self, client, db_session):
        await seed_subscription(db_session, event_types=["order.created"])
        create_resp = await client.post(
            "/events/",
            json={"event_type": "order.created", "payload": {"a": 1}},
        )
        event_id = create_resp.json()["id"]

        response = await client.get(f"/events/{event_id}")

        assert response.status_code == 200
        assert response.json()["id"] == event_id
        assert len(response.json()["deliveries"]) == 1

    async def test_unknown_event_returns_404(self, client):
        response = await client.get(f"/events/{uuid.uuid4()}")

        assert response.status_code == 404
