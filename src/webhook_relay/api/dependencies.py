from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from webhook_relay.models.session import get_db
from webhook_relay.repositories.subscription_repo import SubscriptionRepo
from webhook_relay.services.subscription_service import SubscriptionService


def get_subscription_repo(session: AsyncSession = Depends(get_db)) -> SubscriptionRepo:
    return SubscriptionRepo(session)


def get_subscription_service(
    subscription_repo: SubscriptionRepo = Depends(get_subscription_repo),
) -> SubscriptionService:
    return SubscriptionService(subscription_repo)
