# Android Device Farm: Final Decision Summary & Implementation Plan

**Document:** DOC ADF-DEC-V1.30
**Supersedes:** ADF-DEC-V1.29 (V1.0 is the Z.ai Engineering PDF snapshot, November 2026)
**Revision date:** November 22, 2026
**Status:** living baseline. Every change is a git commit with a reason.

---

## Change log

Status tags used throughout: **[settled]** means decided and reflected in the repository; **[proposed]** means a design change pending working code; **[open]** means an unresolved item with an owner and a date still to be set.

| # | Change from V1.0 | Where | Status |
|---|---|---|---|
| C1 | Interfaces: five seams (InputBackend, CaptureSource, LeaseManager, DeviceEvent, Matcher/OcrEngine), not four. Matcher/OcrEngine is one seam holding two interfaces, so there were six interface types (now seven, see C14). | D4, ch. 4, Week 1 | settled |
| C2 | Contracts hold models and interfaces only (stdlib and pydantic). Fakes and the sim device move to `farm.testing`, outside the production import graph. | D4, ch. 4, ch. 8 | settled |
| C3 | Lease authority moves from the registry to the runner's supervisor. Core 2 becomes "Registry"; core 3 becomes "Runner, orchestration and lease authority". Five cores, same count; the same code changes package, so the custom share is unchanged. | ch. 4, Table 4 | settled |
| C4 | The single writer of the event stream is the supervisor. | ch. 6 | settled |
| C5 | MaaFramework ships as its own distribution (`services/maa_service`, separate venv), so the LGPL boundary is enforced by packaging, not only by process separation. | ch. 5 | proposed (W5; directory reserved with .gitkeep) |
| C6 | Dependency direction is enforced by import-linter; every third-party library is imported by exactly one adapter module. | ch. 4A | settled |
| C7 | The ESP32 wire protocol and the farm-to-Maa message surface are specified in `protocol/` with golden test vectors. | ch. 4A | proposed (serial due W2, Maa spec due W5; directory reserved with .gitkeep) |
| C8 | Two seat classes: standard (ESP32 HID + UVC capture, most phones) and ADB-only (ADB control + screencap, a minority). Phones without video out are valid seats. | ch. 2 | proposed |
| C9 | `CaptureSource` gains a second implementation, ADB screencap, with a latency caveat against the 300 to 500 ms budget (unmeasured). | ch. 4, ch. 9 | proposed |
| C10 | Coordinates are normalized at the contract level; each backend owns its conversion to device units. | ch. 2, ch. 4 | settled in contracts (Action, Region, Match); backend conversion pending W2 and W3 |
| C11 | Risk register renumbered R1 to R7 (V1.0 began at R2 with no R1). Three rows and an owner column added. | ch. 9 | settled |
| C12 | Reconciled the 57% coverage and 55% allocation figures, and stated the implied 10% commodity slice as two features. | ch. 3, ch. 4 | settled (wording); see O1 |
| C13 | Scope of the "roughly a third" custom share stated: host software only, firmware tracked separately. | ch. 4 | proposed |
| C14 | `SettleChecker` is its own interface, separate from `Matcher`, because imagehash backs it in both the Maa and the OpenCV case and it runs before every action, so it must stay in-process. Seven interface types in five seams. | ch. 4.1 | settled |
| C15 | Lease semantics fixed: one holder per device; `acquire` on a held device raises even for the same holder; fencing token increases per grant and is unchanged by `renew`; valid while now < expiry; stale `release` or `renew` never affects a newer holder. The InputRouter checks leases; backends never see them. | ch. 4.1 | settled |
| C16 | The `DeviceEvent` seam is carried by a `DeviceEventSource` interface (blocking `events()`, `close()`), with USB vendor and product ids validated as four lowercase hex digits. Distinct from the `Event` log model. | ch. 4.1 | settled |
| C17 | Every seam has a reusable contract suite run against its fake and, later, against the real adapter, so a fake cannot drift from reality unnoticed. | ch. 4.1 | settled |
| C18 | Contract models in code: `DeviceProfile` (device id, ordered non-empty duplicate-free input modes), `Frame` (monotonic capture timestamp, source kind, encoded payload as bytes, to be revisited after the W3 measurements) and `Action` (Tap, Swipe, Key, Text in normalized coordinates, no device id). | ch. 2, ch. 4 | settled |
| C19 | Seat contract models in `contracts/seats.py`: roles (hid_board, capture_card, phone), by-id/by-path `DeviceMatch`, `SeatSpec`, `SeatTable` enrollment with uniqueness rules, and `SeatState`/`SeatChange`. C8 stays proposed until registry resolution and C9 land. | ch. 2.1, ch. 4.2, Table 5 #2 | settled (models); resolution pending |
| C20 | Registry slice: `ProfileStore` (enrollment, duplicate-id rejection) and `SeatRegistry`, which resolves `DeviceEvent` streams against a `SeatTable` into `SeatState`/`SeatChange` transitions using per-role device claims. Virtual attach/detach runs on a fake udev feed in CI. | ch. 4.2, ch. 8, Table 5 #2 | settled |
| C21 | Day-5 dual-client test: the same labelled frame corpus drives `FakeInputBackend` and a stub of Maa's custom-controller callbacks, asserting equivalent actions. The stub imports no `maafw` (C5). Corpus is synthetic pending recorded footage (R9). | D6, ch. 5.1, ch. 8, W1 | settled (shape); corpus provisional |
| C22 | Four CI gates now run: ruff, mypy, lint-imports and pytest. A zero-byte tracked-file test replaces the empty scaffold placeholders with `.gitkeep` markers, and C5/C7 are re-tagged `proposed` because their files belong to W2/W5. | ch. 4.3, ch. 8, PDF recs 3-5 | settled |
| C23 | Sim core (`farm.testing.SimDevice`): a virtual seat emits udev-shaped `DeviceEvent`s with monotonic timestamps through a real `DeviceEventSource`; the production `SeatRegistry` drives virtual attach/detach in CI. This closes the W1 exit demo. | ch. 8 (days 6-7), W1 | settled |
| C24 | Renamed `DeviceRole.HID_CONTROLLER` to `HID_BOARD` (`"hid_board"`). Roles name physical hardware; "controller" collided with MaaFramework's custom-controller callback API. No serialized data exists yet, so the value change needs no migration. | ch. 4.1, Table 4 | settled |
| C25 | M1 (review v3): one `DeviceEvent` whose identifiers match several roles of the same seat is recorded as an ambiguous claim that contests those roles instead of filling them. A single physical device can no longer make a seat READY; the same event may still fill one role in each of several seats. | ch. 2.1, Table 5 #2 | settled |
| C26 | N2 (review v2): `SeatState.ready_modes` records which input modes are usable now, derived from `present ∩ role-requirements`. `SeatStatus` remains an inventory-completeness signal, not a schedulability gate: a dual-mode seat with only the phone attached is usable via ADB while its status is PARTIAL. | ch. 2.1, ch. 4.2 | settled |
| C27 | R1 (review v4): a DETACH releases every claim for the same device across all roles and both claim dictionaries, using identifier agreement where both reports supply a field. An asymmetric detach — fewer matched roles or an omitted optional identifier — can no longer wedge a seat in CONFLICT; a genuinely different claimant is still left alone. | ch. 4.2, Table 5 #2 | settled |
| C28 | R2/R3 (review v4): role requirements are per mode — HID needs both `HID_BOARD` and `CAPTURE_CARD`, ADB needs `PHONE` — and `ready_modes` requires all of them, so a board without a capture card is not schedulable. A CONFLICT removes only the modes whose required roles are conflicted; `SeatState` documents that schedulers must consult `ready_modes`, not `status` alone. The registry test helper now takes `ready_modes` as an explicit literal rather than re-deriving production's formula. | ch. 2.1, ch. 4.2 | settled |
| C29 | N1 (reviews v2 and v4): `DeviceEventSource.events()` must yield a synthetic ATTACHED event for every already-present matching device at iteration start, before live changes (coldplug), so a restarted host discovers its plugged-in seats. The reusable event-source suite pins that ordering, and `SimDevice` gains a `present` mode that drives the production registry to READY without a new physical plug. The real pyudev adapter implements enumeration in W2. | ch. 4.1, ch. 8, C17 | settled (contract + suite); adapter due W2 |
| C30 | CR-6 (review v4, corrected): `EventLog.since()` returns deep copies, so a consumer editing a result cannot change the stored log. `append()` already copied its mapping, and pydantic copied nested values, so no change was needed there. | ch. 6, C17 | settled |
| C31 | CR-2 (review v4, amended): `MODE_ROLES` lives once in `contracts/seats.py` and is shared by enrollment and readiness. Enrollment accepts a seat when at least one declared mode has all its required roles, rather than requiring every mode — a dual-mode seat with no capture card remains a valid ADB seat. A board-only HID seat is rejected. | ch. 2.1, ch. 4.2, C19/C28 | settled |
| C32 | CR-3 (review v4, amended): every physical device gets a stable `by_id` unique to it; serial-less devices such as UVC cards get a synthesized `vendor:product` + USB port path, owned by the udev adapter at the seam. On DETACH, a lone matching claim is released even with omitted optional fields (C27), but when several claims match only an exact field-for-field match is released; otherwise the seat stays CONFLICT until such a detach arrives. | ch. 2.1, ch. 4.1, Table 5 #2 | settled |
| C33 | CR-1 (review v4): `SeatChange` now carries `ready_modes_before` and `ready_modes_after` (default empty), and `apply()` emits a change when the usable mode set changes even if `SeatStatus` does not. A scheduler consuming the change stream can no longer miss a fallback becoming usable or disappearing. The three-field construction stays valid. | ch. 4.2, ch. 6, C26 | settled |
| C34 | CR-9 (review v4): `tests/` and `tests/contracts/` are packages and all five fake suites import their suites as `tests.contracts.<suite>`. The same tests now collect under pytest's default prepend mode and under `--import-mode=importlib`, so the W2 adapter tests can reuse the suites from any directory. An AST guard rejects bare suite imports; `repo_audit.sh` EXPECTED covers the new files. | ch. 4.1, C17 | settled |
| C35 | N3/N4, amended by `docs/ARCHITECTURE.md` §4.4 / D-4 / D-7: `Key.code` is a canonical `KeyCode` StrEnum with exactly five values — `HOME`, `BACK`, `ENTER`, `DEL`, `APP_SWITCH`. HOME/BACK map to consumer usages 0x223/0x224 in composite firmware, ENTER/DEL to keyboard usages 0x28/0x2A; APP_SWITCH has a HID path (usage 0x1a2 → `KEY_APPSELECT` 580 → keycode 187 on common keymaps) that is kernel/keymap-version dependent and not relied on, so the HID backend reports `supports() == False` and scenarios use a touch macro or ADB keycode 187. Power, volume and mute are out of scope (D-4). Uppercase values keep existing `Key(code="HOME")` scenarios working. `InputBackend.perform()` blocks until full injection, and for Swipe until the gesture completes; the Maa stub records the canonical string and notes that real Maa's W6 adapter owns the integer-keycode mapping. | ch. 2.1, ch. 4.1, D6, D-4, D-7 | settled |
| C36 | Task 12: `docs/ARCHITECTURE.md` becomes the hardware source of truth. Corrected in this memo: the ESP32 is a HID digitizer, not a pointer (§12.1); no L1 tap-grid, alignment = active-area crop + `RES` (§12.2); firmware base is `stop-esp32-s3-to-reboot` touch-fw-2, D3 is session ideas only (§12.3); serial is UART0 over the USB-serial bridge with no-reset discipline, not CDC (§12.5); standard-seat ADB fallback is Wi-Fi (§12.6); dual-client proves verb shape only (§12.7); board health is `BOOT`/`PING`, not udev (§12.8). HANDOFF.md was deleted. | ch. 2.2, ch. 4, ch. 7, ch. 10, D3, arch §12 | settled |
| C37 | CR-5 (Task 5): `FakeDeviceEventSource` has a separate preload list; `events()` yields coldplug devices in preload order before any live event, and `close()` seals the feed (buffered events still drain; later `push`/`preload` are ignored). The reusable suite pins ordering, post-close drops, and preload+detach; an anti-vacuity check proved the ordering test fails when preload is aliased to push. The seal is a fake determinism choice, documented as such; real adapters manage their own lifetime. | ch. 4.1, C17, C29 | settled |
| C38 | CR-4 (Task 4): `LeaseManager.is_valid()` now states that it checks the **current grant's** expiry, not the snapshot's own `expires_ns`. `renew()` extends the grant for every same-token snapshot, so a pre-renew lease stays valid until the renewed grant expires. The reusable suite pins this behavior and the docstring. | ch. 4.1, C15 | settled |
| C39 | CR-6 (Task 6): `DeviceProfile.input_modes` and `SeatTable.seats` are tuples, so a frozen model cannot be edited through a mutable list. `SeatRegistry` deep-copies the enrollment table at construction, and `FakeEventLog` deep-copies `data` on append (with `since()` already returning deep copies), so neither can be changed through a caller's nested data. `SeatSpec.devices` stays an unfrozen dict for now; its wrapping cost is revisited with retention at W9 (N8). | ch. 4.1, ch. 6, C18/C19 | settled |
| C40 | Task 9: `mypy` strict mode is on and clean; dev dependencies have upper bounds, `actions/checkout` and `actions/setup-python` are SHA-pinned, and CI runs a Python 3.11 + 3.12 matrix with a 15-minute timeout. | ch. 4.3, ch. 8 | settled |
| C41 | Task 10: README documents purpose, layout, setup, the five gates and the memo links; reviews v1/v3/v4 are committed as markdown summaries (PDFs stay local per `.gitignore`); `HANDOFF.md` is gone; `repo_audit.sh` EXPECTED covers every tracked path including the 14 `.gitkeep` markers, so drift is zero. No LICENSE file is committed by owner decision — the gap is recorded in O9. | ch. 4.3, F6 | settled (LICENSE gap recorded) |
| C42 | CR-8/CR-7b (Task 11): `CaptureSource.latest(max_age_ms)` rejects negative values with `ValueError`; `latest(0)` still accepts a frame stamped at the current clock. `SimDevice.attach()` validates the entire role batch before attaching any, so a rejected batch leaves no queued event and no partial state. | ch. 4.1, ch. 4.2 | settled |
| C43 | `SimDevice.attach()` also rejects a role repeated within one batch, so `attach([HID, HID])` raises before queuing anything. `FakeDeviceEventSource` consumes its preload list on the first `events()` call, so coldplug is never re-delivered; the finite fake may still be iterated again to drain later live events (the incremental `drain()` pattern). The contract and reusable suite document both rules. | ch. 4.1, C29 | settled |
| C44 | CR-10 definition recovered and O17 closed as a recovery item: `SeatRegistry.apply()` constructs two `SeatState` models per seat per event to compare status and modes. Reclassified as a W9 performance item — derive the comparison from claim sets and build `SeatState` only on demand. Deferred deliberately. | ch. 4.2, O17 | settled (definition); work deferred to W9 |
| C45 | Serial protocol v1 is specified in `protocol/serial_v1.md` from the proven touch-fw-2 firmware: UART0 bridge at 115200, LF-framed ASCII lines, lockstep `PING`/`RES`/`TAP`/`SWIPE`, error vocabulary, digitizer coordinate mapping, timing and the no-reset open sequence. `protocol/serial_vectors.json` holds 26 golden cases (boundaries, invalid inputs, boot banner) shared by Python and firmware. | ch. 4A, C7, arch §5–6 | settled (base); hardening designed |
| C46 | First hardware-free adapter slice: `farm.adapters.esp32_serial` provides the encoder/reply decoder, `Esp32SerialBackend` (Tap/Swipe only, normalized→crop-pixel conversion, blocking `perform`, BOOT detection) and `open_esp32_no_reset` with lazy pyserial import. Tests use `farm.testing.FakeEsp32Serial`; no hardware needed. pyserial is now a declared runtime dependency. | ch. 4A, ch. 4.1, C7 | settled (base); no-ADB acceptance pending W2 hardware |
| C47 | Serial hardening B/K/D/E: the per-command deadline includes gesture duration (a long swipe can take up to 10 s host-side); swipe ms is bounded 16..10000 in the host; `handshake()` re-PINGs every 0.5 s for cold boots; `sync_resolution()` updates the adapter's coordinate size; timeouts and `BOOT` drain the port and set `needs_rehandshake`, and `perform()` refuses work until `recover()` re-handshakes and re-sends `RES`. | ch. 4A, C46, arch §5 | settled |
| C48 | Serial hardening C/F/G: inbound bytes are buffered until LF so partial reads cannot split a reply; a bare `ERR` is an error; `Esp32SerialBackend` runs the reusable `InputBackendContract` suite (C17) in addition to the vector tests. The single-caller assumption and the normalized 1.0→crop-size convention are documented. | ch. 4.1, C17, C46 | settled |
| C49 | Final review corrections: if a `BOOT` banner is seen during `handshake()`, the host re-sends `RES` before clearing `needs_rehandshake` — a restart resets the firmware's coordinate space, so skipping this silently misplaces taps. The APP_SWITCH rationale is corrected: HID usage 0x1a2 → `KEY_APPSELECT` 580 → keycode 187 exists but is kernel/keymap-version dependent and not relied on; disposition stays touch macro / ADB 187. `ARCHITECTURE.md` status refreshed to 456 tests / memo V1.25 and the serial adapter marked [built]. | ch. 4A, C35, C47, arch §11 | settled |
| C50 | Host preparation (Stage 0): runtime deps `pyudev`, `opencv-python-headless`, `numpy` and `PyYAML` declared alongside pyserial; `farm.adapters.udev` discovers ESP32 boards by by-id and capture cards by by-path using `VIDIOC_QUERYCAP`, skipping webcams and synthesizing C32 ids; `farm.adapters.uvc_cv2` provides MJPG capture, no-signal detection and active-area cropping behind the CaptureSource seam; `tools/probe_esp32.py` and `tools/probe_capture.py` are host diagnostics. No hardware I/O was performed. | ch. 4A, C7, C32 | settled (software); hardware verification pending |
| C51 | Stage 1 hardware verification and HDMI lock wait. Both ESP32 boards answered PING with READY and **zero** BOOT banners through the no-reset open; board `5C63001367` accepted a TAP, board `5C63002523` reported `usb send failed` (no phone attached). On this host the card shows color bars for ~4 s, then black ~2 s, then a stable crop — so `UvcCaptureSource.refresh()` now retries for up to 20 s (0.5 s interval) before raising `StaleFrame`. Verified live crop `(746, 10, 1202, 1061)` → 457×1052 at `/dev/video0`. | ch. 4A, C50, arch §7 | settled |
| C52 | Topology reliability: `find_active_area()` now uses the fraction of pixels above background+25 per column/row instead of mean luma, so dim screens no longer shift the crop; `stable_area()` majority-votes jittery samples. `tools/diagnose_topology.py` reports every board (PING/READY, BOOT count) and card (NO_SIGNAL / BLACK / ACTIVE with crop and stability) with one exit code. `topology_snapshot()`/`diff_snapshots()` record stable identities so a replug or port move is reported as an added/removed id — readiness for topology changes, though no live pyudev monitor exists yet. | ch. 4A, C50, arch §7/§9 | settled |
| C53 | Hardware runbook and recovery: `docs/HARDWARE_DIAGNOSTICS.md` keeps the diagnostic commands, the dual-HDMI ffplay command and the symptom→cause→fix table from the bring-up (colour bars, black screen, busy V4L node, hung board, by-path churn, ttyACM renumbering). `diagnose_topology.py` gains `--recover`: a deliberate DTR/RTS reset that waits for `BOOT`, re-PINGs and is explicitly an exception to no-reset-on-open. A hung board (`5C63002523`) was recovered this way; a 30 s soak afterwards gave 55/55 READY on both boards. | ch. 4A, ch. 8, C52 | settled |
| C54 | Diagnostic enforcement: a baseline snapshot now fails the run if a previously known board or card disappears (the baseline is not overwritten while missing, so the failure stays visible). Recovery re-sends `RES` when `--resolution W H` is given — required because BOOT resets the firmware's coordinate space. Opt-in `--check-hid` sends one centre TAP per READY board; `DONE` proves the HID gadget reaches a phone, `ERR usb send failed` proves it does not. Verified live: both boards DONE, both cards ACTIVE, RESULT OK; a deliberately stale baseline correctly reported MISSING and RESULT NOT READY. | ch. 4A, C52/C53 | settled |

**Open items carried forward**

| # | Item | Status |
|---|---|---|
| O1 | The itemised rubric behind MaaFramework's 3.30 / 5.00 prior score is not in the memo and must be attached, or the score removed. | open |
| O2 | Week-9 exit criteria must be stated in numbers (seat count, soak hours, lease-acquisition latency percentiles, a measurable bound on failure recovery). | open, before W9 |
| O3 | The feature-by-feature mapping behind the 55 / 10 / 35 split (which of the 20 features sit in which bucket) is not listed. | open |
| O4 | ADB-only seats: measure screencap latency in W3 and decide whether those seats get a looser budget or a lower cycle rate. | open, W3 |
| O5 | Share of ADB-only seats among the fifty, and whether they ever also get an ESP32 and capture card as a fallback. | open |
| O6 | Firmware/protocol versions at handshake are not recorded, and ADB screencap (C9) stays proposed until W3. Seat resolution and the profile store landed with C20. | open (W3/W5 follow-up) |
| O7 | The dual-client test uses synthetic labelled frames; replace with recorded footage from target phones before the W5 probe (R9). | open, before W5 |
| O8 | Task 13: composite keyboard + consumer firmware, heartbeat/STOP/dedup, version banner, golden vectors, and the architecture §15 no-ADB acceptance checklist. Owner TBD, W2. | open, W2 |
| O9 | No LICENSE file is committed by owner decision (22 November 2026). The farm and experiments repositories remain unlicensed until a choice is made; this is a known gap, not an oversight. | open, owner: user |
| O10 | N5: document that `Frame.captured_ns` is host arrival time; measure content-to-input latency for ADB screencap (ties O4/R10). | open, W3 |
| O11 | N6: lease-proxy locality note on the `LeaseManager` seam and a `worker_ipc.md` spec under C7 before the runner. | open, W4 |
| O12 | N7: single owner for enrollment plus persistence; wire `app.py` when the first adapter lands. | open, W2 |
| O13 | N8: event-log retention policy; restate gapless-from-1 as gapless within the retained window. | open, W7 |
| O14 | N9: state that fencing tokens are monotonic per supervisor lifetime and equality-based validity is restart-safe. | open, W7 |
| O15 | N10: registry concurrency model (confine to supervisor thread + lock when the udev listener lands). | open, W2/W8 |
| O16 | CR-7: give `SimDevice` a serial-less capture-card mode for the coldplug/restart scenario. | open, W2 |
| O17 | CR-10 (definition recovered 22 November 2026): `SeatRegistry.apply()` builds two full `SeatState` pydantic snapshots per seat per event just to compare status and modes — O(seats) model constructions. Measured 100 snapshots per event at 50 seats, about 0.82 ms/event locally. Fix: derive status/modes directly from the claim sets and construct `SeatState` only on demand. Reclassified as a **W9 performance item**; no action now. | open, W9 |

---

## 1. Executive Summary: The Agreed Decisions

This document closes the study phase of the Android Device Farm project. The question set was: which open-source repositories cover the farm's feature baseline, should the system be written from scratch or assembled from existing code, can that code be composed as microservices, and which module is built first. Every question has a defended answer. The verdict is a hybrid: one framework adopted behind a decision gate, fourteen commodity libraries sealed behind farm-owned interfaces, and five custom cores that carry the farm's differentiating topology. The ten-week plan in chapter 7 turns those answers into a build order.

| 7 | 14 | 5 | 10 |
|---|---|---|---|
| repositories evaluated | libraries adopted | custom cores to write | weeks, one engineer |

The decisions below are the baseline that any future change proposal must argue against.

**D1: Hybrid build-reuse strategy.** Neither from scratch nor deep reuse. MaaFramework (LGPL-3.0) is adopted as the recognition and pipeline engine, fourteen permissive commodity libraries cover plumbing, and roughly a third of the host software is written by hand because no repository covers the ESP32-HID + UVC-capture + fifty-seat topology.

**D2: MaaFramework behind a week-five gate.** It scored highest of the viable candidates (~57% feature coverage, active, 5.2k stars) but its vision and pipeline semantics must first pass a probe on recorded frames. The probe is cheap precisely because the interfaces exist before the integration code does.

**D3: firmware base is `stop-esp32-s3-to-reboot` (touch-fw-2).** *(Corrected by `docs/ARCHITECTURE.md` §12.)* The working firmware is a two-finger USB HID **digitizer** (usage page 0x0D, usage 0x04), not a keyboard/mouse pointer. It injects absolute touch with no root, no ADB and no app on the phone. `esp32-android-agent` uses the wrong HID layer (keyboard + mouse, per-phone pointer calibration); keep it only for session ideas — heartbeat, cancel, no-replay.

**D4: Contracts first.** The first module is the contracts package: the `Event` and `DeviceProfile` models plus the five seams (InputBackend, CaptureSource, LeaseManager, DeviceEvent, Matcher/OcrEngine). Contracts contain models and interfaces only, with stdlib and pydantic as the sole imports. Fakes live in `farm.testing`. Everything else compiles against contracts; every adoption is sealed inside them. *(Changed in V1.1: C1, C2.)*

**D5: Modular monolith, not microservices.** The farm runs as one deployable with per-device worker processes. The closed control loop is latency-sensitive, frame transport across service boundaries is wasteful at fifty seats, and process isolation already delivers the failure containment and license separation microservices would buy (chapter 6).

**D6: Dual-client interface test on day five.** The same recorded-frame corpus drives both the farm's fake InputBackend and a stub of MaaFramework's custom-controller callbacks, converting the week-five adoption decision from an architecture change into a configuration change.

**D7: Vision stays minimal until the gate.** Custom template matching and OCR work before week five carries a live probability of being deleted by the probe. Vision is built last among the cores, smallest, and only far enough to close the capture→recognise→act→verify loop.

**D8: Streaming is a view, not a core.** Dashboard live views run on the internal event and frame stream (MJPEG over WebSocket). External broadcast to Facebook or YouTube, if ever needed, stays outside the farm: the platforms' native apps cover single-platform casts and PRISM Live Studio covers simultaneous multi-platform pushes.

---

## 2. System Baseline: The Twenty-Feature Mandate

The farm automates interaction with physical Android phones. A decision engine closes a loop: it captures a frame, recognises screen state, chooses an action, injects it, and verifies the result before proceeding. Fifty seats must run this loop unattended, overnight, with a single writer per device enforced by leases.

### 2.1 Seat classes *(proposed, C8)*

Phones differ in what they accept, so a seat is one of two classes:

| Class | Control | Observation | Share |
|---|---|---|---|
| Standard seat | ESP32-S3 HID injection (root-free) | HDMI / UVC capture card | most phones |
| ADB-only seat | ADB | ADB screencap | a minority (exact share open, O5) |

- Each standard seat pairs one ESP32-S3, which injects touch and key input as a USB HID device, with one UVC capture card that observes the phone's screen.
- Some phones refuse ADB; the HID path exists for them, which is why it is root-free and carries the project's biggest hardware risk.
- Some phones cannot feed a capture card or do not accept HID. They remain valid seats through ADB control and ADB screencap.
- A phone may support both backends. Its `DeviceProfile` then holds an ordered preference list; the first usable entry is tried first and the other serves as fallback. Only one backend is active at a time, and the lease enforces it. On a standard seat the USB-C port is occupied by the HDMI hub, so the fallback is **ADB over Wi-Fi** (paired once), not wired ADB.
- A manually operated seat is an operator concern (the dashboard's manual-control path, week 8), not a backend and not an entry in a preference list.

**Device identity (C32).** Every physical device has a stable `by_id` that is unique to it. Devices without a serial, such as a UVC capture card, get a synthesized id from `vendor:product` plus the physical USB port path; the udev adapter owns that synthesis at the seam. Because ids never collide between physical devices, a detach carrying only `by_id` normally identifies one claimant. The registry still guards the ambiguous case: if several claims match, only an exact field-for-field match is released.

Everything above the seams is shared by both classes: vision (matching and OCR), scenarios, queue, retries, leases, the event log and the console.

### 2.2 Normalized coordinates *(C10)*

Scenarios, the decision engine and the runner express positions in normalized coordinates (0 to 1). Each `InputBackend` converts them to its own units. *(Corrected by `docs/ARCHITECTURE.md` §12.)* The ESP32 is a **HID digitizer** with absolute coordinates, not a pointer. There is **no tap-grid calibration**. Alignment is a chain of fixed linear maps: normalized 0–1 → capture active-area crop pixels → `RES`-declared coordinate space → HID logical 0–32767 → Android's automatic display scaling. The "active area" is the portrait phone image inside HDMI pillarboxes, detected in the capture frame; the crop also becomes the touch coordinate space because `RES` is set to the crop size. ADB converts by screen width and height. See §8 of the architecture document.

### 2.3 The twenty-feature baseline

The baseline is the scoring yardstick used throughout the repository study, distilled from the high-level design description and the design review. Every coverage figure in chapter 3 is measured against it.

| Domain | Features in the baseline | Count |
|---|---|---|
| Input | ESP32-S3 HID backend (root-free); ADB backend; unified Action API; per-device input preference list | 4 |
| Capture | UVC / HDMI capture-card path; MJPG with buffer-one and latest-frame freshness; exposure lock | 3 |
| Vision | Template matching with ROI and threshold; OCR; perceptual-hash settle check | 3 |
| Automation | Decision engine with interrupt rules; declarative YAML scenarios; scheduler with queue, retry and timeout; settle-verify closed loop | 4 |
| Farm | Lease with single-writer rule; active-area crop detection and linear normalized-coordinate mapping; dashboard live view with manual control; REST API; WebSocket event stream; fifty-device scaling | 6 |

*Table 1. Sum check: 4 + 3 + 3 + 4 + 6 = 20.*

Two scope notes. First, the loop has a latency budget on the order of 300 to 500 milliseconds from frame to input; that budget drives the architecture decision in chapter 6. Second, live screen display in the dashboard is a consumer of the capture pipeline, never a second writer of device state, the same invariant that keeps the dashboard a view (D8).

---

## 3. Open-Source Landscape: Seven Repositories

Seven repositories were evaluated against the baseline. Each was scored on feature coverage with a 45% adoption threshold, then weighed on activity and health, license, architectural fit and replaceability. Coverage alone never decided anything: the highest-scoring candidate was rejected as a code donor, and one apparently healthy project turned out to be archived.

| Repository | Coverage | Stars | Status | License | Verdict |
|---|---|---|---|---|---|
| LmeSzinc / AzurLaneAutoScript | ~60% | 9.8k | Active | GPL-3.0 | Reference only: game-specific automation, GPL |
| MaaXYZ / MaaFramework | ~57% | 5.2k | Active | LGPL-3.0 | Adopt: vision, OCR and pipeline engine behind W5 gate |
| shenlan-ai / esp32-android-agent | ~52% | 34 | New project | MIT | Reference only for session ideas (heartbeat/cancel). Firmware base is `stop-esp32-s3-to-reboot` touch-fw-2 — a digitizer, not a pointer |
| SonicCloudOrg / sonic | ~50% | n/a | Archived 2025-03 | AGPL-3.0 | Excluded: archived by its maintainers |
| AirtestProject / Airtest | ~45% | 12k | Low activity | Apache-2.0 | Not adopted: at threshold, weaker fit than Maa |
| DeviceFarmer / stf | ~42% | 4.7k | Low activity | Apache-2.0 | Reference only: device-seat topology ideas |
| shamanec / GADS | ~41% | 408 | Active | AGPL-3.0 | Excluded: below threshold and AGPL |

*Table 2. Coverage is measured against the twenty-feature baseline; star counts are as of the survey date (not recorded in V1.0; to be dated on the next survey).*

Three findings shaped everything that follows. First, no repository covers the farm's actual topology: ESP32 HID input, UVC capture routing and multi-seat orchestration appear together nowhere, which is why a composite strategy was inevitable. Second, coverage can lie: AzurLaneAutoScript posts the highest number but is a game-specific automation suite whose GPL-3.0 license would contaminate the whole codebase, so it serves as architecture reading material and nothing more. Third, apparent health can lie too: Sonic presented roughly half the baseline on paper, yet its repositories were archived in March 2025; the study caught this only by checking archival status directly, which is why the adoption checklist in chapter 5 treats project health as a hard gate rather than a star count.

**Coverage versus allocation (C12).** The 57% in Table 2 is raw feature coverage: the share of the twenty features that MaaFramework implements. The 55% in the allocation (Table 3) is the share of the baseline *assigned* to MaaFramework in the build plan. The two measure different things, and the allocation can sit below coverage where a feature that MaaFramework covers is built elsewhere in the plan. The feature-level mapping is not yet listed (O3).

---

## 4. Build vs. Reuse: The Hybrid Decision

With the landscape mapped, the from-scratch question has a short answer. Rewriting the recognition stack (template matching, OCR, pipeline semantics, retry behavior) means owning every bug in the part of the system with the highest iteration cost and the least differentiation, and arriving six or more months later with a worse version of solved problems. Deeper reuse fails at the other end: the remaining candidates are archived (Sonic), license-contaminating (GADS, AzurLaneAutoScript) or below the coverage threshold (stf). The hybrid sits between the extremes.

| Source | Share of baseline | Features (of 20) |
|---|---|---|
| MaaFramework engine (contingent on the W5 gate) | 55% | 11 |
| Commodity libraries and glue (assumes the gate passes) | 10% | 2 |
| Custom farm code (five cores) | 35% | 7 |

*Table 3. Allocation of the twenty-feature baseline. The commodity slice is the remainder, 100 − 55 − 35 = 10%, which is two features. V1.0 left this figure implicit (C12).*

**Scope of the custom share (C13, proposed).** The "roughly a third" figure counts host-software features only. Firmware for the ESP32-S3 seat is tracked separately and is not part of the 35%. This keeps the figure from being silently re-denominated later.

**Moving code between cores does not change the custom share.** The 35% is counted in features. "Lease with single-writer rule" is one custom feature wherever its code lives, so relocating lease authority from the registry to the supervisor (C3) changes the package, not the count.

### 4.1 The seams

Adoption only works because every library arrives sealed behind a farm-owned interface, and those interfaces live in the contracts module. For each adopted component, the table names the interface that isolates it and what a late swap would cost if the seam did not exist. This is the mechanism that makes the week-five MaaFramework decision reversible, that keeps a udev library swap internal to the registry, and that lets the ADB and HID input paths stay interchangeable per device profile.

| Seam (`contracts/`) | What it seals | Cost if the seam is missing |
|---|---|---|
| DeviceEvent | pyudev device events | Udev event shapes leak into every consumer of attach/detach; a library swap becomes a farm-wide refactor |
| InputBackend | adbutils (ADB path); ESP32 HID (custom) | Input routing forks per backend; per-device input preference collapses into if-else chains |
| CaptureSource | opencv-python-headless (UVC); ADB screencap *(proposed, C9)* | The freshness contract and latest-frame slot get rebuilt around whatever codec path replaces it |
| Matcher / OcrEngine / SettleChecker | MaaFramework or OpenCV (Matcher, OcrEngine); imagehash (SettleChecker, in both cases) | The week-five decision stops being a configuration change and becomes a migration; settle checks would pull a Maa round trip into every action |
| LeaseManager | Nothing: pure custom core | The single-writer invariant loses its single implementation point |

*Table 4. Five seams, seven interface types: InputBackend, CaptureSource, LeaseManager, DeviceEventSource, and Matcher, OcrEngine and SettleChecker sharing one seam row. Interfaces exist before the libraries arrive, not after.*

`LeaseManager` is a seam in contracts; its implementation lives in the runner's supervisor (C3). Lease semantics (C15): a device has at most one holder; `acquire` on a held device raises `LeaseHeld`, even for the same holder; each grant carries a fencing token that increases per device and is unchanged by `renew`; a lease is valid while the monotonic clock is below its expiry; `renew` of an expired, released or taken-over lease raises `LeaseExpired`; a stale `release` never frees a newer holder's lease. The InputRouter checks `is_valid` before every `perform`, and backends never see leases. The `Event` log model (sequence and timestamp) and the `DeviceEvent` seam (pyudev attach/detach) are different things and live in different contract modules.

**ADB screencap as a second CaptureSource *(proposed, C9)*.** ADB-only seats observe the screen through ADB screencap, which is generally slower and heavier than a UVC frame grab. Its latency has not been measured (O4). The frame type carries a capture timestamp and a source kind, so the freshness contract and settle checks can judge frames from either source, while vision stays identical.

### 4.2 The five custom cores

The custom third of the baseline is not leftover work; it is the product. Five cores carry it, and each is custom for the same reason: no existing repository implements this farm's seat topology.

| # | Custom core | What it owns and why it stays custom |
|---|---|---|
| 1 | Input control | The ESP32 UART0 line protocol over the USB-serial bridge, the HID digitizer descriptor, and the InputRouter that applies each device's input-mode preference. Root-free absolute touch injection is the farm's signature capability. |
| 2 | Registry | Device identity by by-id / by-path rules, seat resolution, inventory, enrollment, and the firmware and protocol versions recorded at handshake. It does not own leases. |
| 3 | Runner, orchestration and lease authority | The supervisor (single writer of the event stream and holder of the leases), per-device workers, the scenario interpreter, the queue, scheduling, retries and timeouts across fifty seats. Scheduling semantics are coupled to the lease and event model. |
| 4 | Capture routing and active-area detection | UVC seat routing, the freshness contract, MJPG capture, no-signal detection, and pillarbox crop detection that defines the touch coordinate space. |
| 5 | Console wiring | The event-stream views, the manual-control path and the dashboard assembly. FastAPI and Jinja2 are commodities; what they display is farm state. Views, never writers. |

*Table 5. The five custom cores (~35% of the baseline, host software).*

Vision is **not** a core. It is the adopted engine (MaaFramework) plus a minimal fallback matcher (D7), the only custom vision code.

### 4.3 Code layout and enforcement *(C6)*

The source tree is `src/farm/`. Dependency direction is enforced by import-linter, highest layer first; a layer may import only from layers below it:

```
testing
adapters
console
runner
control | registry | vision      (siblings: may not import each other)
calibration
capture
contracts
```

- `app.py` is the composition root, directly under the root package and outside the layers. It is the only importer of `adapters`.
- `farm.testing` and `farm.adapters` sit above everything, so production code cannot import fakes and cannot reach a third-party library except through the composition root.
- Each third-party library is imported in exactly one adapter module (`udev.py`, `adb.py`, `esp32_serial.py`, `uvc_cv2.py`, `maa_client.py`, `http_ws.py` for the console's server stack). This makes the seams table a property of the code.
- The calibration layer detects the phone's active area in the captured frame and converts normalized coordinates; it receives the `InputBackend` interface by injection and does not import control. It performs no tap-grid calibration. Control checks leases through the `LeaseManager` interface from contracts, not through the runner.
- Contracts are checked by an AST allowlist test: stdlib, pydantic and `farm.contracts` only. A dependency added later is rejected by default. The test has self-tests proving the guard can fail.
- Cross-process contracts live in `protocol/`: `serial_v1.md` with golden vectors (`serial_vectors.json`) exercised from both the Python tests and the firmware, and `maa_ipc.md` for the farm-to-Maa message surface (to be written in week 5).

---

## 5. Adoptions and License Strategy

Fourteen libraries carry the adopted share of the baseline. The set was chosen so that every runtime dependency is permissive (MIT, Apache-2.0, BSD-style or MPL-2.0) except the two LGPL components, and those two are held at arm's length by design. Nothing under GPL or AGPL enters the dependency tree; that constraint eliminated three of the seven candidates before fit was even discussed.

| Library | Role in the farm | License |
|---|---|---|
| pydantic | Contracts: Event and DeviceProfile models; validation at every module boundary | MIT |
| pyudev | Registry: udev attach/detach events behind DeviceEvent | LGPL-2.1+ |
| adbutils | InputBackend, ADB path: tap, swipe, key, text; ADB screencap *(proposed)* | Apache-2.0 |
| pyserial | Control: line protocol v1 over the ESP32's UART0 USB-serial bridge (115200), no-reset open discipline | PSF / BSD-style |
| opencv-python-headless | Capture (VideoCapture, MJPG, buffer-one) and the fallback matcher | Apache-2.0 |
| imagehash | Perceptual-hash settle checks in the verify loop | MIT |
| MaaFramework (maafw) | Vision, OCR and pipeline engine behind the week-five gate | LGPL-3.0 |
| FastAPI | REST API surface and dashboard backend | MIT |
| uvicorn | ASGI server for FastAPI | BSD-3-Clause |
| Jinja2 | Dashboard server-rendered views | BSD-3-Clause |
| websockets | Event stream push and manual-control channel | BSD-3-Clause |
| PyYAML | Declarative scenario files | MIT |
| pytest | Test runner behind the CI gate | MIT |
| hypothesis | Property tests for the contracts models | MPL-2.0 |

*Table 6. The fourteen adopted libraries. License families: 5 MIT, 2 Apache-2.0, 3 BSD-3-Clause, 1 PSF/BSD-style, 1 MPL-2.0, 1 LGPL-2.1+, 1 LGPL-3.0 (total 14). Tooling alongside: ruff, mypy, import-linter, SQLite (stdlib). ruff, mypy and import-linter are development tools, not runtime dependencies.*

### 5.1 Keeping LGPL at arm's length

MaaFramework is LGPL-3.0, which permits use in a proprietary system provided the library remains a separate work that the user can replace. The farm satisfies this structurally rather than by legal argument:

- MaaFramework runs as its own operating-system process, driven through its custom-controller interface (connect, screencap, click, swipe, touch down/move/up, press key, input text), which maps one-to-one onto the InputBackend and CaptureSource verbs the farm already speaks.
- **(C5)** The service is its own distribution, `services/maa_service`, with its own `pyproject.toml` and virtual environment. `maafw` is not a dependency of the farm package, so an import from farm code is impossible rather than merely forbidden. The decision is recorded in `adoption/` as: "maa_service is a separate distribution because of the LGPL boundary."
- No farm code links against it statically, and any local modifications to the framework would be published upstream.
- pyudev, the other LGPL component, is used unmodified as a normal Python dependency, which LGPL-2.1+ expressly permits.

### 5.2 The compliance checklist

Four checks run for every dependency, existing or candidate; the archived-Sonic episode explains why the second one exists.

- **License screened:** GPL and AGPL candidates are rejected on sight, however good the coverage. AzurLaneAutoScript and GADS failed this check; Sonic failed the next one.
- **Health verified beyond stars:** archival status, last-commit date and release cadence are checked directly at the source, not through catalogs.
- **Sealed behind a contracts interface before first use,** so a swap touches one module instead of the farm.
- **Modifications policy written down before the first patch:** upstream first, fork only with a dated note in the adoption file.

---

## 6. Architecture: Modular Monolith, Not Microservices

One question from the study remained open until this chapter: can the existing code be composed as microservices, and would that genuinely help? The candidates invited the idea (stf is a modular WebSocket plugin architecture, Sonic was a hub-agent split, GADS runs Node.js workers, and MaaFramework separates pipeline from controller). All four were examined, and the answer is still no.

> **Verdict: a modular monolith with per-device worker processes.** Microservices are rejected: the benefits they would deliver are already bought cheaper by process boundaries, and the costs they add land exactly on the farm's most latency-sensitive path.

Five arguments, in decreasing weight.

1. **The closed control loop.** Each cycle moves a frame from capture through recognition to a decision to an injected action, inside a 300-to-500-millisecond budget. An in-process call costs microseconds; every network hop between services adds serialization, queueing and scheduling jitter measured in tens of milliseconds. Spent five times per loop, per device, that overhead is not marginal; it is the budget.
2. **Frame transport.** A compressed 1080p frame is on the order of 300 KB; at 5 to 10 frames per second across 50 devices, a service-boundary topology moves roughly 73 to 147 MB/s (stated in V1.0 as the order of 75 to 150 MB/s) of image data that an in-process design never copies at all.
3. **Operations.** Fifty seats are one rack, not a fleet: the deployment, discovery and monitoring machinery of a service mesh solves a scaling problem the farm does not have.
4. **Licenses.** The isolation microservices would provide for LGPL code is already provided by running MaaFramework as a separate process behind the custom-controller interface; the same boundary serves both goals.
5. **Failure isolation.** The failure that matters is one device's loop, and per-device worker processes contain exactly that: a vision worker crashing for seat seven never touches seat twelve.

What the farm keeps from microservice thinking is the discipline, not the deployment topology:

- **(C4)** The event stream has a **single writer: the supervisor**, which also holds the leases. Per-device workers send events to the supervisor over IPC, so there is one place where state changes. Every dashboard, logger and API is a consumer: views, never writers.
- MaaFramework stays a separate process at a message boundary.
- Workers scale per device, which is the axis the farm actually grows on. If a future vision pool ever needs independent scaling, the split happens along worker lines, not functional ones.

---

## 7. Step-by-Step Implementation Plan (W1 to W10)

The plan runs ten weeks for one engineer, with vertical slices throughout: every week ends with something real running, and hardware meets code in week two rather than at the end. Third-party libraries are named per week, and nothing enters the build that is not on the adoption table.

| Week | Focus and deliverables | Third-party libraries | Exit criteria |
|---|---|---|---|
| W1 | Contracts slice (Event, DeviceProfile, the five seams); `farm.testing` fakes and sim device; registry on a fake udev feed; import-linter and purity-guard CI gates; dual-client interface test on day 5 | pydantic, pyudev, pytest, hypothesis, ruff, mypy, import-linter | Virtual device attaches and detaches in CI; pytest and lint-imports green; dual-client test passes |
| W2 | Control on real hardware: line protocol v1 over the UART0 bridge with golden vectors; no-reset serial open + `BOOT` health monitoring; active-area crop + `RES` sync; InputRouter with per-device preference; extend touch-fw-2 with composite keyboard/consumer keys | pyserial, adbutils | First real tap through the ESP32 on a real phone; HID acceptance verified on a no-ADB phone; architecture §15 acceptance checklist |
| W3 | Capture closed loop: VideoCapture over UVC, MJPG, buffer-one, exposure locked; latest-frame slot with freshness contract; **measure ADB screencap latency (O4)** | opencv-python-headless | Frame-to-tap round trip on one device within the latency budget |
| W4 | Active-area crop detection and `RES` sync (no tap grid); runner v1 with SQLite queue; scenario interpreter v1; dashboard v0 as views on the event stream | PyYAML, FastAPI, Jinja2, uvicorn | First unattended overnight run on one device |
| W5 | MaaFramework probe gate: Python binding driven on the recorded-frame corpus; scored against coverage, activity, license, fit and replaceability (prior score 3.30 / 5.00, rubric to be attached, O1); write `protocol/maa_ipc.md` | maafw | Adopt-or-reject decision recorded; either branch is a configuration change |
| W6 | Integration branch: Maa custom-controller adapter (connect, screencap, click, swipe, touch, key, text), or on rejection a minimal matcher with ROI restriction | maafw or opencv-python-headless | Settle-verify loop closed with vision in the loop |
| W7 | Decision-engine hardening: interrupt rules, lease-held steps, settle-verify parameters; event-log discipline (seq, ts monotonic) | None (custom core) | Interrupt and recovery paths pass fault-injection tests |
| W8 | Dashboard live: WebSocket event stream, manual control path, complete REST surface | websockets, FastAPI, uvicorn | Operator observes and overrides a running device from the dashboard |
| W9 | Farm scaling: registry seats, lease contention, soak from ten toward fifty devices; health monitoring; retry and timeout tuning | None (custom core) | Overnight soak at target seat count with bounded failure recovery (**numeric criteria to be defined before W9, O2**) |
| W10 | Hardening: failure injection across all cores, license audit of LGPL boundaries, documentation, full CI gates | pytest, hypothesis | Beta: ten weeks end with the farm running unattended at scale |

*Table 7. The ten-week plan.*

### 7.1 The four milestones

**Week two** exists to retire risk, not to add features. Until a tap sent over HID lands on a real phone, ideally a phone that refuses ADB, every interface in the contracts module is untested against physics. One ESP32-S3, one capture card and two phones (one no-ADB) are all the hardware the week needs.

**Week four** proves the farm can be left alone. The overnight run exercises the runner, the queue, retries and the lease together, and its failure log becomes the input for week seven's interrupt rules.

**Week five** is the pivot of the plan: the probe replays a recorded-frame corpus through MaaFramework's Python binding and scores the results. Because the dual-client test ran in week one, either outcome, adopt or reject, lands as a configuration choice rather than a rewrite.

**Week nine** is where the fifty-seat promise is tested: lease contention under soak, worker process counts, and the point at which per-device processes stop being cheap. This is the plan's most optimistic single assumption for one engineer; see R6 and the recommendation to split the ramp from the soak.

---

## 8. Week One in Detail

Week one is scripted to the day, because it is the week that makes every later adoption cheap. Its exit demo is deliberately modest: a virtual device attaches and detaches through the real registry path in CI, pytest and lint-imports are green, and the contracts models reject malformed events. What the demo quietly proves is bigger: the interfaces speak the same verbs MaaFramework's custom controller expects.

- **Days 1 and 2, contracts.** The `Event` model, the `DeviceProfile` model with its input-mode preference list (non-empty, no duplicates), and the five seams. Property tests with hypothesis pin the invariants: profiles reject empty input-mode lists; event sequence numbers and timestamps are monotonic across a stream. Because monotonicity is a property of a stream rather than of one model, it is checked by a sequence checker, and the supervisor is its writer (C4).
- **Days 3 and 4, registry.** The pyudev listener lands behind `DeviceEvent` and is tested against a fake udev feed so CI never needs hardware. The device profile store arrives here too.
- **Day 5, the dual-client interface test.** The same recorded-frame corpus drives both the farm's fake InputBackend and a stub of MaaFramework's custom-controller callback shape. Half a day, no hardware, and it converts the week-five decision from architecture work into configuration.
- **Days 6 and 7, sim core and CI.** The virtual device attaches and detaches through the real registry path. ruff, mypy, import-linter and the purity test gate every commit, so contract drift is a build failure rather than a review comment.

One caution colors the whole week: **contracts must not grow beyond models and interfaces.** The moment they acquire a serial client, a udev listener or an HTTP server they stop being contracts and become the coupling they exist to prevent. This is enforced mechanically (section 4.3).

---

## 9. Risk Register and Mitigations

The register is the short list that survived the study. Each risk names its mitigation and the week that retires it. Rows R1 to R7 are renumbered from V1.0 (where the first row was labelled R2); R8 to R10 are new in V1.1 (C11).

| ID | Risk | Severity | Mitigation | Retired by | Owner |
|---|---|---|---|---|---|
| R1 | HID input rejected on no-ADB phones | High | Week-two real-hardware test against a no-ADB phone; touch-fw-2 digitizer firmware; Wi-Fi ADB fallback on dual-mode seats | W2 | TBD |
| R2 | MaaFramework probe fails the gate | Medium | Minimal vision path already scoped (ROI-restricted matching, imagehash settle); interfaces make either branch a configuration change | W5 to W6 | TBD |
| R3 | UVC frame freshness and exposure drift | Medium | Exposure locked at capture; buffer-one with latest-frame freshness contract; perceptual-hash settle check before every action | W3 | TBD |
| R4 | OCR accuracy varies across device models | Medium | MaaFramework brings its own OCR stack; scenarios prefer template anchors over free-text reading where possible | W5 to W6 | TBD |
| R5 | License contamination via GPL/AGPL code | High | Adoption checklist screens licenses on sight; GPL/AGPL repositories studied as reading material only, never imported; Maa isolated by process and by packaging | Continuous | TBD |
| R6 | Fifty-seat scaling surprises | Medium | Per-device worker processes; supervisor-held single-writer lease; W9 soak ramps ten toward fifty with contention measurements. The ramp should be split from the soak or a target below fifty stated with a follow-on sprint. | W9 | TBD |
| R7 | Closed-loop latency exceeds budget | Medium | Modular monolith avoids IPC hops on the loop path; settle-verify absorbs jitter; latency budget asserted in W3 exit criteria | W3, W9 | TBD |
| R8 | Hardware supply and USB topology at fifty seats (capture cards on hubs, bandwidth, driver variance across phone models) | Medium | Procurement lead time and hub topology planned before W2; bandwidth per hub measured in W3 | Before W2, W9 | TBD |
| R9 | Probe-corpus quality undermines the W5 decision | Medium | Corpus recorded from target phones from week one, labeled with expected recognitions, reviewed before W5 | W5 | TBD |
| R10 | ADB-only seats miss the latency budget (*proposed, C9*) | Medium | Measure screencap latency in W3; looser budget or lower cycle rate for ADB-only seats | W3 | TBD |

*Table 8. Risk register with retiring milestones. The owner column is new and still unassigned.*

---

## 10. Monday Morning: The First Moves

None of these requires permission, budget beyond pocket-change hardware, or more than one engineer.

- Order the week-two hardware now: one ESP32-S3 board, one UVC capture card, two test phones, one of which refuses ADB. Include hardware supply and hub topology in the plan (R8).
- Initialize the repository with the contracts skeleton and CI running ruff, mypy, lint-imports and pytest from the first commit.
- Port the proven `stop-esp32-s3-to-reboot` touch-fw-2 digitizer and its line protocol into the farm adapters behind the seams; read MaaFramework's custom-controller callback list. Those two documents are the shape of the week-five gate. See `docs/ARCHITECTURE.md` Appendix A.
- Start recording the probe corpus: representative screen footage from the target phones, labeled with expected recognitions, so week five has its replays ready (R9).

Success for the ten weeks is equally concrete: a tap injected through an ESP32 landing on a real phone in week two; an unattended overnight run in week four; a recorded adopt-or-reject decision on MaaFramework in week five; and fifty seats running the loop unattended, observed from the dashboard, by week ten. One rule carries the whole plan: **one backend, one device, one end-to-end action, before anything scales.**
