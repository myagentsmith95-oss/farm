# Hardware diagnostics runbook

Commands and fixes from bringing the two-seat test stand up. Keep this next to
`ARCHITECTURE.md`; the hardware facts live there, the operational fixes live here.

## Essential commands

```bash
# One authoritative check: boards, cards, signal, crop, topology changes.
cd /home/agent-smith/Documents/farm && .venv/bin/python tools/diagnose_topology.py

# Same, with a baseline snapshot (created on first run, compared on later runs).
cd /home/agent-smith/Documents/farm && .venv/bin/python tools/diagnose_topology.py --snapshot /tmp/topology.json

# Deliberately reset any board that does not answer PING, then re-PING and re-send RES.
cd /home/agent-smith/Documents/farm && .venv/bin/python tools/diagnose_topology.py --recover --resolution 494 1019

# Prove both boards' HID gadgets reach a phone: swipe up then swipe down on each.
cd /home/agent-smith/Documents/farm && .venv/bin/python tools/diagnose_topology.py --check-hid --resolution 494 1019

# Live HDMI preview, one card at a time.
ffplay -f v4l2 -input_format mjpeg -video_size 1920x1080 -i /dev/video0
ffplay -f v4l2 -input_format mjpeg -video_size 1920x1080 -i /dev/video4

# Both streams at once (two windows; the shell waits for both to close).
ffplay -f v4l2 -input_format mjpeg -video_size 1920x1080 -i /dev/video0 & ffplay -f v4l2 -input_format mjpeg -video_size 1920x1080 -i /dev/video4 & wait

# Single-shot frame from a card.
ffmpeg -hide_banner -loglevel error -f v4l2 -input_format mjpeg -video_size 1920x1080 -i /dev/video0 -frames:v 1 -y /tmp/card.jpg

# Individual probes.
cd /home/agent-smith/Documents/farm && .venv/bin/python tools/probe_esp32.py
cd /home/agent-smith/Documents/farm && .venv/bin/python tools/probe_capture.py

# Three screenshots per paired device: shade closed → open → closed.
cd /home/agent-smith/Documents/farm && .venv/bin/python tools/capture_evidence.py --evidence evidence --resolution 494 1019 --settle 1.0 --between 0.8 --drain 5
# Override the board↔card pairing if the wiring changed:
cd /home/agent-smith/Documents/farm && .venv/bin/python tools/capture_evidence.py --map 5C63001367=<card-by-path> --map 5C63002523=<card-by-path>
# Or capture evidence from inside the full diagnostic:
cd /home/agent-smith/Documents/farm && .venv/bin/python tools/diagnose_topology.py --evidence var/evidence --resolution 494 1019
```

`diagnose_topology.py` exits 0 only when every discovered board answers READY and
every discovered card has a stable active-area crop. With `--snapshot`, a previously
known device that disappears makes it exit 1; the baseline is not overwritten while
something is missing, so the failure stays visible until acknowledged. `--check-hid`
is opt-in because it injects a 500 ms swipe up then a 500 ms swipe down per board;
`DONE` for both means the HID gadget reaches a phone, `ERR usb send failed` means it
does not. The vertical pair also exercises movement and can wake a sleeping screen —
it brought the second seat back to ACTIVE during bring-up. `--recover` resets a
hung board and re-sends `RES` when `--resolution` is supplied — without it the caller
must re-sync the coordinate space before injecting touch.

## Symptom → cause → fix

| Symptom | Cause | Fix |
|---|---|---|
| Card shows **colour bars** | No HDMI source at all | Check that phone is on, unlocked, mirroring; check cable and hub port |
| Card shows **solid black** | HDMI linked but phone screen off/locked | Wake/unlock; enable stay-awake (D-4 means no power control) |
| `cannot open /dev/videoN`, OpenCV warning `backend is generally available but can't be used to capture by name` | Another process holds the card (ffplay or a probe) | Close the other process, e.g. `pkill -f 'ffplay -f v4l2'`, then retry |
| Card appears after ~4 s of bars and ~2 s of black | Normal HDMI lock delay | Already handled: `refresh()` retries up to 20 s |
| Crop differs by a few pixels between runs | Normal jitter | Already handled: coverage-based detection + `stable_area()` |
| Board answers **no PING at all** but its USB bridge exists | Firmware hang (observed on `5C63002523`) | Run `diagnose_topology.py --recover`, or power-cycle the board. It then prints `BOOT touch-fw-2` and answers READY |
| Unexpected `BOOT` banner during a session | Board reset | Re-handshake and re-send `RES`; firmware resets its coordinate space |
| `ttyACM0` / `ttyACM1` swapped after replug | Kernel numbering is not stable | Always use `/dev/serial/by-id/...` from discovery |
| by-path changed (`usb-0:1.3.1.1` → `.2` etc.) | Card moved to another physical port | Fix the cabling; use `--snapshot` to see added/removed ids |
| `ERR usb send failed` on TAP | Board's HID gadget not attached to a phone | Check the phone-side USB connection, not the host serial |
| Two capture cards failing together | Shared host controller / hub bandwidth (R8) | Put each card on its own USB controller and use powered hubs; both cards currently work simultaneously after external hub power |

## Hard-won rules

- Never open the ESP32 serial port with default pyserial settings — DTR/RTS can
  reset the chip and detach its HID gadget from the phone. Use `open_esp32_no_reset()`.
- A **deliberate** reset is acceptable only as explicit recovery (`--recover`),
  never during normal session startup.
- Never hardcode `/dev/videoN`; on this host `/dev/video2` is the webcam. Use
  by-path discovery, which also skips metadata nodes.
- Do not run ffplay and a probe on the same card at once — one V4L2 node allows
  one opener.
- The second card was unstable until its USB hubs got external power; after that
  both cards streamed simultaneously without conflict. Concurrent capture was
  **not** the cause of the colour bars.

## Screenshot evidence

`tools/capture_evidence.py` writes a timestamped folder under `evidence/`
(gitignored). Each **device** — one ESP32 board paired with one capture
card — gets one folder containing the three states in sequence:

```
evidence/<timestamp>/
  README.txt, manifest.json
  device-<board-serial>--card-<vendor>-<product>-<usb-port>/
    01-current.jpg
    02-after-swipe-1.jpg
    03-after-swipe-2.jpg
```

### Why this layout

The earlier version scattered screenshots across `before/`, `up/` and `down/`
folders and captured every card for every board. That made it hard to answer the
simple question: "what did this one phone screen do when I swiped its board?"
The device folder keeps the complete before/after/after sequence together, with
file names that say exactly which moment they show.

Folder names use stable hardware identities, never `/dev/videoN` — those numbers
swap between cards after a replug. The board serial comes from by-id, the card
part comes from vendor:product + by-path, so a moved card gets a different folder
and the change is visible.

### How the pairing is decided

Frame differencing was tried first and rejected: during bring-up one board's
swipe produced a 50.15 mean grey change on a card, while another board produced
0.00 on both — a swipe can legitimately change nothing visible, so a diff is not
an authority. The pairing is therefore **explicit**, taken from the experiments
repo `hil-rig/devices/rig-*.yaml`:

```
5C63001367 -> pci-0000:0a:00.0-usb-0:2:1.0   (/dev/video0)
5C63002523 -> pci-0000:00:1d.0-usb-0:1.3.1.1:1.0  (/dev/video4)
```

These are the tool defaults. `--map SERIAL=CARD_KEY` overrides them when the
wiring changes; `CARD_KEY` can be a full by-path/by-id or a unique fragment.
`README.txt` and `manifest.json` record the mapping actually used. `--keep N`
(default 5) prunes old runs.

### Idea behind the code

The frame writer depends only on the `Frame` contract (`Frame.data`) and the
swipes use the canonical `Swipe` model. When the ADB path is built later, an ADB
`CaptureSource` and `InputBackend` plug into the same runner — the folder layout,
naming and three-state sequence do not change. Only the source/binding code is
new, exactly as the LGPL and seam decisions require.

### Why the three frames were identical, and the fix

Two causes were found, both in the capture path, not in HID:

1. OpenCV buffers frames. `read()` could return an image captured **before**
   the swipe, so all three screenshots were byte-identical. `refresh()` now
   discards `drain - 1` stale frames before storing the newest one; `--drain`
   defaults to 3 and 5 works well on this host.
2. The starting screen may not be what the previous run left. The sequence now
   begins with a mid-screen swipe, then reverses it, then repeats it. On this
   launcher that pair toggles the **app drawer**, so the frames are home screen →
   app drawer → home screen. This is *not* the notification shade — that needs a
   swipe from the top edge (y≈30→900) and was a separate live test.

Verified live: the app-drawer frame differs from the home-screen frames by
about 67 (board `5C63001367`) and 61 (board `5C63002523`) mean grey levels.

### Key ideas, findings and traps

This was a long debugging session. The traps were mostly about *false signals* —
measurements that looked like answers but were not.

| Trap | What it looked like | What was actually true |
|---|---|---|
| `DONE` from firmware means the phone acted | Every swipe returned `DONE`, so the evidence should show a change | `DONE` only means the ESP32 sent a HID report. The phone's reaction is a separate fact and must be observed on the screen |
| Identical screenshots mean the gesture failed | All three files byte-identical, so we tried new gestures, longer waits and `RES` sync | HID was working (a top-edge swipe visibly pulled down the notification shade; the evidence pair toggles the app drawer). OpenCV's `read()` was returning a frame buffered *before* the swipe |
| Waiting longer fixes stale frames | 1–2 s waits made no difference | The buffer still held old frames. The fix was to *discard* `drain - 1` frames, not to wait more |
| A fresh capture per screenshot is cleaner | Each state opened a new `UvcCaptureSource`; timing was hidden inside `start()` (2 s settle + 15 warm-up frames) | Re-opening made timing uncontrolled. One source stays open per device; explicit `settle`/`between` waits govern the sequence |
| The first frame is a neutral baseline | `01-current.jpg` could show whatever the previous run left on screen | The sequence must establish a known state: first swipe, reverse, repeat — and the writer must not *name* the state without looking at the image |
| Frame diff can pair boards with cards | A 50.15 diff on one card suggested a pairing; 0.00 on both suggested none | A swipe can legitimately produce no visible change. Pairing is explicit from `hil-rig/devices/rig-*.yaml`, not inferred from pixels |
| `/dev/videoN` identifies a card | The experiments hardcoded `/dev/video2` | On this host `/dev/video2` is the webcam; the card was `/dev/video0`. Nodes swap after replug. Use by-path/by-id identities |
| Two capture cards cannot run together | One card failed to open while another tool held the device | Concurrent capture works; the failure was a busy V4L2 node (ffplay). One opener per node, plus external hub power |
| A visual glance is enough to compare frames | Frames "looked the same" | Compare SHA-256 hashes and mean grey difference. Identical hashes prove the capture is stale, not that the UI is static |
| A large diff identifies the UI element that changed | A 67-level diff was labelled "notification shade" | The images showed home screen → app drawer → home screen. A diff proves *something* changed, not *what*. Always open the frame before naming the state |

Key ideas that came out of it:

1. **Separate the three claims**: report sent (`DONE`), phone reacted (watch it), frame captured (hash/diff). Never infer one from another.
2. **A V4L2 capture source is a buffer, not a snapshot.** `VideoCapture.read()`
   can return an older buffered frame, so drain stale frames before storing one.
3. **Establish initial state before evidence.** "Current" must mean a defined state, not whatever was left behind.
4. **Use stable identifiers everywhere** — board serial and card by-path — in folder names, manifests and pairings.
5. **Keep contract-only code in the evidence path** so the future ADB screencap implementation is a drop-in, not a rewrite.

## Milestone tag: `w2-pipeline-ready`

The git tag `w2-pipeline-ready` marks this verified state of the test stand:

- contracts, registry, serial protocol v1, no-reset ESP32 adapter, stable
  hardware discovery, UVC capture adapter and fake-serial tests;
- `diagnose_topology.py` with expected-topology enforcement, `--recover`,
  `--check-hid` and `--evidence`;
- evidence capture with explicit board↔card pairing and three frames per device;
- 495 green tests, mypy strict, ruff, lint-imports and a clean repo audit;
- memo V1.37, change log through C61.

It is an annotated tag, so `git show w2-pipeline-ready` records why it exists.
To roll back to this exact state:

```bash
git fetch --tags
git checkout w2-pipeline-ready
```

That produces a detached HEAD. To work from it, create a branch:

```bash
git switch -c work-from-w2-pipeline w2-pipeline-ready
```

## Golden vectors against a real board

The 26 protocol cases are driven against the firmware by:

```bash
.venv/bin/python tools/run_golden_vectors.py --serial 5C63001367 --timeout 20
```

The runner opens the port with `open_esp32_no_reset()` (never toggles DTR/RTS),
re-PINGs until READY, then sends each host line from `protocol/serial_vectors.json`
and compares the board's reply verbatim. It re-sends `RES <w> <h>` whenever the case's
coordinate space differs from the current one — needed because `RES 65535 65535`
changes the space, which would otherwise make the out-of-range TAP/SWIPE cases pass
for the wrong reason. An unexpected `BOOT` fails that case and all later ones.

This is a protocol check, not a physical one: `DONE` still only means the HID report
was sent. Verified **26/26** on both `5C63001367` and `5C63002523` on 22 November 2026.

## Next after `RESULT: OK`

Golden vectors are done. The next step is the no-ADB acceptance checklist in
`ARCHITECTURE.md` §15, followed by the firmware extension (which needs a flashing
toolchain decision).
