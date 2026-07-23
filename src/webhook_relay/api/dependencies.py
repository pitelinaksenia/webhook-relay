from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from webhook_relay.models.session import get_db
from webhook_relay.repositories.event_repo import EventRepo
from webhook_relay.repositories.subscription_repo import SubscriptionRepo
from webhook_relay.services.event_service import EventService
from webhook_relay.services.subscription_service import SubscriptionService


def get_subscription_repo(session: AsyncSession = Depends(get_db)) -> SubscriptionRepo:
    return SubscriptionRepo(session)


def get_subscription_service(
    subscription_repo: SubscriptionRepo = Depends(get_subscription_repo),
) -> SubscriptionService:
    return SubscriptionService(subscription_repo)


def get_event_repo(session: AsyncSession = Depends(get_db)) -> EventRepo:
    return EventRepo(session)


def get_event_service(
    event_repo: EventRepo = Depends(get_event_repo),
) -> EventService:
    return EventService(event_repo)
