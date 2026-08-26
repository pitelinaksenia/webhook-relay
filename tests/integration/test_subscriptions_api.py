import uuid

from tests.integration.conftest import seed_subscription


class TestCreateSubscription:
    async def test_creates_subscription_and_does_not_leak_plain_secret(self, client):
        response = await client.post(
            "/subscriptions/",
            json={
                "url": "http://mock-receiver/hook",
                "event_types": ["order.created"],
                "secret": "top-secret",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["event_types"] == ["order.created"]
        assert body["is_active"] is True
        assert "secret" not in body


class TestGetSubscription:
    async def test_returns_subscription_by_id(self, client, db_session):
        subscription = await seed_subscription(db_session)

        response = await client.get(f"/subscriptions/{subscription.id}")

        assert response.status_code == 200
        assert response.json()["id"] == str(subscription.id)

    async def test_unknown_subscription_returns_404(self, client):
        response = await client.get(f"/subscriptions/{uuid.uuid4()}")

        assert response.status_code == 404

    async def test_list_returns_all_subscriptions(self, client, db_session):
        await seed_subscription(db_session, url="http://a")
        await seed_subscription(db_session, url="http://b")

        response = await client.get("/subscriptions/")

        assert response.status_code == 200
        assert len(response.json()) == 2


class TestDeleteSubscription:
    async def test_deletes_subscription_without_deliveries(self, client, db_session):
        subscription = await seed_subscription(db_session)

        response = await client.delete(f"/subscriptions/{subscription.id}")
        assert response.status_code == 200

        get_response = await client.get(f"/subscriptions/{subscription.id}")
        assert get_response.status_code == 404

    async def test_unknown_subscription_returns_404(self, client):
        response = await client.delete(f"/subscriptions/{uuid.uuid4()}")

        assert response.status_code == 404

    async def test_subscription_with_deliveries_cannot_be_deleted(self, client, db_session):
        subscription = await seed_subscription(db_session, event_types=["order.created"])
        await client.post(
            "/events/",
            json={"event_type": "order.created", "payload": {}},
        )

        response = await client.delete(f"/subscriptions/{subscription.id}")

        assert response.status_code == 409


class TestSubscriptionDeliveries:
    async def test_returns_deliveries_for_subscription(self, client, db_session):
        subscription = await seed_subscription(db_session, event_types=["order.created"])
        await client.post(
            "/events/",
            json={"event_type": "order.created", "payload": {}},
        )

        response = await client.get(f"/subscriptions/{subscription.id}/deliveries")

        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["subscription_id"] == str(subscription.id)

    async def test_unknown_subscription_returns_404(self, client):
        response = await client.get(f"/subscriptions/{uuid.uuid4()}/deliveries")

        assert response.status_code == 404
