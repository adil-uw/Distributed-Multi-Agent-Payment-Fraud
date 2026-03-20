import asyncio
import time
import uuid

from fastapi import FastAPI

from geo_agent_service.schemas import AgentEvaluateResponse, TransactionEvaluateRequest

AGENT_NAME = "geo"

# Demo rule set: ISO 3166-1 alpha-2 codes treated as elevated geo risk for coursework.
RISKY_COUNTRIES = frozenset(
    {
        "AF",
        "IR",
        "KP",
        "MM",
        "NG",
        "PK",
        "SY",
        "YE",
    }
)

app = FastAPI(
    title="Geo Agent",
    description="Rule-based geographic risk scoring for payment transactions",
)


def _risk_from_country(location_country: str) -> tuple[float, str]:
    code = (location_country or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return (
            0.55,
            "Country code missing or not a 2-letter ISO code — elevated uncertainty",
        )
    if code in RISKY_COUNTRIES:
        return 0.86, f"Country {code} is on the elevated-risk geo list"
    return 0.20, f"Country {code} is not on the elevated-risk geo list"


@app.get("/health")
async def health():
    return {"status": "ok", "service": AGENT_NAME, "port": 8002}


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

    score, reason = _risk_from_country(body.location_country)
    return AgentEvaluateResponse(
        transaction_id=tx_id,
        agent_name=AGENT_NAME,
        risk_score=round(score, 4),
        reason=reason,
        processing_time_ms=elapsed_ms,
        status="success",
    )
