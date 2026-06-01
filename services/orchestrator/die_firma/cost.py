"""Cost guard: hard daily USD limit (prompt §1/§7).

The orchestrator queries the day's accumulated spend (from /api/metrics) before
each dispatch and pauses the queue when the limit is reached. Pure decision
helper here → 100% coverage target.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostDecision:
    allowed: bool
    spent_usd: float
    limit_usd: float

    @property
    def remaining_usd(self) -> float:
        return max(self.limit_usd - self.spent_usd, 0.0)


def evaluate(spent_usd: float, limit_usd: float) -> CostDecision:
    """Decide whether another dispatch is permitted.

    A non-positive limit means "no limit" (disabled). Otherwise dispatch is
    blocked once spend reaches or exceeds the limit.
    """
    if limit_usd <= 0:
        return CostDecision(allowed=True, spent_usd=spent_usd, limit_usd=limit_usd)
    return CostDecision(allowed=spent_usd < limit_usd, spent_usd=spent_usd, limit_usd=limit_usd)
