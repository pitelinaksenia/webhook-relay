from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from webhook_relay.exceptions import InUseError, NotFoundError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(InUseError)
    async def in_use_handler(request: Request, exc: InUseError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
