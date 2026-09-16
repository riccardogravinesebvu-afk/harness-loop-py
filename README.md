# harness-loop-py

An optimizer agent that improves another agent by iterating on evals: propose a hypothesis, edit prompts and tool descriptions on a git branch, re-run the eval suite, keep or roll back, write the changelog. Reimplemented in Python from the method Nearform's AI Lead presents publicly (see Origin), and extended with three things the published method does not have:

1. **Cost budget per iteration.** The loop stops when marginal gain per euro drops below a threshold. The README shows the cost/pass-rate curve.
2. **Per-category regression gate.** A hypothesis that raises the total pass rate but lowers any eval category is rejected.
3. **Human feedback inside the loop.** Cases flagged through a feedback endpoint enter the dataset with higher weight, so the next iteration targets what users rejected.

## Status

Day 1 of 6: agent under test, 40-case dataset, deterministic checks, LLM judge, eval runner. Baseline measured. Next: Langfuse traces (day 2), optimizer node (day 3), budget and gate (day 4), feedback (day 5).

Design: `docs/plans/2026-09-11-harness-loop-py-design.md`. Decisions: `docs/PRD.md` §11.

## Results

Baseline, before any optimizer iteration. File: [`evals/results/2026-09-16T141714+0000.json`](evals/results/2026-09-16T141714+0000.json) (agent `claude-haiku-4-5-20251001`, judge `claude-sonnet-4-6`, seed 42, sha `28e0ffb`).

| Metric | Value |
|---|---|
| pass rate, all 40 cases (weighted) | 45% |
| pass rate, 30 visible / 10 holdout | 47% / 40% |
| per category: lookup / aggregation / reasoning / refusal | 90% / 60% / 30% / 0% |
| runs that never called `final_answer` / hit the step cap | 13 / 3 |
| cost of one full eval (agent + judge) | $0.43 (€0.37) |

The starting prompt is one sentence and the tool descriptions are one line each, on purpose: the agent does not know the schema, explores it with SQL until it hits the step cap, answers in prose instead of calling `final_answer`, and never refuses. That is the surface the optimizer gets to work on. The curves below stay empty until the loop runs.

| Metric | Value | Results file |
|---|---|---|
| pass rate per iteration, total, per category, visible and holdout | _day 3_ | — |
| cost per iteration, marginal gain per euro, stop point | _day 4_ | — |
| hypotheses rejected by the category gate | _day 4_ | — |
| iterations to recover a case flagged via feedback | _day 5_ | — |
| variance over 3 runs at temperature 0 | _day 6_ | — |

Every number in these tables points at a results file (model ids, seed, git sha, cost inside).

## The agent under test

A LangGraph graph over an invented SME ledger on SQLite (8 customers, 24 invoices, 13 payments, reference date 2026-09-01): one LLM node, one tool node, three tools (`run_sql` read-only, `lookup_customer`, `compute`) and a fourth tool, `final_answer(answer, refused)`, that ends the run. Structured output is a tool call, not parsed prose. The optimizer may edit only `src/agent_under_test/prompts/system.md` and `prompts/tools.yaml`.

Evals: `evals/dataset.yaml`, 40 cases in four categories (`lookup`, `aggregation`, `reasoning`, `refusal`), 30 visible to the optimizer and 10 held out. Checks are deterministic (`exact`, `contains`, `contains_any`, `number` with 0.5% tolerance, `refused`) except `reasoning`, graded by an LLM judge against a hand-written reference on three weighted dimensions (correctness 0.5, grounding 0.3, completeness 0.2) with a ×0.3 penalty when a number has no evidence in the tool outputs. Pass at 0.7.

## Quickstart

```bash
uv sync --group dev
cp .env.example .env          # set LLM_API_KEY; default endpoint is Anthropic, any OpenAI-compatible base URL works
just test                     # unit tests, no key needed
just evals                    # 40 cases → evals/results/<timestamp>.json, about $0.45
```

Determinism: temperature 0 everywhere; the Anthropic endpoint ignores `seed`, so runs can differ slightly. Day 6 reports the variance over 3 runs.

## Origin

Method: Alfonso Graziano (Nearform), "Agents Building Agents" talk and the AutoAgent write-up (2026): an optimizer agent iterating on evals with keep/rollback, reported at 18% → 83%. Nearform has not published code; this is an independent reimplementation of the described method. Shared background, not specific to that work: eval-driven development, LLM-as-a-judge, one git branch per hypothesis (Karpathy's auto-research is the common ancestor). Added here: the cost budget with a marginal-gain stop, the per-category regression gate, and weighted human feedback inside the dataset. This repository contains no code from that work or from any employer.

## License

MIT. See `LICENSE`.
