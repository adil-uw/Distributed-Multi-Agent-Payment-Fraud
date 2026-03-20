from typing import Literal, Optional

from coordinator_service.schemas import AgentFanOutResult

AGENT_WEIGHTS: dict[str, float] = {
    "behavioral": 0.30,
    "geo": 0.20,
    "merchant": 0.20,
    "history": 0.30,
}

Decision = Literal["APPROVE", "CHALLENGE", "DECLINE"]


def _is_timeout_error(error: Optional[str]) -> bool:
    if not error:
        return False
    lowered = error.lower()
    return "timed out" in lowered or "timeout" in lowered


def _classify_slot(
    result: AgentFanOutResult,
) -> tuple[bool, bool]:
    """
    Returns (is_missing, is_failed). At most one should be True.
    missing = coordinator-side timeout waiting for the agent.
    failed = agent error, HTTP error, bad payload, or agent status == failed.
    """
    if not result.success:
        if _is_timeout_error(result.error):
            return True, False
        return False, True
    if result.data is not None and result.data.status == "failed":
        return False, True
    return False, False


def partition_agents(
    results: list[AgentFanOutResult],
) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    failed: list[str] = []
    for r in results:
        is_missing, is_failed = _classify_slot(r)
        if is_missing:
            missing.append(r.agent)
        elif is_failed:
            failed.append(r.agent)
    return missing, failed


def weighted_final_risk_score(results: list[AgentFanOutResult]) -> float:
    """Renormalized weighted mean over agents that returned status success."""
    numerator = 0.0
    denominator = 0.0
    for r in results:
        if r.success and r.data is not None and r.data.status == "success":
            w = AGENT_WEIGHTS[r.agent]
            numerator += w * r.data.risk_score
            denominator += w
    if denominator == 0:
        return 1.0
    return numerator / denominator


def decision_from_score(score: float) -> Decision:
    if score >= 0.8:
        return "DECLINE"
    if score >= 0.5:
        return "CHALLENGE"
    return "APPROVE"


def aggregate(results: list[AgentFanOutResult]) -> tuple[float, Decision, list[str], list[str]]:
    score = weighted_final_risk_score(results)
    missing, failed = partition_agents(results)
    decision = decision_from_score(score)
    return round(score, 4), decision, missing, failed
