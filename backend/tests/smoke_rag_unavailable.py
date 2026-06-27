"""
Smoke test: RAG enrichment degrades gracefully when the database is unavailable.

Monkeypatches AsyncSessionLocal to None and verifies that
enrich_summary_with_rag() returns with rag_status="unavailable"
instead of crashing.
"""

import asyncio
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, ".")


async def main() -> None:
    from backend.rag.enrich import enrich_summary_with_rag
    from backend.session.models import ExtractedFields, PreVisitSummary

    fields = ExtractedFields()

    # ------------------------------------------------------------------
    # Case 1: embedding succeeds, but AsyncSessionLocal is None
    # ------------------------------------------------------------------
    print("--- Case 1: db_unavailable ---")
    summary = PreVisitSummary(patient_name="Test Patient", chief_complaint="cough")

    import backend.database as db_mod

    original_session = db_mod.AsyncSessionLocal
    db_mod.AsyncSessionLocal = None

    with patch("backend.rag.enrich.embed", new_callable=AsyncMock) as mock_embed:
        mock_embed.return_value = [0.1, 0.2, 0.3]
        try:
            await enrich_summary_with_rag(summary, fields)
        except Exception as exc:
            db_mod.AsyncSessionLocal = original_session
            print(f"FAIL: enrich_summary_with_rag raised {exc}")
            return 1

    db_mod.AsyncSessionLocal = original_session

    ctx = summary.clinician_context
    if ctx is None:
        print("FAIL: clinician_context is None, expected rag_status='unavailable'")
        return 1
    if ctx.get("rag_status") != "unavailable":
        print(f"FAIL: rag_status={ctx.get('rag_status')!r}, expected 'unavailable'")
        return 1
    if ctx.get("rag_error") != "db_unavailable":
        print(f"FAIL: rag_error={ctx.get('rag_error')!r}, expected 'db_unavailable'")
        return 1
    print(f"PASS: rag_status=unavailable, rag_error={ctx.get('rag_error')!r}")

    # ------------------------------------------------------------------
    # Case 2: embedding itself fails (no API key)
    # ------------------------------------------------------------------
    print("--- Case 2: embedding_failed ---")
    summary2 = PreVisitSummary(patient_name="Test Patient", chief_complaint="cough")

    try:
        await enrich_summary_with_rag(summary2, fields)
    except Exception as exc:
        print(f"FAIL: enrich_summary_with_rag raised {exc}")
        return 1

    ctx2 = summary2.clinician_context
    if ctx2 is None:
        print("FAIL: clinician_context is None (expected unavailable after embedding fail)")
        return 1
    if ctx2.get("rag_status") != "unavailable":
        print(f"FAIL: rag_status={ctx2.get('rag_status')!r}, expected 'unavailable'")
        return 1
    if ctx2.get("rag_error") != "embedding_failed":
        print(f"FAIL: rag_error={ctx2.get('rag_error')!r}, expected 'embedding_failed'")
        return 1
    print(f"PASS: rag_status=unavailable, rag_error={ctx2.get('rag_error')!r}")

    print("All RAG-unavailable smoke tests passed.")
    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
