"""
Async Database Session — engine, session factory, and dependency.

Architecture:
    create_async_engine  →  async_sessionmaker  →  get_db() dependency
         (one global)         (one global)        (yields per-request)

Every FastAPI endpoint that needs the DB declares:
    async def my_endpoint(db: AsyncSession = Depends(get_db)):
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# ── Async Engine ───────────────────────────────────────────────────────
# pool_pre_ping=True: test connections before using them (handles DB restarts)
# echo=False: set to True for SQL logging during development
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
)

# ── Session Factory ────────────────────────────────────────────────────
# expire_on_commit=False: prevents lazy-load errors after commit when
# accessing model attributes outside the session context (common in
# FastAPI where the response serialisation happens after commit).
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── FastAPI Dependency ─────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session for a single request lifecycle.

    The session is automatically closed when the request finishes,
    whether it succeeded or raised an exception. This is the standard
    FastAPI dependency-injection pattern for database access.

    Usage in a route:
        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()
    """
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
