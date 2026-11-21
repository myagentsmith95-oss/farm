# farm

An Android device farm: 50 physical phones running a capture → recognise → decide →
inject → verify loop unattended. Each lease enforces one writer per device.

A **standard seat** uses an ESP32-S3 as a USB HID digitizer (root-free absolute touch)
and an HDMI mirror into a UVC capture card. An **ADB-only seat** uses ADB input and
screencap. Contracts come first; every third-party library sits behind a farm-owned
interface so the W5 MaaFramework decision stays reversible.

## Layout

```
src/farm/
  contracts/    models and interfaces only (stdlib + pydantic, AST-guarded)
  testing/      fakes, SimDevice, reusable contract suites' counterparts
  registry/     seat resolution and profile store
  adapters/     one module per third-party library (wired in W2)
  calibration/  capture/  control/  runner/  vision/  console/   (cores)
  app.py        composition root, the only importer of adapters
tests/          property tests, reusable contract suites, registry + sim tests
docs/
  decision-memo.md     living decision baseline (DOC ADF-DEC-Vx.y)
  ARCHITECTURE.md      hardware and feature source of truth
  farm-code-review-*.md  independent review findings
protocol/ adoption/ services/maa_service/   reserved for W2/W5 slices
```

The enforced layering is `testing → adapters → console → runner →
(control | registry | vision) → calibration → capture → contracts`.

## Setup

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Python 3.11 or 3.12. No hardware is needed for the test suite.

## Gates

Every change runs all five checks:

```bash
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/lint-imports
.venv/bin/pytest -q
bash repo_audit.sh
```

Convention: red tests → green implementation → memo row + audit update.

## Documents

- [Decision memo](docs/decision-memo.md) — decisions, change log, open items.
- [Architecture](docs/ARCHITECTURE.md) — proven hardware topology, command catalog,
  coordinate model, and the W2 acceptance checklist. When the two disagree, the
  architecture document wins on hardware facts.
- [Review findings](docs/farm-code-review-v2.md) and the v1/v3/v4 summaries — the
  audit trail of open and closed defects.
