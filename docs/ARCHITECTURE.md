# Android Device Farm — Project Documentation

**Version:** 1.2 · November 22, 2026
**Baselines:** farm repo @ `main` (memo V1.33, 492 tests green) ·
experiments repo `stop-esp32-s3-to-reboot` @ `c29950e` (working hardware proof)
**Status as of:** 22 November 2026 — fix tasks 1–12 and the first W2 serial slice are
complete (see the memo change log, C25–C57). The farm baseline is stated by memo version
and test count because a git hash goes stale on every merge; the experiments hash anchors
the hardware facts in §§3–8, which were **not** changed by this status refresh.
**Status labels used everywhere:** [proven] = runs on real hardware in experiments ·
[built] = implemented and CI-tested in the farm repo · [designed] = specified, not built ·
[unverified] = needs a hardware or measurement check.

This document supersedes the misleading parts of memo V1.11. Every correction is listed in §12.

---

## 1. Purpose

Automate interaction with **50 physical Android phones**, unattended, overnight.
Each seat runs a closed loop: **capture a frame → recognize the screen → choose an
action → inject it → verify the result**. A lease enforces one writer per device.

Two seat classes:
- **Standard seat** — root-free touch via an ESP32-S3 USB HID digitizer; screen observed
  via HDMI mirror into a UVC capture card. Works on phones that refuse ADB.
- **ADB-only seat** — ADB input + ADB screencap, for phones without video out or HID support.

The signature capability is the standard seat: **no root, no ADB, no app installed on the
phone**. The phone only sees a USB touchscreen and mirrors its own screen to HDMI.

## 2. Key ideas

1. **Contracts first.** Five seams (InputBackend, CaptureSource, LeaseManager,
   DeviceEventSource, Matcher/OcrEngine/SettleChecker) live in `farm.contracts` before any
   adapter exists. Models + interfaces only; stdlib + pydantic only, AST-enforced.
2. **Hybrid reuse.** MaaFramework (LGPL) is the recognition engine behind a week-5
   adopt/reject gate. Fourteen permissive commodity libraries sit behind adapters. Five
   custom cores carry the farm's topology: input control, registry, runner, capture
   routing, console wiring.
3. **Modular monolith, per-device workers.** One deployable. The 300–500 ms loop budget
   [unverified] forbids network hops on the loop path. Process boundaries give failure
   containment and the LGPL separation.
4. **Single writer.** The supervisor owns the event log (gapless seq, monotonic ts) and
   all leases. Workers propose; the supervisor records. Dashboards are views, never writers.
5. **Normalized coordinates.** Everything above the seams speaks 0–1. Each backend owns
   its conversion. Timestamps are host `monotonic_ns`.
6. **Capability-gated backends.** A backend declares `supports(action)`. Unsupported
   actions raise `UnsupportedAction` — never a silent no-op. The shared action vocabulary
   is a superset; no backend promises every capability.
7. **Fake universe + reusable contract suites.** Every seam has a contract suite run
   against its fake today and its real adapter later (C17), so a fake cannot drift from
   reality unnoticed. A SimDevice drives the production registry in CI.
8. **Mechanical discipline.** Test-first (red → green → memo row). Four CI gates (ruff,
   mypy, import-linter, pytest) plus a repo audit script. The decision memo is the living
   baseline; every change is a commit with a reason.
9. **One backend, one device, one end-to-end action — before anything scales.**

## 3. Seat classes & hardware topology [proven, one seat]

### 3.1 Standard seat wiring

```
                FARM HOST (Linux)
                 │ USB                │ USB
                 ▼                    ▼
        ┌────────────────┐   ┌──────────────────┐
        │ UVC capture    │   │ ESP32-S3 board   │
        │ card           │   │  UART0 ◄── USB-serial bridge (WCH 1a86,
        └───────▲────────┘   │            has real serial → /dev/serial/by-id/…)
                │ HDMI       │  native USB (TinyUSB, device mode)
                │            └──────────┬───────┘
        ┌───────┴───────────────────────▼───────┐
        │  USB-C HUB — own power supply          │
        │  HDMI out  +  downstream USB-A ports   │
        └───────────────────▲───────────────────┘
                            │ USB-C (phone is host; DP-alt-mode video out)
                       ┌────┴─────┐
                       │  PHONE   │  on, unlocked, mirroring
                       └──────────┘
```

Confirmed decisions:
- **Host ↔ ESP32 control channel: USB**, via the board's USB-serial bridge chip to
  UART0, 115200 baud. The S3's native USB is reserved for the phone. "USB CDC On Boot"
  is disabled in firmware build settings.
- **Phone port: a self-powered HDMI hub with USB.** The phone does DP-alt-mode video out
  and USB-host simultaneously through the hub. The ESP32 plugs into a hub USB-A port.
- **Power: everything external.** Hub has its own supply. Boards are externally powered.
  Nothing draws from the phone's OTG budget.

### 3.2 Two USB worlds (important)

- The **farm host** sees: the capture card (UVC) and the ESP32's **UART bridge** (1a86).
  These are the devices udev reports and the registry enrolls.
- The **phone** sees: the ESP32's **HID digitizer gadget**. The host never sees this in udev.
- Consequence: a firmware crash does **not** produce a udev event (the bridge stays
  attached). Board health is monitored over the protocol (`BOOT` banner, `PING`), not udev.
- Consequence: the phone itself is invisible to the host on a standard seat. The seat
  model needs only HID_BOARD + CAPTURE_CARD — which is exactly what `MODE_ROLES` says (C28).

### 3.3 ADB

- The phone's USB-C port is occupied by the hub. **Wired ADB is impossible on a standard
  seat.** Dual-mode seats use **ADB over Wi-Fi** (pair once) as the fallback path.
- No-ADB phones: HID only. This is the R1 acceptance case.
- ADB-only seats: phone cabled to the host directly; no hub, no board.

### 3.4 Per-seat BOM (standard)

| Item | Notes |
|---|---|
| Android phone | video-out over USB-C DP-alt-mode; on, unlocked, mirroring |
| USB-C hub, self-powered | HDMI out + ≥1 USB-A downstream |
| HDMI cable → UVC capture card | MJPG 1080p into the host |
| ESP32-S3 dev board | two USB ports: native USB → hub; bridge USB → host |
| Power supplies | hub + board external |

At 50 seats: plan host USB topology and powered-hub bandwidth (R8). MJPG keeps each
1080p stream inside USB2 budget [unverified at scale]. `by-id` paths keep enrollment
stable across replugs [proven for the bridge].

## 4. Input subsystem: the ESP32-S3 digitizer

### 4.1 What it is [proven]

A **USB HID digitizer** — Usage Page 0x0D, Usage 0x04 (Touch Screen). The phone treats it
as an external touchscreen. Reports carry **absolute** contacts: tip switch, contact ID,
X/Y. The working descriptor:

- 2 finger slots (`MAX_FINGERS = 2`), contact-count-maximum feature report (ID 0x03).
- Touch report ID 0x02: per finger {tip 1 bit, pad 7 bits, contact ID 8 bits, X 16 bits,
  Y 16 bits}, then scan time (16 bits, 100 µs units) and contact count (8 bits).
- **Logical range 0–32767 per axis.**
- Android classifies it as a direct touch screen and **auto-scales** to display pixels:
  `displayX = (x − minX) · displayWidth / (maxX − minX + 1)`. No root, no `.idc`, no drivers.

### 4.2 What it is NOT

- Not a mouse/pointer. No cursor, no homing, no acceleration, no drift.
- Not a keyboard. **A pure digitizer injects no keys.** Keys/text need extra HID
  interfaces (composite firmware, §4.4).
- The old memo's "emulates a pointer" + L1 tap-grid calibration is **wrong** (§12).

### 4.3 Command catalog

**Tier 1 — touch (digitizer).**

| Command | Status | Notes |
|---|---|---|
| `TAP x y [hold_ms]` | **[proven]** | hold 20–5000 ms, default 200. Long-press = TAP with hold. |
| `SWIPE x1 y1 x2 y2 ms` | **[proven]** | ms 16–10000. Straight line, ~8 ms/report. |
| scroll | [proven, as swipe] | Touchscreen scrolling is a drag. Host-side alias. |
| double-tap | [designed] | two TAPs with a fixed gap; host-side macro. |
| path (multi-waypoint drag) | [designed] | firmware extension; one press/release. |
| pinch / zoom / rotate | [designed] | descriptor already declares 2 fingers; add a command when a scenario needs it. |

**Tier 2 — navigation as touch (host-side macros, no firmware work).**

| Macro | How |
|---|---|
| home / back / recents | tap the on-screen nav bar, or run the gesture (edge swipe). Coordinates enrolled per phone model. |

These work **today** with TAP/SWIPE. They are the fallback if consumer keys misbehave on a ROM.

**Tier 3 — keys & text (composite firmware extension) [designed].**

Add two HID interfaces to the same TinyUSB device: keyboard (page 0x07) and consumer
control (page 0x0C).

| Command | Interface | Status |
|---|---|---|
| `KEY ENTER` / `KEY DEL` (backspace) | keyboard 0x28 / 0x2A | [designed] |
| `TEXT "ascii"` | keyboard, US layout | [designed]; ASCII only, reject non-ASCII |
| `KEY HOME` / `KEY BACK` | consumer AC Home 0x223 / AC Back 0x224 | [designed]; verify per ROM in W2 |
| ESC, TAB, arrows | keyboard | optional, cheap once the keyboard exists |

**Removed by decision (Nov 22): POWER, VOLUME_UP/DOWN, MUTE, media keys.** No power or
volume control is needed. Screen stays on via the phone's stay-awake setting.

**APP_SWITCH (recents):** a HID path does exist — usage 0x1a2 maps to `KEY_APPSELECT`
(580) and then to Android keycode 187 on common keymaps — but the mapping is
kernel/keymap-version dependent and is **not relied on**. The farm uses a Tier-2 touch
macro, or ADB keycode 187 where ADB exists. Never a HID `KEY` in the farm's own firmware
extension.

### 4.4 Canonical KeyCode (farm contracts)

| KeyCode | HID path | Android keycode | HID backend `supports()` |
|---|---|---|---|
| HOME | consumer 0x223 | 3 | True after composite firmware; else touch macro |
| BACK | consumer 0x224 | 4 | True after composite firmware; else touch macro |
| ENTER | keyboard 0x28 | 66 | True after composite firmware |
| DEL | keyboard 0x2A | 67 | True after composite firmware |
| APP_SWITCH | 0x1a2 exists but version-dependent, not relied on | 187 | False → touch macro or ADB |

Until composite firmware lands, the HID backend supports **Tap and Swipe only**;
`Key`/`Text` raise `UnsupportedAction`. The InputRouter falls back to ADB (Wi-Fi) on
dual-mode seats, or the scenario uses touch macros.

## 5. Serial protocol v1 — the proven base

Transport: UART0 over the USB-serial bridge, **115200 baud, one ASCII line per message,
`\n`-terminated**, max line 96 chars. Strict lockstep: one command in flight; the firmware
blocks while executing. Do not pipeline.

| Host → board | Reply | Semantics |
|---|---|---|
| `PING` | `READY` | handshake; also covers boot-in-progress |
| `RES <w> <h>` | `OK` | declares the coordinate space for TAP/SWIPE (1..65535) |
| `TAP <x> <y> [hold]` | `DONE` / `ERR <reason>` | hold default 200, range 20–5000 |
| `SWIPE <x1> <y1> <x2> <y2> <ms>` | `DONE` / `ERR <reason>` | ms 16–10000 |

Board-initiated lines: `BOOT <fw-name>` on **every** restart (an unexpected BOOT = reset);
`# …` log lines (ignore). Errors: `ERR bad resolution`, `ERR out of range`,
`ERR usb send failed`, `ERR unknown command`, `ERR line too long`.

**Coordinates:** integers in the RES-declared space. Firmware maps
`x · 32767 / screenW` (clamped). `RES 32767 32767` = identity/raw logical units.
The proven flow sets `RES` to the **capture active-area size** (§7), so host commands use
crop-pixel coordinates. The farm adapter converts normalized 0–1 → crop pixels. Keep this
proven approach; identity mode is an option later.

**Timing model [proven]:** TAP re-sends the contact every ~20 ms during hold; SWIPE takes
`ms/8` steps, one report per step (~8 ms cadence, 5 retries on a busy endpoint). Lift-off
is always attempted hard (25 retries) — **a finger is never left down**. Known bug already
fixed in the base: `ms < 8` caused divide-by-zero → chip reset; minimum is now 16.

**Planned hardening (W2, [designed] — not in the base):**
- Heartbeat + watchdog release (borrow the D3 reference's session ideas: 500 ms host
  heartbeat, 1500 ms timeout, release on loss).
- `STOP` (cancel mid-action, release contacts), action ids + dedup, explicit `BUSY`.
- Firmware/protocol version in the `BOOT`/`READY` banner (settles O6).
- New commands: `PATH`, `KEY`, `TEXT`, consumer HOME/BACK; optional `PINCH`.
- `protocol/serial_v1.md` + `serial_vectors.json`: golden vectors for every command,
  boundary coordinates, min/max durations, invalid inputs. Python encoder and firmware
  run the same vectors.

## 6. The no-reset serial discipline [proven — critical]

The repo's namesake. Dev boards have a 2-transistor auto-reset circuit on DTR/RTS:

| DTR | RTS | effect |
|---|---|---|
| 1 | 1 | nothing (Linux open default — safe) |
| 1 | 0 | GPIO0 low (harmless while running) |
| 0 | 1 | **EN low = chip RESET** |
| 0 | 0 | nothing |

Wrong order (DTR off first) passes through (0,1) and reboots the chip. A reboot detaches
the HID gadget from the phone mid-session.

**Rules for the farm adapter:**
1. Preferred: pre-open the port at OS level (`O_RDWR|O_NOCTTY|O_NONBLOCK`), set `CLOCAL`,
   clear `HUPCL`, close; then open via pyserial with `dsrdtr=False`; then drop **RTS first,
   DTR second**. (Both mitigations exist and work in the experiments.)
2. **Open the port once per session and keep it open.** Single open = zero resets, HID
   stays attached.
3. Treat any unexpected `BOOT` line as a board reset: re-handshake, re-send `RES`, and
   surface a health event. udev will not tell you (§3.2).
4. Identify the board by `/dev/serial/by-id/…` — never `ttyUSB0` (moves on replug).

## 7. Capture subsystem [proven, one seat]

Path: phone HDMI mirror → hub HDMI out → UVC card → host V4L2.

- **MJPG at 1920×1080 is mandatory** (raw YUYV at 1080p is a few fps). Set FOURCC MJPG.
- Signal lock: wait ~2 s, discard ~15 warm-up frames. On this host the card can then
  show color bars for ~4 s and black for ~2 s before the phone crop appears, so the
  adapter retries signal acquisition for up to 20 s (C51).
- **No-signal detection:** capture cards emit color bars/solid color without HDMI.
  Test: fraction of pixels with HSV saturation > 150 ≥ 0.35, and low column variance on a
  64×36 thumbnail. Working thresholds from the experiments.
- **Active-area detection (this is the real "L2"):** a portrait phone sits centered with
  black pillarboxes. Take the darkest 40×40 corner median as background; threshold = bg + 25
  luma; columns/rows whose mean exceeds it bound the screen. Reject if empty (screen
  off/locked) or wider than 60% of the frame (test pattern). Working example:
  **494×1019 at offset (713, 0)** inside 1920×1080.
- The crop is the vision input and the touch coordinate space (`RES` syncs them).
- Operational requirements: phone **on, unlocked, mirroring**. Keep it awake via settings
  (no power control by decision). Screen off ⇒ no active area ⇒ seat not usable.
- Freshness contract [built]: `Frame.captured_ns` is host arrival time; `latest(max_age_ms)`
  returns the newest fresh frame or raises `StaleFrame`. Caveat N5 stands: for ADB screencap,
  arrival ≠ content time; W3 must measure content-to-input latency (O4).
- ADB screencap as a second CaptureSource: [designed], latency unmeasured (C9/O4/R10).

## 8. Coordinate model, end to end

```
vision/Match/Action (normalized 0–1, contracts)
   │  adapter: × crop size
   ▼
serial TAP/SWIPE (integer crop pixels, RES = crop W×H)
   │  firmware: × 32767 / RES
   ▼
HID logical units (0–32767)
   │  Android: linear auto-scale to the display
   ▼
display pixels on the phone
```

Reverse for vision: capture frame → crop active area → normalize to 0–1.
Every stage is a fixed linear map. **There is no tap-grid calibration.** Alignment is:
detect the crop correctly + send the matching `RES`. Rotation/landscape changes the crop;
re-detect and re-`RES` (W2 verification item per phone model).

## 9. Host software: architecture & contracts [built]

### 9.1 Layout and enforced layering

`src/farm/` with import-linter layers (higher may import lower; siblings isolated):

```
testing → adapters → console → runner → (control | registry | vision)
        → calibration → capture → contracts
```

`app.py` is the composition root and the only importer of adapters. Each third-party
library lives in exactly one adapter module (`esp32_serial.py`, `uvc_cv2.py`, `adb.py`,
`udev.py`, `maa_client.py`, `http_ws.py`). Contracts purity is AST-guarded with self-tests.
Fakes live in `farm.testing`, above everything — production can never import them.

### 9.2 Contracts reference (key invariants)

| Module | Content | Invariants |
|---|---|---|
| actions | Tap, Swipe, Key, Text | coords 0–1, no NaN/inf, no device id, discriminated union |
| frame | Frame | monotonic captured_ns, source kind, encoded bytes |
| input | InputBackend | supports/perform/close; closed ⇒ InputError; unsupported ⇒ UnsupportedAction |
| capture | CaptureSource | latest never waits; fresh ⇔ age ≤ max_age_ms; CaptureError/StaleFrame |
| events | DeviceEvent + Source | by_id required, USB ids 4 lowercase hex; **coldplug**: synthetic ATTACHED for already-present devices before live events (C29) |
| seats | roles, SeatSpec/Table/State/Change | HID_BOARD/CAPTURE_CARD/PHONE; unique enrollment identifiers; `ready_modes` per mode (C26/C28) |
| lease | Lease + LeaseManager | one holder; acquire on held raises even for same holder; token per grant, unchanged by renew; valid while now < expiry; stale release ignored (C15) |
| event_log | Event + EventLog | seq gapless from 1, ts never decreases, single writer |
| matching | Matcher/Ocr/Settle | normalized regions; settle symmetric, in-process |

### 9.3 Registry (seat resolution) [built]

Resolves DeviceEvents against the enrollment table. Per-role claim sets; one event
matching several roles of one seat = **ambiguous claim** that contests those roles (C25).
Detach releases claims by identifier agreement, tolerating missing optional fields (C27).
Status (ABSENT/PARTIAL/READY/CONFLICT) is inventory completeness; **schedulers must consult
`ready_modes`**, not status. HID needs board + card; ADB needs phone (C28).

Enrollment example (real identifiers from the experiments):

```
seat-01: modes [hid]
  hid_board:    by_id = usb-1a86_USB_Single_Serial_5C63002523-if00
  capture_card: by_path = <host USB port>   # cards without serial; by_id synthesis decided in §14 / memo C32
```

### 9.4 Testing & process [built]

492 tests: property tests (hypothesis) pin model invariants; reusable contract suites per
seam with anti-vacuity guards; SimDevice drives the production registry through attach/
detach/coldplug in CI; dual-client test proves the farm seams and a Maa-shaped controller
speak the same verbs (shape only — see §12). CI: ruff, mypy, lint-imports, pytest.
`repo_audit.sh` checks files, placeholders, duplicates, memo version. Convention: red test →
green fix → memo row + audit update.

## 10. Designed, not built

- **Runner/supervisor:** per-device workers, SQLite queue, YAML scenarios, retries,
  timeouts, settle-verify loop. Lease authority in the supervisor. Lease-proxy pattern for
  workers (local expiry check, async renew) recommended; **worker↔supervisor IPC spec is
  missing from C7** — add `worker_ipc.md` before W4.
- **Vision:** minimal fallback matcher until the W5 Maa gate. SettleChecker (imagehash)
  stays in-process. Maa runs as a separate distribution (`services/maa_service`) — LGPL
  boundary by packaging, AST-guarded. The current Maa stub mirrors verb names only; the
  real API uses integer keycodes and pixel coordinates. W6 adapter owns conversions.
- **Console:** dashboard live view (MJPEG over WebSocket), manual control, REST. Views only.
- **Open design items:** event-log retention vs gapless-from-1 (N8), fencing-token
  durability across restart (N9), registry concurrency model (N10), enrollment persistence
  + single owner (N7).

## 11. Current state, verified defects, fix order

### 11.1 Maturity map

| Component | State |
|---|---|
| Contracts, registry, fakes, suites, gates | **[built]** 492 tests green @ main (memo V1.33) |
| Digitizer firmware (TAP/SWIPE, 2-finger descriptor) | **[proven]** one phone, screenshots saved |
| HDMI capture + active-area + RES alignment | **[proven]** one phone |
| No-reset serial discipline | **[proven]** |
| Composite keys/text, session hardening | [designed] |
| Serial v1 golden vectors + `esp32_serial` adapter | **[built]** protocol spec, 26 vectors, hardware-free tests |
| udev / uvc_cv2 discovery + capture adapters | **[built]** software only; hardware verification pending (Stage 1) |
| Runner, vision, console, calibration core | [designed] |
| No-ADB phone acceptance, rotation, 50-seat scale, latency budget | [unverified] |

### 11.2 Verified defects — all closed

Every defect below was reproduced at 43be1a6 and has since been fixed.

| Finding | Disposition |
|---|---|
| CR-1 no `SeatChange` on a `ready_modes` transition | PR #18 (memo C33) |
| CR-2 board-only HID enrollment | PR #17 (memo C31) |
| CR-3 id-only detach over-releases claims | PR #17 (memo C32) |
| CR-4 `is_valid` after renew unpinned | PR #23 (memo C38) |
| CR-5 vacuous coldplug suite / post-close push | PR #22 (memo C37) |
| CR-6 shallow-frozen models | PR #24 (memo C39) |
| CR-9 suite imports not reusable | PR #19 (memo C34) |
| N3/N4 free-form keys, no completion clause | PR #20 (memo C35) |
| F5 CI / mypy hardening | PR #25 (memo C40) |
| F6 hygiene | PR #25 (memo C41) |
| CR-8 / CR-7b negative `max_age`, non-atomic attach | PR #25 (memo C42) |

### 11.3 Execution order — completed

The audit order was executed as: tasks 1+2 (PRs #17/#18, memo V1.12/V1.13) → task 7
(#19) → task 8 (#20) → tasks 5, 4, 6 (#22/#23/#24) → task 3 (#17) → tasks 9, 10, 11
(#25) → task 12 (#21, memo V1.16). The baseline at the top of this document records the
final green state.

Still open: **Task 13** (composite firmware + golden vectors + W2 acceptance, memo O8),
the design items O10–O16, and the LICENSE decision O9. CR-10 is now defined and
deferred to W9 as a performance item — see the memo's open items.

## 12. Corrections to earlier documentation

| # | Old claim (memo V1.11 / reviews) | Corrected fact | Evidence |
|---|---|---|---|
| 1 | "ESP32 emulates a pointer" (§2.2, C10) | USB HID **digitizer**, absolute touch | working descriptor 0x0D/0x04 |
| 2 | L1 tap-grid + L2 active-area **calibration** | No tap grid. "Active area" = **HDMI pillarbox crop detection**; alignment = crop + `RES` sync | experiments README + code |
| 3 | D3 `esp32-android-agent` as firmware reference | Wrong HID layer (keyboard+mouse, per-phone pointer calibration). Real base = `stop-esp32-s3-to-reboot` touch-fw-2. Keep D3 only for session ideas (heartbeat/cancel/no-replay) | both firmwares read |
| 4 | Flat KeyCode list incl. POWER/VOLUME | Pure digitizer sends no keys. Tiered vocabulary; **power/volume removed by decision**; APP_SWITCH = touch macro/ADB (HID 0x1a2 exists but is version-dependent, not relied on) | §4 |
| 5 | "Serial protocol over CDC" (ambiguous) | **UART0 via USB-serial bridge**, 115200; native USB reserved for the phone; CDC-on-boot disabled | firmware header + by-id log |
| 6 | ADB as fallback on dual-mode seats | Phone USB is occupied by the hub → **Wi-Fi ADB** required | topology + reference docs |
| 7 | Dual-client test ⇒ Maa interchangeable | Verb **shape** only; real Maa API uses int keycodes/pixels; W6 adapter owns mapping | stub vs Maa API |
| 8 | Board presence via udev implies firmware health | Host sees the **bridge**, not the HID gadget. Health = BOOT/PING monitoring | §3.2 |
| 9 | HANDOFF "untracked on purpose", V1.8 baseline | Tracked and stale; memo is V1.11. Reviews v1/v3/v4 cited but not committed; EXPECTED missing 18 paths | audit |
| 10 | SimDevice capture-card USB ids 1d6b:0002 | That is a Linux root hub, not a UVC card (cosmetic) | USB ids |

## 13. Decisions log (November 22, 2026)

- D-1: Host ↔ ESP32 = USB (UART bridge). D-2: phone → self-powered HDMI hub with USB.
  D-3: all components externally powered.
- D-4: **No power and no volume control.** POWER/VOLUME/MUTE/media removed from scope.
- D-5: Firmware base = `stop-esp32-s3-to-reboot` (touch-fw-2), extended in place.
- D-6: Keep the proven wire protocol and RES = capture-crop approach for W2.
- D-7: KeyCode core = HOME, BACK, ENTER, DEL (composite firmware); APP_SWITCH via macro/ADB (HID 0x1a2 exists but is version-dependent, not relied on).

## 14. Open items & risks

| Item | Status |
|---|---|
| LICENSE for both repos | No LICENSE file by owner decision (22 Nov 2026); tracked as memo O9. |
| by_id synthesis rule for serial-less capture cards | Decided in memo C32: synthesized `vendor:product` + USB port path, owned by the udev adapter. |
| Nav-bar/gesture macro coordinates per phone model | enroll during W2 acceptance |
| Rotation / landscape crop handling | [unverified] per phone |
| No-ADB phone acceptance (R1) | pending hardware; tap+swipe already proven on one phone |
| Consumer HOME/BACK mapping per ROM | [unverified] — W2 checklist |
| Latency budget 300–500 ms; ADB screencap latency (O4) | [unverified] — W3 |
| Maa rubric (O1), W9 numeric criteria (O2), feature mapping (O3), corpus (O7) | open, unchanged |
| N5–N10 design items | tracked, see §10 |
| 50-seat USB bandwidth / hub topology (R8) | measure in W3/W9 |
| Coverage/allocation percentages (57/55/35) | planning estimates, not measurements |

## 15. Updated roadmap & acceptance

**Now:** fix tasks 1–12 are complete (§11.3). Next is task 13 / W2 hardware work.
**W2:** port the experiments into farm adapters behind the seams (`esp32_serial.py` with
the no-reset open + BOOT monitoring; `uvc_cv2.py` with MJPG + no-signal + active-area;
`udev.py` with coldplug enumeration). Extend firmware: composite keyboard + consumer
(HOME/BACK), heartbeat/STOP/dedup, version banner, PATH; golden vectors both sides.
Task 13 acceptance on the **no-ADB phone**:
- [ ] enumerates as a direct touch screen; tap lands correctly in all rotations
- [ ] HOME/BACK via consumer keys; ENTER/DEL/TEXT in a text field (English IME)
- [ ] recents via enrolled touch macro
- [ ] zero resets across a full session; BOOT recovery re-handshakes and re-RESes
- [ ] watchdog/STOP releases contacts mid-swipe; no stuck fingers
- [ ] all golden vectors green on Python and firmware
**W3:** capture loop in the farm + latency measurement (content-to-input for ADB seats).
**W4:** runner v1 + overnight run. **W5:** Maa gate. **W9:** scale soak.

---

## Appendix A — Experiment repo inventory (`stop-esp32-s3-to-reboot` @ c29950e)

| File | Purpose | Value for the farm |
|---|---|---|
| `hil_touch_updated.ino` | touch-fw-2: 2-finger digitizer + UART protocol | **the firmware base** |
| `esp32_closed_loop_test.py` | capture → active area → PING/RES → TAP/SWIPE → proof crops | adapter blueprint (RTS-first no-reset) |
| `test_pipeline.py` | same loop with the stronger CLOCAL/HUPCL pre-open no-reset | **preferred serial-open recipe** |
| `hil_shell.py` | interactive tap/swipe/snap shell | manual-control path prototype (W8) |
| `hdmi-stream-test.py` | live capture + active-area measure tool | calibration/diagnostics tool |
| `proof_1_tap_center.png`, `proof_2_swipe_up.png` | hardware evidence | W2 partial acceptance |
| `debug_active_area.png`, `debug_frame.png` | crop/no-signal diagnostics | keep as debug artifacts |
| `bybit-ws-subscriber/` (Go) | Bybit market-data WebSocket client | adjacent experiment; not part of the farm core |
| `hil-rig` | git submodule, contents not in this repo | resolve and review separately |

## Appendix B — Proven parameters (pin these in golden vectors)

| Parameter | Value |
|---|---|
| Serial | 115200 baud, `\n` lines, max 96 chars, lockstep |
| HID logical range | 0–32767 per axis; report ID 2 touch, 3 max-count feature |
| Fingers | 2 declared; commands use 1 today |
| TAP hold | default 200 ms; valid 20–5000 ms; ~20 ms report cadence during hold |
| SWIPE | valid 16–10000 ms; steps = ms/8; ~8 ms/report; 5 send retries |
| Lift-off | always attempted, 25 retries |
| RES | 1..65535; proven flow = capture crop size (e.g. 494×1019) |
| Capture | MJPG 1920×1080; ~2 s lock + 15 warm-up frames |
| No-signal | sat>150 fraction ≥ 0.35 + low column variance |
| Active area | corner-median bg + 25 luma; reject empty or >60% width |
| Boot | `BOOT touch-fw-2` banner; 3 s enumeration delay after USB.begin() |