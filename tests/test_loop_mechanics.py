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
    # baseline 47%/40%; hyp 1: visible up, holdout 0.5 then confirmed at 0.4 → accepted, bar = 0.4;
    # hyp 2: no gain → rejected without confirmation; hyp 3: gain, holdout 0.4 on the first run
    # but 0.3 on the confirmation → rejected: holdout_confirm
    up = dict(VIS, refusal=4 / 8)
    plan = iter([(0.4667, 0.4, VIS), (0.6, 0.5, up), (None, 0.4, up), (0.6, 0.5, up),
                 (0.7, 0.4, up), (None, 0.3, up)])  # fmt: skip
    calls = {"n": 0, "splits": []}

    async def run_evals(ns):
        calls["n"] += 1
        calls["splits"].append(ns.split)
        v, h, c = next(plan)
        assert (ns.split == "holdout") == (v is None)
        return fake_results(clone / "evals" / "results" / f"fake{calls['n']}.json", v or 0, h, c)

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
    cfg = {"max_iterations": 3, "max_eur": 10, "min_gain": 0.03, "seed": 42, "loop_id": "T"}
    final = await lp.build_loop(cfg, root=clone).ainvoke({}, config={"recursion_limit": 40})

    repo = Repo(clone)
    assert final["stop"] == "max_iterations" and final["best"]["visible"] == 0.6
    assert repo.active_branch.name == "main" and not repo.is_dirty() and not repo.untracked_files
    assert {b.name for b in repo.branches} >= {"main", "hyp/1", "hyp/2"}
    assert "final_answer" in (clone / "src/agent_under_test/prompts/system.md").read_text()
    rows = [ln for ln in (clone / "CHANGELOG.md").read_text().splitlines() if ln.startswith("| ")]
    rows = rows[-3:]  # the clone carries the real CHANGELOG; only the new rows matter
    assert "| accepted |" in rows[0] and "rejected: no_gain" in rows[1]
    assert "rejected: holdout_confirm 30% vs 40%" in rows[2] and "(confirm 30%)" in rows[2]
    assert "(confirm 40%)" in rows[0]
    assert calls["splits"] == ["all", "all", "holdout", "all", "all", "holdout"]
    assert "+13.3pp" in rows[0] and "| 0/0/0/+" in rows[0]  # refusal delta = 4/8 ÷ (1/n_refusal)
    doc = json.loads((clone / "evals/results/loops/T.json").read_text())
    assert [i["verdict"] for i in doc["iterations"]] == [
        "baseline", "accepted", "rejected: no_gain", "rejected: holdout_confirm 30% vs 40%",
    ]  # fmt: skip
    assert doc["stop"] == {"reason": "max_iterations", "at": 3}
    assert doc["iterations"][1]["holdout_confirm"]["holdout"] == 0.4
    assert doc["iterations"][1]["holdout"] == 0.4  # min of the two runs is the new bar
    assert (clone / doc["iterations"][3]["holdout_confirm"]["results_file"]).exists()
    assert doc["iterations"][1]["cost_eur"]["optimizer"] > 0  # optimizer tokens are charged
    assert "hyp/1" in (clone / "evals/proposed.yaml").read_text()
    msgs = [c.message.splitlines()[0] for c in repo.iter_commits("main", max_count=5)]
    assert msgs[0].startswith("hyp/3 rejected: holdout_confirm")
    assert msgs[1].startswith("hyp/2 rejected: no_gain") and msgs[2].startswith("hyp/1 accepted")
    assert msgs[3].startswith("hyp/1: always call final_answer")
    assert msgs[4].startswith("loop T: baseline")
