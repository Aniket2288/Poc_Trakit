import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_context import current_request_id


class AppError(Exception):
    """Base error. Services raise these; the handlers below turn them into JSON."""

    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, headers: dict | None = None):
        super().__init__(message)
        self.message = message
        self.headers = headers


class AuthenticationError(AppError):
    """401: we don't know who you are (no token, bad token, expired token, wrong password)."""

    status_code = 401
    code = "unauthenticated"


class PermissionDeniedError(AppError):
    """403: we know who you are, but you are not allowed to do this."""

    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"


class InvalidTransitionError(AppError):
    """422: the request is well-formed, but the state machine doesn't allow this move."""

    status_code = 422
    code = "invalid_transition"


class UnprocessableError(AppError):
    """422: well-formed request that breaks a business rule (e.g. assignee not in the workspace)."""

    status_code = 422
    code = "unprocessable"


def error_body(code: str, message: str, details=None) -> dict:
    """Every error the API returns has this same shape."""
    # request_id lets a user quote one id and lets us find every log line for that request.
    return {"error": {"code": code, "message": message, "details": details, "request_id": current_request_id()}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    def handle_app_error(request: Request, exc: AppError):
        headers = dict(exc.headers or {})
        if exc.status_code == 401:
            headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message), headers=headers)

    @app.exception_handler(RequestValidationError)
    def handle_validation_error(request: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in err["loc"]), "message": err["msg"]} for err in exc.errors()]
        return JSONResponse(status_code=422, content=error_body("validation_error", "Request data is invalid", details))

    @app.exception_handler(StarletteHTTPException)
    def handle_http_error(request: Request, exc: StarletteHTTPException):
        # FastAPI's own errors, e.g. 404 for an unknown URL or 405 for a wrong method.
        return JSONResponse(status_code=exc.status_code, content=error_body("http_error", str(exc.detail)), headers=exc.headers)

    @app.exception_handler(Exception)
    def handle_unexpected_error(request: Request, exc: Exception):
        # Never send a stack trace to the client. It goes to the log, tagged with the request id.
        logging.getLogger("trackit.error").exception("unhandled error")
        return JSONResponse(status_code=500, content=error_body("internal_error", "Something went wrong"))
