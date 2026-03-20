import asyncio
from typing import Any, Literal

import httpx

from coordinator_service.config import settings
from coordinator_service.schemas import AgentEvaluateResponse, AgentFanOutResult

AgentKey = Literal["behavioral", "geo", "merchant", "history"]


def _agent_urls() -> tuple[tuple[AgentKey, str], ...]:
    return (
        ("behavioral", settings.behavioral_agent_url),
        ("geo", settings.geo_agent_url),
        ("merchant", settings.merchant_agent_url),
        ("history", settings.history_agent_url),
    )


def _evaluate_url(base: str) -> str:
    return f"{base.rstrip('/')}/evaluate"


async def _call_agent(
    client: httpx.AsyncClient,
    agent_key: AgentKey,
    base_url: str,
    payload: dict[str, Any],
) -> AgentFanOutResult:
    url = _evaluate_url(base_url)
    try:
        response = await client.post(url, json=payload)
    except httpx.TimeoutException:
        return AgentFanOutResult(
            agent=agent_key,
            success=False,
            error="Request timed out",
        )
    except httpx.RequestError as exc:
        return AgentFanOutResult(
            agent=agent_key,
            success=False,
            error=str(exc),
        )

    if 200 <= response.status_code < 300:
        try:
            data = AgentEvaluateResponse.model_validate(response.json())
            return AgentFanOutResult(
                agent=agent_key,
                success=True,
                http_status=response.status_code,
                data=data,
            )
        except Exception as exc:
            return AgentFanOutResult(
                agent=agent_key,
                success=False,
                http_status=response.status_code,
                error=f"Invalid agent response: {exc}",
            )

    text = response.text
    if len(text) > 500:
        text = text[:500] + "..."
    return AgentFanOutResult(
        agent=agent_key,
        success=False,
        http_status=response.status_code,
        error=text or f"HTTP {response.status_code}",
    )


async def fan_out_evaluate(payload: dict[str, Any]) -> list[AgentFanOutResult]:
    timeout = httpx.Timeout(settings.agent_request_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        tasks = [
            _call_agent(client, key, base, payload)
            for key, base in _agent_urls()
        ]
        return list(await asyncio.gather(*tasks))
