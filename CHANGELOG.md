# Changelog

One row per optimizer hypothesis. Δ in pass-rate points (pp) or visible cases.

| n | hyp | sha | target | title | verdict | visible Δ | lookup/aggr/reas/ref Δ (cases) | holdout Δ | cost € | cumul € | results |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | hyp/1 | 9cf95f2 | system.md | Add schema, refusal rules, and SQL guidance to system prompt | accepted | +40.0pp | 0/+2/+2/+8 | +40.0pp | 0.32 | 0.69 | evals/results/2026-09-16T224744+0000.json |
| 2 | hyp/2 | 5b757df | system.md | Fix Italy country code lookup and oldest-invoice ordering guidance | rejected: leaks_expected L02:Switzerland | — | — | — | 0.04 | 0.74 | — |
| 3 | hyp/3 | 1102f84 | system.md | Fix country code lookup and oldest-invoice ordering guidance without leaking expected values | rejected: leaks_expected L02:Switzerland | — | — | — | 0.04 | 0.78 | — |
