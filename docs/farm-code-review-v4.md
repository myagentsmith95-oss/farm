# Code Review v4 — Post-merge application state

**Review date:** 21 November 2026. **Head reviewed:** `600f2e7` (merge of PR #14).
**Method:** full read of 36 source modules and 23 test files, all gates, `repo_audit.sh`,
and behavioral probes; two independent reviewer passes cross-checked.

## Verdict

W1 was complete and all gates passed (342 tests, ruff/mypy/lint-imports clean, audit
11 ok). But PR #14's fixes had two residuals that a W2 adapter or InputRouter would hit
immediately, plus the still-open findings from earlier reviews.

## Blockers found

- **R1** — an ambiguous claim only cleared on an *identical* DETACH. Asymmetric
  identifiers left a seat wedged in CONFLICT forever. Fixed by PR #15 (C27).
- **R2** — `ready_modes` reported HID usable with no capture card. A test enshrined the
  wrong behavior. Fixed by PR #15 (C28) and the enrollment rule in PR #17 (C31).
- **N10** — registry concurrency: `apply()` mutates what `state()` iterates; the M1 fix
  added a second iterated dict. One reviewer reproduced `RuntimeError`; still open.

## Other findings

- `HANDOFF.md` was stale (wrong commit, version, test count, and "untracked on purpose").
- The registry test helper re-derived production's `ready_modes` formula, making
  equality tests self-confirming. Fixed by PR #15.
- C17's fake↔real guarantee was aspirational: no real adapters existed and the suites
  had no coldplug or completion cases. Addressed by PRs #16 and #19.
- Remaining: N1 coldplug, N3 keys, N4 completion, N5 frame timing, N6 worker IPC,
  N7 enrollment owner, N8 retention, N9 token lifetime, M2/M3/M4/M5, `mypy --strict`,
  no LICENSE, merged branch hygiene, vacuous property test, stale `.pyc` files.

## Verified good

M1's primary false-READY was fixed; mixed claims detached correctly; N2's phone-only ADB
case worked; snapshots were immutable; memo V1.9 matched the code; PR #14 followed the
three-commit rhythm.

## Disposition

Findings entered `FIX_TASKS.md` and were executed in PRs #15–#24. `docs/ARCHITECTURE.md`
then corrected the underlying hardware assumptions (digitizer, UART bridge, Wi-Fi ADB,
no tap-grid), and Task 12 aligned the memo to that baseline.
