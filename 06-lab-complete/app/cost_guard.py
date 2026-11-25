"""
Cost guard (tiêu chí 8) — Theo dõi chi phí LLM trong Redis và chặn khi vượt ngân sách.
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import r

PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

_fallback_spend: dict[str, float] = {}


def _budget_key() -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"cost:daily:{day}"


def _budget_limit() -> float:
    return min(settings.daily_budget_usd, settings.monthly_budget_usd)


def check_budget() -> None:
    """Gọi trước khi gọi LLM. Vượt budget → raise HTTPException(status_code=402)."""
    key = _budget_key()
    limit = _budget_limit()
    current = 0.0

    if r is not None:
        try:
            raw = r.get(key)
            current = float(raw) if raw is not None else 0.0
        except (RedisError, ValueError):
            current = _fallback_spend.get(key, 0.0)
    else:
        current = _fallback_spend.get(key, 0.0)

    if current >= limit:
        raise HTTPException(
            status_code=402,
            detail="Daily budget exceeded",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Cộng chi phí request vào Redis và trả về chi phí request (USD)."""
    cost = (
        (input_tokens / 1000.0) * PRICE_INPUT_PER_1K
        + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    )
    key = _budget_key()

    if r is not None:
        try:
            r.incrbyfloat(key, cost)
            r.expire(key, 48 * 3600)
            return cost
        except RedisError:
            pass

    _fallback_spend[key] = _fallback_spend.get(key, 0.0) + cost
    return cost
