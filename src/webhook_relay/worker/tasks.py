from webhook_relay.models.session import SessionLocal
from webhook_relay.repositories.dead_letter_repo import DeadLetterRepo
from webhook_relay.repositories.delivery_repo import DeliveryRepo
from webhook_relay.services.webhook_delivery_service import WebhookDeliveryService


async def deliver_webhook(ctx: dict, delivery_id: str) -> None:
    async with SessionLocal() as session:
        service = WebhookDeliveryService(
            session=session,
            http_client=ctx["httpx_client"],
            arq_redis=ctx["redis"],
            delivery_repo=DeliveryRepo(session),
            dead_letter_repo=DeadLetterRepo(session),
        )
        await service.deliver(delivery_id)
