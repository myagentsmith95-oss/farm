#!/usr/bin/env bash
# Read-only audit of the farm repository. Changes nothing.
# Run from the repo root with the venv active:  bash repo_audit.sh
set -u

[ -f pyproject.toml ] && [ -d src/farm ] || { echo "Run from the repo root."; exit 1; }

PASS=0; FAIL=0; WARN=0
ok()   { echo "  [ok]   $1"; PASS=$((PASS+1)); }
bad()  { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
warn() { echo "  [warn] $1"; WARN=$((WARN+1)); }

echo "== 1. Git state"
BRANCH=$(git branch --show-current)
echo "  branch: $BRANCH"
git fetch --prune --quiet 2>/dev/null && ok "fetched origin" || warn "could not fetch origin (offline?)"
if [ -z "$(git status --porcelain)" ]; then ok "working tree clean"; else bad "uncommitted or untracked changes:"; git status --short | sed 's/^/           /'; fi
if git rev-parse --verify --quiet origin/main >/dev/null; then
  AHEAD=$(git rev-list --count origin/main..HEAD 2>/dev/null)
  BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null)
  echo "  vs origin/main: ahead $AHEAD, behind $BEHIND"
  if [ "$BRANCH" = "main" ]; then
    [ "$AHEAD" = 0 ] && [ "$BEHIND" = 0 ] && ok "main matches origin/main" || bad "main differs from origin/main"
  fi
fi
echo "  local branches:"
git branch -vv | sed 's/^/           /'
GONE=$(git branch -vv | grep ': gone\]' || true)
[ -z "$GONE" ] && ok "no local branches tracking deleted remotes" || warn "branches whose remote is gone (safe to delete if merged): see list above"
UNMERGED=$(git branch -r --no-merged origin/main 2>/dev/null | grep -v HEAD || true)
if [ -z "$UNMERGED" ]; then ok "no remote branches waiting to merge"; else warn "remote branches not merged into main:"; echo "$UNMERGED" | sed 's/^/           /'; fi
echo "  recent history:"
git log --oneline -8 | sed 's/^/           /'

echo
echo "== 2. Expected files (present and tracked)"
EXPECTED="
pyproject.toml .importlinter .gitignore README.md .github/workflows/ci.yml
docs/decision-memo.md docs/ARCHITECTURE.md docs/HARDWARE_DIAGNOSTICS.md
protocol/serial_v1.md protocol/serial_vectors.json
src/farm/__init__.py src/farm/app.py
src/farm/contracts/__init__.py src/farm/contracts/models.py src/farm/contracts/actions.py
src/farm/contracts/frame.py src/farm/contracts/errors.py src/farm/contracts/input.py
src/farm/contracts/capture.py src/farm/contracts/matching.py src/farm/contracts/events.py
src/farm/contracts/lease.py src/farm/contracts/event_log.py src/farm/contracts/seats.py
src/farm/testing/__init__.py src/farm/testing/clock.py src/farm/testing/input.py
src/farm/testing/capture.py src/farm/testing/matching.py src/farm/testing/events.py
src/farm/testing/lease.py src/farm/testing/event_log.py src/farm/testing/maa_stub.py src/farm/testing/sim_device.py
src/farm/testing/fake_serial.py
src/farm/adapters/__init__.py src/farm/adapters/esp32_serial.py
src/farm/adapters/udev.py src/farm/adapters/uvc_cv2.py
src/farm/registry/__init__.py src/farm/registry/profiles.py src/farm/registry/seats.py src/farm/calibration/__init__.py
src/farm/capture/__init__.py src/farm/control/__init__.py src/farm/runner/__init__.py
src/farm/vision/__init__.py src/farm/console/__init__.py src/farm/console/views/__init__.py
tests/__init__.py tests/contracts/__init__.py tests/adapters/__init__.py
tests/adapters/test_esp32_serial.py
tests/adapters/test_udev_discovery.py tests/adapters/test_uvc_cv2.py
tests/tools/__init__.py tests/tools/test_diagnose_topology.py tests/tools/test_capture_evidence.py tests/tools/test_run_golden_vectors.py
tests/test_contracts_purity.py tests/d6_day5_dual_client_test.py tests/test_no_empty_placeholders.py
tests/test_contract_suite_imports.py
tests/properties/test_device_profile.py tests/properties/test_actions.py tests/properties/test_frame.py
tests/properties/test_matching_models.py tests/properties/test_events_lease_models.py
tests/properties/test_event_model.py tests/properties/test_event_stream_invariants.py
tests/properties/test_seat_models.py
tests/registry/test_profile_store.py tests/registry/test_seat_registry.py tests/registry/test_sim_core.py
tests/contracts/input_backend_suite.py tests/contracts/test_fake_input_backend.py
tests/contracts/capture_source_suite.py tests/contracts/test_fake_capture_source.py
tests/contracts/matching_suite.py tests/contracts/test_fake_matching.py
tests/contracts/events_suite.py tests/contracts/lease_suite.py tests/contracts/test_fake_events_lease.py
tests/contracts/event_log_suite.py tests/contracts/test_fake_event_log.py
repo_audit.sh src/farm/testing/invariants.py
docs/farm-code-review-v1.md docs/farm-code-review-v2.md docs/farm-code-review-v3.md docs/farm-code-review-v4.md
adoption/.gitkeep firmware/esp32_seat/.gitkeep ops/systemd/.gitkeep probe/.gitkeep protocol/.gitkeep
scenarios/.gitkeep services/maa_service/.gitkeep tests/hardware/.gitkeep tests/input/.gitkeep
tests/integration/.gitkeep tests/properties/.gitkeep tests/soak/.gitkeep tests/unit/.gitkeep tools/__init__.py tools/.gitkeep tools/probe_esp32.py tools/probe_capture.py
tools/diagnose_topology.py tools/capture_evidence.py tools/run_golden_vectors.py
"
MISSING=0
for f in $EXPECTED; do
  if [ ! -e "$f" ]; then bad "missing: $f"; MISSING=$((MISSING+1));
  elif ! git ls-files --error-unmatch "$f" >/dev/null 2>&1; then bad "not tracked by git: $f"; MISSING=$((MISSING+1)); fi
done
[ "$MISSING" = 0 ] && ok "all expected files present and tracked"
echo "  (files for slices not yet merged into the branch you are on will show as missing)"

echo
echo "== 3. Placeholders and leftovers"
[ -e docs/errata.md ] && warn "docs/errata.md still exists (the plan was to drop it)"
EMPTY=$(find . -type f -empty -not -path './.git/*' -not -path './.venv/*' -not -name '__init__.py' -not -name '.gitkeep' -not -path '*/__pycache__/*' -not -path '*.egg-info/*' | sort)
if [ -n "$EMPTY" ]; then echo "  empty files (expected placeholders for later weeks):"; echo "$EMPTY" | sed 's/^/           /'; fi
STRAY=$(git ls-files | grep -E '(\.pyc$|__pycache__|\.egg-info|^\.venv/)' || true)
[ -z "$STRAY" ] && ok "no cache, venv or egg-info files tracked" || bad "tracked junk: $STRAY"
BADNAMES=$(git ls-files | grep -E '[^A-Za-z0-9_./-]' || true)
[ -z "$BADNAMES" ] && ok "no oddly named tracked files" || bad "odd file names (garbled paste?): $BADNAMES"

echo
echo "== 4. Duplicate definitions (the earlier paste problem)"
python3 - << 'PYEOF'
import ast, pathlib, sys
problems = []
for root in ("src", "tests"):
    for path in sorted(pathlib.Path(root).rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        def check(body, scope):
            seen = set()
            for node in body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    if node.name in seen:
                        problems.append(f"{path}: duplicate {node.name} in {scope}")
                    seen.add(node.name)
                    if isinstance(node, ast.ClassDef):
                        check(node.body, node.name)
        check(tree.body, "module")
for p in problems:
    print("  [FAIL] " + p)
if not problems:
    print("  [ok]   no duplicate functions or classes")
sys.exit(1 if problems else 0)
PYEOF
[ $? -eq 0 ] && PASS=$((PASS+1)) || FAIL=$((FAIL+1))

echo
echo "== 5. Memo"
grep -m1 -o "DOC ADF-DEC-V[0-9.]*" docs/decision-memo.md 2>/dev/null | sed 's/^/  version: /' || warn "memo version line not found"

echo
echo "== 6. Tests and layering"
PYTEST=$(command -v pytest || echo .venv/bin/pytest)
if [ -x "$PYTEST" ]; then
  OUT=$("$PYTEST" -q 2>&1 | tail -n 3)
  echo "$OUT" | sed 's/^/  /'
  echo "$OUT" | grep -q "passed" && ! echo "$OUT" | grep -qE "failed|error" && ok "pytest green" || bad "pytest not green"
else
  warn "pytest not found; activate the venv"
fi
LINT_IMPORTS=$(command -v lint-imports || echo .venv/bin/lint-imports)
if [ -x "$LINT_IMPORTS" ]; then
  LI=$("$LINT_IMPORTS" 2>&1 | grep -E "KEPT|BROKEN|Contracts:" )
  echo "$LI" | sed 's/^/  /'
  echo "$LI" | grep -q "0 broken" && ok "import layering kept" || bad "import layering broken"
else
  warn "lint-imports not found; activate the venv"
fi

echo
echo "== 7. CI (optional)"
if command -v gh >/dev/null 2>&1; then
  gh run list --limit 3 2>/dev/null | sed 's/^/  /' || warn "gh could not list runs (not logged in?)"
else
  warn "GitHub CLI not installed; check the Actions tab in the browser"
fi

echo
echo "== Summary: $PASS ok, $WARN warnings, $FAIL failures"
[ "$FAIL" = 0 ] && echo "Repository state looks complete for this branch." || echo "Fix the [FAIL] items above, then rerun."
