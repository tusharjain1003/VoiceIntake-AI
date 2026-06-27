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
    try:
        query_embedding = await embed(query)
    except Exception as exc:
        logger.warning("Embedding failed — skipping RAG enrichment: %s", exc)
        return

    async with AsyncSessionLocal() as db:
        try:
            results = await retrieve_all_categories(db, query_embedding, top_k_per_category=2)
        except Exception as exc:
            logger.warning("RAG retrieval failed — skipping enrichment: %s", exc)
            return

    if results:
        summary.clinician_context = results
