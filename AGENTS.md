# Working agreement

The north star is an exploration algorithm that is strong, computationally
useful, and behaviorally interesting. Mathematical correctness is a gate and a
diagnostic tool, not the final product.

- Preserve matched budgets, seed hierarchy, candidate identity, and strict JSON.
- Do not turn plumbing self-tests into algorithmic performance claims.
- Keep LM prior, learned return, uncertainty proxy, routing, and pruning roles
  explicit in code and reports.
- Treat negative results as durable evidence; do not tune them away silently.
- Separate QMC action perturbation from QMC semantic routing before adding more
  architectural complexity.
- Track reports, summaries, and manifests. Raw JSONL stays local/ignored and must
  continue to match its tracked manifest.
- Run `python scripts/validate.py` before declaring a change complete.
