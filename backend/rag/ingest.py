"""
CLI entrypoint: ``python -m backend.rag.ingest``

Reads all documents from ``knowledge_base/``, splits into chunks,
embeds them via OpenAI, and stores in pgvector.
"""

import asyncio
import json
import logging
import pathlib

from sqlalchemy import delete

from backend.config import settings
from backend.database import AsyncSessionLocal, async_engine, close_engine, create_engine
from backend.db.migrate import run_migrations
from backend.db.models import DocumentChunk
from backend.rag.embedder import embed_batch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag.ingest")

_KB_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent / "knowledge_base"

_CATEGORY_MAP: dict[str, str] = {
    "intake_templates": "intake_template",
    "symptom_redflags": "red_flag",
    "clinic_policy": "clinic_policy",
}


def _chunk_text(text: str) -> list[str]:
    """Split text on double newlines; return non-empty stripped paragraphs."""
    chunks = [p.strip() for p in text.split("\n\n") if p.strip()]
    # Further split very long paragraphs (> 1000 chars) on sentence boundaries
    result = []
    for chunk in chunks:
        if len(chunk) > 1000:
            sentences = chunk.replace("\n", " ").split(". ")
            buf = ""
            for sent in sentences:
                if len(buf) + len(sent) < 1000:
                    buf += (". " if buf else "") + sent
                else:
                    if buf:
                        result.append(buf.strip() + ".")
                    buf = sent
            if buf:
                result.append(buf.strip() + ".")
        else:
            result.append(chunk)
    return result


async def ingest_all() -> None:
    """Main ingestion routine."""
    create_engine()
    if async_engine is None:
        logger.error("No engine available")
        return

    await run_migrations(async_engine)

    if not settings.openai_api_key:
        logger.error("OPENAI_API_KEY not set — skipping embedding. Set it in .env")
        return

    all_chunks: list[tuple[str, str, int, str]] = []  # (source, category, idx, text)

    # Walk knowledge_base directories
    if not _KB_ROOT.is_dir():
        logger.warning("knowledge_base/ not found at %s", _KB_ROOT)
        return

    for kb_dir in sorted(_KB_ROOT.iterdir()):
        if not kb_dir.is_dir():
            continue
        category = _CATEGORY_MAP.get(kb_dir.name)
        if category is None:
            logger.warning("Unknown KB directory: %s — skipping", kb_dir.name)
            continue

        for fpath in sorted(kb_dir.iterdir()):
            if fpath.suffix in (".md", ".txt", ".json"):
                logger.info("Reading %s", fpath)
                raw = fpath.read_text(encoding="utf-8")

                if fpath.suffix == ".json":
                    data = json.loads(raw)
                    flags = data.get("flags", data) if isinstance(data, dict) else data
                    for i, flag in enumerate(flags):
                        if isinstance(flag, dict):
                            text = (
                                f"# {flag.get('label', flag.get('id', 'Unknown'))}\n\n"
                                f"Severity: {flag.get('severity', 'N/A')}\n"
                                f"Description: {flag.get('description', '')}\n"
                                f"Keywords: {', '.join(flag.get('keywords', []))}\n"
                            )
                            all_chunks.append((str(fpath.relative_to(_KB_ROOT)), category, i, text))
                else:
                    chunks = _chunk_text(raw)
                    for i, text in enumerate(chunks):
                        all_chunks.append((str(fpath.relative_to(_KB_ROOT)), category, i, text))

    if not all_chunks:
        logger.warning("No chunks found to ingest")
        return

    logger.info("Total chunks to embed: %d", len(all_chunks))

    # Clear existing chunks
    async with AsyncSessionLocal() as db:
        await db.execute(delete(DocumentChunk))
        await db.commit()
    logger.info("Cleared existing document chunks")

    # Embed in batches
    texts = [chunk[3] for chunk in all_chunks]
    batch_size = 20
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        total_batches = (len(texts) - 1) // batch_size + 1
        logger.info("Embedding batch %d/%d", start // batch_size + 1, total_batches)
        embeddings = await embed_batch(batch)
        async with AsyncSessionLocal() as db:
            for (source, category, idx, text), emb in zip(
                all_chunks[start : start + batch_size], embeddings
            ):
                db.add(
                    DocumentChunk(
                        source=source,
                        category=category,
                        chunk_index=idx,
                        text=text,
                        embedding=emb,
                    )
                )
            await db.commit()
        logger.info("  Stored %d chunks", len(embeddings))

    logger.info("Ingestion complete — %d chunks stored", len(all_chunks))
    await close_engine()


if __name__ == "__main__":
    asyncio.run(ingest_all())
