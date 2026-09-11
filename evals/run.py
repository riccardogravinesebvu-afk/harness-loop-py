"""Run the eval dataset against the agent under test and write evals/results/<ts>.json.

Usage: uv run python -m evals.run --seed 42
Results carry: model id, seed, git sha, per-case pass, per-category pass rate, total cost.
"""

import argparse
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import yaml

RESULTS = Path(__file__).parent / "results"


def load_dataset() -> dict:
    return yaml.safe_load((Path(__file__).parent / "dataset.yaml").read_text())


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    ds = load_dataset()
    raise SystemExit(
        f"agent under test not implemented yet: {len(ds['cases'])} cases loaded, "
        f"seed={args.seed}, sha={git_sha()}. "
        "Results dir: " + str(RESULTS) + " (" + datetime.now(UTC).isoformat() + ")"
    )


if __name__ == "__main__":
    main()
