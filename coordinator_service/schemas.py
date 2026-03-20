from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class TransactionEvaluateRequest(BaseModel):
    transaction_id: Optional[str] = None
    user_id: str
    amount: float = Field(..., gt=0)
    currency: str
    timestamp: datetime
    location_country: str
    location_city: Optional[str] = None
    merchant_id: str
    merchant_category: str
    device_id: Optional[str] = None
    payment_method: Optional[str] = None
    simulate_delay: bool = False
    delay_ms: int = Field(0, ge=0, le=60_000)
    simulate_failure: bool = False


class AgentEvaluateResponse(BaseModel):
    transaction_id: str
    agent_name: str
    risk_score: float = Field(..., ge=0.0, le=1.0)
    reason: str
    processing_time_ms: int = Field(..., ge=0)
    status: Literal["success", "failed"]


class AgentFanOutResult(BaseModel):
    agent: Literal["behavioral", "geo", "merchant", "history"]
    success: bool
    http_status: Optional[int] = None
    data: Optional[AgentEvaluateResponse] = None
    error: Optional[str] = None


class CoordinatorEvaluateResponse(BaseModel):
    transaction_id: str
    final_risk_score: float
    decision: Literal["APPROVE", "CHALLENGE", "DECLINE"]
    agent_results: list[AgentFanOutResult]
    missing_agents: list[str]
    failed_agents: list[str]
    total_processing_time_ms: int


class TransactionStored(BaseModel):
    transaction_id: str
    user_id: str
    amount: float
    currency: str
    timestamp: datetime
    location_country: str
    location_city: Optional[str] = None
    merchant_id: str
    merchant_category: str
    device_id: Optional[str] = None
    payment_method: Optional[str] = None

    final_risk_score: float
    decision: Literal["APPROVE", "CHALLENGE", "DECLINE"]
    missing_agents: list[str]
    failed_agents: list[str]
    total_processing_time_ms: int
    created_at: datetime


class TransactionsListResponse(BaseModel):
    transactions: list[TransactionStored]


class DecisionCounts(BaseModel):
    APPROVE: int = 0
    CHALLENGE: int = 0
    DECLINE: int = 0


class FailureCounts(BaseModel):
    """Rollups from stored `failed_agents` / `missing_agents` arrays per transaction."""

    transactions_with_failed_agents: int
    transactions_with_missing_agents: int
    total_failed_agent_slots: int
    total_missing_agent_slots: int


class MetricsSummaryResponse(BaseModel):
    total_transactions: int
    decision_counts: DecisionCounts
    avg_risk_score: float
    avg_latency_ms: float
    failure_counts: FailureCounts
