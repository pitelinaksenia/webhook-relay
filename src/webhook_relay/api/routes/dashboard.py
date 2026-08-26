import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from webhook_relay.api.dependencies import (
    get_dead_letter_service,
    get_delivery_repo,
    get_event_repo,
    get_subscription_service,
)
from webhook_relay.api.templates import templates
from webhook_relay.exceptions import DeliveryNotFoundError, SubscriptionInUseError
from webhook_relay.models.delivery import DeliveryStatus
from webhook_relay.repositories.delivery_repo import DeliveryRepo
from webhook_relay.repositories.event_repo import EventRepo
from webhook_relay.schemas.subscription import SubscriptionCreate
from webhook_relay.services.dead_letter_service import DeadLetterService
from webhook_relay.services.subscription_service import SubscriptionService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

STATS_WINDOW = timedelta(hours=24)
PAGE_SIZE = 20


@router.get("/", response_class=HTMLResponse)
async def overview(
    request: Request,
    status: DeliveryStatus | None = None,
    event_type: str | None = None,
    page: int = 1,
    delivery_repo: DeliveryRepo = Depends(get_delivery_repo),
    event_repo: EventRepo = Depends(get_event_repo),
) -> HTMLResponse:
    offset = (page - 1) * PAGE_SIZE
    deliveries = await delivery_repo.get_all(
        status=status, event_type=event_type, limit=PAGE_SIZE, offset=offset
    )
    total = await delivery_repo.count(status=status, event_type=event_type)
    stats = await delivery_repo.stats_since(datetime.now(UTC) - STATS_WINDOW)
    event_types = await event_repo.distinct_event_types()

    context = {
        "request": request,
        "active_nav": "overview",
        "deliveries": deliveries,
        "stats": stats,
        "event_types": event_types,
        "selected_status": status,
        "selected_event_type": event_type,
        "page": page,
        "has_next": offset + PAGE_SIZE < total,
        "total": total,
        "statuses": list(DeliveryStatus),
    }
    return templates.TemplateResponse(request, "overview.html", context)


@router.get("/deliveries", response_class=HTMLResponse)
async def deliveries_table(
    request: Request,
    status: DeliveryStatus | None = None,
    event_type: str | None = None,
    page: int = 1,
    delivery_repo: DeliveryRepo = Depends(get_delivery_repo),
) -> HTMLResponse:
    offset = (page - 1) * PAGE_SIZE
    deliveries = await delivery_repo.get_all(
        status=status, event_type=event_type, limit=PAGE_SIZE, offset=offset
    )
    total = await delivery_repo.count(status=status, event_type=event_type)

    context = {
        "request": request,
        "deliveries": deliveries,
        "selected_status": status,
        "selected_event_type": event_type,
        "page": page,
        "has_next": offset + PAGE_SIZE < total,
        "total": total,
    }
    return templates.TemplateResponse(request, "partials/deliveries_table.html", context)


@router.get("/deliveries/{delivery_id}", response_class=HTMLResponse)
async def delivery_detail(
    request: Request,
    delivery_id: uuid.UUID,
    delivery_repo: DeliveryRepo = Depends(get_delivery_repo),
) -> HTMLResponse:
    delivery = await delivery_repo.get_with_attempts(delivery_id)
    if delivery is None:
        raise DeliveryNotFoundError(delivery_id)

    return templates.TemplateResponse(
        request,
        "delivery_detail.html",
        {"request": request, "active_nav": "overview", "delivery": delivery},
    )


@router.get("/dead-letters", response_class=HTMLResponse)
async def dead_letters(
    request: Request,
    page: int = 1,
    dead_letter_service: DeadLetterService = Depends(get_dead_letter_service),
) -> HTMLResponse:
    offset = (page - 1) * PAGE_SIZE
    dead_letter_list = await dead_letter_service.get_all(limit=PAGE_SIZE, offset=offset)

    return templates.TemplateResponse(
        request,
        "dead_letters.html",
        {
            "request": request,
            "active_nav": "dead-letters",
            "dead_letters": dead_letter_list,
            "page": page,
        },
    )


@router.post("/dead-letters/{dead_letter_id}/retry", response_class=HTMLResponse)
async def retry_dead_letter(
    request: Request,
    dead_letter_id: uuid.UUID,
    dead_letter_service: DeadLetterService = Depends(get_dead_letter_service),
) -> HTMLResponse:
    await dead_letter_service.retry(dead_letter_id)
    return HTMLResponse("")


@router.get("/subscriptions", response_class=HTMLResponse)
async def subscriptions_page(
    request: Request,
    page: int = 1,
    subscription_service: SubscriptionService = Depends(get_subscription_service),
) -> HTMLResponse:
    offset = (page - 1) * PAGE_SIZE
    subscriptions = await subscription_service.get_all(limit=PAGE_SIZE, offset=offset)

    return templates.TemplateResponse(
        request,
        "subscriptions.html",
        {"request": request, "active_nav": "subscriptions", "subscriptions": subscriptions},
    )


@router.post("/subscriptions", response_class=HTMLResponse)
async def create_subscription(
    request: Request,
    url: str = Form(...),
    event_types: str = Form(...),
    secret: str = Form(...),
    subscription_service: SubscriptionService = Depends(get_subscription_service),
) -> HTMLResponse:
    types = [t.strip() for t in event_types.split(",") if t.strip()]
    subscription_data = SubscriptionCreate.model_validate(
        {"url": url, "event_types": types, "secret": secret}
    )
    await subscription_service.create(subscription_data)

    subscriptions = await subscription_service.get_all(limit=PAGE_SIZE, offset=0)
    return templates.TemplateResponse(
        request,
        "partials/subscriptions_table.html",
        {"request": request, "subscriptions": subscriptions},
    )


@router.post("/subscriptions/{subscription_id}/activate", response_class=HTMLResponse)
async def activate_subscription(
    request: Request,
    subscription_id: uuid.UUID,
    subscription_service: SubscriptionService = Depends(get_subscription_service),
) -> HTMLResponse:
    sub = await subscription_service.set_active(subscription_id, is_active=True)
    return templates.TemplateResponse(
        request, "partials/subscription_row.html", {"request": request, "sub": sub}
    )


@router.post("/subscriptions/{subscription_id}/deactivate", response_class=HTMLResponse)
async def deactivate_subscription(
    request: Request,
    subscription_id: uuid.UUID,
    subscription_service: SubscriptionService = Depends(get_subscription_service),
) -> HTMLResponse:
    sub = await subscription_service.set_active(subscription_id, is_active=False)
    return templates.TemplateResponse(
        request, "partials/subscription_row.html", {"request": request, "sub": sub}
    )


@router.post("/subscriptions/{subscription_id}/delete", response_class=HTMLResponse)
async def delete_subscription(
    request: Request,
    subscription_id: uuid.UUID,
    subscription_service: SubscriptionService = Depends(get_subscription_service),
) -> HTMLResponse:
    try:
        await subscription_service.delete(subscription_id)
    except SubscriptionInUseError:
        sub = await subscription_service.get(subscription_id)
        return templates.TemplateResponse(
            request,
            "partials/subscription_row.html",
            {
                "request": request,
                "sub": sub,
                "error": "Can't delete: subscription has deliveries. Deactivate it instead.",
            },
        )

    return HTMLResponse("")
