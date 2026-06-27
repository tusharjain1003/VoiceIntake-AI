"""
Create all tables and enable the pgvector extension on startup.

Idempotent — safe to call every time the application starts.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from backend.db.models import Base

logger = logging.getLogger(__name__)


async def run_migrations(engine: AsyncEngine) -> None:
    """Enable pgvector extension and create all tables if they don't exist."""
    async with engine.connect() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.commit()
        logger.info("pgvector extension enabled")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("All database tables created")
