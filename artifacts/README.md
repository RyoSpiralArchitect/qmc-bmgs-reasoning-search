# Experiment registry

| Experiment | Purpose | Durable read |
|---|---|---|
| `role_lock/d3/20260717_lm_budget_baseline` | aligned strata positive control and controls | `report.md` |
| `role_lock/d4/20260717_noise_sweep_n64` | IID vs combined Sobol across SD scale and LM cap | `report.md` |
| `role_lock/d4/20260717_primary_precision_n256` | precision-triggered Primary extension | `report.md` |
| `role_lock/d4/20260717_channel_ablation_fresh_n256` | fresh-cohort routing/action coordinate-source localization | `report.md` |
| `role_lock/d4/20260718_fixed_verifier_n128` | fixed-verifier conversion and deep-breadth failure analysis | `report.md` |
| `role_lock/d4/20260718_two_phase_n64` | exploratory late IID-action switch and validation gate | `report.md` |
| `role_lock/d4/20260718_two_phase_validation_n128` | standalone validation of the fixed two-phase schedule | `report.md` |
| `role_lock/d4/20260719_credit_assignment_n128` | fixed routing-only terminal versus prefix-progress mechanism diagnostic | `report.md` |

Each promoted directory tracks `report.md`, `summary.json`, `manifest.json`, and immutable
`records.jsonl`. The first three runs were imported with explicit pre-repository provenance; the
channel ablation, fixed-verifier, two-phase selection, standalone validation, and credit-assignment runs record exact clean generation revisions.
High-churn work stays under ignored `artifacts/work/` until promotion. Verify evidence with:

```bash
python scripts/verify_artifacts.py
```

Regenerated output should first go to `artifacts/work/`. Promotion into this registry requires a
matched command, validation PASS, and an updated manifest.
