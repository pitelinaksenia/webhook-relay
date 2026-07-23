import uuid

from sqlalchemy.exc import IntegrityError

from webhook_relay.exceptions import SubscriptionInUseError, SubscriptionNotFoundError
from webhook_relay.models.subscription import Subscription
from webhook_relay.repositories.subscription_repo import SubscriptionRepo
from webhook_relay.schemas.subscription import SubscriptionCreate


class SubscriptionService:
    def __init__(self, subscription_repo: SubscriptionRepo):
        self.subscription_repo = subscription_repo

    async def create(self, subscription_data: SubscriptionCreate) -> Subscription:
        return await self.subscription_repo.create(subscription_data)

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
