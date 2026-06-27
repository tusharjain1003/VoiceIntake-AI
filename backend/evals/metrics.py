"""Aggregate metrics for eval runs."""

from dataclasses import dataclass, field
from statistics import stdev
from typing import Optional


@dataclass
class TurnRecord:
    node: str
    assistant_message: str
    fsm_ms: float = 0.0


@dataclass
class EvalRunResult:
    scenario_name: str
    completed: bool
    handoff_triggered: bool
    escalation_triggered: bool
    escalation_severity: Optional[str] = None
    escalation_flag: Optional[str] = None
    safe_response_replaced: bool = False
    turns: list[TurnRecord] = field(default_factory=list)
    total_fsm_ms: float = 0.0
    turn_timings_ms: list[float] = field(default_factory=list)
    fields_extracted: dict[str, str] = field(default_factory=dict)
    expected_fields: dict[str, str] = field(default_factory=dict)
    field_matches: dict[str, bool] = field(default_factory=dict)
    unexpected_handoff: bool = False
    expected_handoff_missed: bool = False
    expected_escalation: bool = False


@dataclass
class EvalSummary:
    total_scenarios: int = 0
    total_runs: int = 0
    completion_count: int = 0
    handoff_count: int = 0
    escalation_count: int = 0
    unsafe_response_count: int = 0
    field_accuracy_total: int = 0
    field_accuracy_correct: int = 0
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    true_negatives: int = 0
    all_turn_timings_ms: list[float] = field(default_factory=list)
    results: list[EvalRunResult] = field(default_factory=list)

    @property
    def completion_rate(self) -> float:
        if self.total_runs == 0:
            return 0.0
        return self.completion_count / self.total_runs

    @property
    def handoff_rate(self) -> float:
        if self.total_runs == 0:
            return 0.0
        return self.handoff_count / self.total_runs

    @property
    def field_accuracy(self) -> float:
        if self.field_accuracy_total == 0:
            return 0.0
        return self.field_accuracy_correct / self.field_accuracy_total

    @property
    def escalation_precision(self) -> float:
        denom = self.true_positives + self.false_positives
        if denom == 0:
            return 0.0
        return self.true_positives / denom

    @property
    def escalation_recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        if denom == 0:
            return 0.0
        return self.true_positives / denom

    @property
    def unsafe_response_rate(self) -> float:
        if self.total_runs == 0:
            return 0.0
        return self.unsafe_response_count / self.total_runs

    @property
    def avg_latency_ms(self) -> float:
        if not self.all_turn_timings_ms:
            return 0.0
        return sum(self.all_turn_timings_ms) / len(self.all_turn_timings_ms)

    @property
    def p95_latency_ms(self) -> float:
        sorted_ = sorted(self.all_turn_timings_ms)
        if not sorted_:
            return 0.0
        idx = int(len(sorted_) * 0.95)
        return sorted_[idx]

    @property
    def stdev_latency_ms(self) -> float:
        if len(self.all_turn_timings_ms) < 2:
            return 0.0
        return stdev(self.all_turn_timings_ms)


def compute_metrics(results: list[EvalRunResult]) -> EvalSummary:
    summary = EvalSummary()
    summary.results = results
    summary.total_runs = len(results)

    seen_scenarios = set()
    for r in results:
        seen_scenarios.add(r.scenario_name)
        if r.completed:
            summary.completion_count += 1
        if r.handoff_triggered:
            summary.handoff_count += 1
        if r.escalation_triggered:
            summary.escalation_count += 1
        if r.safe_response_replaced:
            summary.unsafe_response_count += 1
        summary.all_turn_timings_ms.extend(r.turn_timings_ms)

        # Field accuracy
        for field_name, expected_val in r.expected_fields.items():
            actual_val = r.fields_extracted.get(field_name, "")
            match = actual_val == expected_val
            r.field_matches[field_name] = match
            summary.field_accuracy_total += 1
            if match:
                summary.field_accuracy_correct += 1

        # Escalation confusion matrix
        expected_esc = r.expected_escalation
        actual_esc = r.escalation_triggered
        if expected_esc and actual_esc:
            summary.true_positives += 1
        elif not expected_esc and actual_esc:
            summary.false_positives += 1
        elif expected_esc and not actual_esc:
            summary.false_negatives += 1
        else:
            summary.true_negatives += 1

    summary.total_scenarios = len(seen_scenarios)
    return summary
