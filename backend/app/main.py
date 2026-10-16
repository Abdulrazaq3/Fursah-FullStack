from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import routes
from .infrastructure.config import get_settings
from .infrastructure.errors import ErrorCode
from .schemas import ApiErrorDetail, ApiErrorResponse

settings = get_settings()

app = FastAPI(
    title="FURSAH API",
    version="1.0.0-starter",
    description="Applied AI Engineering Bootcamp starter backend.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes.router)


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError):
    request_id = (request.headers.get("x-request-id") or "").strip()[:120] or str(uuid4())
    details: list[ApiErrorDetail] = []

    for item in exc.errors():
        loc = [str(part) for part in item.get("loc", []) if part != "body"]
        details.append(
            ApiErrorDetail(
                field=".".join(loc) or None,
                message=item.get("msg", "Invalid value."),
            )
        )

    payload = ApiErrorResponse(
        request_id=request_id,
        error_code=ErrorCode.REQUEST_VALIDATION,
        message="The request body is invalid.",
        details=details,
    )
    return JSONResponse(status_code=422, content=payload.model_dump(mode="json"))


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    request_id = (
        getattr(request.state, "request_id", None)
        or (request.headers.get("x-request-id") or "").strip()[:120]
        or str(uuid4())
    )
    payload = ApiErrorResponse(
        request_id=request_id,
        error_code=ErrorCode.INTERNAL,
        message="An unexpected backend error occurred.",
        details=[],
    )
    return JSONResponse(status_code=500, content=payload.model_dump(mode="json"))
