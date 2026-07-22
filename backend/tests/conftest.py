"""
conftest.py — shared pytest fixtures for the Lead Management CRM test suite.

Strategy:
- Each test gets a real AsyncSession wrapped in a SAVEPOINT (nested transaction).
- The outer transaction is never committed, so every test is fully isolated
  and your seed data is never touched.
- Google sync and Gemini AI calls are mocked at the service layer so tests
  never hit external APIs.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from unittest.mock import AsyncMock, patch

from app.main import app
from app.db.session import get_db
from app.core.config import settings
from app.core.security import hash_password
from app.models.user import User
from app.models.lead import LeadSource, Lead
from app.models.enums import UserRole, LeadStatus


from sqlalchemy.pool import StaticPool
from app.db.base import Base

# ── Engine (isolated in-memory SQLite database for tests) ─────────────────────

@pytest_asyncio.fixture(scope="session")
async def engine():
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()


@pytest.fixture(scope="session")
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


# ── Per-test isolated DB session via nested transactions ──────────────────────

@pytest_asyncio.fixture()
async def db_session(engine):
    """
    Yields an AsyncSession inside a SAVEPOINT.
    Any data written during the test is rolled back when the test ends.
    Your existing seed data is completely safe.
    """
    async with engine.connect() as conn:
        await conn.begin()                          # outer transaction
        await conn.begin_nested()                   # SAVEPOINT

        session = AsyncSession(bind=conn, expire_on_commit=False)

        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()                   # rolls back the SAVEPOINT + outer


# ── Override FastAPI's get_db dependency with the test session ────────────────

@pytest_asyncio.fixture()
async def client(db_session):
    """
    AsyncClient wired to your FastAPI app, with get_db overridden
    to use the isolated test session and rate limiting disabled for tests.
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    was_enabled = getattr(app.state.limiter, "enabled", True)
    app.state.limiter.enabled = False

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac

    app.state.limiter.enabled = was_enabled
    app.dependency_overrides.clear()


# ── Seed helpers — insert test records into the rolled-back session ───────────

@pytest_asyncio.fixture()
async def admin_user(db_session):
    user = User(
        name="Test Admin",
        email="testadmin@example.com",
        phone_number="9999900001",
        hashed_password=hash_password("admin123"),
        role=UserRole.admin,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture()
async def manager_user(db_session):
    user = User(
        name="Test Manager",
        email="testmanager@example.com",
        phone_number="9999900002",
        hashed_password=hash_password("manager123"),
        role=UserRole.manager,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture()
async def sales_rep_user(db_session):
    user = User(
        name="Test Rep",
        email="testrep@example.com",
        phone_number="9999900003",
        hashed_password=hash_password("rep123"),
        role=UserRole.sales_rep,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture()
async def lead_source(db_session):
    source = LeadSource(name="Test Source", priority="high")
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


@pytest_asyncio.fixture()
async def sample_lead(db_session, lead_source, admin_user):
    lead = Lead(
        name="Sample Lead",
        profession="Investor",
        email="lead@example.com",
        phone_number="9876543210",
        status=LeadStatus.unassigned,
        source_id=lead_source.id,
        assigned_rep_id=admin_user.id,
    )
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)
    return lead


# ── JWT token fixtures — log in via the API and return Bearer tokens ──────────

@pytest_asyncio.fixture()
async def admin_token(client, admin_user):
    resp = await client.post("/api/v1/auth/login", data={
        "username": admin_user.email,
        "password": "admin123",
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest_asyncio.fixture()
async def manager_token(client, manager_user):
    resp = await client.post("/api/v1/auth/login", data={
        "username": manager_user.email,
        "password": "manager123",
    })
    assert resp.status_code == 200, f"Manager login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest_asyncio.fixture()
async def sales_rep_token(client, sales_rep_user):
    resp = await client.post("/api/v1/auth/login", data={
        "username": sales_rep_user.email,
        "password": "rep123",
    })
    assert resp.status_code == 200, f"Sales rep login failed: {resp.text}"
    return resp.json()["access_token"]


# ── Convenience header builder ────────────────────────────────────────────────

def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Mock external services globally for all tests ────────────────────────────
# Prevents any test from hitting Google APIs or Gemini.

@pytest.fixture(autouse=True)
def mock_google_sync():
    with patch("app.services.google_sync.sync_appointment_to_calendar", new_callable=AsyncMock) as m1, \
         patch("app.services.google_sync.sync_task_to_google", new_callable=AsyncMock) as m2:
        yield m1, m2


@pytest.fixture(autouse=True)
def mock_gemini():
    from io import BytesIO
    fake_docx = BytesIO(b"fake docx content")

    with patch("app.api.v1.reports.generate_lead_journey_report", new_callable=AsyncMock) as m1, \
         patch("app.api.v1.reports.generate_periodic_leads_report", new_callable=AsyncMock) as m2, \
         patch("app.api.v1.reports.generate_user_performance_report", new_callable=AsyncMock) as m3, \
         patch("app.api.v1.reports.generate_team_performance_report", new_callable=AsyncMock) as m4, \
         patch("app.api.v1.reports.build_docx_report") as m5:
        m1.return_value = "AI narrative for lead journey."
        m2.return_value = "AI narrative for periodic leads."
        m3.return_value = "AI narrative for user performance."
        m4.return_value = "AI narrative for team performance."
        m5.return_value = BytesIO(b"fake docx content")
        yield m1, m2, m3, m4, m5


@pytest.fixture(autouse=True, scope="session")
def disable_rate_limiters():
    """Disable slowapi rate limiters for the test session."""
    from app.main import limiter as main_limiter
    from app.api.v1.auth import limiter as auth_limiter
    main_limiter.enabled = False
    auth_limiter.enabled = False
    yield
