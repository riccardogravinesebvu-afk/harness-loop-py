"""Per-category regression gate: reject a hypothesis if any category gets worse."""


def passes_gate(
    before: dict[str, float], after: dict[str, float], tolerance: float = 0.0
) -> tuple[bool, list[str]]:
    """before/after: {category: pass_rate}. Returns (ok, regressed_categories)."""
    regressed = [c for c, v in before.items() if after.get(c, 0.0) + tolerance < v]
    return (not regressed, regressed)
