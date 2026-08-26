import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest_asyncio
from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from webhook_relay.api.dependencies import arq_pool_dependency
from webhook_relay.main import app
from webhook_relay.models import Base, Event, Subscription
from webhook_relay.models.session import get_db
from webhook_relay.security.hmac_signer import encrypt_secret

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5433/webhook_relay_test"
TEST_REDIS_URL = "redis://localhost:6380/0"


@pytest_asyncio.fixture
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    connection = await db_engine.connect()
    outer_transaction = await connection.begin()
    session = AsyncSession(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )

    try:
        yield session
    finally:
        await session.close()
        await outer_transaction.rollback()
        await connection.close()


@pytest_asyncio.fixture
async def arq_redis() -> AsyncGenerator[ArqRedis, None]:
    pool = await create_pool(RedisSettings.from_dsn(TEST_REDIS_URL))
    yield pool
    await pool.aclose()


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession, arq_redis: ArqRedis
) -> AsyncGenerator[httpx.AsyncClient, None]:
    async def override_get_db():
        yield db_session

    def override_arq_pool():
        return arq_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[arq_pool_dependency] = override_arq_pool

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


async def seed_subscription(
    session: AsyncSession,
    url: str = "http://mock-receiver/hook",
    event_types: list[str] | None = None,
    plain_secret: str = "whsec_test_secret",
    is_active: bool = True,
) -> Subscription:
    subscription = Subscription(
        id=uuid.uuid4(),
        url=url,
        event_types=event_types or ["order.created"],
        secret=encrypt_secret(plain_secret),
        is_active=is_active,
    )
    session.add(subscription)
    await session.flush()
    return subscription


async def seed_event(
    session: AsyncSession,
    event_type: str = "order.created",
    payload: dict | None = None,
    idempotency_key: str | None = None,
) -> Event:
    event = Event(
        id=uuid.uuid4(),
        event_type=event_type,
        payload=payload if payload is not None else {"foo": "bar"},
        idempotency_key=idempotency_key or str(uuid.uuid4()),
    )
    session.add(event)
    await session.flush()
    return event
