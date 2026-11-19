"""CI guard: no tracked file may be a zero-byte placeholder.

The scaffold reserved protocol/, adoption/ and services/ paths as empty files
and tagged them "settled" in the memo. That let a reader believe specifications
existed when they did not. Reserve directories with .gitkeep instead, and write
the real file in the week that owns it.
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKERS = frozenset({".gitkeep", "__init__.py"})


def test_no_empty_tracked_files():
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8").split("\0")
    empty = sorted(
        name
        for name in tracked
        if name
        and Path(name).name not in MARKERS
        and (ROOT / name).is_file()
        and (ROOT / name).stat().st_size == 0
    )
    assert empty == [], f"empty tracked files (use .gitkeep instead): {empty}"
