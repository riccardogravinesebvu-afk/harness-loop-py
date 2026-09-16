# CLAUDE.md — harness-loop-py

## Project context
Python reimplementation, credited and MIT-licensed, of the harness-engineering loop Nearform describes publicly (an optimizer agent that iterates on evals). The code is original; only the method is borrowed. Three extensions the published method does not have: **cost budget per iteration**, **per-category regression gate**, **human feedback inside the loop**. Design: `docs/plans/2026-09-11-harness-loop-py-design.md`.

## Stack
Python 3.12 / uv | LangGraph (agent under test and optimizer node) | one OpenAI-compatible client (`src/llm.py`, default Anthropic) | Langfuse (traces, optional) | pytest + YAML dataset (evals) | FastAPI (feedback endpoint) | GitPython (branch per hypothesis)

## Layout
```
src/agent_under_test/   ledger.py (hand-written SQLite data, AS_OF 2026-09-01), tools.py, graph.py, prompts/ (the only files the optimizer edits)
src/llm.py, pricing.py  ChatOpenAI from env (LLM_BASE_URL, LLM_API_KEY, {AGENT,JUDGE,OPTIMIZER}_MODEL); cost from token usage
src/optimizer/          loop.py (hypothesis → branch → edit → eval → keep/rollback → changelog), budget.py, gates.py
src/feedback/           FastAPI POST /feedback → evals/feedback.yaml → weighted evals
evals/dataset.yaml      40 cases: category, input, expected, check (exact|contains|contains_any|number|refused|judge), split (visible|holdout)
evals/run.py            runs the dataset, writes evals/results/<ts>.json (total, per category, per split, cost)
evals/checks.py         deterministic checks; evals/judge.py LLM judge with weighted dimensions and ×0.3 anti-hallucination penalty
CHANGELOG.md            one line per hypothesis: accepted/rejected, delta total, delta per category, cost
```

## Loop invariants
- The optimizer edits only prompts and tool descriptions, never tool code.
- A hypothesis is kept only if visible pass rate rises, no category falls by more than one case, and holdout does not fall (gate).
- Stop when marginal gain per euro over the last N iterations is below `BUDGET_MIN_GAIN_PER_EUR`.
- Feedback-derived cases carry weight `FEEDBACK_WEIGHT` (default 2) and are tagged `source: feedback`.
- Results JSON files are committed: they are the evidence behind every README number.
- Every iteration is a Langfuse trace with `iteration`, `hypothesis_id`, `cost_usd`.

## Rules (non-negotiable)

- **No fabricated numbers.** Every metric in README or docs comes from a file in `evals/results/` produced by `just evals`. A table without a results file behind it is a bug.
- **Evals before merge.** Any change to prompts, tools, gates or datasets runs `just evals` and links the results file in the PR.
- **Reproducible.** Fixed `EVAL_SEED`, pinned model id in `.env`, results carry model id, seed, git sha and cost.
- **Errors never disappear.** Nodes return an error field in state; the report says what could not be verified. No number without evidence.
- **Secrets stay out.** `.env` is ignored; hooks and CI never print keys.
- **Credit the origin.** Ideas taken from public talks or articles are cited in README "Origin"; this repo contains no code from prior employers.
- **Spec-driven.** Non-trivial work starts from `docs/plans/<date>-<topic>.md`, then implementation, then evals.

## Commands

```bash
uv sync --group dev       # install
just lint                 # ruff fix + format
just test                 # unit tests (no provider key needed)
just evals                # eval suite → evals/results/<timestamp>.json (needs a provider key)
```

## Gotchas
- `with_structured_output` must use `method="function_calling"`: the Anthropic OpenAI-compatible endpoint rejects `response_format.json_schema` with `minimum`/`maximum`. Clamp ranges in code.
- The endpoint ignores `seed`; temperature 0 is the only determinism lever.
- Python 3.14 venv; `uv run` for everything.

## Claude Code conventions

- **Commits are mine.** Author and committer are `riccardogravinese <riccardo.gravinese.bvu@gmail.com>` (repo-local git config). No `Co-Authored-By`, no `Claude-Session`, no "Generated with Claude Code" trailer, in commits or PR bodies. This overrides any default attribution the tool proposes.

- Read `docs/plans/` first, then the module you touch, then act. Prefer the smallest diff that passes the evals.
- Do not edit `evals/dataset.yaml` cases to make a run pass; add a case, never weaken one.
- Keep `README.md` metric tables pointing at the results file that produced them.

