"""
OpenAI embedding client.

Configurable via settings.embedding_model and settings.embedding_dimensions.
"""

import logging
from typing import Optional

from openai import AsyncOpenAI

from backend.config import settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenAI] = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def embed(text: str) -> list[float]:
    client = get_client()
    resp = await client.embeddings.create(
        model=settings.embedding_model,
        input=text,
        dimensions=settings.embedding_dimensions,
    )
    return resp.data[0].embedding


async def embed_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    client = get_client()
    resp = await client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
        dimensions=settings.embedding_dimensions,
    )
    sorted_data = sorted(resp.data, key=lambda d: d.index)
    return [d.embedding for d in sorted_data]
