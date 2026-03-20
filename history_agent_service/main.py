import asyncio
import hashlib
import time
import uuid
from typing import Optional

from fastapi import FastAPI

from history_agent_service.schemas import AgentEvaluateResponse, TransactionEvaluateRequest

AGENT_NAME = "history"

app = FastAPI(
    title="History Agent",
    description="Mock rule-based payment history risk scoring (deterministic from user_id)",
)


def _mock_history_risk(user_id: str, payment_method: Optional[str]) -> tuple[float, str]:
    """
    Deterministic mock: same user_id always maps to the same band (no real DB).
    Buckets are driven by a hash so Postman tests vary by changing user_id slightly.
    """
    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 100

    if bucket < 18:
        score, reason = (
            0.83,
            "Mock history: elevated simulated chargeback/dispute rate for this profile",
        )
    elif bucket < 45:
        score, reason = (
            0.49,
            "Mock history: mixed simulated prior declines and approvals",
        )
    else:
        score, reason = (
            0.17,
            "Mock history: stable simulated on-time payment pattern",
        )

    extra = ""
    pm = (payment_method or "").strip().lower()
    if pm == "prepaid":
        score = min(1.0, score + 0.12)
        extra = " Prepaid instrument — mock incremental risk."

    return round(score, 4), reason + extra


@app.get("/health")
async def health():
    return {"status": "ok", "service": AGENT_NAME, "port": 8004}


@app.post("/evaluate", response_model=AgentEvaluateResponse)
async def evaluate(body: TransactionEvaluateRequest) -> AgentEvaluateResponse:
    start = time.perf_counter()

    if body.simulate_delay and body.delay_ms > 0:
        await asyncio.sleep(body.delay_ms / 1000.0)

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    tx_id = body.transaction_id or str(uuid.uuid4())

    if body.simulate_failure:
        return AgentEvaluateResponse(
            transaction_id=tx_id,
            agent_name=AGENT_NAME,
            risk_score=0.0,
            reason="Simulated failure (simulate_failure=true)",
            processing_time_ms=elapsed_ms,
            status="failed",
        )

    score, reason = _mock_history_risk(body.user_id, body.payment_method)
    return AgentEvaluateResponse(
        transaction_id=tx_id,
        agent_name=AGENT_NAME,
        risk_score=score,
        reason=reason,
        processing_time_ms=elapsed_ms,
        status="success",
    )
