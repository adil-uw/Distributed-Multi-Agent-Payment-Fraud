from datetime import datetime
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from coordinator_service.config import settings

_client: Optional[AsyncIOMotorClient] = None

COLLECTION_TRANSACTIONS = "transactions"
COLLECTION_EVALUATION_LOGS = "evaluation_logs"


def get_client() -> AsyncIOMotorClient:
    if _client is None:
        raise RuntimeError("MongoDB client is not initialized")
    return _client


def get_database() -> AsyncIOMotorDatabase:
    return get_client()[settings.mongodb_db_name]


async def connect_mongodb() -> None:
    global _client
    if _client is not None:
        return
    _client = AsyncIOMotorClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=5000,
    )


async def disconnect_mongodb() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


async def ping_mongodb() -> None:
    """Raises if the server does not respond to a ping."""
    await get_client().admin.command("ping")


async def upsert_transaction(transaction_doc: dict[str, Any]) -> None:
    """
    Store the transaction outcome in `transactions`.
    Uses `transaction_id` as a stable key so repeated evaluations overwrite.
    """
    if "created_at" not in transaction_doc:
        transaction_doc["created_at"] = datetime.utcnow()

    collection = get_database()[COLLECTION_TRANSACTIONS]
    await collection.update_one(
        {"transaction_id": transaction_doc["transaction_id"]},
        {"$set": transaction_doc},
        upsert=True,
    )


async def insert_evaluation_log(evaluation_log_doc: dict[str, Any]) -> None:
    """Append an evaluation log in `evaluation_logs` for each evaluation call."""
    if "created_at" not in evaluation_log_doc:
        evaluation_log_doc["created_at"] = datetime.utcnow()

    collection = get_database()[COLLECTION_EVALUATION_LOGS]
    await collection.insert_one(evaluation_log_doc)


async def get_transaction_by_id(transaction_id: str) -> Optional[dict[str, Any]]:
    projection = {"_id": 0}
    doc = await get_database()[COLLECTION_TRANSACTIONS].find_one(
        {"transaction_id": transaction_id},
        projection,
    )
    return doc


async def list_transactions(limit: int = 20) -> list[dict[str, Any]]:
    if limit < 1:
        limit = 1
    if limit > 100:
        limit = 100

    cursor = (
        get_database()[COLLECTION_TRANSACTIONS]
        .find({}, projection={"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def get_metrics_summary() -> dict[str, Any]:
    """
    Aggregates over `transactions` (current stored state; upserts overwrite per transaction_id).
    """
    coll = get_database()[COLLECTION_TRANSACTIONS]
    pipeline: list[dict[str, Any]] = [
        {
            "$facet": {
                "count_all": [{"$count": "n"}],
                "by_decision": [
                    {"$group": {"_id": "$decision", "c": {"$sum": 1}}},
                ],
                "stats": [
                    {
                        "$group": {
                            "_id": None,
                            "avg_risk": {"$avg": "$final_risk_score"},
                            "avg_latency": {"$avg": "$total_processing_time_ms"},
                            "transactions_with_failed_agents": {
                                "$sum": {
                                    "$cond": [
                                        {
                                            "$gt": [
                                                {"$size": {"$ifNull": ["$failed_agents", []]}},
                                                0,
                                            ]
                                        },
                                        1,
                                        0,
                                    ]
                                }
                            },
                            "transactions_with_missing_agents": {
                                "$sum": {
                                    "$cond": [
                                        {
                                            "$gt": [
                                                {"$size": {"$ifNull": ["$missing_agents", []]}},
                                                0,
                                            ]
                                        },
                                        1,
                                        0,
                                    ]
                                }
                            },
                            "total_failed_agent_slots": {
                                "$sum": {
                                    "$size": {"$ifNull": ["$failed_agents", []]}
                                }
                            },
                            "total_missing_agent_slots": {
                                "$sum": {
                                    "$size": {"$ifNull": ["$missing_agents", []]}
                                }
                            },
                        }
                    }
                ],
            }
        }
    ]

    rows = await coll.aggregate(pipeline).to_list(length=1)
    if not rows:
        return _empty_metrics_summary()

    facet = rows[0]
    total = int(facet["count_all"][0]["n"]) if facet.get("count_all") else 0

    decision_map: dict[str, int] = {}
    for row in facet.get("by_decision") or []:
        key = row.get("_id")
        if key is not None:
            decision_map[str(key)] = int(row.get("c", 0))

    stats_list = facet.get("stats") or []
    stats = stats_list[0] if stats_list else None

    if stats:
        avg_risk = float(stats.get("avg_risk") or 0.0)
        avg_latency = float(stats.get("avg_latency") or 0.0)
        tx_failed = int(stats.get("transactions_with_failed_agents") or 0)
        tx_missing = int(stats.get("transactions_with_missing_agents") or 0)
        failed_slots = int(stats.get("total_failed_agent_slots") or 0)
        missing_slots = int(stats.get("total_missing_agent_slots") or 0)
    else:
        avg_risk = 0.0
        avg_latency = 0.0
        tx_failed = tx_missing = failed_slots = missing_slots = 0

    return {
        "total_transactions": total,
        "decision_counts": {
            "APPROVE": decision_map.get("APPROVE", 0),
            "CHALLENGE": decision_map.get("CHALLENGE", 0),
            "DECLINE": decision_map.get("DECLINE", 0),
        },
        "avg_risk_score": round(avg_risk, 4),
        "avg_latency_ms": round(avg_latency, 2),
        "failure_counts": {
            "transactions_with_failed_agents": tx_failed,
            "transactions_with_missing_agents": tx_missing,
            "total_failed_agent_slots": failed_slots,
            "total_missing_agent_slots": missing_slots,
        },
    }


def _empty_metrics_summary() -> dict[str, Any]:
    return {
        "total_transactions": 0,
        "decision_counts": {"APPROVE": 0, "CHALLENGE": 0, "DECLINE": 0},
        "avg_risk_score": 0.0,
        "avg_latency_ms": 0.0,
        "failure_counts": {
            "transactions_with_failed_agents": 0,
            "transactions_with_missing_agents": 0,
            "total_failed_agent_slots": 0,
            "total_missing_agent_slots": 0,
        },
    }
