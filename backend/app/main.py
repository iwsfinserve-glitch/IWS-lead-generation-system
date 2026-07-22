"""
FastAPI Application Entrypoint.

This module initializes the FastAPI app, configures CORS, and
includes all the routers defined in the API layer.
# Triggering uvicorn reload to pick up new env vars.

"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.scheduler import scheduler, setup_scheduler, _reconcile_appointments_job
from app.api.v1 import auth, sources, leads, appointments, tasks, reports
from app.api.v1 import due_date_requests, notifications, lead_transfers, ai_insights

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background scheduler on boot, shut it down on exit."""
    setup_scheduler()
    scheduler.start()
    # Fire reconcile immediately on startup to catch thresholds crossed while offline
    asyncio.ensure_future(_reconcile_appointments_job())
    yield
    scheduler.shutdown()


app = FastAPI(
    title="Lead Management CRM API",
    description="Asynchronous backend for the Lead Management System",
    version="1.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS Configuration ─────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global Exception Handlers ─────────────────────────────────────────

@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    """Catch database errors and return a clean 503 response."""
    logger.error("Database error on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=503,
        content={"error": "A database error occurred. Please try again later.", "code": "DB_ERROR"},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Catch-all for unexpected server errors — prevents stack trace leakage."""
    logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "code": "INTERNAL_ERROR"},
    )


# ── Include API Routers ────────────────────────────────────────────────
app.include_router(auth.router, prefix="/api/v1")
app.include_router(sources.router, prefix="/api/v1")
app.include_router(leads.router, prefix="/api/v1")
app.include_router(appointments.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
app.include_router(due_date_requests.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(lead_transfers.router, prefix="/api/v1")
app.include_router(ai_insights.router, prefix="/api/v1")

@app.get("/health", tags=["Health"])
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok"}

