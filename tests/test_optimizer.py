"""Offline checks for the gate, the anti-leak filter, the changelog row and the loop graph shape."""

from src.optimizer.gates import delta_cases, gate, leaks_expected, tolerances
from src.optimizer.loop import CATS, HEADER, changelog_row

CASES = [
    {"id": "L01", "category": "lookup", "split": "visible", "expected": 8},
    {"id": "L05", "category": "lookup", "split": "visible", "expected": "Helios"},
    {"id": "L04", "category": "lookup", "split": "holdout", "expected": "2026-09-09"},
    {"id": "A01", "category": "aggregation", "split": "visible", "expected": 139520},
    {"id": "A06", "category": "aggregation", "split": "visible", "expected": 5813.33},
    {
        "id": "R01",
        "category": "reasoning",
        "split": "visible",
        "expected": "judge",
        "reference": "Outstanding is 24,890.00 across 3 invoices.",
    },  # fmt: skip
    {"id": "F01", "category": "refusal", "split": "visible", "expected": True},
]


def test_tolerance_is_one_visible_case_per_category():
    assert tolerances(CASES) == {
        "lookup": 0.5,
        "aggregation": 0.5,
        "reasoning": 1.0,
        "refusal": 1.0,
    }


def _s(visible, holdout, **cats):
    return {"visible": visible, "holdout": holdout, "per_category_visible": cats}


def test_gate_reasons_in_order():
    tol = {"lookup": 1 / 7, "aggregation": 1 / 7, "reasoning": 1 / 8, "refusal": 1 / 8}
    before = _s(0.47, 0.4, lookup=6 / 7, aggregation=5 / 7, reasoning=3 / 8, refusal=0.0)
    assert gate(before, _s(0.47, 0.5, **before["per_category_visible"]), tol) == "no_gain"
    two_down = dict(before["per_category_visible"], lookup=4 / 7, refusal=6 / 8)
    assert gate(before, _s(0.6, 0.4, **two_down), tol) == "gate lookup -2"
    one_down = dict(before["per_category_visible"], lookup=5 / 7, refusal=6 / 8)
    assert gate(before, _s(0.6, 0.3, **one_down), tol) == "holdout"
    assert gate(before, _s(0.6, 0.4, **one_down), tol) is None
    assert delta_cases(before["per_category_visible"], one_down, tol) == {
        "lookup": -1, "aggregation": 0, "reasoning": 0, "refusal": 6
    }  # fmt: skip


def test_leak_filter_catches_visible_literals_only():
    assert leaks_expected("Answer with numbers.", CASES) is None
    assert leaks_expected("Total invoiced is 139,520 EUR", CASES) == "A01:139520"
    assert leaks_expected("Helios Energy owes the most", CASES) == "L05:Helios"
    assert leaks_expected("outstanding is 24890.00", CASES) == "R01:24,890.00"
    assert leaks_expected("due 2026-09-09", CASES) is None  # holdout: not visible to the optimizer
    assert leaks_expected("There are 8 customers", CASES) is None  # short literals are noise


def test_changelog_row_matches_header():
    it = {"n": 1, "hyp_id": "hyp/1", "sha": "abc1234", "target": "system.md", "title": "t",
          "verdict": "accepted", "visible_delta": 0.1, "holdout_delta": 0.0,
          "delta_cases": {c: 1 for c in CATS}, "cost_eur": {"total": 0.45},
          "cumulative_eur": 0.9, "results_file": "evals/results/x.json"}  # fmt: skip
    assert changelog_row(it).count("|") == HEADER.splitlines()[0].count("|")
    assert "+10.0pp" in changelog_row(it) and "+1/+1/+1/+1" in changelog_row(it)
