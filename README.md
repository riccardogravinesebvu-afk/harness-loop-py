# harness-loop-py

An optimizer agent that improves another agent by iterating on evals. It proposes one hypothesis,
edits a prompt file on a git branch, re-runs the eval suite, keeps the change or rolls it back, and
records the result. Then it does it again, until the gains stop paying for themselves.

The method is Alfonso Graziano's, from Nearform, and he presents it publicly (see [Origin](#origin)).
His own implementation is public too, in TypeScript. This one is written from the talk, in Python, on
a domain of my own, and differs where it matters most: the rule that decides whether a change is kept.
His is a hand-written tolerance band on aggregate accuracy. Mine has to clear three separate bars,
one of them on cases the optimizer never sees, confirmed by a second run.

Every number below comes out of a JSON file committed in `evals/results/`. A number without a file
behind it is a bug.

## Setup

The agent under test answers questions about an invented SME ledger in SQLite (8 customers, 24
invoices, 13 payments, reference date fixed at 2026-09-01) using three tools plus a structured
`final_answer`. It starts with a one-sentence system prompt and one-line tool descriptions, so it
doesn't know the schema and never refuses anything. That's the surface the optimizer works on, and
the only surface: it can read the tool code, it can only write the two prompt files.

The eval set is 44 hand-written cases in four categories, 34 visible to the optimizer and 10 held
out. Most checks are deterministic; reasoning cases go to an LLM judge scoring against a reference
written from the data. Six loops ran over two days: 19 hypotheses, about €9.3 of API spend, one
results file per evaluated iteration.

## Results

| | total | visible | holdout | |
|---|---|---|---|---|
| starting prompt | 45% | 47% | 40% | [file](evals/results/2026-09-16T143601+0000.json) |
| after the loop, judge v1, 40 cases | 87% | 94% | 67% | mean of 3 replications |
| same prompts, judge v2, 44 cases | 91% | 97% | 70% | mean of 3 replications |
| plus one hypothesis accepted by hand over the gate | 98% | 100% | 90% | [file](evals/results/2026-09-17T212958+0000.json) |

Rows two and three are the same agent measured two ways, so the 4-point difference between them is
rubric, not behaviour. Row four is a human overriding a gate decision, kept as a separate row so the
loop's own curve stays clean.

![pass rate per iteration](docs/img/pass_rate.svg)

![cost vs pass rate](docs/img/cost.svg)

Per-loop tables, every hypothesis and every verdict: [docs/loops.md](docs/loops.md).

## Findings

**The gain is concentrated in one hypothesis.** Hypothesis 1 moved the visible rate from 50% to 90%
and refusals from 0% to 100% in a single edit: the optimizer read `ledger.py` and `tools.py`, worked
out that the agent had no schema, and wrote the schema, the overdue arithmetic and the refusal policy
into the system prompt. The remaining 18 hypotheses produced one accepted change between them. Most
of the value of this kind of loop appears to be in finding the first missing thing.

**Single-run gating is unsound at this resolution.** With 10 holdout cases, one case is 10 points,
and measured run-to-run noise was about one case. Hypothesis 12 passed the gate with the holdout at
80%; three replications of those exact prompts put it at 67%, with the same case (`F08`) failing each
time. A regression the gate had rejected four times passed on the fifth attempt because of sampling,
not because of the change. The loop now re-runs the holdout before accepting and takes the lower of
the two runs as the new bar, which costs about $0.10 per acceptance.

**The judging rubric moves the score more than most hypotheses do.** Judge v1 flagged any figure not
literally present in the tool outputs, so "5,250 outstanding" failed when `run_sql` had returned
3,750 and 1,500 separately. Judge v2 accepts sums, differences and counts as grounded. Same agent,
same seed: +4 points total, and run-to-run flips went from 1 case in 40 to 0 in 44. Results files
carry `judge_version` so numbers either side of that change are never pooled.

**The optimizer only fixes what it can see.** Refusal failures of the prediction and external-fact
kind sat in the holdout for five loops and were never targeted, because the optimizer is shown
visible failures only. Adding one visible case of that class produced a working fix within three
iterations, and that fix repaired the two held-out cases as well. Split design is not just an
anti-overfitting device; it also decides what the loop is capable of noticing.

**Rejections outnumber acceptances by an order of magnitude, and that's the working state.** Of 19
hypotheses: 2 accepted by the loop, 1 accepted by a human over the gate, 5 rejected on the holdout, 6
on no visible gain, 6 refused before any eval ran. The budget rule ended five of the six loops, each
time after three flat iterations.

**The residual noise is in the structured flag, not the judge.** After the rubric fix, three
back-to-back runs agree on all 44 cases except one: a refusal where the agent declines in the right
words and leaves `refused=false`. The check demands the flag deliberately, because a refusal the
caller can't detect isn't a refusal, so this is a real property of the agent rather than measurement
error. It is also the last failing case.

## Limitations

The dataset is small and single-domain: 44 cases, one ledger, one provider, one agent. Holdout
resolution is 10 points per case, so any claim about a 1-case difference is at the noise floor.

Two accepted hypotheses is a small sample. Statements here about what the gate prevents are backed by
its rejections, which are more numerous, not by a controlled comparison against a loop running
without it.

The per-category gate never fired in 19 hypotheses. Nothing raised the total while lowering a visible
category, so that rule has unit tests and no field evidence.

The optimizer, the judge and this write-up's conclusions all share a model family. Three of the four
eval categories are deterministic and can't be flattered, and judged cases are scored against
hand-written references at temperature 0, but the risk is structural and worth naming.

The anti-leak check, which refuses hypotheses that write an expected answer into the prompt,
initially scanned every visible case including passing ones. A list of ISO codes containing
`Switzerland` and a mention of the year `2026` were refused on that basis: six iterations and €0.25
spent before the scope was narrowed to currently-failing cases.

## Running it

```bash
uv sync --group dev
cp .env.example .env   # LLM_API_KEY; the default endpoint is Anthropic, any OpenAI-compatible base URL works
just test              # unit tests, no API key needed
just evals             # 44 cases, about $0.35, writes evals/results/<timestamp>.json
just loop max=6        # baseline plus up to 6 hypotheses, about €0.35 per evaluated iteration
just feedback          # the feedback endpoint on :8765
```

The loop refuses to start on a dirty working tree, so every number is committed alongside the code
that produced it. Accepted hypotheses fast-forward `main`; rejected ones leave their branch as
`hyp/<n>` and only the evidence lands on `main`.

Temperature is 0 everywhere and `EVAL_SEED` is passed to the provider, though the Anthropic endpoint
ignores it. `scripts/plot.py` regenerates the charts from the loop files; `scripts/variance.py` takes
any number of results files and reports min/mean/max plus the cases that disagree.

## Implementation

`src/optimizer/loop.py` is a LangGraph graph: baseline, propose, apply, evaluate, decide. The
optimizer (Sonnet 4.6) is shown the current prompts, the agent's code, the pass rate per category,
every failing visible case with the agent's answer and tool calls, and the changelog of what's
already been tried. It returns one hypothesis: one target file and its complete new content. Two
static checks run before any eval is spent, on length and on leaked expected values.

The gate keeps a hypothesis only if the visible rate rises, no category loses more than one visible
case (tolerance `1/n`, computed from the dataset), and the holdout doesn't fall on two separate runs.
Cost per iteration is computed from token usage against a local price table, includes the optimizer's
own tokens and every rejected hypothesis, and drives the stop rule.

The optimizer can also propose eval cases. They land in `evals/proposed.yaml` and stay there until a
human moves them, because a loop that writes its own exams isn't measuring anything. Cases in the
dataset get added, never weakened; that rule is in `CLAUDE.md` and it held for the whole project.

`POST /feedback` takes a run's trace id and a note. A dataset case doubles in weight and the note
appears beside the failure the optimizer reads; an ad-hoc question becomes a new judged case with the
note as its reference. A case flagged this way, failing since loop 1, came back two iterations later,
and the loop records that number itself.

Langfuse is optional: with keys, each eval run of each case is one trace carrying the case, the
verdict and the cost. The trace id is derived locally either way, which is what lets the feedback
endpoint find a run again without it.

## Origin

The method comes from Alfonso Graziano (Nearform), in the talk
["Agents Building Agents"](https://www.youtube.com/watch?v=aHhB3sjGjkI)
([summary](https://daily.dev/posts/agents-building-agents---alfonso-graziano-nearform-p61ktlb5k)):
an optimizer agent that generates hypotheses, edits the agent, runs the evals and rolls back
regressions, reported at 18% to 83% on a fresh agent and 67% to 86% on a production one, with
Karpathy's auto-research as the stated inspiration. His article
["From AI prototype to production"](https://nearform.com/digital-community/from-ai-prototype-to-production-how-to-build-evals-for-reliable-agents/)
covers the eval side. Both read on 2026-09-17.

His implementation is public: [`alfonsograziano/auto-agent`](https://github.com/alfonsograziano/auto-agent)
(TypeScript, MIT, sponsored by Nearform) with its target repo
[`auto-agent-demo`](https://github.com/alfonsograziano/auto-agent-demo), a Mastra math agent and a
60-case golden dataset. I built this from the talk and found the repository afterwards, which is why
none of its code is here and why the two designs diverge where they do.

Read side by side, the loop is the same shape and the accept rule is not:

| | auto-agent | here |
|---|---|---|
| keeps a change when | accuracy improves, or dips within a hand-written ~1-2pp band the LLM judges "structurally sound" | the visible rate strictly rises, no category loses more than one case, the holdout does not fall on either of two runs |
| held-out split | none | 10 cases, in the gate, never shown to the optimizer |
| stops when | `--max-iterations` (default 5) | marginal pass-rate gain per euro falls below a threshold over a 3-iteration window, or a hard cap |
| cost and latency | fields in the job template, injected into the optimizer's prompt; the spec lists multi-metric constraints as out of scope | computed from token usage, includes rejected hypotheses, drives the stop rule |
| the optimizer may edit | system prompts, tool descriptions, tool code, new tools | two prompt files, nothing else |
| memory across iterations | `MEMORY.md` the optimizer maintains | the changelog rows, passed back as context |

His optimizer has the larger surface and mine has the stricter gate. The 18% to 83% figure is his; it
is not reproduced here and not claimed here. On his own account that baseline is a deliberate floor:
the agent has no tools, and 18% is what the model answers from its weights alone. The number of his
worth comparing against is the second one, 67% to 86% on an agent people had already tuned by hand.

Eval-driven development, LLM-as-a-judge and a branch per hypothesis are common background rather than
his. The talk also describes a second loop over production traces and user feedback, so feedback in
the loop is not my idea either; the addition here is turning it into weighted eval cases with a
measured recovery time. The cost budget, the category and holdout gate, and the confirmation run are
mine.

No code from that work, or from any employer, is in this repository.

## Prior art

The loop is not new and he does not claim it is: his README credits Karpathy's autoresearch in its
first line. Writing it down for anyone who knows the field:

- **The primitive.** A candidate per git commit, evaluated, kept or restored, under a budgeted
  evaluator, is published as [VeRO](https://arxiv.org/abs/2602.22480) (Feb 2026), which predates
  `auto-agent`, and as [HarnessOpt-Bench](https://arxiv.org/abs/2608.06301) (Aug 2026).
- **The gate.** [Self-Harness](https://arxiv.org/abs/2606.09498) accepts only when held-in and
  held-out both fail to regress, which is the same instinct as the rule here.
  [GRASP](https://arxiv.org/abs/2605.29668) (EMNLP 2026) admits a candidate on a balanced held-out
  probe stratified by task type under a hard regression budget, which is the nearest published thing
  to a per-category gate. [GEPA](https://arxiv.org/abs/2507.19457) keeps a Pareto front over
  individual instances, but to choose the next parent, not to accept.
- **The optimizers.** [OPRO](https://arxiv.org/abs/2309.03409) hill-climbs on a scored history with
  no rollback; [DSPy MIPROv2](https://arxiv.org/abs/2406.11695) runs Bayesian optimization over
  instruction and demo combinations; [TextGrad](https://arxiv.org/abs/2406.07496) backpropagates
  natural-language gradients and accepts every step. All of them optimize more systematically than a
  single hypothesis per iteration.
- **The result I reproduced without meaning to.**
  [HarnessDev](https://arxiv.org/abs/2609.01437) (Sep 2026) reports that evolution gains on the
  visible set often shrink or reverse on held-out tasks. Five of my nineteen hypotheses were rejected
  for exactly that, before I had read it.
- **The critique this design has to answer.** [ACE](https://arxiv.org/abs/2510.04618) names *context
  collapse*: an optimizer that regenerates a whole prompt each round drifts towards shorter, blander
  text and loses detail. Hypotheses here are full-file rewrites (a deliberate choice, because
  LLM-written diffs corrupt whitespace), so the length cap is the only thing standing against it and
  no measurement here rules it out.

What is left after all that is not the loop. It is the accept rule when the eval suite is small,
noisy and expensive, which is the regime both his 60 cases and my 44 are in, and where one case is
worth ten points. The findings above are about that, and so are the three additions.

## License

MIT.
