"""
FastAPI Application Entrypoint.

This module initializes the FastAPI app, configures CORS, and
includes all the routers defined in the API layer.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1 import auth, sources, leads, appointments, tasks, reports

app = FastAPI(
    title="Lead Management CRM API",
    description="Asynchronous backend for the Lead Management System",
    version="1.0.0",
)

# ── CORS Configuration ─────────────────────────────────────────────────
# Update allow_origins for production to the specific Streamlit frontend URL
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for local dev
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# ── Include API Routers ────────────────────────────────────────────────
app.include_router(auth.router, prefix="/api/v1")
app.include_router(sources.router, prefix="/api/v1")
app.include_router(leads.router, prefix="/api/v1")
app.include_router(appointments.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")

@app.get("/health", tags=["Health"])
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok"}
