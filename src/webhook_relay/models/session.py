from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from webhook_relay.config import Environment, settings

engine = create_async_engine(
    settings.database_url.get_secret_value(),
    echo=settings.debug,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={"ssl": "require"} if settings.env == Environment.PRODUCTION else {},
)

SessionLocal = async_sessionmaker(engine, autocommit=False, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
