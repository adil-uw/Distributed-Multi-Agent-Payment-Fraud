import asyncio
import re
import time
import uuid

from fastapi import FastAPI

from merchant_agent_service.schemas import AgentEvaluateResponse, TransactionEvaluateRequest

AGENT_NAME = "merchant"

# Normalized keys: lowercase, spaces/hyphens → underscores.
HIGH_RISK_CATEGORIES = frozenset({"gambling", "crypto", "gift_cards"})

app = FastAPI(
    title="Merchant Agent",
    description="Rule-based merchant category risk scoring for payment transactions",
)


def _normalize_merchant_category(raw: str) -> str:
    s = (raw or "").strip().lower()
    s = re.sub(r"[\s\-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def _risk_from_category(merchant_category: str) -> tuple[float, str]:
    key = _normalize_merchant_category(merchant_category)
    if not key:
        return 0.50, "Merchant category missing — elevated uncertainty"
    if key in HIGH_RISK_CATEGORIES:
        return 0.87, f"Merchant category '{key}' is high-risk (gambling / crypto / gift_cards)"
    return 0.19, f"Merchant category '{key}' is not in the high-risk category list"


@app.get("/health")
async def health():
    return {"status": "ok", "service": AGENT_NAME, "port": 8003}


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

    score, reason = _risk_from_category(body.merchant_category)
    return AgentEvaluateResponse(
        transaction_id=tx_id,
        agent_name=AGENT_NAME,
        risk_score=round(score, 4),
        reason=reason,
        processing_time_ms=elapsed_ms,
        status="success",
    )
