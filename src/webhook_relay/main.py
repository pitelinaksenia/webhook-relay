from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager

from webhook_relay.api.exception_handlers import register_exception_handlers
from webhook_relay.api.routes import dead_letters, events, subscriptions
from webhook_relay.config import settings
from webhook_relay.queue.pool import get_arq_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.arq_pool = await get_arq_pool()
    yield
    await app.state.arq_pool.close()


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
app.include_router(subscriptions.router)
app.include_router(events.router)
app.include_router(dead_letters.router)

register_exception_handlers(app)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
