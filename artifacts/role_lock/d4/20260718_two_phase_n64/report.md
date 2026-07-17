# QMC-BMGS two-phase action-source experiment

## Outcome

Role-Lock D4, exact verifier cap 700, switch after request 256, paired n=64.

| Method | Readout success | LM nodes | Edges | Late on-path share | Late EOS / request |
|---|---:|---:|---:|---:|---:|
| `sobol_all` | 37.5% (24/64) | 401.0 | 2537.1 | 0.1249 | 0.0107 |
| `sobol_routing_only` | 35.9% (23/64) | 397.1 | 2539.3 | 0.1213 | 0.0097 |
| `two_phase_action_256` | 40.6% (26/64) | 395.3 | 2544.4 | 0.1319 | 0.0125 |

## Behavioral telemetry

| Method | Final nodes d0/d1/d2/d3 | Late d3 nodes | Late oracle actions d0/d1/d2/d3 | Late PROBE share | Late immediate-repeat share | Late PROBE-reselection share | Root coverage deviation |
|---|---:|---:|---:|---:|---:|---:|---:|
| `sobol_all` | 1.0/9.0/77.1/313.9 | 144.6 | 104.2/31.4/11.7/4.8 | 0.2028 | 0.1003 | 0.0541 | 0.0019 |
| `sobol_routing_only` | 1.0/9.0/76.7/310.4 | 143.9 | 102.3/30.1/10.8/4.3 | 0.2020 | 0.1015 | 0.0531 | 0.0019 |
| `two_phase_action_256` | 1.0/9.0/76.3/309.0 | 139.7 | 108.8/34.3/13.2/5.5 | 0.2067 | 0.1021 | 0.0554 | 0.0019 |

## Paired contrasts

| Contrast | Role | Success delta | Simultaneous 95% | Holm p | On-path delta | EOS-rate delta |
|---|---|---:|---:|---:|---:|---:|
| `two_phase_vs_routing_only` | primary_engineering_substrate | +4.7 pp | [-9.4 pp, +18.8 pp] | 1 | +0.0105 | +0.0028 |
| `two_phase_vs_sobol_all` | primary_switch_effect | +3.1 pp | [-10.9 pp, +17.2 pp] | 1 | +0.0070 | +0.0017 |
| `sobol_all_vs_routing_only` | secondary_descriptive_control | +1.6 pp | nominal only | not in family | +0.0035 | +0.0011 |

## Engineering gate

- Mechanism gate: `True`.
- Action: `authorize_one_fresh_standalone_n128_validation`.
- Reason: paired success point estimate and both mechanism endpoints improved.
- This exploratory full-cohort gate authorizes validation; it does not declare a winner.

## Data quality

Status: `PASS`. Records: 192; paired groups: 64.
Minimum guard headroom: LM nodes 685, edges 860.

## Claim boundary

The threshold was selected from a previous cohort. Telemetry is oracle-informed and descriptive; equal verifier calls are not equal total compute.

## Reproduce

```bash
python -m qmc_bmgs.experiments.two_phase_sampler
```
