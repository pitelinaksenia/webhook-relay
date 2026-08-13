import uuid

from fastapi import APIRouter, Depends

from webhook_relay.api.dependencies import get_dead_letter_service
from webhook_relay.schemas.dead_letter import DeadLetterResponse
from webhook_relay.schemas.delivery import DeliveryResponse
from webhook_relay.services.dead_letter_service import DeadLetterService

router = APIRouter(
    prefix="/dead-letters",
    tags=["dead-letters"],
)


@router.post("/{dead_letter_id}/retry", response_model=DeliveryResponse, status_code=202)
async def retry_dead_letter(
    dead_letter_id: uuid.UUID,
    dead_letter_service: DeadLetterService = Depends(get_dead_letter_service),
) -> DeliveryResponse:
    return await dead_letter_service.retry(dead_letter_id)


@router.get("/", response_model=list[DeadLetterResponse])
async def get_dead_letters(
    limit: int = 20,
    offset: int = 0,
    dead_letter_service: DeadLetterService = Depends(get_dead_letter_service),
) -> list[DeadLetterResponse]:
    return await dead_letter_service.get_all(limit=limit, offset=offset)
