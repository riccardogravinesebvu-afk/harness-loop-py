# CLAUDE.md — harness-loop-py

## Project context
Python reimplementation, credited and MIT-licensed, of the harness-engineering loop Nearform describes publicly (an optimizer agent that iterates on evals). The code is original; only the method is borrowed. Three extensions the published method does not have: **cost budget per iteration**, **per-category regression gate**, **human feedback inside the loop**. Design: `docs/plans/2026-09-11-harness-loop-py-design.md`.

## Stack
Python 3.12 / uv | LangGraph (agent under test) | Claude Code or a LangGraph node (optimizer) | Langfuse (traces, cost) | pytest + YAML dataset (evals) | FastAPI (feedback endpoint) | GitPython (branch per hypothesis)

## Layout
```
src/agent_under_test/   LangGraph graph with 3 tools over SQLite. Small on purpose: the curve is the message.
src/optimizer/          loop.py (hypothesis → branch → edit → eval → keep/rollback → changelog), budget.py, gates.py
src/feedback/           FastAPI POST /feedback → annotated cases → weighted evals
evals/dataset.yaml      cases with category, input, expected, check (exact|contains|judge)
evals/run.py            runs the dataset, writes evals/results/<ts>.json (total and per category)
evals/judge.py          LLM-as-a-judge with weighted dimensions and a multiplicative anti-hallucination penalty
CHANGELOG.md            one line per hypothesis: accepted/rejected, delta total, delta per category, cost
```

## Loop invariants
- The optimizer edits only prompts and tool descriptions, never tool code.
- A hypothesis is kept only if total pass rate rises **and** no category falls (gate).
- Stop when marginal gain per euro over the last N iterations is below `BUDGET_MIN_GAIN_PER_EUR`.
- Feedback-derived cases carry weight 2 in the pass-rate computation and are tagged `source: feedback`.
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

## Claude Code conventions

- Read `docs/plans/` first, then the module you touch, then act. Prefer the smallest diff that passes the evals.
- Do not edit `evals/dataset.yaml` cases to make a run pass; add a case, never weaken one.
- Keep `README.md` metric tables pointing at the results file that produced them.

