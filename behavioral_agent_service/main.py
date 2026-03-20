import asyncio
import time
import uuid

from fastapi import FastAPI

from behavioral_agent_service.schemas import AgentEvaluateResponse, TransactionEvaluateRequest

AGENT_NAME = "behavioral"

app = FastAPI(
    title="Behavioral Agent",
    description="Rule-based behavioral risk scoring for payment transactions",
)


def _risk_from_amount(amount: float) -> tuple[float, str]:
    """Higher amount → higher risk (simple tiered rules, currency-agnostic)."""
    if amount >= 10_000:
        return 0.92, "Amount >= 10,000 — treated as very high risk"
    if amount >= 5_000:
        return 0.78, "Amount >= 5,000 — elevated risk"
    if amount >= 1_000:
        return 0.52, "Amount >= 1,000 — moderate risk"
    return 0.18, "Amount below 1,000 — low behavioral risk"


@app.get("/health")
async def health():
    return {"status": "ok", "service": AGENT_NAME, "port": 8001}


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

    score, reason = _risk_from_amount(body.amount)
    return AgentEvaluateResponse(
        transaction_id=tx_id,
        agent_name=AGENT_NAME,
        risk_score=round(score, 4),
        reason=reason,
        processing_time_ms=elapsed_ms,
        status="success",
    )
