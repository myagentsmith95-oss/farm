#!/usr/bin/env python3
"""Host probe: enumerate capture cards by by-path and report the phone crop.

Never uses a hardcoded /dev/videoN — on this host /dev/video2 is the webcam.
"""
import argparse

from farm.adapters.udev import enumerate_capture_cards
from farm.adapters.uvc_cv2 import UvcCaptureSource


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video-dev", help="explicit /dev/videoN (by-path is preferred)")
    parser.add_argument("--save", help="write the cropped frame as JPEG to this path")
    args = parser.parse_args()

    cards = enumerate_capture_cards()
    print(f"discovered {len(cards)} capture card(s)")
    for card in cards:
        print(f"  {card.video_dev}  by_id={card.by_id}  by_path={card.by_path}")

    targets = [args.video_dev] if args.video_dev else [card.video_dev for card in cards]
    for target in targets:
        print(f"\n== {target} ==")
        source = UvcCaptureSource(target)
        try:
            source.start()
            frame = source.refresh()
            print(f"  active area: {source.area}")
            print(f"  frame: {frame.width}x{frame.height}, {len(frame.data)} JPEG bytes")
            if args.save:
                with open(args.save, "wb") as handle:
                    handle.write(frame.data)
                print(f"  saved {args.save}")
        except Exception as exc:  # diagnostic tool: report and continue
            print(f"  ERROR {type(exc).__name__}: {exc}")
        finally:
            source.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
