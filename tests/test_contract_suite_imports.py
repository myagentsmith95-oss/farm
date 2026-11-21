"""Contract suites must be importable from anywhere, not just from pytest's cwd.

The W2 adapter tests will reuse these suites from other directories, so bare
`from events_suite import ...` imports (which rely on pytest's prepend mode)
are not enough. Package-qualified imports work in both prepend and importlib
collection modes.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_contract_test_dirs_are_packages():
    assert (ROOT / "tests" / "__init__.py").is_file()
    assert (ROOT / "tests" / "contracts" / "__init__.py").is_file()


def test_suite_imports_are_package_qualified():
    for path in sorted((ROOT / "tests" / "contracts").glob("test_fake_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.endswith("_suite")
            ):
                assert node.module.startswith("tests.contracts."), (
                    f"{path.name}: bare suite import {node.module!r}"
                )
