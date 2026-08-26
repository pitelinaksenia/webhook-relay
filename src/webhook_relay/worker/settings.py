import logging

import httpx

from webhook_relay.config import settings
from webhook_relay.queue.pool import get_redis_settings
from webhook_relay.worker.tasks import deliver_webhook

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


async def startup(ctx: dict) -> None:
    ctx["httpx_client"] = httpx.AsyncClient(
        timeout=httpx.Timeout(
            settings.http_read_timeout,
            connect=settings.http_connect_timeout,
        )
    )


async def shutdown(ctx: dict) -> None:
    client = ctx.get("httpx_client")
    if client is not None:
        await client.aclose()


class WorkerSettings:
    functions = [deliver_webhook]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = get_redis_settings()
