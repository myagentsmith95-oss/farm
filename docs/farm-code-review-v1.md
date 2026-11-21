# Code Review v1 — Repository Analysis & Build Readiness

**Original:** `Android_Device_Farm_Repository_Analysis.pdf`, 15 pages, 15 November 2026.
**Repository reviewed:** `9d3efb9` (merge of PR #4), 18 commits, 99 tests green.
**Status:** markdown summary of the original PDF; the PDF remains a local analysis snapshot.

## Verdict

An honest early-W1 skeleton with one material discrepancy. The code that existed was
real and well made: four contract models, two interface seams, three fakes, two
reusable contract suites, a self-tested purity guard, and passing import-linter
layering. Test-first was already a habit, and the reversible-adoption machinery
(reusable suites, purity guard) was the strongest fact about the repository.

The discrepancy was the **settled-tag gap**: four V1.1 change-log rows claimed
repository changes that were zero-byte placeholders — `protocol/serial_v1.md`,
`serial_vectors.json`, `maa_ipc.md`, `adoption/lgpl_process_boundary.md`,
`services/maa_service/pyproject.toml`, `tests/d6_day5_dual_client_test.py`, and two
serial test files. A reader trusting the tags would believe golden vectors existed.

## Main findings

- Finish the contracts: `Event` with monotonic seq/ts, and the four missing interfaces
  (`LeaseManager`, `DeviceEvent`, `Matcher`, `OcrEngine`) with fakes.
- Write the day-5 dual-client test — the mechanism that makes W5 a configuration change.
- Close the tag gap by writing the files or re-tagging C5/C7 to `proposed`.
- Add ruff and mypy to dev dependencies and CI (only pytest + lint-imports ran).
- Add a CI check failing on zero-byte tracked files.
- Build the registry on a fake udev feed and the profile store.
- Start recording the probe corpus (R9).

## Disposition

All items were implemented across PRs #5–#13 (memo V1.8, C14–C24), including the
zero-byte guard test and the honest re-tagging. Review v2 then turned to whether the
contracts were complete for the W2–W9 universe; review v3 verified that work.
