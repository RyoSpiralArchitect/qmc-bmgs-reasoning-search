# Two-phase action-source standalone validation: fresh n=128

## Outcome

Role-Lock D4, exact verifier cap 700, paired seeds 704--831. The preceding n=64 selection cohort is not pooled.

| Method | Readout success | LM nodes | Edges |
|---|---:|---:|---:|
| `sobol_all` | 35.9% (46/128) | 404.1 | 2540.6 |
| `sobol_routing_only` | 40.6% (52/128) | 393.8 | 2542.9 |
| `two_phase_action_256` | 37.5% (48/128) | 400.4 | 2537.3 |

## Co-primary paired contrasts

| Contrast | Success delta | Simultaneous 95% | McNemar p | Holm p |
|---|---:|---:|---:|---:|
| `two_phase_vs_routing_only` | -3.1 pp | [-13.3 pp, +7.0 pp] | 0.6076 | 1 |
| `two_phase_vs_sobol_all` | +1.6 pp | [-8.6 pp, +11.7 pp] | 0.8714 | 1 |

## Engineering decision

- Status: `direction_not_replicated`.
- Action: `stop_threshold_tuning_and_run_credit_assignment_ablation`.
- Reason: at least one co-primary success point delta is nonpositive.
- This closes threshold tuning for this toy task.

## Fixed-window pre-hit telemetry (descriptive)

| Method | Eligible runs | Requests | On-path / nonroot | EOS / request |
|---|---:|---:|---:|---:|
| `sobol_all` | 114 | 13637 | 0.0827 | 0.0000 |
| `sobol_routing_only` | 106 | 12878 | 0.0843 | 0.0000 |
| `two_phase_action_256` | 114 | 13982 | 0.0848 | 0.0000 |

The first-hit request itself is excluded. Eligibility depends on when success occurred, so these values explain behavior but do not estimate a causal effect or enter the decision rule.

## Data quality

Status: `PASS`. Records: 384; paired groups: 128.

## Claim boundary

This test bears only on direction within the fixed Role-Lock D4 toy. It is not evidence of transfer to natural-language reasoning.

## Reproduce

```bash
python -m qmc_bmgs.experiments.two_phase_validation
```
