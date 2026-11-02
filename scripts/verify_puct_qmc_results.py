"""Verify the public source-level PUCT outcomes without executing any search."""

import csv
from fractions import Fraction
import hashlib
import io
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/results/puct_qmc_series"
METHODS = ("hybrid", "root", "unvisited")
DATES = ("20261027", "20261029", "20261030")
FIELDS = ["study", "source_slot", "source_fingerprint", "puct"] + [
    f"{m}_r{i}" for m in ("qmc", "iid") for i in range(4)
]


def require(ok, msg):
    if not ok:
        raise ValueError(msg)


def authenticated(path, expected_hash):
    blob = path.read_bytes()
    require(hashlib.sha256(blob).hexdigest() == expected_hash, f"hash: {path.name}")
    return blob


def summarize(rows):
    require(len(rows) == 512, "512 sources required")
    gains = losses = 0
    deltas = []
    totals = [0, 0, 0]
    for row in rows:
        require(len(row) == 9 and all(x in ("0", "1") for x in row), "binary outcomes")
        control, *arms = map(int, row)
        q, iid = arms[:4], arms[4:]
        totals = [totals[0] + sum(q), totals[1] + sum(iid), totals[2] + control]
        gains += sum(x > control for x in q)
        losses += sum(x < control for x in q)
        deltas.append(Fraction(sum(q), 4) - control)
    mean = sum(deltas) / len(deltas)
    variance = sum((x - mean) ** 2 for x in deltas) / (len(deltas) - 1)
    half = 2 * math.sqrt(float(variance)) / math.sqrt(len(deltas))
    lo, hi = float(mean) - half, float(mean) + half
    if not variance:
        decision = "UNRESOLVED"
    elif half > 0.05:
        decision = "IMPRECISE"
    elif lo > 0.02:
        decision = "PROMISING_FOR_FRESH_CONFIRMATION"
    elif hi <= 0.02:
        decision = "NO_PRACTICAL_UPLIFT_SIGNAL"
    else:
        decision = "UNRESOLVED"
    return totals, [gains, losses], mean, variance, [lo, hi], decision


def main():
    manifest = json.loads((DATA / "manifest.json").read_bytes())
    require(set(manifest["studies"]) == set(METHODS), "study identities")
    blob = authenticated(DATA / "outcomes.csv", manifest["outcomes_sha256"])
    rows = csv.reader(io.StringIO(blob.decode("ascii"), newline=""))
    require(next(rows) == FIELDS, "outcome schema")
    seen = set()
    for name, date in zip(METHODS, DATES):
        study = manifest["studies"][name]
        require(date == study["date"], "study date")
        plan = json.loads(authenticated(
            ROOT / f"docs/preregistrations/countdown_search_value_puct_qmc_{name}_{date}.plan.json",
            study["plan_sha256"],
        ))
        cohort = json.loads(authenticated(
            ROOT / f"docs/qualifications/countdown_puct_qmc_{name}_development_{date}.cohort.json",
            study["cohort_sha256"],
        ))
        require(study["plan_digest"] == plan["deterministic_digest"] == cohort["plan_digest"], "plan identity")
        require(study["roots"] == plan["roots"] and len(set(study["roots"])) == 4, "root identity")
        outcomes = []
        for slot, task in enumerate(cohort["tasks"]):
            fp = task["source_multiset_fingerprint"]
            require(fp not in seen, "repeated source across cohorts")
            seen.add(fp)
            row = next(rows, [])
            require(row[:3] == [name, str(slot), fp], "source identity/order")
            outcomes.append(row[3:])
        totals, gl, mean, variance, interval, decision = summarize(outcomes)
        require(totals == study["totals_qmc_iid_puct"] and gl == study["primary_gain_loss"], "counts")
        require(mean == Fraction(*study["primary_mean"]), "source mean")
        require(variance == Fraction(*study["primary_variance"]), "source variance")
        require(len(study["primary_interval"]) == 2 and all(
            math.isclose(a, b, rel_tol=0, abs_tol=1e-15)
            for a, b in zip(interval, study["primary_interval"])
        ), "model interval")
        require(decision == study["primary_readout"], "readout")
        print(f"{name}: {gl[0]} gains / {gl[1]} losses, {float(mean)*100:+.6f} pp; {decision}")
    require(next(rows, None) is None and len(seen) == 1536, "unexpected sources")
    print("PASS: 1,536 disjoint source rows; 13,824 physical outcomes.")


if __name__ == "__main__":
    main()
