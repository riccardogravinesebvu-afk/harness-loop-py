# harness-loop-py

An optimizer agent that improves another agent by iterating on evals: propose a hypothesis, edit prompts and tool descriptions on a git branch, re-run the eval suite, keep or roll back, write the changelog. Reimplemented in Python from the method Nearform's AI Lead presents publicly (see Origin), and extended with three things the published method does not have:

1. **Cost budget per iteration.** The loop stops when marginal gain per euro drops below a threshold. The README shows the cost/pass-rate curve.
2. **Per-category regression gate.** A hypothesis that raises the total pass rate but lowers any eval category is rejected.
3. **Human feedback inside the loop.** Cases flagged through a feedback endpoint enter the dataset with higher weight, so the next iteration targets what users rejected.

## Status

Day 3 of 6: agent under test, 40-case dataset, checks and LLM judge, eval runner with Langfuse traces, and the optimizer loop with branch per hypothesis, regression gate, budget stop and changelog. First curve below. Next: gate and budget evidence across more iterations (day 4), feedback endpoint (day 5), variance and charts (day 6).

Design: `docs/plans/2026-09-11-harness-loop-py-design.md`. Decisions: `docs/PRD.md` §11 (day 1) and §12 (days 2-6).

## Results

Baseline, before any optimizer iteration. File: [`evals/results/2026-09-16T143601+0000.json`](evals/results/2026-09-16T143601+0000.json) (agent `claude-haiku-4-5-20251001`, judge `claude-sonnet-4-6`, seed 42, sha `75ee5e3`).

| Metric | Value |
|---|---|
| pass rate, all 40 cases (weighted) | 45% |
| pass rate, 30 visible / 10 holdout | 47% / 40% |
| per category: lookup / aggregation / reasoning / refusal | 90% / 60% / 30% / 0% |
| runs that never called `final_answer` / hit the step cap | 13 / 4 |
| cost of one full eval (agent + judge) | $0.42 (€0.36) |

An earlier run of the same prompts ([`2026-09-16T141714+0000.json`](evals/results/2026-09-16T141714+0000.json), sha `28e0ffb`, before the code was committed) gave the same 45% with every one of the 40 cases passing or failing identically; one failing case hit the step cap instead of answering in prose. Two runs are not a variance estimate; day 6 reports three runs of the final prompts.

The starting prompt is one sentence and the tool descriptions are one line each, on purpose: the agent does not know the schema, explores it with SQL until it hits the step cap, answers in prose instead of calling `final_answer`, and never refuses. That is the surface the optimizer gets to work on. The curves below stay empty until the loop runs.

### First optimizer loop

`just loop max=6`, stopped by the budget rule after 4 hypotheses. Loop file: [`evals/results/loops/2026-09-16T224557+0000.json`](evals/results/loops/2026-09-16T224557+0000.json); one results file per evaluated iteration, linked in [`CHANGELOG.md`](CHANGELOG.md). Optimizer `claude-sonnet-4-6`, agent `claude-haiku-4-5-20251001`, seed 42.

| iteration | hypothesis (branch) | verdict | visible | holdout | lookup / aggr / reasoning / refusal (visible) | cost € | cumulative € |
|---|---|---|---|---|---|---|---|
| 0 | baseline (`5799a80`) | — | 50% | 40% | 86 / 71 / 50 / 0 | 0.37 | 0.37 |
| 1 | schema, refusal rules, SQL guidance in `system.md` (`hyp/1`) | **accepted** | **90%** | **80%** | 86 / 100 / 75 / 100 | 0.32 | 0.69 |
| 2 | ISO country codes + ordering rules (`hyp/2`) | rejected before eval: prompt spells out an expected value (`Switzerland`) | — | — | — | 0.04 | 0.74 |
| 3 | same, reworded (`hyp/3`) | rejected before eval: same literal | — | — | — | 0.04 | 0.78 |
| 4 | same, without the literal (`hyp/4`) | rejected: holdout fell | 100% | 70% | 100 / 100 / 100 / 100 | 0.33 | 1.11 |
| stop | budget: the last 3 hypotheses bought 0 points per euro, threshold 0.03 | | | | | | 1.11 |

What the table shows, and what it does not:

- **One hypothesis did almost all the work.** The optimizer read the agent's code, put the schema, the outstanding/overdue arithmetic, the refusal policy and "always call `final_answer`" into the system prompt: visible 50% → 90%, holdout 40% → 80%, refusal 0 → 100%. The 40-case dataset is small on purpose; the curve is short because the first fix was the right one.
- **The holdout gate rejected a 100%-visible prompt.** Hypothesis 4 fixes the three remaining visible failures and loses one held-out reasoning case (`R06`, judged as reporting a figure not present in the tool outputs). With 10 holdout cases the gate's resolution is one case, and one judged case is also the run-to-run noise we observe (see below), so this is a conservative rejection, not proof of overfitting. It is what the gate is for.
- **The anti-leak check has false positives.** Hypotheses 2 and 3 were rejected without an eval because the prompt listed ISO country codes and the word `Switzerland` is an accepted answer of a visible case. The rule is mechanical by design (an expected value in the prompt is rejected, no judgement call); it cost €0.08 and two iterations. The optimizer got past it on the third try by dropping the literal.
- **Run-to-run noise is about one case.** The loop's baseline (47.5%) differs from the day-2 baseline (45%) by one judged reasoning case (`R08`) that flipped. Every eval runs at temperature 0; the endpoint ignores `seed`.
- **The budget rule fired for the right reason.** Three hypotheses in a row left the best visible pass rate unchanged; gain per euro over that window was 0.

| Metric | Value | Results file |
|---|---|---|
| pass rate per iteration, total, per category, visible and holdout | table above | loop file above |
| cost per iteration, marginal gain per euro, stop point | table above, stop at iteration 4 | loop file above |
| hypotheses rejected by the category gate | 0 by category, 1 by holdout, 2 by anti-leak | `CHANGELOG.md` |
| iterations to recover a case flagged via feedback | _day 5_ | — |
| variance over 3 runs at temperature 0 | _day 6_ | — |

Every number in these tables points at a results file (model ids, seed, git sha, cost inside).

## The agent under test

A LangGraph graph over an invented SME ledger on SQLite (8 customers, 24 invoices, 13 payments, reference date 2026-09-01): one LLM node, one tool node, three tools (`run_sql` read-only, `lookup_customer`, `compute`) and a fourth tool, `final_answer(answer, refused)`, that ends the run. Structured output is a tool call, not parsed prose. The optimizer may edit only `src/agent_under_test/prompts/system.md` and `prompts/tools.yaml`.

Evals: `evals/dataset.yaml`, 40 cases in four categories (`lookup`, `aggregation`, `reasoning`, `refusal`), 30 visible to the optimizer and 10 held out. Checks are deterministic (`exact`, `contains`, `contains_any`, `number` with 0.5% tolerance, `refused`) except `reasoning`, graded by an LLM judge against a hand-written reference on three weighted dimensions (correctness 0.5, grounding 0.3, completeness 0.2) with a ×0.3 penalty when a number has no evidence in the tool outputs. Pass at 0.7.

## Observability

Every eval run of one case is one Langfuse trace, named `eval:<case id>`, tagged with category and split, with a root span `eval_context` (input: case id, check, expected; output: answer, refused, error, passed, judge score; metadata: seed, git sha, results file, iteration, hypothesis id, cost) and the agent's LLM and tool calls underneath, plus the judge call for `judge` cases, so cost per case in Langfuse is agent + judge like in the results file. A `passed` score (0/1) is attached to the trace. Without `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` nothing is sent and nothing is logged.

The trace id is derived locally from the run timestamp and the case id, so it exists with or without Langfuse. The same id keys `evals/results/runs.jsonl`, a git-ignored append-only log with one line per run (input, expected, answer, tool calls with truncated outputs, verdict, cost, git sha, results file, iteration). Day 5's feedback endpoint rebuilds a flagged case from that line.

## The optimizer loop

`src/optimizer/loop.py` is a LangGraph graph: `baseline → propose → apply → evaluate → decide`, repeated until a stop. Each iteration:

1. **propose**: `claude-sonnet-4-6` reads the current prompt files, the agent's code (read-only), the visible pass rate per category, the failing visible cases with the agent's answer and tool calls, and the changelog of previous hypotheses. It never sees holdout cases. It returns one hypothesis: one target file (`system.md` or `tools.yaml`), its complete new content, a rationale, and optional eval cases for a human to review (`evals/proposed.yaml`). The prompt is generic (`src/optimizer/prompt.md`): it describes the method, not the ledger.
2. **apply**: branch `hyp/<n>` from `main`, write the file, commit. Two checks run before spending an eval: length caps (6000 / 3000 chars) and the anti-leak rule (no expected value of a visible case spelled out in the prompt).
3. **evaluate**: the full 40-case suite, with `iteration` and `hypothesis_id` in the results file and on every Langfuse trace.
4. **decide**: the gate keeps the hypothesis only if the visible pass rate rises, no category drops by more than one visible case (tolerance `1/n` computed from the dataset), and the holdout pass rate does not fall. Accepted: `main` fast-forwards. Rejected: `main` gets only the evidence (results file, changelog row, loop file); the branch stays. Stop when the marginal gain per euro over the last 3 iterations is below `BUDGET_MIN_GAIN_PER_EUR`, or at `MAX_ITERATIONS` / `MAX_TOTAL_EUR`. Every iteration's cost includes the optimizer's own tokens.

The loop refuses to start on a dirty working tree, so every number it produces is committed with the code that produced it.

## Quickstart

```bash
uv sync --group dev
cp .env.example .env          # set LLM_API_KEY; default endpoint is Anthropic, any OpenAI-compatible base URL works
                              # optional: LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY for traces
just test                     # unit tests, no key needed
just evals                    # 40 cases → evals/results/<timestamp>.json, about $0.45
just loop max=6               # optimizer loop: baseline + up to 6 hypotheses, about €0.35 per evaluated iteration
```

Determinism: temperature 0 everywhere; the Anthropic endpoint ignores `seed`, so runs can differ slightly. Day 6 reports the variance over 3 runs.

## Origin

Method: Alfonso Graziano (Nearform), "Agents Building Agents" talk and the AutoAgent write-up (2026): an optimizer agent iterating on evals with keep/rollback, reported at 18% → 83%. Nearform has not published code; this is an independent reimplementation of the described method. Shared background, not specific to that work: eval-driven development, LLM-as-a-judge, one git branch per hypothesis (Karpathy's auto-research is the common ancestor). Added here: the cost budget with a marginal-gain stop, the per-category regression gate, and weighted human feedback inside the dataset. This repository contains no code from that work or from any employer.

## License

MIT. See `LICENSE`.
