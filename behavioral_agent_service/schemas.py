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
