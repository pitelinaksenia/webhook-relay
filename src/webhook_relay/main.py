from fastapi import FastAPI

from webhook_relay.api.exception_handlers import register_exception_handlers
from webhook_relay.api.routes import events, subscriptions
from webhook_relay.config import settings

app = FastAPI(title=settings.app_name, debug=settings.debug)
app.include_router(subscriptions.router)
app.include_router(events.router)

register_exception_handlers(app)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
