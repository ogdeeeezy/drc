# HANDOFF — agentic-drc

## What This Is
Open-source DRC tool — PVS alternative for semiconductor layout verification. Checks GDSII layouts against PDK design rules, triages violations, suggests geometric fixes, auto-applies high-confidence fixes, runs LVS, and generates parameterized cells.

## Current State
- **Phases 1-5**: ALL COMPLETE (33/33 stories)
- **703 unit + 12 E2E tests passing**, 94% coverage, frontend builds clean
- **GitHub**: https://github.com/ogdeeeezy/drc — all pushed to main
- **All PCells DRC-clean**, CI/CD enhanced with lint/test/integration/frontend jobs

## How to Run
- Backend: `make run` (uvicorn on port 8000)
- Frontend: `make frontend` (Vite dev on 5173, proxies /api)
- Tests: `.venv/bin/python -m pytest tests/unit/ -q --cov=backend` (703 tests, 94%)
- E2E: `.venv/bin/python -m pytest tests/integration/test_e2e_phase5.py -v -s` (requires KLayout)

## Immediate Next
- **Branch protection** — Enable in GitHub repo settings (manual): require `lint`, `test`, `frontend` to pass
- **Monte Carlo optimization** — klayout.db in-process for 10k+ geometric variants
- **LLM-assisted DRC deck generator** — auto-generate rules from DRM tables
- **More PDKs** — GF180, ASAP7 (solidify SKY130 framework first)

## Key Test Files
- `tests/unit/test_fix_strategies.py` — 59 strategy tests (21 original + 38 extended coverage)
- `tests/unit/test_api_coverage.py` — 69 API route tests
- `docs/tmp-cicd-plan.md` — CI/CD plan + coverage analysis

## E2E Results (Current)
```
PMOS 4-finger (W=1.0 L=0.15 F=4): 0 violations
Poly resistor (W=0.35 L=2.0 S=2):  0 violations
NMOS minimum (W=0.30 L=0.15 F=1):  0 violations
NMOS basic (W=0.5 L=0.15 F=1):     0 violations
Pipeline (W=0.42 L=0.15 F=2):      0 violations
LVS NMOS:                          match=True
MIM capacitor (W=5.0 L=5.0):       0 violations
```

## Gotchas
- SKY130 DRC deck defaults ALL rule groups to disabled — `DEFAULT_DRC_FLAGS` fixes this
- KLayout macOS needs Gatekeeper bypass: `sudo xattr -r -d com.apple.quarantine /Applications/KLayout/klayout.app`
- .lvsdb format is NOT XML — it's S-expression text (custom parser in lvs_parser.py)
- MOSFET min contactable W is ~0.26um (licon_size + 2*licon_enc_by_diff), not 0.15um
- m1.5 rule: 0.060um on BOTH edges of ONE adjacent pair (not all 4 sides)
- Poly resistor licon.1: RPM layer extends beyond poly body, licons overlapping RPM get clipped by DRC
- SKY130 DRC deck via2.5: description says "m3 enclosure" but code checks m2 (`m2.enclosing(via2, 0.085)`)
