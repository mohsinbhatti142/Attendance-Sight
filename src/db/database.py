"""Database connection and session management."""
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from src.core.config import get_settings

settings = get_settings()

is_sqlite = settings.database_url.startswith("sqlite")
engine_kwargs = {"echo": settings.database_echo}
if not is_sqlite:
    engine_kwargs.update({
        "pool_size": 20,
        "max_overflow": 10,
        "pool_pre_ping": True,
    })

engine = create_async_engine(
    settings.database_url,
    **engine_kwargs
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


async def get_db() -> AsyncSession:
    """Dependency to get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        columns = await conn.run_sync(
            lambda sync_connection: {
                column["name"]
                for column in inspect(sync_connection).get_columns("admin_users")
            }
        )
        if "email_verified" not in columns:
            await conn.execute(
                text(
                    "ALTER TABLE admin_users "
                    "ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
        if "session_version" not in columns:
            await conn.execute(
                text(
                    "ALTER TABLE admin_users "
                    "ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0"
                )
            )
