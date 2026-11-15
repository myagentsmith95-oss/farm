# Android Device Farm: Final Decision Summary & Implementation Plan

**Document:** DOC ADF-DEC-V1.1
**Supersedes:** ADF-DEC-V1.0 (Z.ai Engineering, November 2026; the PDF is the V1.0 snapshot)
**Revision date:** November 15, 2026
**Status:** living baseline. Every change is a git commit with a reason.

---

## Change log

Status tags used throughout: **[settled]** means decided and reflected in the repository; **[proposed]** means a design change pending working code; **[open]** means an unresolved item with an owner and a date still to be set.

| # | Change from V1.0 | Where | Status |
|---|---|---|---|
| C1 | Interfaces: five seams (InputBackend, CaptureSource, LeaseManager, DeviceEvent, Matcher/OcrEngine), not four. Matcher/OcrEngine is one seam holding two interfaces, so there are six interface types. | D4, ch. 4, Week 1 | settled |
| C2 | Contracts hold models and interfaces only (stdlib and pydantic). Fakes and the sim device move to `farm.testing`, outside the production import graph. | D4, ch. 4, ch. 8 | settled |
| C3 | Lease authority moves from the registry to the runner's supervisor. Core 2 becomes "Registry"; core 3 becomes "Runner, orchestration and lease authority". Five cores, same count; the same code changes package, so the custom share is unchanged. | ch. 4, Table 4 | settled |
| C4 | The single writer of the event stream is the supervisor. | ch. 6 | settled |
| C5 | MaaFramework ships as its own distribution (`services/maa_service`, separate venv), so the LGPL boundary is enforced by packaging, not only by process separation. | ch. 5 | settled |
| C6 | Dependency direction is enforced by import-linter; every third-party library is imported by exactly one adapter module. | ch. 4A | settled |
| C7 | The ESP32 wire protocol and the farm-to-Maa message surface are specified in `protocol/` with golden test vectors. | ch. 4A | settled (serial); Maa spec due W5 |
| C8 | Two seat classes: standard (ESP32 HID + UVC capture, most phones) and ADB-only (ADB control + screencap, a minority). Phones without video out are valid seats. | ch. 2 | proposed |
| C9 | `CaptureSource` gains a second implementation, ADB screencap, with a latency caveat against the 300 to 500 ms budget (unmeasured). | ch. 4, ch. 9 | proposed |
| C10 | Coordinates are normalized at the contract level; each backend owns its conversion to device units. | ch. 2, ch. 4 | proposed |
| C11 | Risk register renumbered R1 to R7 (V1.0 began at R2 with no R1). Three rows and an owner column added. | ch. 9 | settled |
| C12 | Reconciled the 57% coverage and 55% allocation figures, and stated the implied 10% commodity slice as two features. | ch. 3, ch. 4 | settled (wording); see O1 |
| C13 | Scope of the "roughly a third" custom share stated: host software only, firmware tracked separately. | ch. 4 | proposed |

**Open items carried forward**

| # | Item | Status |
|---|---|---|
| O1 | The itemised rubric behind MaaFramework's 3.30 / 5.00 prior score is not in the memo and must be attached, or the score removed. | open |
| O2 | Week-9 exit criteria must be stated in numbers (seat count, soak hours, lease-acquisition latency percentiles, a measurable bound on failure recovery). | open, before W9 |
| O3 | The feature-by-feature mapping behind the 55 / 10 / 35 split (which of the 20 features sit in which bucket) is not listed. | open |
| O4 | ADB-only seats: measure screencap latency in W3 and decide whether those seats get a looser budget or a lower cycle rate. | open, W3 |
| O5 | Share of ADB-only seats among the fifty, and whether they ever also get an ESP32 and capture card as a fallback. | open |

---

## 1. Executive Summary: The Agreed Decisions

This document closes the study phase of the Android Device Farm project. The question set was: which open-source repositories cover the farm's feature baseline, should the system be written from scratch or assembled from existing code, can that code be composed as microservices, and which module is built first. Every question has a defended answer. The verdict is a hybrid: one framework adopted behind a decision gate, fourteen commodity libraries sealed behind farm-owned interfaces, and five custom cores that carry the farm's differentiating topology. The ten-week plan in chapter 7 turns those answers into a build order.

| 7 | 14 | 5 | 10 |
|---|---|---|---|
| repositories evaluated | libraries adopted | custom cores to write | weeks, one engineer |

The decisions below are the baseline that any future change proposal must argue against.

**D1: Hybrid build-reuse strategy.** Neither from scratch nor deep reuse. MaaFramework (LGPL-3.0) is adopted as the recognition and pipeline engine, fourteen permissive commodity libraries cover plumbing, and roughly a third of the host software is written by hand because no repository covers the ESP32-HID + UVC-capture + fifty-seat topology.

**D2: MaaFramework behind a week-five gate.** It scored highest of the viable candidates (~57% feature coverage, active, 5.2k stars) but its vision and pipeline semantics must first pass a probe on recorded frames. The probe is cheap precisely because the interfaces exist before the integration code does.

**D3: esp32-android-agent as firmware reference.** The MIT-licensed ESP32 HID reference validates the riskiest hardware assumption, root-free input injection on phones without ADB, before any farm firmware is written.

**D4: Contracts first.** The first module is the contracts package: the `Event` and `DeviceProfile` models plus the five seams (InputBackend, CaptureSource, LeaseManager, DeviceEvent, Matcher/OcrEngine). Contracts contain models and interfaces only, with stdlib and pydantic as the sole imports. Fakes live in `farm.testing`. Everything else compiles against contracts; every adoption is sealed inside them. *(Changed in V1.1: C1, C2.)*

**D5: Modular monolith, not microservices.** The farm runs as one deployable with per-device worker processes. The closed control loop is latency-sensitive, frame transport across service boundaries is wasteful at fifty seats, and process isolation already delivers the failure containment and license separation microservices would buy (chapter 6).

**D6: Dual-client interface test on day five.** The same recorded-frame corpus drives both the farm's fake InputBackend and a stub of MaaFramework's custom-controller callbacks, converting the week-five adoption decision from an architecture change into a configuration change.

**D7: Vision stays minimal until the gate.** Custom template matching and OCR work before week five carries a live probability of being deleted by the probe. Vision is built last among the cores, smallest, and only far enough to close the calibration loop.

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
- A phone may support both backends. Its `DeviceProfile` then holds an ordered preference list; the first usable entry is tried first and the other serves as fallback. Only one backend is active at a time, and the lease enforces it.
- A manually operated seat is an operator concern (the dashboard's manual-control path, week 8), not a backend and not an entry in a preference list.

Everything above the seams is shared by both classes: vision (matching and OCR), scenarios, queue, retries, leases, the event log and the console.

### 2.2 Normalized coordinates *(proposed, C10)*

Scenarios, the decision engine and the runner express positions in normalized coordinates (0 to 1). Each `InputBackend` converts them to its own units. HID needs the L1 tap-grid and L2 active-area calibration, because the ESP32 emulates a pointer and where a tap lands depends on the phone's active area. ADB takes native pixels, so its conversion is a scale by screen width and height and needs no calibration. Calibration is therefore an HID-path concern, and ADB-only seats skip it.

### 2.3 The twenty-feature baseline

The baseline is the scoring yardstick used throughout the repository study, distilled from the high-level design description and the design review. Every coverage figure in chapter 3 is measured against it.

| Domain | Features in the baseline | Count |
|---|---|---|
| Input | ESP32-S3 HID backend (root-free); ADB backend; unified Action API; per-device input preference list | 4 |
| Capture | UVC / HDMI capture-card path; MJPG with buffer-one and latest-frame freshness; exposure lock | 3 |
| Vision | Template matching with ROI and threshold; OCR; perceptual-hash settle check | 3 |
| Automation | Decision engine with interrupt rules; declarative YAML scenarios; scheduler with queue, retry and timeout; settle-verify closed loop | 4 |
| Farm | Lease with single-writer rule; calibration mapping pixels to normalized coordinates; dashboard live view with manual control; REST API; WebSocket event stream; fifty-device scaling | 6 |

*Table 1. Sum check: 4 + 3 + 3 + 4 + 6 = 20.*

Two scope notes. First, the loop has a latency budget on the order of 300 to 500 milliseconds from frame to input; that budget drives the architecture decision in chapter 6. Second, live screen display in the dashboard is a consumer of the capture pipeline, never a second writer of device state, the same invariant that keeps the dashboard a view (D8).

---

## 3. Open-Source Landscape: Seven Repositories

Seven repositories were evaluated against the baseline. Each was scored on feature coverage with a 45% adoption threshold, then weighed on activity and health, license, architectural fit and replaceability. Coverage alone never decided anything: the highest-scoring candidate was rejected as a code donor, and one apparently healthy project turned out to be archived.

| Repository | Coverage | Stars | Status | License | Verdict |
|---|---|---|---|---|---|
| LmeSzinc / AzurLaneAutoScript | ~60% | 9.8k | Active | GPL-3.0 | Reference only: game-specific automation, GPL |
| MaaXYZ / MaaFramework | ~57% | 5.2k | Active | LGPL-3.0 | Adopt: vision, OCR and pipeline engine behind W5 gate |
| shenlan-ai / esp32-android-agent | ~52% | 34 | New project | MIT | Adopt as firmware reference for the HID path |
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
| Matcher / OcrEngine | MaaFramework, or OpenCV + imagehash | The week-five decision stops being a configuration change and becomes a migration |
| LeaseManager | Nothing: pure custom core | The single-writer invariant loses its single implementation point |

*Table 4. Five seams, six interface types (Matcher and OcrEngine are two interfaces in one seam). Interfaces exist before the libraries arrive, not after.*

`LeaseManager` is a seam in contracts; its implementation lives in the runner's supervisor (C3). The `Event` log model (sequence and timestamp) and the `DeviceEvent` seam (pyudev attach/detach) are different things and live in different contract modules.

**ADB screencap as a second CaptureSource *(proposed, C9)*.** ADB-only seats observe the screen through ADB screencap, which is generally slower and heavier than a UVC frame grab. Its latency has not been measured (O4). The frame type carries a capture timestamp and a source kind, so the freshness contract and settle checks can judge frames from either source, while vision stays identical.

### 4.2 The five custom cores

The custom third of the baseline is not leftover work; it is the product. Five cores carry it, and each is custom for the same reason: no existing repository implements this farm's seat topology.

| # | Custom core | What it owns and why it stays custom |
|---|---|---|
| 1 | Input control | The ESP32 serial protocol over CDC, the HID descriptors, and the InputRouter that applies each device's input-mode preference. Root-free HID injection is the farm's signature capability. |
| 2 | Registry | Device identity by by-id / by-path rules, seat resolution, inventory, enrollment, and the firmware and protocol versions recorded at handshake. It does not own leases. |
| 3 | Runner, orchestration and lease authority | The supervisor (single writer of the event stream and holder of the leases), per-device workers, the scenario interpreter, the queue, scheduling, retries and timeouts across fifty seats. Scheduling semantics are coupled to the lease and event model. |
| 4 | Capture routing and calibration | UVC seat routing, the freshness contract, tap-grid and active-area calibration turning pixels into normalized coordinates. |
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
- Calibration receives the `InputBackend` interface from contracts by injection and does not import control. Control checks leases through the `LeaseManager` interface from contracts, not through the runner.
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
| pyserial | Control: serial protocol v1 over CDC to the ESP32-S3 | PSF / BSD-style |
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
| W2 | Control on real hardware: serial protocol v1 over CDC with golden vectors; InputRouter with per-device input preference; firmware from the esp32-android-agent reference | pyserial, adbutils | First real tap through the ESP32 on a real phone; HID acceptance verified on a no-ADB phone |
| W3 | Capture closed loop: VideoCapture over UVC, MJPG, buffer-one, exposure locked; latest-frame slot with freshness contract; **measure ADB screencap latency (O4)** | opencv-python-headless | Frame-to-tap round trip on one device within the latency budget |
| W4 | Calibration L1 tap-grid and L2 active-area crop; runner v1 with SQLite queue; scenario interpreter v1; dashboard v0 as views on the event stream | PyYAML, FastAPI, Jinja2, uvicorn | First unattended overnight run on one device |
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
| R1 | HID input rejected on no-ADB phones | High | Week-two real-hardware test against a no-ADB phone; esp32-android-agent reference firmware; ADB fallback per device profile | W2 | TBD |
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
- Clone esp32-android-agent and MaaFramework; read the former's HID descriptors and the latter's custom-controller callback list. Those two documents are the shape of the week-five gate.
- Start recording the probe corpus: representative screen footage from the target phones, labeled with expected recognitions, so week five has its replays ready (R9).

Success for the ten weeks is equally concrete: a tap injected through an ESP32 landing on a real phone in week two; an unattended overnight run in week four; a recorded adopt-or-reject decision on MaaFramework in week five; and fifty seats running the loop unattended, observed from the dashboard, by week ten. One rule carries the whole plan: **one backend, one device, one end-to-end action, before anything scales.**
