# Countdown calibration grid n=128 release capsule

This release preserves the complete offline development artifact used to freeze
the `(prior_bonus=1.0, posterior_sd_scale=1.0)` calibration candidate.

It is development evidence on two frozen Countdown tasks and two frozen
provider proposal snapshots. It is not task-transfer, provider-superiority, or
QMC-superiority evidence.

## Identity

- preregistration commit:
  `bb681d22cb50e6509f9b8ddbcd44e03ee1703afa`
- decision-freeze commit:
  `2869012dce66660291171171143cec1bfe83d909`
- summary deterministic digest:
  `82542ba2a8a9f9622a0302ecdde132aeeb4f9a452d1983ddfc27630b32e5efac`
- manifest deterministic digest:
  `49d8a0465c89584f18b4242d329ffc58482453f8f5f6d5b6af87e91041414270`
- perturbation-bank SHA-256:
  `385c67b060634791c8228aa0809362064c541be7d094120b5241674779d2d06d`
- seed-map digest:
  `1d5e37cd950b87351de27e04cf571e8bb90aad4bfb2400068b2647e82e9e70b0`
- full-provenance archive SHA-256:
  `countdown_calibration_grid_n128_v1_full_provenance.tar.gz` =
  `a4938c0ad5c0c59d1fc85082d17e2ae3f3a6b9b0456e1724f757a4d66702abf2`
- independent audit report SHA-256:
  `countdown_calibration_adversarial_audit_v1.json` =
  `19a571f0bfb8aff3152b288544b8cc03eec8aa794788be5e73a0cf7b8f0b6811`
- independent audit deterministic digest:
  `0fe86974fa06103240262b41d339cb30cb8266c03ebbc4dcb141b2e1c2353f81`

The full-provenance archive contains:

- `countdown_calibration_grid_n128_v1`
- `countdown_anthropic_dev_20260722_live_v3`
- `countdown_openai_dev_20260724_live_v2`

The calibration artifact contains 9,216 compact search records, 4,608 matched
IID/Sobol blocks, 256 shared dual-stream banks, copied proposal rows, the
preregistration, summary, and manifest.

## Replay boundary

Search-only replay reconstructs all nine grid shards byte-for-byte from the
stored proposal rows and banks. Full provenance replay additionally validates
the two original provider artifacts on scratch copies under the network guard
and checks their frozen receipts.

After building the archive above, it was extracted into a fresh temporary
directory and passed full provenance replay with provider credentials unset.
The replay reproduced summary digest
`82542ba2a8a9f9622a0302ecdde132aeeb4f9a452d1983ddfc27630b32e5efac`.

```bash
env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY PYTHONPATH=src \
  python3 -m qmc_bmgs.experiments.countdown_calibration_grid \
  --replay countdown_calibration_grid_n128_v1 \
  --anthropic-dir countdown_anthropic_dev_20260722_live_v3 \
  --openai-dir countdown_openai_dev_20260724_live_v2
```

The independent audit verifies all 14 manifest-declared files, then reconstructs
the compact search evidence without importing the grid runner:

```bash
PYTHONPATH=src python3 -m \
  qmc_bmgs.experiments.countdown_calibration_adversarial_audit \
  --artifact-dir countdown_calibration_grid_n128_v1
```

The historical v1 schema uses “common random number” wording too broadly.
Random values are genuinely reused across configurations and providers within
each source. IID and Sobol use distinct source-specific streams, so their
comparison is a matched dual-stream comparison, not an IID/Sobol CRN
variance-reduction design.

See the post-run adversarial review before using this artifact to design a
held-out experiment.
