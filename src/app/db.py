# src/app/db.py
from __future__ import annotations
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.settings import settings

# Create async engine (no sslmode for local asyncpg)
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ✅ IMPORTANT: plain async generator (NO @asynccontextmanager)
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            # SessionLocal context handles close; this block is just explicit
            await session.close()
