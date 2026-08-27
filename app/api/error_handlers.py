import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.services.exceptions import (
    AllGatewaysExhaustedError,
    DomainException,
    FailoverBudgetExceededError,
    IdempotencyConflictError,
    IllegalTransitionError,
    NoHealthyGatewayError,
    TransactionNotFoundException,
)

logger = structlog.get_logger(__name__)


def make_error_response(
    status_code: int,
    error_code: str,
    message: str,
    details: dict | list | None = None,
) -> JSONResponse:
    """Builds a standardized error envelope across all API endpoints."""
    content = {
        "success": False,
        "error": {
            "code": error_code,
            "message": message,
        }
    }
    if details is not None:
        content["error"]["details"] = details

    return JSONResponse(status_code=status_code, content=content)


def register_error_handlers(app: FastAPI) -> None:
    # 404: Transaction Not Found
    @app.exception_handler(TransactionNotFoundException)
    async def transaction_not_found_handler(request: Request, exc: TransactionNotFoundException):
        logger.warning("transaction_not_found", path=request.url.path, error=str(exc))
        return make_error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="TRANSACTION_NOT_FOUND",
            message=str(exc),
            details={"transaction_id": str(exc.transaction_id)},
        )

    # 409: Illegal State Transition
    @app.exception_handler(IllegalTransitionError)
    async def illegal_transition_handler(request: Request, exc: IllegalTransitionError):
        logger.warning(
            "illegal_state_transition",
            path=request.url.path,
            from_status=exc.current_status,
            to_status=exc.target_status,
            transaction_id=str(exc.transaction_id),
        )
        return make_error_response(
            status_code=status.HTTP_409_CONFLICT,
            error_code="ILLEGAL_STATE_TRANSITION",
            message=str(exc),
            details={
                "current_status": exc.current_status,
                "target_status": exc.target_status,
                "transaction_id": str(exc.transaction_id),
            },
        )

    # 409: Idempotency Lock Conflict
    @app.exception_handler(IdempotencyConflictError)
    async def idempotency_conflict_handler(request: Request, exc: IdempotencyConflictError):
        logger.warning(
            "idempotency_conflict",
            path=request.url.path,
            idempotency_key=exc.idempotency_key,
        )
        return make_error_response(
            status_code=status.HTTP_409_CONFLICT,
            error_code="IDEMPOTENCY_CONFLICT",
            message=str(exc),
            details={"idempotency_key": exc.idempotency_key},
        )

    # 422: Request Validation Errors (FastAPI / Pydantic)
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        logger.warning("request_validation_failed", path=request.url.path, errors=exc.errors())
        return make_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_ERROR",
            message="The request payload or headers failed validation.",
            details=exc.errors(),
        )

    # 500: Uncaught Generic Exceptions
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception(
            "unhandled_server_error",
            path=request.url.path,
            method=request.method,
            error=str(exc),
        )
        return make_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="INTERNAL_SERVER_ERROR",
            message="An unexpected error occurred while processing the request.",
        )
        
        
    # Inside register_error_handlers(app):
    @app.exception_handler(AllGatewaysExhaustedError)
    @app.exception_handler(FailoverBudgetExceededError)
    @app.exception_handler(NoHealthyGatewayError)
    async def gateway_failover_error_handler(request: Request, exc: DomainException):
        logger.error("gateway_failover_exhaustion", path=request.url.path, error=str(exc))
        return make_error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code="GATEWAY_UNAVAILABLE",
            message=str(exc)
        )