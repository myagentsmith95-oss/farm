# Serial protocol v1 — farm host ↔ ESP32-S3

**Status:** [proven] base commands from `stop-esp32-s3-to-reboot` @ `c29950e`
(`hil_touch_updated.ino`, `FW_NAME touch-fw-2`); [designed] hardening is listed at the end.
**Golden vectors:** `serial_vectors.json` — the same cases must pass on the Python
encoder and on the firmware. Hardware facts come from `docs/ARCHITECTURE.md` §§5–6.

## 1. Transport

- UART0 on the board, reached through the USB-serial bridge (`1a86`), **115200 baud**.
- The S3's native USB is the **phone-facing HID gadget** and is never a serial port here.
- One ASCII line per message, terminated by `\n`. `MAX_LINE = 96` characters; a longer
  line gets `ERR line too long`.
- **Strict lockstep:** one command in flight. The firmware blocks while executing and
  answers exactly once. Do not pipeline.
- Board log lines begin with `#` and are ignored by the host.

## 2. Command set (proven)

| Host → board | Board → host | Meaning |
|---|---|---|
| `PING` | `READY` | Handshake. Repeat until READY; also covers a board still booting. |
| `RES <w> <h>` | `OK` / `ERR bad resolution` | Declare the coordinate space, 1..65535 per axis. |
| `TAP <x> <y> [hold]` | `DONE` / `ERR ...` | hold defaults to 200 ms, valid 20..5000. |
| `SWIPE <x1> <y1> <x2> <y2> <ms>` | `DONE` / `ERR ...` | `ms` valid 16..10000. Straight line only. |

Board-initiated lines:

- `BOOT <name>` on **every** restart. An unexpected `BOOT` during a session means the
  board reset: re-handshake, re-send `RES`, and surface a health event. The host does
  **not** see a udev event — the serial bridge stays attached (architecture §3.2).

Error replies: `ERR bad resolution`, `ERR out of range`, `ERR usb send failed`,
`ERR unknown command`, `ERR line too long`.

## 3. Coordinates

`RES` declares the space that TAP/SWIPE coordinates live in. The proven flow sets it to
the **HDMI capture active-area crop size** (example: 494×1019 at offset (713,0)). The
firmware maps each coordinate into the digitizer's logical range with
`x · 32767 / screenW`, clamped to 0..32767, and Android auto-scales that to display
pixels. `RES 32767 32767` is a raw/identity mode, reserved for diagnostics.

The farm adapter converts contract coordinates (normalized 0–1) to crop pixels with
half-up rounding and clamping to `0..width` / `0..height`, then sends them unchanged.
There is no tap-grid calibration (architecture §8).

## 4. Timing (proven)

- TAP re-sends the contact roughly every 20 ms during the hold.
- SWIPE takes `steps = ms / 8` steps, one report per step at roughly 8 ms cadence,
  with up to 5 retries when the USB endpoint is busy. Values below 8 ms previously
  caused a divide-by-zero and chip reset; the protocol minimum is now 16 ms.
- Lift-off is always attempted hard (25 retries) so a finger is never left down.
- A prior bug fixed in the base is documented in the vectors; do not reintroduce it.

## 5. Opening the port without resetting the board

Dev boards use a two-transistor auto-reset circuit driven by DTR/RTS. The fatal state is
`DTR=0, RTS=1` (EN held low). The host must never pass through it:

1. OS-level pre-open with `O_RDWR|O_NOCTTY|O_NONBLOCK`; set `CLOCAL`, clear `HUPCL`; close.
2. Open with pyserial, `dsrdtr=False`.
3. Drop **RTS first, then DTR**.
4. Keep the port open for the whole session — one open means zero resets.
5. Drain stale input once when the session opens, **not** inside the handshake, so a
   READY already queued is not discarded.

Implemented as `open_esp32_no_reset()` in `farm.adapters.esp32_serial`.

## 6. Golden vectors and the Python side

`serial_vectors.json` carries 26 cases: handshake, `RES` boundaries, TAP/SWIPE boundary
coordinates and min/max durations, invalid inputs, the unknown-command and line-too-long
errors, and the boot banner. Each case has a structured `command`, the exact `host` line,
and the expected `board` reply, so the encoder and the firmware can be checked against
the same data.

Python implementation: `farm.adapters.esp32_serial` (`encode_command`, `decode_reply`,
`Esp32SerialBackend`). Tests drive a fake serial, so no hardware is needed. `perform()`
blocks until `DONE`, as required by the InputBackend seam (N4). Only Tap and Swipe are
supported until composite firmware lands; Key and Text raise `UnsupportedAction`.
The adapter also runs the reusable `InputBackendContract` suite.

The third leg — the real firmware — is checked by `tools/run_golden_vectors.py`. It
opens a board without resetting it (`open_esp32_no_reset`), handshakes with PING, and
sends all 26 vector lines, comparing each reply verbatim. Before a case it re-declares
`RES` whenever the required coordinate space differs from the current one; this is
essential after `RES 65535 65535` succeeds, or the out-of-range TAP/SWIPE cases would
pass for the wrong reason. A `BOOT` banner during the run fails that case and every
case after it. Run: `.venv/bin/python tools/run_golden_vectors.py --serial 5C63001367`.
Verified 26/26 on both seats on 22 November 2026.

Host-side hardening (all covered by tests):

- The deadline for one command is `timeout_s + gesture duration` — a 10 s swipe must not
  be declared failed while the board is still moving. A late reply would otherwise be
  consumed by the next command and report a false success.
- Swipe duration is validated host-side to 16..10000 ms, matching the firmware.
- `handshake()` re-PINGs every 0.5 s until READY; one PING is not enough for a cold boot.
- `sync_resolution(w, h)` updates the adapter's coordinate size, so rotation and re-crop
  convert subsequent actions with the size the board was actually told about.
- On a timeout the port is drained and `needs_rehandshake` is set; `perform()` then
  refuses further work until `recover()` drains, re-handshakes and re-sends `RES` (the
  firmware resets its coordinate space on restart). An unexpected `BOOT` does the same.
- Inbound bytes are accumulated until LF, so a partial pyserial read cannot split a
  `DONE` reply into fragments. A bare `ERR` is classified as an error, not ignored.

The backend assumes a single caller; the supervisor must not drive one port from
multiple threads. Normalized 1.0 maps to the crop size (one past the last pixel index),
which the firmware clamps — harmless by design.

## 7. Planned hardening [designed — not in the base]

- Heartbeat and watchdog release (architecture §5): 500 ms host heartbeat, 1500 ms
  timeout, release contacts on loss.
- `STOP` to cancel mid-action, action ids with dedup, explicit `BUSY`.
- Firmware/protocol version in the `BOOT`/`READY` banner (settles O6).
- New commands: `PATH`, `KEY`, `TEXT`, consumer `HOME`/`BACK`, optional `PINCH`.
- `docs/ARCHITECTURE.md` §15 acceptance checklist on a no-ADB phone.
