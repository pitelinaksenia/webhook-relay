import uuid

from fastapi import APIRouter, Depends

from webhook_relay.api.dependencies import get_subscription_service
from webhook_relay.schemas.delivery import DeliveryResponse
from webhook_relay.schemas.subscription import SubscriptionCreate, SubscriptionResponse
from webhook_relay.services.subscription_service import SubscriptionService

router = APIRouter(
    prefix="/subscriptions",
    tags=["subscriptions"],
)


@router.post("/", response_model=SubscriptionResponse, status_code=201)
async def create_subscription(
    subscription_data: SubscriptionCreate,
    subscription_service: SubscriptionService = Depends(get_subscription_service),
) -> SubscriptionResponse:
    return await subscription_service.create(subscription_data)


@router.get("/", response_model=list[SubscriptionResponse])
async def get_subscriptions(
    limit: int = 20,
    offset: int = 0,
    subscription_service: SubscriptionService = Depends(get_subscription_service),
) -> list[SubscriptionResponse]:
    return await subscription_service.get_all(limit=limit, offset=offset)


@router.get("/{subscription_id}/deliveries", response_model=list[DeliveryResponse])
async def get_deliveries(
    subscription_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
    subscription_service: SubscriptionService = Depends(get_subscription_service),
) -> list[DeliveryResponse]:
    return await subscription_service.get_deliveries(subscription_id, limit=limit, offset=offset)


@router.get("/{subscription_id}", response_model=SubscriptionResponse)
async def get_subscription_by_id(
    subscription_id: uuid.UUID,
    subscription_service: SubscriptionService = Depends(get_subscription_service),
) -> SubscriptionResponse:
    return await subscription_service.get(subscription_id)


@router.post("/{subscription_id}/deactivate", response_model=SubscriptionResponse)
async def deactivate_subscription(
    subscription_id: uuid.UUID,
    subscription_service: SubscriptionService = Depends(get_subscription_service),
) -> SubscriptionResponse:
    return await subscription_service.set_active(subscription_id, is_active=False)


@router.post("/{subscription_id}/activate", response_model=SubscriptionResponse)
async def activate_subscription(
    subscription_id: uuid.UUID,
    subscription_service: SubscriptionService = Depends(get_subscription_service),
) -> SubscriptionResponse:
    return await subscription_service.set_active(subscription_id, is_active=True)


@router.delete("/{subscription_id}")
async def delete_subscription_by_id(
    subscription_id: uuid.UUID,
    subscription_service: SubscriptionService = Depends(get_subscription_service),
) -> None:
    return await subscription_service.delete(subscription_id)
