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

## Next after `RESULT: OK`

Run the 26 golden vectors against board `5C63001367`, then the no-ADB acceptance
checklist in `ARCHITECTURE.md` §15.
