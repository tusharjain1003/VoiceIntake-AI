#!/usr/bin/env python3
"""
Eval harness for the VoiceIntake text-only FSM.

Usage:
    python -m backend.evals.run_evals --runs 50
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.evals.metrics import EvalRunResult, EvalSummary, TurnRecord, compute_metrics
from backend.evals.patient_simulator import get_response
from backend.evals.scenarios import SCENARIOS, validate_scenarios
from backend.fsm.runner import run_turn
from backend.session.models import ExtractedFields, IntakeState

_SAFE_REPLACEMENT_SIGNATURE = "I've noted that for the care team"


def _extract_field_value(fields: ExtractedFields, name: str) -> str:
    fv = getattr(fields, name, None)
    if fv is None:
        return ""
    return fv.value


def _fields_dict(fields: ExtractedFields) -> dict[str, str]:
    out = {}
    for name in (
        "patient_name",
        "date_of_birth",
        "chief_complaint",
        "symptoms",
        "symptom_duration",
        "medical_history",
        "allergies",
        "medications",
        "visit_reason",
    ):
        val = _extract_field_value(fields, name)
        if val:
            out[name] = val
    return out


def _detect_unsafe(message: str) -> bool:
    return _SAFE_REPLACEMENT_SIGNATURE in message


MAX_TURNS = 50


def simulate_scenario(scenario) -> EvalRunResult:
    fields = ExtractedFields()
    retries: dict[str, int] = {}
    current_node = IntakeState.GREETING.value
    turns: list[TurnRecord] = []
    total_timings: list[float] = []
    total_fsm_ms = 0.0
    safe_replaced = False
    confirmation_visits = 0
    last_result = None

    any_handoff = False
    any_escalation = False
    max_severity: Optional[str] = None
    max_flag: Optional[str] = None

    for _ in range(MAX_TURNS):
        message = get_response(scenario, current_node, len(turns), confirmation_visits)

        start = time.perf_counter()
        result = run_turn(
            current_node_name=current_node,
            message=message,
            fields=fields,
            retry_count_by_node=retries,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        last_result = result

        if result.handoff_triggered:
            any_handoff = True
        if result.handoff_triggered or result.red_flag_severity:
            any_escalation = True
            if result.red_flag_severity == "CRITICAL":
                max_severity = "CRITICAL"
                max_flag = result.red_flag_id
            elif max_severity != "CRITICAL" and result.red_flag_severity == "HIGH":
                max_severity = "HIGH"
                max_flag = result.red_flag_id

        total_fsm_ms += elapsed_ms
        total_timings.append(elapsed_ms)

        assistant_msg = result.assistant_message
        if _detect_unsafe(assistant_msg):
            safe_replaced = True

        turns.append(
            TurnRecord(
                node=current_node,
                assistant_message=assistant_msg[:200],
                fsm_ms=elapsed_ms,
            )
        )

        if current_node == IntakeState.CONFIRMATION.value:
            confirmation_visits += 1

        fields = result.fields
        retries = result.retry_count_by_node or retries
        current_node = result.next_node

        if result.call_complete or current_node is None:
            break

    extracted = _fields_dict(fields)

    run_result = EvalRunResult(
        scenario_name=scenario.name,
        completed=(
            current_node == IntakeState.COMPLETE.value
            or (last_result is not None and last_result.call_complete)
        ),
        handoff_triggered=any_handoff,
        escalation_triggered=any_escalation,
        escalation_severity=max_severity,
        escalation_flag=max_flag,
        safe_response_replaced=safe_replaced,
        turns=turns,
        total_fsm_ms=total_fsm_ms,
        turn_timings_ms=total_timings,
        fields_extracted=extracted,
        expected_fields=scenario.expected_fields,
    )

    run_result.expected_escalation = scenario.expect_escalation
    run_result.unexpected_handoff = any_handoff and not scenario.expect_escalation
    run_result.expected_handoff_missed = scenario.expect_handoff and not any_handoff

    return run_result


def print_table(summary: EvalSummary) -> None:
    header = f"{'Metric':<40} {'Value':>15}"
    sep = "-" * 55
    lines = [sep, header, sep]
    lines.append(f"{'Total runs':<40} {summary.total_runs:>15}")
    lines.append(f"{'Total scenarios':<40} {summary.total_scenarios:>15}")
    lines.append(f"{'Completion rate':<40} {summary.completion_rate:>14.1%}")
    lines.append(f"{'Handoff rate':<40} {summary.handoff_rate:>14.1%}")
    lines.append(f"{'Escalation count':<40} {summary.escalation_count:>15}")
    lines.append(f"{'Escalation precision':<40} {summary.escalation_precision:>14.1%}")
    lines.append(f"{'Escalation recall':<40} {summary.escalation_recall:>14.1%}")
    lines.append(f"{'Field extraction accuracy':<40} {summary.field_accuracy:>14.1%}")
    lines.append(f"{'Unsafe response rate':<40} {summary.unsafe_response_rate:>14.1%}")
    lines.append(f"{'Average turn latency (ms)':<40} {summary.avg_latency_ms:>14.2f}")
    lines.append(f"{'P95 turn latency (ms)':<40} {summary.p95_latency_ms:>14.2f}")
    lines.append(f"{'Latency std dev (ms)':<40} {summary.stdev_latency_ms:>14.2f}")
    lines.append(sep)

    lines.append("")
    lines.append(f"{'Scenario breakdown':^55}")
    lines.append(sep)
    lines.append(f"{'Scenario':<35} {'Runs':>6} {'Compl%':>7} {'Field%':>7}")
    lines.append(sep)

    by_scenario: dict[str, list[EvalRunResult]] = {}
    for r in summary.results:
        by_scenario.setdefault(r.scenario_name, []).append(r)

    for sname, runs in sorted(by_scenario.items()):
        n = len(runs)
        compl = sum(1 for r in runs if r.completed) / n
        total_f = sum(len(r.field_matches) for r in runs)
        correct_f = sum(sum(1 for v in r.field_matches.values() if v) for r in runs)
        f_acc = correct_f / total_f if total_f > 0 else 0.0
        lines.append(f"{sname:<35} {n:>6} {compl:>6.0%} {f_acc:>7.1%}")

    lines.append(sep)
    print("\n".join(lines))


def write_report(summary: EvalSummary, path: str) -> None:
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# Eval Report",
        "",
        f"Generated: {timestamp}",
        f"Total runs: {summary.total_runs}  |  Scenarios: {summary.total_scenarios}",
        "",
        "## Aggregated Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Completion rate | {summary.completion_rate:.1%} |",
        f"| Handoff rate | {summary.handoff_rate:.1%} |",
        f"| Escalation count | {summary.escalation_count} |",
        f"| Escalation precision | {summary.escalation_precision:.1%} |",
        f"| Escalation recall | {summary.escalation_recall:.1%} |",
        f"| Field extraction accuracy | {summary.field_accuracy:.1%} |",
        f"| Unsafe response rate | {summary.unsafe_response_rate:.1%} |",
        f"| Average turn latency (ms) | {summary.avg_latency_ms:.2f} |",
        f"| P95 turn latency (ms) | {summary.p95_latency_ms:.2f} |",
        f"| Latency std dev (ms) | {summary.stdev_latency_ms:.2f} |",
        "",
        (
            "Latency values in this report are text-only FSM simulation timings. "
            "They do not include browser microphone capture, Deepgram STT, network latency, "
            "LLM calls, or ElevenLabs TTS."
        ),
        "",
        (
            "CRITICAL red-flag scenarios intentionally prioritize immediate handoff over "
            "collecting every remaining intake field. Lower field accuracy in those scenarios "
            "is expected when escalation occurs before later nodes are visited."
        ),
        "",
        "## Scenario Breakdown",
        "",
        "| Scenario | Runs | Completion Rate | Field Accuracy | Handoffs | Escalations |",
        "|----------|------|----------------|----------------|----------|-------------|",
    ]

    by_scenario: dict[str, list[EvalRunResult]] = {}
    for r in summary.results:
        by_scenario.setdefault(r.scenario_name, []).append(r)

    for sname, runs in sorted(by_scenario.items()):
        n = len(runs)
        compl = sum(1 for r in runs if r.completed) / n
        total_f = sum(len(r.field_matches) for r in runs)
        correct_f = sum(sum(1 for v in r.field_matches.values() if v) for r in runs)
        f_acc = correct_f / total_f if total_f > 0 else 0.0
        handoffs = sum(1 for r in runs if r.handoff_triggered)
        escs = sum(1 for r in runs if r.escalation_triggered)
        lines.append(f"| {sname} | {n} | {compl:.0%} | {f_acc:.1%} | {handoffs} | {escs} |")

    lines.append("")
    lines.append("## Confusion Matrix (Escalation)")
    lines.append("")
    lines.append(f"- True positives: {summary.true_positives}")
    lines.append(f"- False positives: {summary.false_positives}")
    lines.append(f"- False negatives: {summary.false_negatives}")
    lines.append(f"- True negatives: {summary.true_negatives}")
    lines.append("")

    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"\nReport written to {path}")


def write_json(results: list[EvalRunResult], summary: EvalSummary, path: str) -> None:
    data = {
        "summary": {
            "total_runs": summary.total_runs,
            "total_scenarios": summary.total_scenarios,
            "completion_rate": summary.completion_rate,
            "handoff_rate": summary.handoff_rate,
            "escalation_count": summary.escalation_count,
            "escalation_precision": summary.escalation_precision,
            "escalation_recall": summary.escalation_recall,
            "field_accuracy": summary.field_accuracy,
            "unsafe_response_rate": summary.unsafe_response_rate,
            "avg_latency_ms": summary.avg_latency_ms,
            "p95_latency_ms": summary.p95_latency_ms,
            "latency_std_dev_ms": summary.stdev_latency_ms,
            "true_positives": summary.true_positives,
            "false_positives": summary.false_positives,
            "false_negatives": summary.false_negatives,
            "true_negatives": summary.true_negatives,
        },
        "results": [
            {
                "scenario": r.scenario_name,
                "completed": r.completed,
                "handoff_triggered": r.handoff_triggered,
                "escalation_triggered": r.escalation_triggered,
                "escalation_severity": r.escalation_severity,
                "escalation_flag": r.escalation_flag,
                "safe_response_replaced": r.safe_response_replaced,
                "total_fsm_ms": r.total_fsm_ms,
                "turn_count": len(r.turns),
                "fields_extracted": r.fields_extracted,
                "field_matches": r.field_matches,
                "unexpected_handoff": r.unexpected_handoff,
                "expected_handoff_missed": r.expected_handoff_missed,
            }
            for r in results
        ],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Results written to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="VoiceIntake eval harness")
    parser.add_argument("--runs", type=int, default=50, help="Number of runs per scenario")
    parser.add_argument("--output-dir", type=str, default="backend/evals", help="Output directory")
    args = parser.parse_args()

    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    results: list[EvalRunResult] = []

    validate_scenarios(SCENARIOS)

    for scenario in SCENARIOS:
        for run_idx in range(args.runs):
            result = simulate_scenario(scenario)
            results.append(result)

    summary = compute_metrics(results)
    print_table(summary)
    write_report(summary, os.path.join(output_dir, "EVAL_REPORT.md"))
    write_json(results, summary, os.path.join(output_dir, "eval_results.json"))

    sys.exit(0)


if __name__ == "__main__":
    main()
