"""
Deterministic patient simulator.

Maps each FSM node to a templated response from the scenario's
patient_responses dict.  No LLM calls — pure string substitution.
"""

from backend.evals.scenarios import Scenario
from backend.session.models import IntakeState


def get_response(
    scenario: Scenario,
    current_node: str,
    turn_count: int,
    confirmation_visits: int = 0,
) -> str:
    """Return the deterministic patient response for the given node.

    *confirmation_visits* tracks how many times we have visited the
    confirmation node so that correction responses are sent only once.
    """
    if current_node in (IntakeState.COMPLETE.value, IntakeState.SUMMARY.value, IntakeState.HANDOFF.value):
        return ""

    if current_node == IntakeState.CONFIRMATION.value:
        correction = scenario.patient_responses.get("confirmation", "")
        if confirmation_visits == 0 and correction and correction.lower().startswith("no"):
            return correction
        return "yes"

    return scenario.patient_responses.get(current_node, "")
