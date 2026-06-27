#!/usr/bin/env python3
"""
Smoke test: verify Postgres persistence layer works end-to-end.

Starts a session, runs a complete intake scenario via the FSM runner,
persists every turn, then queries the audit tables to confirm data
landed correctly.

Requires Postgres to be running (docker-compose up -d).

Usage:
    PYTHONPATH=. uv run python -m backend.tests.smoke_persistence
"""

import asyncio
import logging
import sys

from sqlalchemy import delete, select

logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

_TEST_SESSION_ID = "smoke-test-persistence-000001"


async def main() -> None:
    print("=== Smoke Test: Postgres Persistence ===\n")

    # ------------------------------------------------------------------
    # 1. Bootstrap engine + repository
    # ------------------------------------------------------------------
    from backend.database import AsyncSessionLocal, async_engine, create_engine
    from backend.db import repository as repo
    from backend.db.migrate import run_migrations
    from backend.db.models import (
        EscalationEventRow,
        SessionRow,
        SummaryRow,
        TranscriptRow,
    )

    create_engine()
    if async_engine is None:
        print("FAIL: Could not create DB engine — is Postgres running?")
        sys.exit(1)
    await run_migrations(async_engine)
    repo.init_repository(AsyncSessionLocal)
    assert repo.is_available(), "Repository should be available"
    assert await repo.ping(), "DB ping should succeed"
    print("1. DB engine + repository initialised  ✓")

    # ------------------------------------------------------------------
    # 2. Run a complete intake scenario via the FSM runner
    # ------------------------------------------------------------------
    from backend.evals.patient_simulator import get_response
    from backend.evals.scenarios import SCENARIOS
    from backend.fsm.runner import run_turn
    from backend.session.models import ExtractedFields, IntakeState, SessionData

    scenario = [s for s in SCENARIOS if s.name == "standard_annual_checkup"][0]

    fields = ExtractedFields()
    retries: dict[str, int] = {}
    current_node = IntakeState.GREETING.value
    turn_count = 0

    session = SessionData(session_id=_TEST_SESSION_ID)

    turn_handoffs: list[bool] = []
    turn_escalations: list[bool] = []

    print(f"2. Running scenario '{scenario.name}' ...")

    for _ in range(50):
        message = get_response(scenario, current_node, turn_count, 0)
        if not message and current_node in {
            IntakeState.COMPLETE.value,
            IntakeState.SUMMARY.value,
            IntakeState.HANDOFF.value,
        }:
            break

        turn_count += 1
        result = run_turn(
            current_node_name=current_node,
            message=message,
            fields=fields,
            retry_count_by_node=retries,
            session_id=_TEST_SESSION_ID,
            turn_number=turn_count,
        )

        session.current_node = (
            IntakeState(result.next_node) if result.next_node else IntakeState.COMPLETE
        )
        session.extracted_fields = result.fields
        session.call_complete = result.call_complete
        if result.retry_count_by_node is not None:
            session.retry_count_by_node = result.retry_count_by_node
        session.handoff_triggered = result.handoff_triggered
        session.red_flag_severity = result.red_flag_severity
        session.red_flag_id = result.red_flag_id
        session.handoff_reason = result.handoff_reason

        await repo.save_session(session)
        await repo.save_transcript(_TEST_SESSION_ID, turn_count, "user", message)
        await repo.save_transcript(
            _TEST_SESSION_ID,
            turn_count,
            "assistant",
            result.assistant_message,
        )

        turn_handoffs.append(result.handoff_triggered)

        if result.guardrail_triggered:
            await repo.save_safety_event(
                _TEST_SESSION_ID,
                turn_count,
                category=result.guardrail_category or "",
                original_text=result.guardrail_original or "",
                replacement_text=result.assistant_message,
            )

        if result.handoff_triggered and result.red_flag_id:
            turn_escalations.append(True)
            await repo.save_escalation_event(
                _TEST_SESSION_ID,
                turn_count,
                rule_id=result.red_flag_id,
                severity=result.red_flag_severity or "HIGH",
                immediate_handoff=result.red_flag_severity == "CRITICAL",
            )
        else:
            turn_escalations.append(False)

        fields = result.fields
        retries = result.retry_count_by_node or retries
        current_node = result.next_node

        if result.call_complete or current_node is None:
            break

    if result.call_complete and result.final_summary:
        await repo.save_summary(_TEST_SESSION_ID, result.final_summary.model_dump())

    print(f"   Completed in {turn_count} turns  ✓")

    # ------------------------------------------------------------------
    # 3. Query the audit tables and verify
    # ------------------------------------------------------------------
    print("\n3. Verifying persistence in Postgres audit tables ...")

    async with AsyncSessionLocal() as db:
        sess_row = (
            await db.execute(select(SessionRow).where(SessionRow.session_id == _TEST_SESSION_ID))
        ).scalar_one_or_none()
        assert sess_row is not None, "SessionRow should exist"
        assert sess_row.turn_count == turn_count
        print(f"   sessions: turn_count={sess_row.turn_count}  ✓")

        trows = (
            (
                await db.execute(
                    select(TranscriptRow)
                    .where(TranscriptRow.session_id == _TEST_SESSION_ID)
                    .order_by(TranscriptRow.turn_number, TranscriptRow.role)
                )
            )
            .scalars()
            .all()
        )
        expected_transcripts = turn_count * 2
        actual_transcripts = len(trows)
        assert actual_transcripts == expected_transcripts, (
            f"Expected {expected_transcripts} transcript rows, got {actual_transcripts}"
        )
        print(f"   transcript_messages: {actual_transcripts} rows  ✓")

        if result.call_complete and result.final_summary:
            sum_row = (
                await db.execute(
                    select(SummaryRow).where(SummaryRow.session_id == _TEST_SESSION_ID)
                )
            ).scalar_one_or_none()
            assert sum_row is not None, "SummaryRow should exist"
            assert "patient_name" in sum_row.summary_data
            print(f"   summaries: patient_name={sum_row.summary_data.get('patient_name')}  ✓")

        esc_count = sum(1 for e in turn_escalations if e)
        if esc_count:
            erows = (
                (
                    await db.execute(
                        select(EscalationEventRow).where(
                            EscalationEventRow.session_id == _TEST_SESSION_ID
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(erows) == esc_count
            print(f"   escalation_events: {len(erows)} rows  ✓")

    print("\n4. All persistence checks passed!  ✓")

    # ------------------------------------------------------------------
    # 5. Cleanup test data
    # ------------------------------------------------------------------
    async with AsyncSessionLocal() as db:
        for model in (SummaryRow, EscalationEventRow, TranscriptRow, SessionRow):
            await db.execute(delete(model).where(model.session_id == _TEST_SESSION_ID))
        await db.commit()
    print("5. Cleaned up test data  ✓")
    print("\n=== All smoke tests passed! ===")


if __name__ == "__main__":
    asyncio.run(main())
