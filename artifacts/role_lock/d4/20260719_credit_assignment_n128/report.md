# QMC-BMGS credit-assignment diagnostic

Report schema: `qmc_bmgs_credit_assignment_report_v1`.

Role-Lock D4, routing-only substrate, exact 700 search-feedback calls, paired n=128.
The terminal-only control is referenced from its immutable promoted raw; the new raw contains prefix-progress rows only.

| Condition | Exact successes | Rate |
|---|---:|---:|
| terminal_only_control | 52/128 | 40.6% |
| prefix_progress | 26/128 | 20.3% |

## Primary paired result

Risk difference (prefix-progress minus terminal-only): -20.3%; paired percentile bootstrap 95% [-27.3%, -13.3%]; exact two-sided McNemar p=2.16067e-07.

## Decision

`no_gain` — stop_additional_sampler_tuning_on_this_toy.

Positive prefix feedback is an oracle diagnostic. Exact target success and dense feedback remain separate ledgers throughout search and analysis.
