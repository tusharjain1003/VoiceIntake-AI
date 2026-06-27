"""
Async SQLAlchemy engine + session factory and Redis connection pool.

Initialised at application startup via init_db() / init_redis().
"""

import logging

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.config import settings

logger = logging.getLogger(__name__)

async_engine = None
AsyncSessionLocal = None
redis_client: Redis | None = None


def create_engine() -> None:
    global async_engine, AsyncSessionLocal
    if async_engine is not None:
        return
    async_engine = create_async_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )
    AsyncSessionLocal = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    logger.info("SQLAlchemy async engine created (pool_size=5, max_overflow=10)")


async def close_engine() -> None:
    global async_engine, AsyncSessionLocal
    if async_engine is not None:
        await async_engine.dispose()
        async_engine = None
        AsyncSessionLocal = None
        logger.info("SQLAlchemy async engine disposed")


async def get_db() -> AsyncSession:
    if AsyncSessionLocal is None:
        create_engine()
    session = AsyncSessionLocal()
    try:
        yield session
    finally:
        await session.close()


async def init_redis() -> None:
    global redis_client
    if redis_client is not None:
        return
    redis_client = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    await redis_client.ping()
    logger.info("Redis connected")


async def close_redis() -> None:
    global redis_client
    if redis_client is not None:
        await redis_client.aclose()
        redis_client = None
        logger.info("Redis connection closed")
