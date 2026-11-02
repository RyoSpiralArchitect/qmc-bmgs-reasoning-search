# Allocation result package operator review

The exact approved v3 plan `18f4dd53afd152ef88618e92091e822d56111b6ad04bb67c0aed5755b90da9ed` completed one run and one separate-process
complete analysis at operation `04bbe3c5bcf7380fc1b889b4e8a1de5598a19aae`. Run and analysis exit codes are zero;
both preservation checks match. All 1,536 cells, 2,560 branch searches per pass,
2,048 prefix pairs and 512 structural blocks are retained and verified.

The source/plan were unchanged. Six tracked JSON mirrors are byte-identical to
approval, cohort, COMMIT, analysis summary, execution capture and stdlib report
diagnostics. Raw observations stay local/ignored. The new report recomputer
imports only the standard library and validates every cell summary and the
entire planned reduction against saved events, without generation or search.
Its first invocation passed with empty stderr; no diagnostic failure was hidden.

The observation note reports all three arms, all three contrasts, negative and
null results, source/seed strata, actual work and first-hit/prefix evidence.
Weighted reaches 46/512 versus full continuation 48/512 and equal 40/512.
Its primary contrast is three gains and five losses, not superiority. No winner,
default, population claim, extra allocation or retry is promoted.

All 486 qualified candidate files and the operation's 489 tracked files remain
unchanged; this result package adds evidence and reporting files only. The
58 source references and v3 plan continue to regenerate exactly. Original data,
memberships, absent slots and all earlier failed/interrupted evidence remain.
This is operator review, not independent review or hosted CI approval.

The required result-package `python scripts/validate.py` will run on the committed
result package. A later records-only qualification receipt must name that exact
commit, logs, full test count/skip count and before/after evidence inventories.
No additional experiment or generative replay is required by this qualification.
PR31 must remain unmerged.
