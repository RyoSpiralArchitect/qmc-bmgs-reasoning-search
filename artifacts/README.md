# Experiment registry

| Experiment | Purpose | Durable read |
|---|---|---|
| `role_lock/d3/20260717_lm_budget_baseline` | aligned strata positive control and controls | `report.md` |
| `role_lock/d4/20260717_noise_sweep_n64` | IID vs combined Sobol across SD scale and LM cap | `report.md` |
| `role_lock/d4/20260717_primary_precision_n256` | precision-triggered Primary extension | `report.md` |

Each promoted directory tracks `report.md`, `summary.json`, `manifest.json`, and immutable
`records.jsonl`. These first pre-repository runs are small enough to preserve in Git; new high-churn
work stays under ignored `artifacts/work/` until promotion. Verify evidence with:

```bash
python scripts/verify_artifacts.py
```

Regenerated output should first go to `artifacts/work/`. Promotion into this registry requires a
matched command, validation PASS, and an updated manifest.
