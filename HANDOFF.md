# Handoff — Android Device Farm

**Written:** 2026-11-19. Resume point for the next session.

## Where things stand

- Local `main` at `174d5e5` (merge of PR #13), clean, in sync with `origin/main` (0/0).
- Only branch, local and remote, is `main`. All feature branches were merged and deleted.
- **Week One is complete.** Contracts, registry, dual-client test, sim core, four CI gates, memo **V1.8** with C1–C24 recorded.

### Merged PRs

| PR | Slice |
|---|---|
| #8 | seat contract models (C19) |
| #9 | registry: profile store + seat resolution (C20) |
| #10 | day-5 dual-client test + Maa callback stub (C21) |
| #11 | CI gates, placeholder cleanup, C5/C7 re-tagged (C22) |
| #12 | sim core: virtual device attach/detach (C23) |
| #13 | `HID_CONTROLLER` → `HID_BOARD` rename (C24) |

### Current green baseline

```
ruff check .        all checks passed
mypy src            no issues in 36 source files
lint-imports        farm layering KEPT
pytest -q           342 passed
repo_audit.sh       11 ok, 0 warnings, 0 failures
```

## Next: Week Two

W2 exit criteria: **first real tap through the ESP32 on a real phone**, and **HID acceptance verified on a no-ADB phone** (risk R1).

### Blocker

Hardware is required for the exit test, not for the code phase. The memo says to order: **one ESP32-S3, one UVC capture card, two phones — one that refuses ADB** (ch. 10, R1, R8). Check whether it has arrived before promising the exit criteria.

Calibration values (L1 tap grid, L2 active area) also need a real phone to measure. Golden vectors can use fixed placeholder constants until then.

### Code phase — no blocker, can start now

1. Clone `esp32-android-agent` (D3) and read its HID descriptors — needs network.
2. Decide **O6**: are firmware/protocol version fields part of the serial handshake, or registry metadata?
3. Write `protocol/serial_v1.md` — frame format: start byte, command byte, field widths, byte order, length, checksum.
4. Write `protocol/serial_vectors.json` — ~15–25 cases: each action kind, boundary coordinates (0,0 and 1,1), min/max swipe duration, handshake, invalid inputs.
5. Python encoder + golden-vector tests; `InputRouter` with per-device input preference.
6. Firmware from the reference; both sides run the same vectors.
7. When hardware arrives: real tap and no-ADB acceptance test. Update spec + vectors together if a value was wrong.

## Open items

- **O1** — Maa rubric 3.30 / 5.00 → before W5
- **O2** — numeric W9 exit criteria → before W9
- **O3** — 55 / 10 / 35 feature mapping → documentation only
- **O4** — ADB screencap latency → W3
- **O5** — ADB-only share among the fifty → design/procurement
- **O6** — handshake versions / firmware metadata → decide in W2
- **O7** — replace synthetic dual-client corpus with real footage → before W5

`C5` (W5), `C7` (serial due W2, Maa spec due W5), `C8`, `C9` and `C13` remain tagged `proposed`.

## Conventions established

1. **Test-first, three commits:** red tests, green implementation, memo/audit update.
2. **Memo is the living baseline:** bump `DOC ADF-DEC-Vx.y` and add a change-log row per slice.
3. **`repo_audit.sh` `EXPECTED` list must be updated** whenever files land.
4. **LGPL boundary:** no `maafw` import in the `farm` package (AST-guarded).
5. **No empty tracked files** except `.gitkeep` / `__init__.py`.
6. **Role name is `HID_BOARD`**, not `hid_controller` — "controller" is reserved for Maa's custom-controller API.
7. **Ruff is scoped** to `E4, E7, E9, F, I` — correctness, not style.
8. Coordinates are normalized 0–1; backends convert to device units. Timestamps are monotonic nanoseconds.
9. Contracts marked `PROVISIONAL` are expected to change after hardware or the supervisor exists — that is planned, not a defect.
10. Stacked PRs: base on the parent feature branch, then retarget to `main` after it merges. Delete merged branches with `git branch -d`; `git fetch --prune` cleans deleted remotes.

## Verification commands

```bash
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/lint-imports
.venv/bin/pytest -q
bash repo_audit.sh
```

Note: this file is untracked on purpose. `repo_audit.sh` will report one `FAIL` for uncommitted changes until it is committed or deleted.
