# Code Review v3 — Current Application State

**Original:** `Android_Device_Farm_Code_Review_v3.pdf`, 12 pages, 21 November 2026.
**Repository reviewed:** `fe8c867` (main, clean), 348 tests, memo V1.8.
**Method:** full source/test read, four gates, `repo_audit.sh`, and 20 behavioral probes.

## Verdict

Week One is genuinely complete and the quality bar rose. Every recommendation from
review v1 was implemented: all five seams with seven interfaces, `Event` and its
monotonicity checker, registry and profile store, a meaningful day-5 dual-client test,
sim core, ruff/mypy in CI, and a permanent zero-byte-file guard. The memo honestly
re-tagged C5/C7. The response to review was absorbed into the process.

## Findings

The review independently verified all ten findings of the repository's own review v2
(`docs/farm-code-review-v2.md`, N1–N10). N1 (no coldplug: a restarted farm reports all
50 seats ABSENT until replug) and N2 (`READY` conflates inventory completeness with
usability, hiding a seat usable via ADB) were reproduced exactly and called W2 blockers.

New M-findings:

- **M1 (blocker):** one event carrying both `by_id` and `by_path` could fill two roles of
  one seat — `READY` with a single physical device. Fixed by PR #14 (memo C25).
- **M2:** a conflicted role disappears from `present`; consumers must branch on status.
- **M3:** `resolve_all` closes a source it did not open.
- **M4:** `repo_audit.sh` EXPECTED is a hand-maintained second inventory.
- **M5:** no LICENSE file; `mypy --strict` had 6 errors.

## Recommendation

Do not change the W2 order in HANDOFF. Finish the contracts before adapters depend on
them: coldplug, readiness semantics, key vocabulary, completion semantics, lease
locality, and one enrollment truth. The report closes with the observation that the
repository's own adversarial review and handoff document are the most valuable
artifacts of the cycle.

## Disposition

M1 and N2 were fixed by PR #14; the remaining items entered `FIX_TASKS.md` and were
worked through PRs #15–#24. Review v4 (below) re-audited that work.
