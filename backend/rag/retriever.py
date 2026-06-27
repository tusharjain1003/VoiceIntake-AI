"""
pgvector-based semantic retriever.

Returns the top-k most similar document chunks for a given query text,
filtered by category.
"""

import logging

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import DocumentChunk

logger = logging.getLogger(__name__)


async def retrieve(
    db: AsyncSession,
    query_embedding: list[float],
    category: str,
    top_k: int = 2,
) -> list[dict]:
    """Return up to *top_k* chunks in *category* ordered by cosine distance."""
    vec_literal = f"[{','.join(str(v) for v in query_embedding)}]"

    stmt = (
        select(
            DocumentChunk.id,
            DocumentChunk.source,
            DocumentChunk.chunk_index,
            DocumentChunk.text,
            DocumentChunk.embedding.cosine_distance(vec_literal).label("distance"),
        )
        .where(DocumentChunk.category == category)
        .where(DocumentChunk.embedding.isnot(None))
        .order_by(text("distance"))
        .limit(top_k)
    )

    rows = await db.execute(stmt)
    results = []
    for row in rows:
        results.append(
            {
                "id": row.id,
                "source": row.source,
                "chunk_index": row.chunk_index,
                "text": row.text,
            }
        )
    return results


async def retrieve_all_categories(
    db: AsyncSession,
    query_embedding: list[float],
    top_k_per_category: int = 2,
) -> dict[str, list[dict]]:
    """Run retrieval across all three KB categories."""
    categories = ["intake_template", "red_flag", "clinic_policy"]
    result = {}
    for cat in categories:
        hits = await retrieve(db, query_embedding, cat, top_k=top_k_per_category)
        if hits:
            result[cat] = hits
    return result
