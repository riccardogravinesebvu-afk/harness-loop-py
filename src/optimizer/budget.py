"""Cost budget: stop when marginal pass-rate gain per euro drops below threshold.

ponytail: pure function over the iteration history; Langfuse supplies cost per iteration.
"""


def should_stop(history: list[dict], min_gain_per_eur: float, window: int = 3) -> bool:
    """history items: {"pass_rate": float, "cost_eur": float}.

    Stops when the last `window` iterations
    together bought less than `min_gain_per_eur` pass-rate points per euro."""
    if len(history) < window + 1:
        return False
    recent = history[-window:]
    gain = recent[-1]["pass_rate"] - history[-window - 1]["pass_rate"]
    cost = sum(h["cost_eur"] for h in recent)
    if cost <= 0:
        return False
    return gain / cost < min_gain_per_eur
