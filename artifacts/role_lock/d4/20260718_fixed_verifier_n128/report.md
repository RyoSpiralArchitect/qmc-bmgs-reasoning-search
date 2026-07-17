# QMC-BMGS fixed-verifier conversion test

## Outcome

Role-Lock D4, SD scale 1, exact verifier cap 700, paired n=128.

| Method | Readout success | LM nodes | Prefix tokens | Edges | Best hit |
|---|---:|---:|---:|---:|---:|
| `iid_all` | 43.0% (55/128) | 373.3 | 1395.9 | 2543.0 | 43.0% |
| `sobol_all` | 35.9% (46/128) | 399.7 | 1501.1 | 2543.3 | 35.9% |
| `sobol_routing_only` | 41.4% (53/128) | 396.3 | 1487.6 | 2542.2 | 41.4% |

## Paired contrasts

Resource deltas are candidate minus reference. Positive LM-node delta means more unique search nodes at the same verifier cap.

| Contrast | Role | Success delta | Simultaneous 95% | Holm p | LM-node delta | Edge delta |
|---|---|---:|---:|---:|---:|---:|
| `combined_sobol_vs_iid` | primary | -7.0 pp | [-20.3 pp, +6.2 pp] | 0.6422 | +26.4 | +0.3 |
| `sobol_routing_only_vs_iid` | primary | -1.6 pp | [-14.8 pp, +11.7 pp] | 0.8854 | +23.0 | -0.8 |
| `combined_sobol_vs_routing_only` | secondary_mechanism | -5.5 pp | nominal only | not in family | +3.4 | +1.1 |

## Decision boundary

- `sobol_all` vs IID: success `inconclusive`, LM-node conversion `positive`.
- `sobol_routing_only` vs IID: success `inconclusive`, LM-node conversion `positive`.
- Success superiority and resource conversion are separate claims.
- No natural-language or general QMC claim follows from this toy.

## Data quality

Status: `PASS`. Records: 384; paired groups: 128.
Minimum guard headroom: LM nodes 680, edges 868.

## Reproduce

```bash
python -m qmc_bmgs.experiments.fixed_verifier_budget
```
