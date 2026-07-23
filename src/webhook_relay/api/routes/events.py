import uuid

from fastapi import APIRouter, Depends

from webhook_relay.api.dependencies import get_event_service
from webhook_relay.schemas.event import EventCreate, EventResponse
from webhook_relay.services.event_service import EventService

router = APIRouter(
    prefix="/events",
    tags=["events"],
)


@router.post("/", response_model=EventResponse, status_code=202)
async def create_event(
    event_data: EventCreate, event_service: EventService = Depends(get_event_service)
) -> EventResponse:
    return await event_service.create(event_data)


@router.get("/{event_id}", response_model=EventResponse)
async def get_event_by_id(
    event_id: uuid.UUID, event_service: EventService = Depends(get_event_service)
) -> EventResponse:
    return await event_service.get_by_id(event_id)
