import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from webhook_relay.api.templates import templates
from webhook_relay.exceptions import InUseError, NotFoundError

logger = logging.getLogger(__name__)


def _is_dashboard_request(request: Request) -> bool:
    return request.url.path.startswith("/dashboard")


def _render_dashboard_error(request: Request, status_code: int, detail: str) -> Response:
    template_name = (
        "partials/error_fragment.html" if request.headers.get("HX-Request") else "error.html"
    )
    return templates.TemplateResponse(
        request,
        template_name,
        {"request": request, "status_code": status_code, "detail": detail},
        status_code=status_code,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError):
        if _is_dashboard_request(request):
            return _render_dashboard_error(request, 404, str(exc))
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(InUseError)
    async def in_use_handler(request: Request, exc: InUseError):
        if _is_dashboard_request(request):
            return _render_dashboard_error(request, 409, str(exc))
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        if _is_dashboard_request(request):
            return _render_dashboard_error(request, 500, "Internal server error")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
