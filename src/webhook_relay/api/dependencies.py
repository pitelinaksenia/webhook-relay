from arq import ArqRedis
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from webhook_relay.models.session import get_db
from webhook_relay.repositories.dead_letter_repo import DeadLetterRepo
from webhook_relay.repositories.delivery_repo import DeliveryRepo
from webhook_relay.repositories.event_repo import EventRepo
from webhook_relay.repositories.subscription_repo import SubscriptionRepo
from webhook_relay.services.dead_letter_service import DeadLetterService
from webhook_relay.services.event_service import EventService
from webhook_relay.services.subscription_service import SubscriptionService


def arq_pool_dependency(request: Request) -> ArqRedis:
    return request.app.state.arq_pool


def get_subscription_repo(session: AsyncSession = Depends(get_db)) -> SubscriptionRepo:
    return SubscriptionRepo(session)


def get_delivery_repo(session: AsyncSession = Depends(get_db)) -> DeliveryRepo:
    return DeliveryRepo(session)


def get_event_repo(session: AsyncSession = Depends(get_db)) -> EventRepo:
    return EventRepo(session)


def get_dead_letter_repo(session: AsyncSession = Depends(get_db)) -> DeadLetterRepo:
    return DeadLetterRepo(session)


def get_subscription_service(
    subscription_repo: SubscriptionRepo = Depends(get_subscription_repo),
    delivery_repo: DeliveryRepo = Depends(get_delivery_repo),
) -> SubscriptionService:
    return SubscriptionService(subscription_repo, delivery_repo)


def get_event_service(
    event_repo: EventRepo = Depends(get_event_repo),
    subscription_repo: SubscriptionRepo = Depends(get_subscription_repo),
    delivery_repo: DeliveryRepo = Depends(get_delivery_repo),
    arq_pool: ArqRedis = Depends(arq_pool_dependency),
) -> EventService:
    return EventService(event_repo, subscription_repo, delivery_repo, arq_pool)


def get_dead_letter_service(
    delivery_repo: DeliveryRepo = Depends(get_delivery_repo),
    dead_letter_repo: DeadLetterRepo = Depends(get_dead_letter_repo),
    arq_pool: ArqRedis = Depends(arq_pool_dependency),
) -> DeadLetterService:
    return DeadLetterService(arq_pool, delivery_repo, dead_letter_repo)
