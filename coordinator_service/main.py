import time
import uuid
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from coordinator_service import database
from coordinator_service.agents_client import fan_out_evaluate
from coordinator_service.aggregation import aggregate
from coordinator_service.config import settings
from coordinator_service.schemas import (
    CoordinatorEvaluateResponse,
    MetricsSummaryResponse,
    TransactionEvaluateRequest,
    TransactionStored,
    TransactionsListResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.connect_mongodb()
    try:
        yield
    finally:
        await database.disconnect_mongodb()


app = FastAPI(
    title="Payment Fraud Coordinator",
    description="Coordinator service for distributed fraud evaluation",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "coordinator"}


@app.get("/db-health")
async def db_health():
    try:
        await database.ping_mongodb()
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "mongodb": "unreachable",
                "detail": str(exc),
            },
        )
    return {
        "status": "ok",
        "mongodb": "connected",
        "database": settings.mongodb_db_name,
    }


@app.post("/transactions/evaluate", response_model=CoordinatorEvaluateResponse)
async def evaluate_transaction(body: TransactionEvaluateRequest) -> CoordinatorEvaluateResponse:
    start = time.perf_counter()
    tx_id = body.transaction_id or str(uuid.uuid4())
    payload = body.model_copy(update={"transaction_id": tx_id}).model_dump(mode="json")
    agent_results = await fan_out_evaluate(payload)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    final_risk_score, decision, missing_agents, failed_agents = aggregate(agent_results)
    response = CoordinatorEvaluateResponse(
        transaction_id=tx_id,
        final_risk_score=final_risk_score,
        decision=decision,
        agent_results=agent_results,
        missing_agents=missing_agents,
        failed_agents=failed_agents,
        total_processing_time_ms=elapsed_ms,
    )

    # Persist results in MongoDB (Coordinator-only).
    try:
        transaction_doc = {
            "transaction_id": tx_id,
            "user_id": body.user_id,
            "amount": body.amount,
            "currency": body.currency,
            "timestamp": body.timestamp,
            "location_country": body.location_country,
            "location_city": body.location_city,
            "merchant_id": body.merchant_id,
            "merchant_category": body.merchant_category,
            "device_id": body.device_id,
            "payment_method": body.payment_method,
            "final_risk_score": final_risk_score,
            "decision": decision,
            "missing_agents": missing_agents,
            "failed_agents": failed_agents,
            "total_processing_time_ms": elapsed_ms,
            "created_at": datetime.utcnow(),
        }
        evaluation_log_doc = {
            "transaction_id": tx_id,
            "agent_results": [r.model_dump(mode="json") for r in agent_results],
            "missing_agents": missing_agents,
            "failed_agents": failed_agents,
            "final_risk_score": final_risk_score,
            "decision": decision,
            "total_processing_time_ms": elapsed_ms,
            "created_at": datetime.utcnow(),
        }
        await database.upsert_transaction(transaction_doc)
        await database.insert_evaluation_log(evaluation_log_doc)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"MongoDB write failed: {exc}")

    return response


@app.get("/transactions/{id}", response_model=TransactionStored)
async def get_transaction(id: str) -> TransactionStored:
    doc = await database.get_transaction_by_id(id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return TransactionStored.model_validate(doc)


@app.get("/transactions", response_model=TransactionsListResponse)
async def list_transactions(limit: int = 20) -> TransactionsListResponse:
    docs = await database.list_transactions(limit=limit)
    transactions = [TransactionStored.model_validate(d) for d in docs]
    return TransactionsListResponse(transactions=transactions)


@app.get("/metrics/summary", response_model=MetricsSummaryResponse)
async def metrics_summary() -> MetricsSummaryResponse:
    try:
        await database.ping_mongodb()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"MongoDB unreachable: {exc}",
        )
    try:
        raw = await database.get_metrics_summary()
        return MetricsSummaryResponse.model_validate(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"MongoDB metrics query failed: {exc}",
        )
