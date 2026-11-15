"""Purity guard: farm.contracts may import only the stdlib, pydantic and itself.

This is an allowlist, so a dependency added later is rejected by default.
The self-tests prove the walker can fail, because against an empty
contracts/ the real check would otherwise pass vacuously.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "src" / "farm" / "contracts"
ALLOWED_THIRD_PARTY = frozenset({"pydantic"})


def _absolute_ok(module: str) -> bool:
    parts = module.split(".")
    if parts[0] in sys.stdlib_module_names or parts[0] in ALLOWED_THIRD_PARTY:
        return True
    return parts[:2] == ["farm", "contracts"]


def find_violations(root: Path) -> list[str]:
    violations: list[str] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        depth = len(rel.parts) - 1  # 0 for a file directly in root
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            where = f"{rel}:{getattr(node, 'lineno', '?')}"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if not _absolute_ok(alias.name):
                        violations.append(f"{where} imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # relative import: must stay inside root
                    if node.level > depth + 1:
                        violations.append(f"{where} relative import escapes contracts")
                elif not _absolute_ok(node.module or ""):
                    violations.append(f"{where} imports from {node.module}")
            elif isinstance(node, ast.Call):
                f = node.func
                name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", "")
                if name in {"__import__", "import_module"}:
                    violations.append(f"{where} dynamic import via {name}")
    return violations


def test_real_contracts_are_pure():
    assert CONTRACTS_DIR.is_dir()
    assert find_violations(CONTRACTS_DIR) == []


@pytest.mark.parametrize(
    "source",
    [
        "import serial",
        "import cv2",
        "from pyudev import Context",
        "from adbutils import AdbClient",
        "import farm.runner",
        "from farm.runner import Supervisor",
        "from farm import runner",
        "from .. import runner",
        "__import__('serial')",
        "import importlib\nimportlib.import_module('serial')",
    ],
)
def test_walker_flags_forbidden_imports(tmp_path: Path, source: str):
    (tmp_path / "bad.py").write_text(source, encoding="utf-8")
    assert find_violations(tmp_path) != []


@pytest.mark.parametrize(
    "source",
    [
        "from __future__ import annotations\nimport enum\nfrom pathlib import Path",
        "import typing",
        "from pydantic import BaseModel",
        "from farm.contracts.models import DeviceProfile",
        "from . import models",
        "from .models import DeviceProfile",
    ],
)
def test_walker_accepts_allowed_imports(tmp_path: Path, source: str):
    (tmp_path / "good.py").write_text(source, encoding="utf-8")
    assert find_violations(tmp_path) == []


def test_relative_import_depth_is_respected(tmp_path: Path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "ok.py").write_text("from .. import models", encoding="utf-8")
    (sub / "bad.py").write_text("from ... import runner", encoding="utf-8")
    found = find_violations(tmp_path)
    assert len(found) == 1 and "bad.py" in found[0]
