import uuid

from sqlalchemy.exc import IntegrityError

from webhook_relay.exceptions import SubscriptionInUseError, SubscriptionNotFoundError
from webhook_relay.models.delivery import Delivery
from webhook_relay.models.subscription import Subscription
from webhook_relay.repositories.delivery_repo import DeliveryRepo
from webhook_relay.repositories.subscription_repo import SubscriptionRepo
from webhook_relay.schemas.subscription import SubscriptionCreate
from webhook_relay.security.hmac_signer import encrypt_secret


class SubscriptionService:
    def __init__(self, subscription_repo: SubscriptionRepo, delivery_repo: DeliveryRepo):
        self.subscription_repo = subscription_repo
        self.delivery_repo = delivery_repo

    async def create(self, subscription_data: SubscriptionCreate) -> Subscription:
        encrypted_data = subscription_data.model_copy(
            update={"secret": encrypt_secret(subscription_data.secret)}
        )
        return await self.subscription_repo.create(encrypted_data)

    async def get_all(self, limit: int, offset: int) -> list[Subscription]:
        return await self.subscription_repo.get_all(limit=limit, offset=offset)

    async def get(self, subscription_id: uuid.UUID) -> Subscription:
        subscription = await self.subscription_repo.get_by_id(subscription_id)
        if subscription is None:
            raise SubscriptionNotFoundError(subscription_id)
        return subscription

    async def delete(self, subscription_id: uuid.UUID) -> None:
        try:
            deleted = await self.subscription_repo.delete_by_id(subscription_id)
        except IntegrityError:
            await self.subscription_repo.rollback()
            raise SubscriptionInUseError(subscription_id) from None

        if not deleted:
            raise SubscriptionNotFoundError(subscription_id)

    async def get_deliveries(
        self, subscription_id: uuid.UUID, limit: int, offset: int
    ) -> list[Delivery]:
        await self.get(subscription_id)
        return await self.delivery_repo.get_by_subscription_id(
            subscription_id, limit=limit, offset=offset
        )
