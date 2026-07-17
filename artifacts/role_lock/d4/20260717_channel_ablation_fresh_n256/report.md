# QMC-BMGS uniform-channel ablation

## Outcome

Primary: Role-Lock D4, posterior SD scale 1, LM-node cap 384, paired n=256.
Run mode: `full`; cohort: `fresh_from_prior_d4_discovery_cohort`.

| Method | Readout success | Best observed | Verifier mean | Edge mean | Root coverage deviation |
|---|---:|---:|---:|---:|---:|
| `iid_all` | 35.5% (91/256) | 35.5% | 782.6 | 2851.8 | 0.025 |
| `sobol_all` | 37.5% (96/256) | 37.5% | 666.2 | 2428.2 | 0.002 |
| `sobol_routing_only` | 39.1% (100/256) | 39.1% | 695.9 | 2539.9 | 0.002 |
| `sobol_action_only` | 36.7% (94/256) | 36.7% | 738.2 | 2690.7 | 0.026 |

## Factorial localization

The interval is simultaneous across routing, action, and interaction.

| Effect | Mean risk difference | Simultaneous paired-bootstrap 95% |
|---|---:|---:|
| Routing Sobol main effect | +2.1 pp | [-7.6 pp, +11.9 pp] |
| Action Sobol main effect | -0.2 pp | [-10.0 pp, +9.6 pp] |
| Routing × action interaction | -2.7 pp | [-12.5 pp, +7.0 pp] |

## Planned simple contrasts

McNemar p-values are Holm-adjusted across the five planned contrasts within this primary cell.

| Contrast | Success delta | McNemar p | Holm p | Verifier delta | Edge delta |
|---|---:|---:|---:|---:|---:|
| `routing_effect_under_iid_action` | +3.5 pp | 0.4069 | 1 | -86.7 | -312.0 |
| `routing_effect_under_sobol_action` | +0.8 pp | 0.9241 | 1 | -72.0 | -262.4 |
| `action_effect_under_iid_routing` | +1.2 pp | 0.8304 | 1 | -44.4 | -161.2 |
| `action_effect_under_sobol_routing` | -1.6 pp | 0.775 | 1 | -29.7 | -111.6 |
| `combined_sobol_effect` | +2.0 pp | 0.7093 | 1 | -116.4 | -423.6 |

## Sensitivity

SD 0.5 is a prior-result-selected engineering sensitivity, not a second confirmatory endpoint.

| SD scale | Routing | Action | Interaction |
|---:|---:|---:|---:|
| 0.5 | -3.3 pp | +0.2 pp | +3.5 pp |
| 1 | +2.1 pp | -0.2 pp | -2.7 pp |

## Data quality

Status: `PASS`. Records: 2048; paired groups: 512.

## Decision boundary

- Routing effect: `inconclusive`
- Action effect: `inconclusive`
- Interaction: `inconclusive`
- This fixed full cohort supports toy-task localization only; broader algorithm promotion still requires external matched-compute evidence.
- Gate and cluster quantile remain bundled in the routing factor.
- Only logical LM-node evaluations are exactly matched; other costs are measured outcomes.
- The result is conditional on the aligned Role-Lock toy task.

## Reproduce

```bash
python -m qmc_bmgs.experiments.channel_ablation --sd-scales 0.5,1.0 --budgets 384 --seed-start 256 --seeds 256
```
