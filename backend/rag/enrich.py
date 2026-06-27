"""
Enrich a PreVisitSummary with clinician-facing RAG context.

Called from the WS handler and REST endpoint when a session completes.
RAG output goes into ``summary.clinician_context`` and is never spoken
to the patient.
"""

import logging

from backend.database import AsyncSessionLocal
from backend.rag.embedder import embed
from backend.rag.retriever import retrieve_all_categories
from backend.session.models import ExtractedFields, PreVisitSummary
from backend.tracing.langsmith import Trace

logger = logging.getLogger(__name__)


def _build_query(fields: ExtractedFields) -> str:
    parts = []
    if fields.chief_complaint:
        parts.append(f"Chief complaint: {fields.chief_complaint.value}")
    if fields.symptoms:
        parts.append(f"Symptoms: {fields.symptoms.value}")
    if fields.symptom_duration:
        parts.append(f"Duration: {fields.symptom_duration.value}")
    if fields.medical_history:
        parts.append(f"Medical history: {fields.medical_history.value}")
    if fields.visit_reason:
        parts.append(f"Visit reason: {fields.visit_reason.value}")
    return "\n".join(parts) if parts else "standard intake"


async def enrich_summary_with_rag(
    summary: PreVisitSummary,
    fields: ExtractedFields,
) -> None:
    """Run RAG retrieval and attach clinician_context to *summary*."""
    query = _build_query(fields)
    query_embedding = None

    fields_summary = {k: str(v) for k, v in fields.model_dump().items() if v is not None}
    trace = Trace(
        "rag_enrichment",
        "chain",
        inputs={"query": query, "fields_summary": fields_summary},
    )

    try:
        query_embedding = await embed(query)
        trace.child(
            "embedding",
            "llm",
            inputs={"model": "text-embedding-3-small", "text": query[:500]},
        )
    except Exception as exc:
        logger.warning("Embedding failed — skipping RAG enrichment: %s", exc)
        trace.finish(outputs={"status": "failed", "error": str(exc), "stage": "embedding"})
        return

    async with AsyncSessionLocal() as db:
        try:
            results = await retrieve_all_categories(db, query_embedding, top_k_per_category=2)
        except Exception as exc:
            logger.warning("RAG retrieval failed — skipping enrichment: %s", exc)
            trace.finish(outputs={"status": "failed", "error": str(exc), "stage": "retrieval"})
            return

    if results:
        summary.clinician_context = results
        trace.finish(
            outputs={
                "status": "success",
                "categories_found": list(results.keys()),
                "total_chunks": sum(len(v) for v in results.values()),
            }
        )
    else:
        trace.finish(outputs={"status": "success", "categories_found": [], "total_chunks": 0})
