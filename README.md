# harness-loop-py

An optimizer agent that improves another agent by iterating on evals: propose one hypothesis, edit a prompt file on a git branch, re-run the eval suite, keep or roll back, write the changelog. A Python reimplementation of the method Nearform's AI lead presents publicly (see [Origin](#origin)), with three measured additions: a cost budget that stops the loop, a regression gate on categories and on a held-out split, and human feedback that re-weights eval cases.

## Results at a glance

Three numbers, three different provenances. They are not one curve.

| what | pass rate (total / visible / holdout) | evidence |
|---|---|---|
| starting prompt, one sentence | 45% / 47% / 40% | [`2026-09-16T143601`](evals/results/2026-09-16T143601+0000.json) |
| after the loop alone (2 accepted of 16 hypotheses, 40 cases, judge v1, mean of 3 runs) | 87% / 94% / 67% | [loops 1-5](#the-loops-in-detail), [variance v1](#variance-after-hypothesis-12-judge-v1) |
| same prompts, second measurement (44 cases, judge v2, mean of 3 runs; the agent did not change) | 91% / 97% / 70% | [measurement v2](#fixing-the-measurement-not-the-loop) |
| plus one hypothesis the gate rejected and a human accepted with evidence | 98% / 100% / 90% | [`2026-09-17T212958`](evals/results/2026-09-17T212958+0000.json), [loop 6](#loop-6) |

![pass rate per iteration](docs/img/pass_rate.svg)

![cost vs pass rate](docs/img/cost.svg)

Prompts on `main` today: [`system.md`](src/agent_under_test/prompts/system.md) from hypothesis 1 plus one line from hypothesis 19, [`tools.yaml`](src/agent_under_test/prompts/tools.yaml) from hypothesis 12. Charts from `uv run python scripts/plot.py` over the six loop files in `evals/results/loops/`; iterations are numbered by hypothesis branch, dotted lines mark a new loop with its re-measured baseline. Total API spend for everything in this README: about €9.3.

**Contents**: [Limits](#limits) · [What is added to the method](#what-is-added-to-the-method) · [How it works](#how-it-works) · [The loops in detail](#the-loops-in-detail) · [Reproduce](#reproduce) · [Origin](#origin)

## Limits

- **Small dataset, coarse gate.** 44 cases, 10 held out: one case is 10% of the holdout. The gate has one-case resolution and, until loop 5, one-run evidence. One hypothesis (12) was accepted on a lucky holdout run; the loop now re-runs the holdout before accepting.
- **The noise is in the refusal flag.** With judge v2, three runs of the same prompts give identical outcomes on 44 cases; the one case that still flips (`F08`) refuses in words and sets `refused=false`. Refusal checks demand the flag on purpose.
- **Rubric changes move the numbers.** Judge v2 raised the same prompts from 87% to 91% without touching the agent. Every results file carries `judge_version`; numbers across versions are not compared.
- **Two of the three "additions" are additions; one is a refinement.** Nearform's talk already describes a loop over user traces and feedback. What is added here is feedback as weighted eval cases with a measured recovery time. See [Origin](#origin).
- **The category gate never fired.** In 19 hypotheses nothing lowered a visible category while raising the total; every real rejection came from the holdout or from no gain. The rule is covered by unit tests only.
- **Optimizer and judge are the same model** (`claude-sonnet-4-6`). Three of four categories are deterministic checks and cannot be flattered; the fourth is judged against a hand-written reference at temperature 0.

## What is added to the method

1. **Cost budget.** Every iteration's cost (evals plus the optimizer's own tokens, rejected hypotheses included) is computed from token usage with a local price table. The loop stops when the gain per euro over the last three iterations falls below `BUDGET_MIN_GAIN_PER_EUR`, or at `MAX_ITERATIONS` / `MAX_TOTAL_EUR`. It stopped five loops out of six.
2. **Regression gate on categories and holdout.** A hypothesis is kept only if the visible pass rate rises, no category loses more than one visible case (tolerance computed from the dataset), and the held-out split does not fall, on two separate holdout runs. The optimizer never sees holdout cases.
3. **Human feedback as weighted cases.** `POST /feedback` on a run's trace id re-weights that eval case (default ×2) and puts the human note next to the failure the optimizer reads. The loop records how many iterations it takes to recover a flagged case: 2, in the one trial run.

## How it works

**Agent under test.** A LangGraph graph over an invented SME ledger on SQLite (8 customers, 24 invoices, 13 payments, reference date 2026-09-01): one LLM node (`claude-haiku-4-5-20251001`), one tool node, three tools (`run_sql` read-only, `lookup_customer`, `compute`) and a fourth, `final_answer(answer, refused)`, that ends the run. Structured output is a tool call, not parsed prose. The optimizer may edit only `src/agent_under_test/prompts/system.md` and `prompts/tools.yaml`; it reads the agent's code but never changes it.

**Evals.** `evals/dataset.yaml`: 44 cases (40 at the start, 4 added after loop 5, none ever changed) in four categories (`lookup`, `aggregation`, `reasoning`, `refusal`), 34 visible to the optimizer and 10 held out. Checks are deterministic (`exact`, `contains`, `contains_any`, `number` with 0.5% tolerance, `refused`) except most of `reasoning`, graded by `claude-sonnet-4-6` against a hand-written reference on three weighted dimensions (correctness 0.5, grounding 0.3, completeness 0.2) with a ×0.3 penalty when a figure has no evidence in the tool outputs; pass at 0.7. Every run writes `evals/results/<ts>.json` with model ids, seed, git sha, judge version, per-case outcome and cost.

**Optimizer loop.** `src/optimizer/loop.py`, a LangGraph graph `baseline → propose → apply → evaluate → decide`:

1. **propose**: `claude-sonnet-4-6` reads the current prompt files, the agent's code, the visible pass rate per category, the failing visible cases with the agent's answer and tool calls, and the changelog of previous hypotheses. It returns one hypothesis: one target file, its complete new content, a rationale, and optional eval cases for a human to review (`evals/proposed.yaml`). Its prompt (`src/optimizer/prompt.md`) describes the method, not the ledger.
2. **apply**: branch `hyp/<n>` from `main`, write the file, commit. Two checks run before spending an eval: length caps and the anti-leak rule (no expected value of a failing visible case spelled out in the prompt).
3. **evaluate**: the full suite, with `iteration` and `hypothesis_id` in the results file and on every Langfuse trace; on a pass, the holdout again.
4. **decide**: the gate above. Accepted: `main` fast-forwards. Rejected: `main` gets only the evidence (results file, changelog row, loop summary file); the branch stays. The loop refuses to start on a dirty working tree, so every number is committed with the code that produced it.

**Feedback.** `just feedback` starts a local FastAPI server (no auth: a development tool). `POST /feedback {trace_id, verdict: bad|good, note}` finds the run in `evals/results/runs.jsonl` and appends an entry to `evals/feedback.yaml`; a dataset case gets weight `FEEDBACK_WEIGHT`, an ad-hoc question becomes a new judged case with the note as reference. `good` is recorded and changes nothing; revoking is deleting the entry. The loop re-reads the file every iteration and recomputes its baseline under the new weights.

**Observability.** One Langfuse trace per eval run of one case (root span `eval_context` with case, verdict and cost; the agent's calls and the judge call underneath; a `passed` score). The trace id is derived locally from timestamp and case id, so it keys `runs.jsonl` with or without Langfuse keys; without keys nothing is sent.

## The loops in detail

### Baseline

Before any optimizer iteration. File: [`evals/results/2026-09-16T143601+0000.json`](evals/results/2026-09-16T143601+0000.json) (agent `claude-haiku-4-5-20251001`, judge `claude-sonnet-4-6`, seed 42, sha `75ee5e3`).

| Metric | Value |
|---|---|
| pass rate, all 40 cases (weighted) | 45% |
| pass rate, 30 visible / 10 holdout | 47% / 40% |
| per category: lookup / aggregation / reasoning / refusal | 90% / 60% / 30% / 0% |
| runs that never called `final_answer` / hit the step cap | 13 / 4 |
| cost of one full eval (agent + judge) | $0.42 (€0.36) |

An earlier run of the same prompts ([`2026-09-16T141714+0000.json`](evals/results/2026-09-16T141714+0000.json), sha `28e0ffb`, before the code was committed) gave the same 45% with every one of the 40 cases passing or failing identically; one failing case hit the step cap instead of answering in prose.

The starting prompt is one sentence and the tool descriptions are one line each, on purpose: the agent does not know the schema, explores it with SQL until it hits the step cap, answers in prose instead of calling `final_answer`, and never refuses. That is the surface the optimizer gets to work on.

### Loop 1

**Loop 1**: `just loop max=6`, stopped by the budget rule after 4 hypotheses. Loop file: [`evals/results/loops/2026-09-16T224557+0000.json`](evals/results/loops/2026-09-16T224557+0000.json); one results file per evaluated iteration, linked in [`CHANGELOG.md`](CHANGELOG.md). Optimizer `claude-sonnet-4-6`, agent `claude-haiku-4-5-20251001`, seed 42.

| iteration | hypothesis (branch) | verdict | visible | holdout | lookup / aggr / reasoning / refusal (visible) | cost € | cumulative € |
|---|---|---|---|---|---|---|---|
| 0 | baseline (`5799a80`) | — | 50% | 40% | 86 / 71 / 50 / 0 | 0.37 | 0.37 |
| 1 | schema, refusal rules, SQL guidance in `system.md` (`hyp/1`) | **accepted** | **90%** | **80%** | 86 / 100 / 75 / 100 | 0.32 | 0.69 |
| 2 | ISO country codes + ordering rules (`hyp/2`) | rejected before eval: prompt spells out an expected value (`Switzerland`) | — | — | — | 0.04 | 0.74 |
| 3 | same, reworded (`hyp/3`) | rejected before eval: same literal | — | — | — | 0.04 | 0.78 |
| 4 | same, without the literal (`hyp/4`) | rejected: holdout fell | 100% | 70% | 100 / 100 / 100 / 100 | 0.33 | 1.11 |
| stop | budget: the last 3 hypotheses bought 0 points per euro, threshold 0.03 | | | | | | 1.11 |

### Loops 2 and 3

**Loops 2 and 3** (next day, from the accepted prompt, €3 authorised in total): loop files [`2026-09-17T085216+0000.json`](evals/results/loops/2026-09-17T085216+0000.json) and [`2026-09-17T085632+0000.json`](evals/results/loops/2026-09-17T085632+0000.json), rows 5-10 of the changelog.

| loop | iteration | hypothesis | verdict | visible | holdout | cost € |
|---|---|---|---|---|---|---|
| 2 | 0 | baseline of the accepted prompt | — | 87% | 80% | 0.37 |
| 2 | 5, 6, 7 | ISO country codes + ordering rules, three wordings | rejected before eval: anti-leak on `Switzerland` (see below) | — | — | 0.04 each |
| 2 | stop | budget, €0.39 spent | | | | |
| 3 | 0 | baseline again | — | 87% | 80% | 0.37 |
| 3 | 8 | ISO country codes + overdue-invoice reasoning | rejected: holdout | 97% | 70% | 0.32 |
| 3 | 9 | same, reworded | rejected: holdout | 97% | 60% | 0.32 |
| 3 | 10 | same, reworded | rejected: holdout | 97% | 70% | 0.34 |
| 3 | stop | budget, €1.24 spent | | | | |

What the tables show, and what they do not:

- **One hypothesis did almost all the work.** The optimizer read the agent's code, put the schema, the outstanding/overdue arithmetic, the refusal policy and "always call `final_answer`" into the system prompt: visible 50% → 90%, holdout 40% → 80%, refusal 0 → 100%. The 40-case dataset is small on purpose; the curve is short because the first fix was the right one.
- **The holdout gate rejected the same idea four times.** Hypotheses 4, 8, 9 and 10 are one idea (ISO country codes, rules for "oldest overdue invoice"): each fixes the same three visible cases (`L09`, two reasoning cases) and each loses held-out cases the optimizer never sees. In loop 3 the lost case is always `F08`, a refusal ("What was Helios Energy's revenue last year?"): the agent declines in words but stops setting `refused=true`. At the time this read as a real overfit caught four times; the variance runs later showed that `F08` also flips on its own (it fails in 3 of 3 re-runs of the prompt that was accepted at 80% holdout). The honest reading: the four rejections were the gate doing its job on a signal that is part regression, part flag noise, and the loop had no way to tell them apart until the holdout confirmation of loop 5. A per-category gate on visible cases alone would have accepted all four.
- **The per-category gate did not fire** in these loops (nor later): the rejections came from the holdout. The rule is exercised by unit tests (`tests/test_optimizer.py`).
- **The anti-leak check had a false positive, now fixed.** Hypotheses 2, 3, 5, 6 and 7 were rejected without an eval because the prompt listed ISO codes ("`'CH'` for Switzerland") and `Switzerland` is an accepted answer of `L02`, a case that already passed. The check now covers only failing visible cases, exactly the ones whose expected value the optimizer is shown (PRD §12 D4, amended). Cost of the false positive: €0.21 and five iterations.
- **The optimizer repeats itself.** After a holdout rejection it resubmitted the same change with new wording three times. The optimizer prompt now says that rewording is repeating and that a holdout rejection means the change must shrink or move to a different mechanism (`src/optimizer/prompt.md`, rule 5). Loop 4 shows it working once; loop 5 shows it ignored after a `no_gain` rejection.
- **Run-to-run noise is about one case.** Baselines of the same prompt: 45% and 47.5% on day 2 (one judged case, `R08`), 90% and 87% visible after hypothesis 1 (one judged case, `R03`). Every eval runs at temperature 0; the endpoint ignores `seed`.
- **The budget rule fired three times for the right reason.** Each time, three hypotheses in a row left the best visible pass rate unchanged; gain per euro over that window was 0.

### Loop 4, with human feedback

**Loop 4** (loop file [`2026-09-17T162024+0000.json`](evals/results/loops/2026-09-17T162024+0000.json)): before starting it, the run of `L09` ("List the customers based in Italy", failing since loop 1) was flagged through `POST /feedback` with the note "the answer lists nobody; country is stored as a code, not a name". The entry in [`evals/feedback.yaml`](evals/feedback.yaml) reweights `L09` to 2, so the weighted visible baseline reads 84% instead of 87%, and the optimizer sees the note next to the failure.

| iteration | hypothesis | verdict | visible (weighted) | holdout | cost € |
|---|---|---|---|---|---|
| 0 | baseline, `L09` weight 2 | — | 84% | 80% | 0.37 |
| 11 | ISO country codes in `system.md` | rejected: holdout (lost `R06`) | 94% | 70% | 0.30 |
| 12 | same hint, moved to the `run_sql` description in `tools.yaml` | **accepted** | **94%** | 80% | 0.30 |
| 13 | days-overdue arithmetic | rejected before eval: anti-leak on `2026` (a year in a date, false positive, fixed) | — | — | 0.04 |
| stop | max iterations (3) | | | | 0.90 total |

**Iterations to recover the flagged case: 2** (flagged before iteration 11, passing in accepted iteration 12; `feedback` block of the loop file). Two things happened that had not happened in loops 1-3: the optimizer changed mechanism after a holdout rejection (rule 5 in its prompt, added after loop 3) instead of rewording, and the same fix that had failed the holdout four times inside `system.md` passed it as a one-line tool description. The variance runs below show that pass was a lucky draw on `F08`: the fix was right for `L09`, the holdout evidence for it was not.

### Variance after hypothesis 12 (judge v1)

Three runs of the prompts on `main` after hypothesis 12, same seed, temperature 0, run back to back: [`2026-09-17T163541+0000.json`](evals/results/2026-09-17T163541+0000.json), [`2026-09-17T164030+0000.json`](evals/results/2026-09-17T164030+0000.json), [`2026-09-17T164128+0000.json`](evals/results/2026-09-17T164128+0000.json) (`uv run python scripts/variance.py` on those files; the first run's sha precedes a commit that touched only scripts and the anti-leak check, not the prompts).

| metric | min | mean | max |
|---|---|---|---|
| total (weighted, `L09` ×2) | 85% | 87.0% | 88% |
| visible | 94% | 93.5% | 94% |
| holdout | 60% | 66.7% | 70% |
| lookup / aggregation | 100% | 100% | 100% |
| reasoning | 60% | 66.7% | 70% |
| refusal | 80% | 80% | 80% |

- **Visible is stable**: the same 29 of 30 weighted cases pass in all three runs. One case flips across the three runs, `R06`, a judged holdout reasoning case.
- **The acceptance of hypothesis 12 was a lucky draw.** In the run that got it accepted, holdout was 80% with `F08` ("What was Helios Energy's revenue last year?") passing. In all three re-runs of the same prompts `F08` fails: the agent declines in words without setting `refused=true`, the same regression the holdout gate had rejected four times when the ISO-code hint sat in `system.md`. Moving it to the tool description did not fix that; one run happened to pass. Honest holdout for the final prompts is about 67%, not 80%. The gate had one-case resolution and one-run evidence, and the noise is one case: a real hypothesis slipped through. Fix implemented right after this finding: the holdout is re-run on acceptance and the lower run becomes the bar (loop 5 above); its cost enters the budget.
- **Four cases fail in every run**: `F04` (a refusal), `R03`, `R04`, `R09` (judged reasoning, mostly figures the judge finds unsupported by tool outputs). Reading the references and the answers: `R03` and `R04` were penalised for sums of figures the tools had returned separately. That is a rubric problem, fixed as judge v2 below; `F04` and `R09` are agent problems.

### Loop 5, with holdout confirmation

**Loop 5** (loop file [`2026-09-17T165112+0000.json`](evals/results/loops/2026-09-17T165112+0000.json)): after the variance finding, the loop was changed so that a hypothesis passing the gate is re-run on the 10 holdout cases and kept only if the second run holds too; the lower of the two runs becomes the bar for the next comparison (`docs/plans/2026-09-17-holdout-confirmation.md`). Then one more loop from the final prompts.

| iteration | hypothesis | verdict | visible (weighted) | holdout | cost € |
|---|---|---|---|---|---|
| 0 | baseline, re-measured | — | 97% | 70% | 0.37 |
| 14 | payment dates in reliability analysis | rejected: no gain (fixed `R04`, broke `R02`, `R03`, `R05`, `R06`) | 90% | 60% | 0.33 |
| 15 | same, reworded | rejected: no gain (fixed `R09`, broke `R02`, `R05`, `R06`) | 90% | 70% | 0.34 |
| 16 | same, reworded | rejected: no gain (fixed `F08`, broke `R02`, `R05`, `R06`) | 90% | 70% | 0.33 |
| stop | budget | | | | 1.27 total |

- **The confirmation never ran on a real hypothesis**: nothing passed the gate in loop 5. It is exercised by the mechanics test (`tests/test_loop_mechanics.py`: an accepted hypothesis with both runs holding, and one rejected as `holdout_confirm` when the second run drops). The number it was built to report, "acceptances overturned by the confirmation", is 0 of 0 so far.
- **The loop is at its noise floor.** With one or two visible failures left, every candidate fix buys one case and costs two to four judged reasoning cases: adding detail to the prompt makes the judge find more figures it considers unsupported. The gate is right to refuse all three, and the budget rule stops the loop after three flat iterations. More iterations would not help; a larger dataset and a judge less sensitive to derived figures would. The optimizer also ignored its own rule 4 (it reworded the same idea three times after `no_gain`); rule 5 only covers holdout rejections.
- **Re-measured baseline**: 97% here against 94% right after hypothesis 12 was accepted, same prompts and seed: `R03` passed this time, one judged case.

### Fixing the measurement, not the loop

Loop 5 showed the loop at the noise floor of a 40-case dataset. Two changes to the measurement, both committed before any new run (`eb049ca`), then a re-measured baseline: [`2026-09-17T202029+0000.json`](evals/results/2026-09-17T202029+0000.json).

- **Four cases added, none changed** (`F11`, `F12`, `R11`, `R12`): two visible refusals of the kind that was failing only in holdout (a prediction, an external fact), and the two optimizer proposals worth keeping (earliest overdue invoice, days overdue). 44 cases, 34 visible, 10 holdout. Category tolerance is recomputed from the dataset (one case of 10 for reasoning and refusal).
- **Judge v2**: a figure obtained by adding, subtracting, dividing or counting figures in the tool outputs is supported evidence. Judge v1 penalised "5,250 outstanding" when the tools returned 3,750 and 1,500. `judge_version` is in every results file from here on.

| final prompts, same seed | 40 cases, judge v1 (mean of 3) | 44 cases, judge v2 (mean of 3, plus the first run) |
|---|---|---|
| total | 87% | 91% (first run 93%) |
| visible | 94% | 97% |
| holdout | 67% | 70% (first run 80%) |
| failing | `F04`, `F08`, `R03`, `R04`, `R09` (+`R06` once) | `F04`, `F08`, `F11`, `R09` (`F08` passed in the first run only) |

Variance on the new measurement, three runs back to back ([`202749`](evals/results/2026-09-17T202749+0000.json), [`202856`](evals/results/2026-09-17T202856+0000.json), [`203003`](evals/results/2026-09-17T203003+0000.json)): identical, 0 of 44 cases change outcome. Judge v2 removed the flips on judged cases; what remains noisy is the `refused` flag on `F08`, which passed in the first run of the new baseline and in none of the three after it.

This jump is not an agent improvement: the agent did not change. It is the rubric being fairer on derived figures (`R03`, `R04` now pass) and, in the first run only, `F08` passing. Numbers before and after this point are not comparable, which is why the results file carries the judge version.

### Loop 6

**Loop 6, on the new measurement** (loop file [`2026-09-17T202211+0000.json`](evals/results/loops/2026-09-17T202211+0000.json), rows 17-19 of the changelog): €1.24, budget stop, nothing accepted.

| iteration | hypothesis | verdict | visible | holdout | cost € |
|---|---|---|---|---|---|
| 0 | baseline, re-measured | — | 97% | 70% | 0.29 |
| 17 | refuse future-payment predictions (long rule) | rejected: no gain (fixed all 4 failures, broke `R02`, `R03`, `R07`) | 91% | 100% | 0.31 |
| 18 | prediction/forecast rule, broader | rejected: no gain (broke 5 reasoning cases) | 89% | 70% | 0.32 |
| 19 | one line: "will X pay?" cannot be determined from the ledger | rejected: no gain (fixed `F04`, `F08`, `F11`; lost `F12`) | 97% | 90% | 0.32 |

- **The new visible refusal did its job.** With `F11` failing on visible, the optimizer went straight at the prediction refusals it had never targeted in five loops, and by the third try found the minimal rule (one line). Hypothesis 19 fixes all three prediction/external refusals, two of them in holdout.
- **The gate rejected it, correctly by its own rule, and the rule is right.** Visible pass rate must rise strictly; hypothesis 19 gains `F11` and loses `F12`, net zero, while holdout goes from 70% to 90%. Accepting on holdout gain would turn the holdout into an optimization target, which is the one thing it must not be. The right move is a human one, and it was taken: `hyp/19` was merged by hand (`7a74118`), re-measured ([`2026-09-17T212958+0000.json`](evals/results/2026-09-17T212958+0000.json): visible 100%, holdout 90%, total 98%, only `F08` failing, with the right words and the wrong flag; `F12` passed this time) and written in the changelog as `accepted (human)`. The loop's own curve stops at hypothesis 19; the human decision is a separate row with its own results file, so the two are never confused.
- **The noise is in the structured flag.** Under hypothesis 19 the agent's answer to `F12` ("How many employees does Alpine Foods have?") is the same sentence as at baseline, "I cannot provide employee count information…", but `refused` flips from true to false. The same thing happened to `F08` across the variance runs. The check is right to demand the flag (a refusal the caller cannot detect is not a refusal), and it means refusal cases carry the run-to-run noise that judged cases carry for other reasons.

### Every metric the design asked for

| metric | value | evidence |
|---|---|---|
| pass rate per iteration, total, per category, visible and holdout | tables above | six loop files in `evals/results/loops/` |
| cost per iteration, marginal gain per euro, stop point | tables above; budget stops after hypotheses 4, 7, 10, 16, 19; max-iterations stop after 13 | same |
| verdicts over 19 hypotheses | 2 accepted by the loop, 1 by a human over the gate; 5 rejected on holdout, 6 on no gain, 6 by anti-leak, 0 on a visible category, 0 by holdout confirmation | [`CHANGELOG.md`](CHANGELOG.md) |
| iterations to recover a case flagged via feedback | 2 | loop 4 file, `feedback` block |
| variance over 3 runs at temperature 0 | judge v1: 1 of 40 cases flips; judge v2: 0 of 44 | six results files, linked above |

Every number in this README points at a results file (model ids, seed, git sha, judge version, cost inside).

## Reproduce

```bash
uv sync --group dev
cp .env.example .env          # set LLM_API_KEY; default endpoint is Anthropic, any OpenAI-compatible base URL works
                              # optional: LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY for traces
just test                     # unit tests, no key needed
just evals                    # 44 cases → evals/results/<timestamp>.json, about $0.35
just loop max=6               # optimizer loop from the current main, about €0.35 per evaluated iteration; refuses a dirty tree
just feedback                 # POST /feedback on :8765
uv run python scripts/plot.py                                                   # charts from evals/results/loops/*.json
uv run python scripts/variance.py evals/results/A.json evals/results/B.json     # min/mean/max and flipping cases
```

Temperature is 0 everywhere and `EVAL_SEED` is passed to the provider, but the Anthropic endpoint ignores it. With judge v2 three back-to-back runs were identical on 44 cases; the case that can still flip is a refusal whose `refused` flag the model sets inconsistently. Design: `docs/plans/2026-09-11-harness-loop-py-design.md`; decisions and their amendments: `docs/PRD.md` §11-12.

## Origin

The method is Alfonso Graziano's (Nearform), from the talk ["Agents Building Agents"](https://www.youtube.com/watch?v=aHhB3sjGjkI) (Nearform's channel, 2026; [summary on daily.dev](https://daily.dev/posts/agents-building-agents---alfonso-graziano-nearform-p61ktlb5k)): an optimizer agent that generates hypotheses, edits the agent, runs the evals and rolls back regressions, reported at 18% → 83% on a fresh agent and 67% → 86% on a production one, with Karpathy's auto-research as the stated inspiration. Background on the evals themselves: his article ["From AI prototype to production: how to build evals for reliable agents"](https://nearform.com/digital-community/from-ai-prototype-to-production-how-to-build-evals-for-reliable-agents/) (Nearform, March 2026). Both consulted on 2026-09-17.

Nearform has not published code; this is an independent reimplementation of the described method in Python, on a different domain. The 18% → 83% figure is theirs and is not reproduced here: this repository reports its own curve on its own dataset. Shared background, not specific to that work: eval-driven development, LLM-as-a-judge, one git branch per hypothesis. The talk also describes a second loop over production traces and user feedback to find failure clusters; this repository does not claim that idea. What is added here: the cost budget with a marginal-gain stop, the gate on categories and on a held-out split with confirmation, and feedback turned into weighted eval cases with a measured recovery time. This repository contains no code from that work or from any employer.

## License

MIT. See `LICENSE`.
