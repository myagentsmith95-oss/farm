# Code Review v2 — `myagentsmith95-oss/farm`
## Architecture-informed pass: will these contracts survive W2 → W9?

**Commit:** `174d5e5` (main) · **Companion to:** `farm-code-review.md` (v1, correctness-against-contracts)
**Lens for this pass:** the project's own documented future — W2 real ESP32/ADB/pyudev adapters + InputRouter, W3 capture loop + latency measurement, W5 Maa gate, W7 supervisor + event log, W9 fifty-seat soak, the 300–500 ms loop budget, and the single-writer invariant.
**Method:** re-read the full decision memo (all 361 lines, incl. process model ch. 6, week plan ch. 7, risk register ch. 9) and every remaining test; ran new experiments to verify claims rather than infer them.

---

## 1. Updated verdict

v1 said "high quality, fix the gaps between what contracts promise and what they enforce." This pass **raises** my assessment of the foundations and **relocates** the risk. The code is not the worry — the worry is that several contracts are *complete for the fake universe they were built in* but *incomplete for the physical and process universe the memo commits to*. Every finding below is a place where the W1 scaffold will quietly mis-model reality at W2/W3/W7 unless the contract is amended first. None is a bug in delivered behavior; all are cheap to fix now and expensive to retrofit after adapters depend on them.

Two v1 impressions corrected by evidence:
- **The layering is better than I credited.** I verified by experiment that `control | registry | vision` siblings cannot import each other (a deliberate `registry → vision` probe broke `lint-imports`). Combined with `adapters` sitting *above* every production core, this mechanically forces two things the memo only promises: (a) `app.py` is the only production importer of adapters, and (b) the decision engine depends on vision *interfaces*, never implementations — which is exactly what makes the W5 adopt/reject a configuration change. My v1 nit questioning adapter placement is **withdrawn**; it is intentional and correct.
- **The contracts are already IPC-ready in the right way.** `Lease` and `Event` are frozen, serializable pydantic models, and every timestamp is host `monotonic_ns` — which on Linux is system-wide, hence comparable across the per-device worker processes. That is the precondition for the lease-proxy design recommended in N6.

---

## 2. New findings (N1–N10), ordered by when they bite

### N1 — W2-blocking · No coldplug/enumeration semantics: a restarted farm reports all 50 seats ABSENT
**Where:** `contracts/events.py` (module docstring + `DeviceEventSource`), `registry/seats.py` (`SeatRegistry` starts ABSENT, pinned by `test_registry_starts_all_seats_absent`), `testing/events.py`, `testing/sim_device.py`.

The seam models udev as a stream of *changes*: "attach and detach events from the udev layer." `SeatRegistry` constructs every seat ABSENT and only moves on events. But a real pyudev `Monitor` sees only **future** changes. On farm-host restart with all 50 phones already plugged in, no attach events fire, and the registry reports a fully-populated rack as 50 empty seats until someone replugs every device.

The fake universe hides this perfectly: `FakeDeviceEventSource` starts empty and `SimDevice` starts detached, so **the contract suite would pass for a real adapter that forgets coldplug enumeration** — the exact fake↔real drift C17 exists to prevent. The memo's W1 script says "pyudev listener," never "enumerate existing devices at start."

**Recommendation:**
- Add a clause to the `DeviceEventSource` contract: *a source must deliver synthetic `ATTACHED` events for every already-present matching device when iteration begins (coldplug), before any live change events.*
- Add a contract-suite test: rig pre-loads "already present" devices; the registry must reach READY with no *new* physical event.
- Give `SimDevice` (or the fake feed) an "already attached at construction" mode so the W1 demo can express the restart scenario.
- This interacts with v1-F4 (`by_id` required): serial-less capture cards discovered by coldplug have no `/dev/serial/by-id` entry, so the adapter must synthesize a stable id — decide the synthesis rule now, because it feeds `_Identity` and conflict detection.

### N2 — W2-blocking · `SeatStatus.READY` conflates "all enrolled hardware present" with "usable" — breaking the dual-mode fallback promise
**Where:** `contracts/seats.py` (`SeatStatus`, `_snapshot` in `registry/seats.py:90-113`), memo §2.1.

Confirmed repro: a seat enrolled `input_modes=[HID, ADB]` with HID board + phone + card; attach **only the phone**:

```
status: PARTIAL | present: {PHONE}
ADB mode needs only PHONE -> fully usable, yet status != READY
```

Memo §2.1 promises "the first usable entry is tried first and the other serves as fallback," and W2 delivers the InputRouter that applies this preference. But the obvious scheduling gate — `status == READY` — would **skip a seat that is perfectly usable via ADB** because its capture card is unplugged. `PARTIAL` conflates "degraded but usable" with "missing required hardware." The data to do it right exists (`present: frozenset[DeviceRole]` + the profile's modes), but the status vocabulary invites the wrong consumer logic, and nothing in the contract tells the W2/W4 scheduler which to use.

**Recommendation (decide before W2 scheduling):**
- Either document explicitly that scheduling must derive *usable modes* from `present ∩ role-requirements` per mode, and that `SeatStatus` is an inventory completeness signal, **not** a schedulability gate;
- Or enrich the model: per-mode readiness (e.g. `ready_modes: frozenset[InputMode]` on `SeatState`) so "usable via fallback" is expressible and testable.
- Add the dual-seat-phone-only regression test either way. This clusters with v1-F1 (one event filling two roles → false READY): both are about *what READY is allowed to mean*, and should be fixed together.

### N3 — W2 · No canonical key vocabulary: scenarios won't be portable across seat classes
**Where:** `contracts/actions.py` (`Key.code: str`, free-form), memo §2.1 ("everything above the seams is shared by both classes"), W2/W6.

`Key(code="HOME")` is an uninterpreted string. But the three backends speak different key languages: ESP32 HID needs **HID usage IDs**, ADB needs **Android keycodes** (`KEYCODE_HOME` / 3), and Maa's `press_key` takes an **int keycode**. With no contract-level vocabulary, each adapter invents its own mapping, and the W4 YAML scenarios embed backend-specific codes — silently breaking the promise that scenarios are shared across standard and ADB-only seats, and breaking the dual-client equivalence the whole W5 gate rests on (the stub currently records `press_key("HOME")` only because the test chose a friendly string).

**Recommendation:** add a canonical `KeyCode` StrEnum to contracts (HOME, BACK, APP_SWITCH, ENTER, DEL, POWER, VOLUME_UP/DOWN, … — the set the farm actually uses), keep adapter-owned mapping tables (HID usage ↔ Android keycode), and let the contract suite assert every backend either supports a canonical key or raises `UnsupportedAction`. This fits the purity rule (stdlib enum) and is far cheaper before W2 firmware + W6 Maa adapter than after.

### N4 — W2/W3 · `perform()` completion semantics undefined — matters for swipe, settle-verify, and the latency budget
**Where:** `contracts/input.py` (`perform` docstring: "Carry out the action"), W3 exit ("frame-to-tap round trip within budget"), W6/W7 settle-verify.

Does `perform(Swipe(..., duration_ms=250))` return when the gesture is **queued** or when it **finishes**? ADB `input swipe` blocks for the duration; an ESP32 HID backend may stream reports and return early. The contract doesn't say, so adapters will diverge, and the runner can't reason about when the screen is allowed to start changing. Consequences: (a) the settle checker may sample mid-gesture; (b) a 250 ms swipe silently consumes most of the 300–500 ms budget, and scenario authors have no contract-level way to know; (c) W3's round-trip measurement is ambiguous about what "to input" means.

**Recommendation:** one docstring sentence pinning it — e.g. *"`perform` blocks until the action is fully injected (for Swipe, until the gesture completes); backends that cannot block must document their completion semantics"* — plus a suite note. Decide deliberately; don't let two adapters pick opposite answers.

### N5 — W3 · `Frame.captured_ns` is arrival time, not content time — freshness understates ADB-screen age
**Where:** `contracts/frame.py` ("captured_ns comes from time.monotonic_ns() on the farm host, for every source"), C9/O4/R10.

Freshness is measured against host arrival. For UVC that's ~ms from the sensor — fine. For ADB screencap (tens–hundreds of ms, unmeasured per O4), a frame stamped at arrival looks **age 0** while depicting a screen that is already hundreds of ms old. The settle loop can then act on content that passes freshness but is stale, and W3's latency measurement will understate the true content-to-input latency unless it accounts for capture delay. This is the semantic trap behind R10 ("ADB-only seats miss the latency budget").

**Recommendation:** document `captured_ns` explicitly as *host arrival time*; state that per-source capture latency is a budget accounting concern (W3 must measure content-to-input, not arrival-to-input, for ADB seats). Optionally reserve an optional `source_latency_ms` hint for budget math. Documentation-level now; prevents a wrong W3 measurement later.

### N6 — W4/W7 · The lease-check IPC hop is unresolved, and the worker↔supervisor protocol has no spec home
**Where:** `contracts/lease.py` (synchronous in-process `LeaseManager`), memo C3/C4/C15, ch. 6, R7; `protocol/` (C7).

The memo commits to: supervisor holds leases and is the single event-log writer; **per-device worker processes** run the loop; workers send events to the supervisor **over IPC**; the InputRouter checks `is_valid` **before every `perform`**. If the InputRouter lives in the worker (core 1, `control` layer), then every action requires a cross-process `is_valid` call to the supervisor — an IPC hop on the latency path that R7's own mitigation ("modular monolith avoids IPC hops on the loop path") warns against. The `LeaseManager` Protocol as written is in-process-shaped and says nothing about locality.

The clean resolution is already supported by the contracts: because host `monotonic_ns` is shared across processes and `Lease` is a frozen serializable model, a worker can hold a **lease proxy** that caches the granted `Lease`, checks expiry **locally** (no IPC), renews asynchronously, and treats the supervisor as grant authority; fencing tokens make any stale grant detectable. `is_valid` becomes a pure local computation.

**Recommendation:**
- Add a note to the `LeaseManager` seam sanctioning the proxy pattern: *implementations may be local proxies over a remote grant authority; `is_valid` must be checkable without a round trip, against the host monotonic clock.*
- **C7 gap:** `protocol/` plans `serial_v1.md` (ESP32) and `maa_ipc.md` (Maa), but C4 *mandates* a third cross-process surface — worker↔supervisor (events + lease grants/renews) — with no spec home. Add `worker_ipc.md` to C7's scope before W4 runner v1.

### N7 — W2 · Two enrollment sources of truth, no persistence, no composition wiring
**Where:** `registry/profiles.py` (`ProfileStore`), `contracts/seats.py` (`SeatSpec` embeds `DeviceProfile` **by value**; `SeatTable`), `app.py` (empty).

`SeatRegistry` consumes a `SeatTable` and never touches `ProfileStore`; `SeatSpec` carries its own copy of the profile. So enrollment exists in two places that can drift (update a profile in the store → the table's copy is stale), and nothing joins them. W2's InputRouter needs *both* the profile's mode preference and the seat's presence — the composition root must join them, and `app.py` is still a docstring. Separately, everything is in-memory: a 50-seat farm's enrollment must survive restarts (the memo names SQLite for the W4 queue, but says nothing about enrollment persistence), and restart replay depends on N1's coldplug.

**Recommendation:** decide the single owner of enrollment (likely `ProfileStore`/a SQLite-backed store owns profiles + seat hardware config; `SeatTable` is a derived snapshot), wire it in `app.py` when the first adapter lands, and add a persistence + restart-replay story (reads enrollment from disk, coldplug from udev). Settle before W2 so the InputRouter composes against one truth.

### N8 — W7/W9 · Event-log retention is unspecified and interacts with the gapless-from-1 invariant
**Where:** `contracts/event_log.py` (`since`: "events with seq greater than the given one"; seq gapless from 1), `testing/event_log.py` (unbounded list).

Overnight soak at 50 seats (W9) generates millions of events; the fake grows without bound and the contract says nothing about retention or compaction. But compaction *conflicts* with the current `since` semantics: if old events are dropped, `since(old_seq)` can no longer return "everything after seq," and "gapless from 1" stops being true for the retained window.

**Recommendation:** decide retention before W7 — e.g. bounded window with `since` raising (or returning from earliest-retained) for seqs older than the window, and restate the gapless invariant as "gapless within the retained window." Cheap docstring + suite test now; avoids a contract break after the dashboard/API depend on `since`.

### N9 — W7 · Fencing-token durability across supervisor restart is unstated
**Where:** `testing/lease.py` (`_last_token` per device, in-memory), memo C15 ("token increases per grant").

A supervisor restart resets per-device token counters. Today this is **safe**: `is_valid` compares token *equality*, so pre-restart leases simply become invalid, and backends never see tokens. But C15's "increases per grant" reads as a global monotonic guarantee that a restart silently breaks — and any *future* ordering-based fencing (e.g. a backend or proxy comparing `token >`) would be unsafe across restarts.

**Recommendation:** one docstring sentence: tokens are monotonic *per supervisor lifetime*; equality-based validity is restart-safe; if ordering-based fencing is ever introduced, persist `last_token` (SQLite is already in play). Low effort, closes a latent invariant ambiguity.

### N10 — W2/W8 · Registry concurrency model is undocumented
**Where:** `registry/seats.py` (`apply` mutates `_occupancy`; `state`/`states` read it).

W2 adds a pyudev listener thread; W8 adds dashboard/API readers. `apply` mutating the occupancy dict while `state()` iterates it is a torn-read / `RuntimeError` risk. The memo's single-writer rule (C4) is about the *event log*, not the registry, so it doesn't cover this. The good news: `state()` already returns immutable snapshots — the right foundation.

**Recommendation:** document the registry's concurrency model (likely: confined to the supervisor or one dedicated thread; readers take snapshots) and add a lock around `apply`/`state` when the threaded adapter lands. Note it now so W2 doesn't assume thread-safety that isn't there.

---

## 3. v1 findings re-ranked in light of the roadmap

| v1 | Status now | Why |
|---|---|---|
| **F1** one event → two roles → false READY | **Elevate; cluster with N2** | Both define what READY may mean; fix the role/status model together before W2 scheduling. Add vendor/product to `DeviceMatch`. |
| **F4** contract gaps (`by_id` required, negative `max_age_ms`, `events()` lifecycle) | **Elevate; `by_id` clusters with N1** | Coldplug synthesis for serial-less cards needs the `by_id` rule decided first. |
| **F2** shallow-frozen models | Stands (Medium) | Matters more once enrollment persists (N7) and multiple readers exist (N10). Tuple fields. |
| **F3** event-log read-side mutation | Stands; cheap now | Becomes a real single-writer hazard at W7/W8 when dashboard/API consumers appear. Deep-copy in `since()`. |
| **F5** CI reproducibility / mypy strict (6 errors) | Stands | Do now. |
| **F6** LICENSE + README | Stands | Do now. |
| F7–F11 (SimDevice partial attach, typo kinds, snapshot overhead, Region eps, nits) | Stand (Low/Nit) | Opportunistic. |

---

## 4. Roadmap-aligned action list

| When | Actions |
|---|---|
| **Now (pre-W2)** | N1 coldplug clause + suite test + SimDevice mode; N2 readiness/fallback decision + test; N3 canonical `KeyCode`; N4 `perform` completion clause; F1+F4 `by_id`/vendor-product/role policy; F2 tuple fields; F5 mypy strict + CI hardening; F6 LICENSE/README |
| **W2** | N7 enrollment single-owner + persistence + `app.py` wiring; N10 registry concurrency model; F7 SimDevice atomic attach |
| **W3** | N5 arrival-vs-content freshness doc + measure content-to-input for ADB (ties R10/O4) |
| **W4** | N6 `worker_ipc.md` added to C7; lease-proxy seam note |
| **W7** | N8 retention semantics; N9 token-lifetime clause; F3 deep-copy `since()` |

---

## 5. Bottom line

The foundations are stronger than v1 concluded — the layering mechanically enforces the two properties (adapter isolation, vision-interface-only dependence) that make the whole contracts-first bet pay off, and the models are already shaped for cross-process use. The work is no longer "fix correctness gaps"; it is **finish the contracts for the universe the memo commits to**: coldplug (N1), fallback readiness (N2), a shared key language (N3), action completion (N4), lease locality + the missing worker IPC spec (N6), and one enrollment truth (N7). These are precisely the seams where W2 hardware and W7 processes will first touch the code, and every one is a docstring-plus-test change today versus a contract break after adapters depend on it. The project's own rule — *one backend, one device, one end-to-end action, before anything scales* — is best served by closing these before the first real tap in W2.
