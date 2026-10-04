# Scheduler Evaluation

Generated 2026-10-03 with seed `7`. The reused diagnostic synthetic generator created 1,500 learners; allocation metrics use a reproducible sample of 20 learners, four simulated weeks, and 10 hours per week. Solver scale metrics use 10, 25, and 50 active topics.

## Allocation comparison

| Strategy | Weak-topic coverage after 4 weeks | Hours wasted on mastery >= 0.8 |
|---|---:|---:|
| Weighted by weakness and category importance | 0.995000 | 0.000000 |
| Equal time per topic | 0.827124 | 4.200000 |
| Stated hours without topic weighting | 1.000000 | 0.000000 |

The unweighted baseline sorts only by weakness; the weighted scheduler multiplies weakness by assumed category importance. The baseline is included to show the effect of the category weights, not as a production strategy.

## Solver wall time

Production uses a five-second CP-SAT limit. Evaluation uses a 0.5-second benchmark limit for the scale cases.

| Active topics | Measured wall time (seconds) |
|---:|---:|
| 10 | 0.194393 |
| 25 | 0.580046 |
| 50 | 0.670632 |

The 50-topic case has enough evaluation slots to avoid an accidental slot-grid infeasibility. The measured wall time includes model construction and solver invocation.

## Mandatory coverage infeasibility

A mandatory topic is a topic below mastery `0.6`; each requires one 30-minute block. The rates below are the analytical minimum-hours check across the 20-learner evaluation sample.

| Stated weekly hours | Infeasibility rate |
|---:|---:|
| 1 | 1.000000 |
| 2 | 1.000000 |
| 4 | 1.000000 |
| 8 | 1.000000 |
| 12 | 0.000000 |
| 16 | 0.000000 |
| 20 | 0.000000 |

## Decisions to review

- Minimum block length is 30 minutes. This keeps sessions calendar-sized and prevents fragmented schedules.
- Category importance is currently assumed: DSA `1.20`, CS core `1.15`, system design `1.10`, aptitude `1.00`, behavioral `0.85`. These values are configuration assumptions, not learned from placement outcomes.
- Weakness threshold is `0.60`; mastered threshold is `0.80`.
- Regeneration archives the prior active plan and carries completed sessions into the new plan. Unstarted sessions are replaced.
- The evaluation sample is 20 learners to keep CP-SAT benchmarking bounded on a developer machine; the synthetic population itself remains 1,500 learners.

## Limitations

Topic importance weights are assumed and are not derived from real placement outcome data. The in-memory profile repository does not persist profile edits across process restarts; production persistence requires migration 004 and the service-role Supabase configuration. A real multi-week Supabase history was not available in this environment.
