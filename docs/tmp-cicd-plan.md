# CI/CD Improvement Plan — agentic-drc

## Context
Basic CI exists at `.github/workflows/ci.yml` with: Python unit tests + ruff lint + frontend build.
It triggers on push/PR to main. But it has gaps that reduce its value as a safety net.

## Current CI (`ci.yml`)
- **test job**: checkout → setup-python 3.12 → pip install → ruff check/format → pytest tests/unit/
- **frontend job**: checkout → setup-node 22 → npm ci → npm run build

## What's Missing

### 1. Integration Tests (KLayout)
- 12 E2E tests verify real DRC/LVS against KLayout + SKY130 deck
- Currently skipped in CI (KLayout CLI not installed on ubuntu-latest)
- KLayout installable on Ubuntu: `sudo apt install klayout` or via PPA
- Add as separate job, `continue-on-error: true` initially
- Integration tests auto-skip gracefully if klayout missing (`KLAYOUT_AVAILABLE` flag)

### 2. Concurrency Control
- No concurrency group — multiple CI runs can pile up on rapid pushes
- Add `concurrency: { group: ci-${{ github.ref }}, cancel-in-progress: true }`

### 3. Test Coverage
- No coverage reporting — can't see if coverage drifts
- Add `pytest-cov` to dev deps, run with `--cov=backend --cov-report=term-missing`
- Optionally upload to codecov or just print summary

### 4. Branch Protection (GitHub Settings, not code)
- Recommend enabling: "Require status checks to pass before merging" for `test` and `frontend` jobs
- Recommend: "Require branches to be up to date before merging"
- This is the part that actually BLOCKS bad merges

### 5. Badge
- Add CI status badge to README (if one exists)

## Implementation Plan

### File: `.github/workflows/ci.yml` — Enhance existing
```yaml
Changes:
- Add concurrency group (cancel stale runs)
- Add coverage to unit test step (pytest --cov)
- Add integration test job (optional, install klayout via apt)
- Keep frontend job as-is
```

### File: `pyproject.toml` — Add pytest-cov
```
[project.optional-dependencies]
dev = [..., "pytest-cov>=5.0"]
```

### Proposed workflow structure:
```
jobs:
  lint:          # Fast — ruff check + format (split from test for faster feedback)
  test:          # Unit tests with coverage
  integration:   # KLayout E2E tests (continue-on-error: true)
  frontend:      # npm build (unchanged)
```

### KLayout Installation in CI
```yaml
- name: Install KLayout
  run: |
    sudo apt-get update
    sudo apt-get install -y klayout
```
If apt version is too old, use: download .deb from klayout.de releases page.
The `klayout` pip package (Python bindings) is already in pyproject.toml deps.
The CLI binary is what's needed for DRC/LVS — that's the apt package.

## Key Files
- `.github/workflows/ci.yml` — main CI workflow
- `pyproject.toml` — dev dependencies (add pytest-cov)
- `Makefile` — existing test/lint commands (reference, don't change)
- `backend/config.py` — KLayout binary detection
- `tests/integration/test_e2e_phase5.py` — E2E tests (auto-skip if no klayout)

## Verification
1. Push to a branch, open PR → CI should run all jobs
2. Unit tests + lint should pass (they pass locally)
3. Integration job should either pass (if klayout installs) or skip gracefully
4. Frontend build should pass
5. After merge: recommend enabling branch protection in GitHub repo settings
