"""The loop's git, changelog and stop mechanics on a throwaway clone, with fake evals and LLM.
No provider key, no Langfuse keys, no network."""

import json

import pytest
from git import Repo

from src.optimizer import loop as lp

ROOT = lp.ROOT
VIS = {"lookup": 6 / 7, "aggregation": 5 / 7, "reasoning": 3 / 8, "refusal": 0.0}


def fake_results(path, visible, holdout, per_cat):
    out = {"git_sha": "fake", "pass_rate": {"total": visible, "per_split": {"visible": visible, "holdout": holdout},
           "per_category": per_cat, "per_category_visible": per_cat, "n": 40},
           "cost": {"total_usd": 0.5, "total_eur": 0.4}, "cases": []}  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out))
    return path


@pytest.fixture
def clone(tmp_path, monkeypatch):
    r = Repo.clone_from(ROOT, tmp_path / "r")
    r.git.config("user.name", "t")
    r.git.config("user.email", "t@example.com")
    monkeypatch.setenv("AGENT_MODEL", "a")
    monkeypatch.setenv("JUDGE_MODEL", "j")
    monkeypatch.setenv("OPTIMIZER_MODEL", "claude-sonnet-4-6")
    monkeypatch.setattr(lp, "RUNS_LOG", tmp_path / "runs.jsonl")
    return tmp_path / "r"


async def test_accept_then_reject_then_stop(clone, monkeypatch):
    # iteration 0: baseline 47%; hyp 1 raises visible → accepted; hyp 2 no gain → rejected
    plan = iter(
        [
            (0.4667, 0.4, VIS),
            (0.6, 0.4, dict(VIS, refusal=4 / 8)),
            (0.6, 0.5, dict(VIS, refusal=4 / 8)),
        ]
    )
    calls = {"n": 0}

    async def run_evals(ns):
        calls["n"] += 1
        v, h, c = next(plan)
        return fake_results(clone / "evals" / "results" / f"fake{calls['n']}.json", v, h, c)

    class Raw:
        usage_metadata = {"input_tokens": 1000, "output_tokens": 500}

    class LLM:
        def with_structured_output(self, *a, **k):
            return self

        async def ainvoke(self, msgs, config=None):
            hyp = lp.Hypothesis(title="always call final_answer", rationale="r", target="system.md",
                               content="Always end with final_answer. Today is {as_of}.",
                               proposed_cases=[lp.ProposedCase(category="refusal", input="q", expected="True", check="refused", why="w")])  # fmt: skip
            return {"parsed": hyp, "raw": Raw()}

    monkeypatch.setattr(lp, "run_evals", lambda ns: run_evals(ns))
    monkeypatch.setattr(lp, "make_chat", lambda *a, **k: LLM())
    cfg = {"max_iterations": 2, "max_eur": 10, "min_gain": 0.03, "seed": 42, "loop_id": "T"}
    final = await lp.build_loop(cfg, root=clone).ainvoke({}, config={"recursion_limit": 40})

    repo = Repo(clone)
    assert final["stop"] == "max_iterations" and final["best"]["visible"] == 0.6
    assert repo.active_branch.name == "main" and not repo.is_dirty() and not repo.untracked_files
    assert {b.name for b in repo.branches} >= {"main", "hyp/1", "hyp/2"}
    assert "final_answer" in (clone / "src/agent_under_test/prompts/system.md").read_text()
    rows = [ln for ln in (clone / "CHANGELOG.md").read_text().splitlines() if ln.startswith("| ")]
    rows = rows[-2:]  # the clone carries the real CHANGELOG; only the two new rows matter
    assert "| accepted |" in rows[0] and "rejected: no_gain" in rows[1]
    assert "+13.3pp" in rows[0] and "| 0/0/0/+4 |" in rows[0]
    doc = json.loads((clone / "evals/results/loops/T.json").read_text())
    assert [i["verdict"] for i in doc["iterations"]] == [
        "baseline",
        "accepted",
        "rejected: no_gain",
    ]
    assert doc["stop"] == {"reason": "max_iterations", "at": 2}
    assert doc["iterations"][1]["cost_eur"]["optimizer"] > 0  # optimizer tokens are charged
    assert "hyp/1" in (clone / "evals/proposed.yaml").read_text()
    msgs = [c.message.splitlines()[0] for c in repo.iter_commits("main", max_count=4)]
    assert msgs[0].startswith("hyp/2 rejected: no_gain") and msgs[1].startswith("hyp/1 accepted")
    assert msgs[2].startswith("hyp/1: always call final_answer") and msgs[3].startswith(
        "loop T: baseline"
    )
