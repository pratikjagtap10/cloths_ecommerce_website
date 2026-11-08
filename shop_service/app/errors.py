"""Same error format as the Django service: {"detail": "readable message", ...}"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .services.core_client import CoreServiceError


def _readable(error: dict) -> str:
    field = next((str(p) for p in reversed(error.get("loc", ())) if isinstance(p, str) and p != "body"), None)
    message = str(error.get("msg", "Invalid value")).removeprefix("Value error, ")
    return f"{field.replace('_', ' ').capitalize()}: {message}" if field else message


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(CoreServiceError)
    async def core_service_error(_: Request, exc: CoreServiceError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        errors = exc.errors()
        detail = _readable(errors[0]) if errors else "Invalid request."
        return JSONResponse(
            status_code=422,
            content={"detail": detail, "errors": [{"loc": e.get("loc"), "msg": e.get("msg")} for e in errors]},
        )
