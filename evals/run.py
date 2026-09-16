"""Run the eval dataset against the agent under test and write evals/results/<ts>.json.

Usage: uv run python -m evals.run --seed 42 [--split visible|holdout|all] [--ids L01,A04]
Results carry: models, seed, git sha, per-case pass, pass rate per category and split, cost.
"""

import argparse
import asyncio
import json
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import yaml

from evals.checks import check
from evals.judge import judge
from src.agent_under_test import ledger
from src.agent_under_test.graph import build_graph, run
from src.llm import load_env, model_for
from src.pricing import usd_to_eur

HERE = Path(__file__).parent
RESULTS = HERE / "results"


def load_cases(path: Path = HERE / "dataset.yaml") -> list[dict]:
    cases = yaml.safe_load(path.read_text())["cases"]
    fb = HERE / "feedback.yaml"
    if fb.exists():
        cases += yaml.safe_load(fb.read_text()).get("cases", [])
    for c in cases:
        c.setdefault("weight", 1)
        c.setdefault("source", "seed")
        c.setdefault("split", "visible")
    return cases


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def pass_rate(rows: list[dict]) -> float | None:
    w = sum(r["weight"] for r in rows)
    return round(sum(r["weight"] * r["passed"] for r in rows) / w, 4) if w else None


def summarize(rows: list[dict]) -> dict:
    by_cat, by_split = defaultdict(list), defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)
        by_split[r["split"]].append(r)
    visible = {k: [r for r in v if r["split"] == "visible"] for k, v in by_cat.items()}
    return {
        "total": pass_rate(rows),
        "per_split": {k: pass_rate(v) for k, v in sorted(by_split.items())},
        "per_category": {k: pass_rate(v) for k, v in sorted(by_cat.items())},
        "per_category_visible": {k: pass_rate(v) for k, v in sorted(visible.items())},
        "n": len(rows),
    }


async def eval_case(case: dict, graph, seed: int, sem: asyncio.Semaphore) -> dict:
    async with sem:
        res = await run(case["input"], graph=graph, seed=seed)
        row = {
            "id": case["id"], "category": case["category"], "split": case["split"],
            "weight": case["weight"], "source": case["source"], "check": case["check"],
            "input": case["input"], "answer": res.answer, "refused": res.refused,
            "error": res.error, "tool_calls": [c.name for c in res.tool_calls],
            "tokens": res.input_tokens + res.output_tokens, "cost_usd": round(res.cost_usd, 6),
            "judge_cost_usd": 0.0, "latency_s": res.latency_s,
        }  # fmt: skip
        if case["check"] == "judge":
            j = await judge(case, res.answer, res.tool_calls, seed=seed)
            row.update(passed=j["passed"], detail=j["verdict"], score=j["score"],
                       judge_cost_usd=round(j["judge_cost_usd"], 6))  # fmt: skip
        else:
            ok, detail = check(case, res.answer, res.refused)
            row.update(passed=ok, detail=detail)
        mark = "PASS" if row["passed"] else "FAIL"
        print(
            f"{mark} {case['id']:>4} {case['category']:<12} {row['detail']!s:.70}", file=sys.stderr
        )
        return row


async def main_async(args: argparse.Namespace) -> Path:
    load_env()
    ledger.build_db()
    cases = load_cases()
    if args.split != "all":
        cases = [c for c in cases if c["split"] == args.split]
    if args.ids:
        wanted = set(args.ids.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    cases = cases[: args.limit] if args.limit else cases
    graph = build_graph(seed=args.seed)
    sem = asyncio.Semaphore(args.concurrency)
    rows = await asyncio.gather(*(eval_case(c, graph, args.seed, sem) for c in cases))
    rows = sorted(rows, key=lambda r: r["id"])
    agent_usd = sum(r["cost_usd"] for r in rows)
    judge_usd = sum(r["judge_cost_usd"] for r in rows)
    out = {
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_sha": git_sha(),
        "seed": args.seed,
        "models": {"agent": model_for("agent"), "judge": model_for("judge")},
        "split": args.split,
        "pass_rate": summarize(rows),
        "cost": {
            "agent_usd": round(agent_usd, 4),
            "judge_usd": round(judge_usd, 4),
            "total_usd": round(agent_usd + judge_usd, 4),
            "total_eur": round(usd_to_eur(agent_usd + judge_usd), 4),
        },  # fmt: skip
        "errors": {
            k: sum(1 for r in rows if r["error"] == k)
            for k in ("no_final_answer", "max_steps", "provider_error")
        },  # fmt: skip
        "cases": rows,
    }
    RESULTS.mkdir(exist_ok=True)
    path = args.out or RESULTS / f"{out['timestamp'].replace(':', '')}.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    pr = out["pass_rate"]
    print(f"\npass rate total {pr['total']}  per split {pr['per_split']}")
    print(f"per category {pr['per_category']}")
    print(f"cost {out['cost']}  errors {out['errors']}\n→ {path}")
    return path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--split", choices=["all", "visible", "holdout"], default="all")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--ids", default="")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--out", type=Path, default=None)
    asyncio.run(main_async(p.parse_args()))


if __name__ == "__main__":
    main()
