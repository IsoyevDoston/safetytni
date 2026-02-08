"""Database configuration and session management."""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config import settings


# Create async engine using DATABASE_URL / motive DB URL
engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
)

# Async session factory
async_session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False
)


async def get_session() -> AsyncSession:
    """Utility to get a new AsyncSession (primarily for scripts/tests)."""
    return async_session_maker()

