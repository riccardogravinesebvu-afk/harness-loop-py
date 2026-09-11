# harness-loop-py

An optimizer agent that improves another agent by iterating on evals: propose a hypothesis, edit prompts and tool descriptions on a git branch, re-run the eval suite, keep or roll back, write the changelog. Reimplemented in Python from the method Nearform's AI Lead presents publicly (see Origin), and extended with three things the published method does not have:

1. **Cost budget per iteration.** The loop stops when marginal gain per euro drops below a threshold. The README shows the cost/pass-rate curve.
2. **Per-category regression gate.** A hypothesis that raises the total pass rate but lowers any eval category is rejected.
3. **Human feedback inside the loop.** Cases flagged through a feedback endpoint enter the dataset with higher weight, so the next iteration targets what users rejected.

## Status

Scaffold. Design: `docs/plans/2026-09-11-harness-loop-py-design.md`. No eval results yet: the tables below stay empty until `just evals` writes a file in `evals/results/`.

## Results

| Metric | Value | Results file |
|---|---|---|
| pass rate per iteration, total and per category | _run `just evals`_ | — |
| cost and latency per iteration, marginal gain per euro | _run `just evals`_ | — |
| hypotheses rejected by the category gate | _run `just evals`_ | — |
| iterations to recover a case flagged via feedback | _run `just evals`_ | — |

Every number in this table must point at a results file (model id, seed, git sha, cost inside).

## Quickstart

```bash
uv sync --group dev
cp .env.example .env          # add a provider key; Langfuse optional
just test                     # unit tests, no key needed
just evals                    # eval suite → evals/results/<timestamp>.json
```

## Origin

Method: Alfonso Graziano (Nearform), "Agents Building Agents" talk and the AutoAgent write-up (2026). This repository contains no code from that work or from any employer; it reimplements the described loop and adds the three extensions above. Karpathy's auto-research is the shared intellectual ancestor.

## License

MIT. See `LICENSE`.
