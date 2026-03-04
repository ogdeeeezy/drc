# HANDOFF — agentic-drc

## What This Is
Open-source DRC tool — PVS alternative for semiconductor layout verification. Checks GDSII layouts against PDK design rules, triages violations, suggests geometric fixes, auto-applies high-confidence fixes, runs LVS, and generates parameterized cells.

## Current State
- **Phases 1-5**: ALL COMPLETE (33/33 stories)
- **596 unit + 12 E2E tests passing**, frontend builds clean
- **GitHub**: https://github.com/ogdeeeezy/drc — all pushed to main
- **All PCells DRC-clean**, all committed and pushed

## How to Run
- Backend: `make run` (uvicorn on port 8000)
- Frontend: `make frontend` (Vite dev on 5173, proxies /api)
- Tests: `.venv/bin/python -m pytest tests/ -q --ignore=tests/integration` (unit)
- E2E: `.venv/bin/python -m pytest tests/integration/test_e2e_phase5.py -v -s` (requires KLayout)

## Immediate Next: CI/CD Enhancement

### Problem
Basic CI exists at `.github/workflows/ci.yml` (unit tests + lint + frontend build) but needs hardening.

### Plan (detailed at `docs/tmp-cicd-plan.md`)
1. Add concurrency group (cancel stale runs on rapid pushes)
2. Split lint into its own job (faster feedback)
3. Add test coverage reporting (`pytest-cov`)
4. Add KLayout integration test job (`sudo apt install klayout`, `continue-on-error: true`)
5. Recommend branch protection settings (GitHub UI, not code)

### Key Files
- `.github/workflows/ci.yml` — existing workflow to enhance
- `pyproject.toml` — add `pytest-cov` to dev deps
- `Makefile` — reference for existing test/lint commands

## E2E Results (Current)
```
PMOS 4-finger (W=1.0 L=0.15 F=4): 0 violations ✓
Poly resistor (W=0.35 L=2.0 S=2):  0 violations ✓
NMOS minimum (W=0.30 L=0.15 F=1):  0 violations ✓
NMOS basic (W=0.5 L=0.15 F=1):     0 violations ✓
Pipeline (W=0.42 L=0.15 F=2):      0 violations ✓
LVS NMOS:                          match=True ✓
MIM capacitor (W=5.0 L=5.0):       0 violations ✓
```

## Gotchas
- SKY130 DRC deck defaults ALL rule groups to disabled — `DEFAULT_DRC_FLAGS` fixes this
- KLayout macOS needs Gatekeeper bypass: `sudo xattr -r -d com.apple.quarantine /Applications/KLayout/klayout.app`
- .lvsdb format is NOT XML — it's S-expression text (custom parser in lvs_parser.py)
- MOSFET min contactable W is ~0.26µm (licon_size + 2*licon_enc_by_diff), not 0.15µm
- m1.5 rule: 0.060µm on BOTH edges of ONE adjacent pair (not all 4 sides)
- Poly resistor licon.1: RPM layer extends beyond poly body → licons overlapping RPM get clipped by DRC
- SKY130 DRC deck via2.5: description says "m3 enclosure" but code checks m2 (`m2.enclosing(via2, 0.085)`)

## What's Next (After CI/CD)
1. **Monte Carlo optimization** — klayout.db in-process for 10k+ geometric variants
2. **LLM-assisted DRC deck generator** — auto-generate rules from DRM tables
3. **More PDKs** — GF180, ASAP7 (last — solidify SKY130 framework first)
