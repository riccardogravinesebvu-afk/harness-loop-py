# harness-loop-py

An optimizer agent that improves another agent by iterating on evals. It proposes one hypothesis,
edits a prompt file on a git branch, re-runs the eval suite, keeps the change or rolls it back, and
writes a line in the changelog. Then it does it again, until the money runs out or the gains do.

The method is Alfonso Graziano's, from Nearform, and he presents it publicly (see [Origin](#origin)).
There's no code published for it, so this is my own implementation in Python, on a domain of my own,
with three things the talk doesn't cover: a cost budget that decides when to stop, a regression gate
that watches individual eval categories and a held-out split, and a feedback endpoint that turns a
human "this answer is wrong" into a weighted eval case.

Every number below comes out of a JSON file committed in `evals/results/`. If a number here has no
file behind it, that's a bug.

## What happened

Six loops, nineteen hypotheses, about €9.3 of API spend over two days.

| | total | visible | holdout | |
|---|---|---|---|---|
| starting prompt, one sentence long | 45% | 47% | 40% | [file](evals/results/2026-09-16T143601+0000.json) |
| what the loop achieved on its own | 87% | 94% | 67% | mean of 3 runs |
| same prompts, after I fixed the judge and added 4 cases | 91% | 97% | 70% | mean of 3 runs |
| plus one hypothesis the gate rejected and I accepted by hand | 98% | 100% | 90% | [file](evals/results/2026-09-17T212958+0000.json) |

Those four rows are four different things, not one curve. Rows two and three are the same prompts
measured two different ways; the agent didn't change between them, my rubric did. Row four is a
human overriding the gate, on the record.

![pass rate per iteration](docs/img/pass_rate.svg)

![cost vs pass rate](docs/img/cost.svg)

The interesting part is not the 98%. It's that hypothesis 1 did almost all of the work, that the
gate rejected five hypotheses that raised the visible score, and that I got one acceptance wrong and
only found out by running the same prompts three times.

The blow-by-blow is in [docs/loops.md](docs/loops.md): every hypothesis, what it changed, why it was
kept or thrown away, and what it cost.

## What I got wrong

This is the part I'd want to read first, so it goes near the top.

**I accepted a hypothesis on a coin flip.** Hypothesis 12 passed the gate with the holdout at 80%.
Three later runs of those exact prompts put it at 67%, every time. One holdout case, `F08`, refuses
in words but doesn't set the `refused` flag, and it flips run to run. Ten holdout cases means one
case is 10%, and my gate was making decisions on a single run. A real regression walked straight
through it. The loop now re-runs the holdout before accepting anything and takes the lower of the
two runs as the new bar.

**My anti-leak check cost me five iterations.** It refuses any hypothesis that writes an expected
answer into the prompt, which is the right idea. But it was checking every visible case, including
the ones already passing, so a list of ISO country codes containing the word `Switzerland` got
killed five times across two loops, then a mention of the year `2026` got killed once more. Six
iterations and €0.25 spent on nothing.
It now checks only the cases that are currently failing, which are the only ones the optimizer is
shown.

**My judge was wrong about arithmetic.** It marked "5,250 outstanding" as an unsupported figure
because the tools had returned 3,750 and 1,500 separately. Two reasoning cases failed across four loops
over that. Judge v2 counts sums, differences and counts as supported, and results files now carry a
`judge_version` so numbers from before and after are never averaged together.

**The per-category gate, the feature I was proudest of, never fired.** Nineteen hypotheses and not
one of them lowered a visible category while raising the total. Every real rejection came from the
holdout or from no gain at all. It has unit tests and no field record.

## What I added to the method

**A cost budget.** Each iteration's cost is computed locally from token usage, including the
optimizer's own tokens and every rejected hypothesis, and the loop stops when the last three
iterations bought less than `BUDGET_MIN_GAIN_PER_EUR` of pass rate per euro. There are hard ceilings
on iterations and total euros too. The budget rule ended five of the six loops, every time after
three flat iterations, which is roughly what I'd have done by hand.

**A gate that can say no to an improvement.** A hypothesis is kept only if the visible pass rate
rises, no category loses more than one visible case, and the held-out split doesn't fall on two
separate runs. The optimizer never sees the holdout, and the tolerance isn't hardcoded, it's `1/n`
computed from the dataset. Five hypotheses that raised the visible score were rejected on the
holdout.

**Feedback that changes what the loop optimizes.** `POST /feedback` with a run's trace id and a note.
If it's a dataset case, its weight doubles and my note shows up next to the failure the optimizer
reads. If it's an ad-hoc question, it becomes a new judged case with the note as the reference. I
flagged a case that had been failing since loop 1 and it came back two iterations later. The loop
records that number itself.

## Running it

```bash
uv sync --group dev
cp .env.example .env   # LLM_API_KEY; the default endpoint is Anthropic, any OpenAI-compatible base URL works
just test              # unit tests, no API key needed
just evals             # 44 cases, about $0.35, writes evals/results/<timestamp>.json
just loop max=6        # baseline plus up to 6 hypotheses, about €0.35 per evaluated iteration
just feedback          # the feedback endpoint on :8765
```

The loop won't start on a dirty working tree, so every number it produces is committed alongside the
code that produced it. Accepted hypotheses fast-forward `main`; rejected ones leave their branch
behind as `hyp/<n>` and only the evidence lands on `main`.

Temperature is 0 everywhere and `EVAL_SEED` goes to the provider, but the Anthropic endpoint ignores
seeds. With the current judge, three back-to-back runs came out identical across all 44 cases. The
one case that can still flip is a refusal whose flag the model sets inconsistently.

`uv run python scripts/plot.py` regenerates the charts from the loop files, and
`scripts/variance.py` takes any number of results files and prints min/mean/max plus which cases
disagree.

## How it works

The agent under test is a small LangGraph graph over an invented SME ledger in SQLite: 8 customers,
24 invoices, 13 payments, reference date fixed at 2026-09-01. One LLM node on Haiku 4.5, one tool
node, and four tools, `run_sql` (read-only), `lookup_customer`, `compute`, and `final_answer(answer,
refused)`, which ends the run. The structured output is a tool call, never parsed prose. The
optimizer may edit `prompts/system.md` and `prompts/tools.yaml`. Nothing else, ever, and it knows it
can read the tool code but not change it.

The dataset is 44 hand-written cases in `evals/dataset.yaml`, four categories, 34 visible and 10 held
out. Most checks are deterministic: exact match, substring, numeric with tolerance, and the
structured `refused` flag. Reasoning cases go to a judge on Sonnet 4.6 that scores correctness,
grounding and completeness against a reference I wrote from the data, with a penalty for figures
that aren't in the tool outputs. Cases get added, never weakened. That rule is in `CLAUDE.md` and
it held for the whole project.

The loop itself is `src/optimizer/loop.py`, another LangGraph graph: baseline, propose, apply,
evaluate, decide. The optimizer sees the current prompts, the agent's code, the pass rate per
category, every failing visible case with the agent's answer and its tool calls, and the changelog of
what's already been tried. Its own prompt describes the method and says nothing about ledgers. It can
also propose new eval cases, which land in `evals/proposed.yaml` and stay there until a human moves
them, because a loop that writes its own exams isn't measuring anything.

Langfuse is optional. With keys, each eval run of each case is one trace with an `eval_context` span
carrying the case, the verdict and the cost. Without keys, nothing is sent and nothing breaks. The
trace id is derived locally either way, which is what lets the feedback endpoint find a run again.

## Origin

The method comes from Alfonso Graziano (Nearform) and his talk
["Agents Building Agents"](https://www.youtube.com/watch?v=aHhB3sjGjkI)
([summary](https://daily.dev/posts/agents-building-agents---alfonso-graziano-nearform-p61ktlb5k)):
an optimizer agent that generates hypotheses, edits the agent, runs the evals and rolls back
regressions, reported at 18% to 83% on a fresh agent and 67% to 86% on a production one, with
Karpathy's auto-research as the stated inspiration. His article
["From AI prototype to production"](https://nearform.com/digital-community/from-ai-prototype-to-production-how-to-build-evals-for-reliable-agents/)
covers the eval side. Both read on 2026-09-17.

Nearform hasn't published code for any of it. This is an independent reimplementation of the
described method, in Python, on a domain I made up, and the 18% to 83% figure is theirs. I don't
reproduce it and I don't claim it. The numbers here are mine, on my dataset, with my mistakes in
them.

Eval-driven development, LLM-as-a-judge and a branch per hypothesis are common knowledge, not
his. The talk also describes a second loop over production traces and user feedback, so the idea of
feedback in the loop isn't mine either; what I added is turning it into weighted eval cases with a
measured recovery time. The budget, the category and holdout gate, and the confirmation run are mine.

No code from that work, or from any employer, is in this repository.

## License

MIT.
