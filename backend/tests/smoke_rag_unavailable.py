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


class _SessionCallRaises:
    def __call__(self):
        raise RuntimeError("secret database url should not appear")


class _SessionEnterRaises:
    def __call__(self):
        return self

    async def __aenter__(self):
        raise RuntimeError("secret context failure should not appear")

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _assert_unavailable(ctx: dict | None, expected_error: str) -> bool:
    if ctx is None:
        print("FAIL: clinician_context is None, expected rag_status='unavailable'")
        return False
    if ctx.get("rag_status") != "unavailable":
        print(f"FAIL: rag_status={ctx.get('rag_status')!r}, expected 'unavailable'")
        return False
    if ctx.get("rag_error") != expected_error:
        print(f"FAIL: rag_error={ctx.get('rag_error')!r}, expected {expected_error!r}")
        return False
    if any("secret" in str(value).lower() for value in ctx.values()):
        print(f"FAIL: clinician_context leaked exception detail: {ctx}")
        return False
    print(f"PASS: rag_status=unavailable, rag_error={ctx.get('rag_error')!r}")
    return True


async def main() -> None:
    from backend.rag.enrich import enrich_summary_with_rag
    from backend.session.models import ExtractedFields, PreVisitSummary

    fields = ExtractedFields()

    # ------------------------------------------------------------------
    # Case 1: embedding succeeds, but AsyncSessionLocal is None
    # ------------------------------------------------------------------
    print("--- Case 1: db_unavailable ---")
    summary = PreVisitSummary(patient_name="Test Patient", chief_complaint="cough")

    with patch("backend.rag.enrich.embed", new_callable=AsyncMock) as mock_embed:
        mock_embed.return_value = [0.1, 0.2, 0.3]
        with patch("backend.rag.enrich.AsyncSessionLocal", None):
            try:
                await enrich_summary_with_rag(summary, fields)
            except Exception as exc:
                print(f"FAIL: enrich_summary_with_rag raised {exc}")
                return 1

    if not _assert_unavailable(summary.clinician_context, "db_unavailable"):
        return 1

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

    if not _assert_unavailable(summary2.clinician_context, "embedding_failed"):
        return 1

    # ------------------------------------------------------------------
    # Case 3: AsyncSessionLocal() itself raises
    # ------------------------------------------------------------------
    print("--- Case 3: session_call_raises ---")
    summary3 = PreVisitSummary(patient_name="Test Patient", chief_complaint="cough")

    with patch("backend.rag.enrich.embed", new_callable=AsyncMock) as mock_embed:
        mock_embed.return_value = [0.1, 0.2, 0.3]
        with patch("backend.rag.enrich.AsyncSessionLocal", _SessionCallRaises()):
            try:
                await enrich_summary_with_rag(summary3, fields)
            except Exception as exc:
                print(f"FAIL: enrich_summary_with_rag raised {exc}")
                return 1

    if not _assert_unavailable(summary3.clinician_context, "retrieval_failed"):
        return 1

    # ------------------------------------------------------------------
    # Case 4: AsyncSessionLocal().__aenter__ raises
    # ------------------------------------------------------------------
    print("--- Case 4: session_context_enter_raises ---")
    summary4 = PreVisitSummary(patient_name="Test Patient", chief_complaint="cough")

    with patch("backend.rag.enrich.embed", new_callable=AsyncMock) as mock_embed:
        mock_embed.return_value = [0.1, 0.2, 0.3]
        with patch("backend.rag.enrich.AsyncSessionLocal", _SessionEnterRaises()):
            try:
                await enrich_summary_with_rag(summary4, fields)
            except Exception as exc:
                print(f"FAIL: enrich_summary_with_rag raised {exc}")
                return 1

    if not _assert_unavailable(summary4.clinician_context, "retrieval_failed"):
        return 1

    print("All RAG-unavailable smoke tests passed.")
    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
