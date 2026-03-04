# HANDOFF — agentic-drc

## What This Is
Open-source DRC tool — PVS alternative for semiconductor layout verification. Checks GDSII layouts against PDK design rules, triages violations, suggests geometric fixes, auto-applies high-confidence fixes, runs LVS, and generates parameterized cells.

## Current State
- **Phases 1-5**: ALL COMPLETE (33/33 stories)
- **595 unit + 12 E2E tests passing**, frontend builds clean
- **GitHub**: https://github.com/ogdeeeezy/drc — all pushed to main
- **4 uncommitted files** with completed PCell DRC fixes (see below)

## How to Run
- Backend: `make run` (uvicorn on port 8000)
- Frontend: `make frontend` (Vite dev on 5173, proxies /api)
- Tests: `.venv/bin/python -m pytest tests/ -q --ignore=tests/integration` (unit)
- E2E: `.venv/bin/python -m pytest tests/integration/test_e2e_phase5.py -v -s` (requires KLayout)

## E2E Results (Current)
```
PMOS 4-finger (W=1.0 L=0.15 F=4): 0 violations ✓
Poly resistor (W=0.35 L=2.0 S=2):  0 violations ✓
NMOS minimum (W=0.30 L=0.15 F=1):  0 violations ✓
NMOS basic (W=0.5 L=0.15 F=1):     0 violations ✓
Pipeline (W=0.42 L=0.15 F=2):      0 violations ✓
LVS NMOS:                          match=True ✓
MIM capacitor (W=5.0 L=5.0):       4 violations ✗ (unknown rule)
```

## Immediate Next: MIM Capacitor Investigation

### Problem
4 DRC violations remain on MIM capacitor despite adding `via2_enc_by_met3_adj = 0.085` as via2 array margin. The rule being violated may NOT be via2.5.

### Investigation Steps
1. Run E2E with `-s` flag and examine the violation category names in output
2. Look at the DRC report file (XML) to identify exact rule IDs
3. Compare against SKY130 DRC deck rules for capm/via2/met3 layers
4. May need to examine `backend/pcell/capacitor.py` `_via_array()` method and the margin being passed

### After MIM Cap
- **Stream C: Auto-fix confidence** — Promote `MinSpacingFix` to `FixConfidence.high` when safe (single-layer, small move, no collision). Files: `backend/fix/strategies/spacing.py`, `backend/fix/autofix.py`

## Uncommitted Changes (4 files)
All changes are uncommitted — DO NOT discard them.

| File | Status |
|------|--------|
| `backend/pdk/configs/sky130/sky130A.lvs` | DONE — LVS `.inverted` → `extent.not(nwell)` |
| `backend/pcell/capacitor.py` | DONE but 4 violations remain |
| `backend/pcell/resistor.py` | DONE — 0 violations (licon repositioned outside RPM) |
| `backend/pcell/mosfet.py` | DONE — 0 violations (dynamic gate contact Y + m1.6 enforcement) |

## Hot Files
- `backend/pcell/capacitor.py` — MIM cap investigation (4 violations)
- `backend/fix/strategies/spacing.py` — Stream C auto-fix confidence
- `tests/integration/test_e2e_phase5.py` — E2E validation (12 tests)

## Gotchas
- SKY130 DRC deck defaults ALL rule groups to disabled — `DEFAULT_DRC_FLAGS` fixes this
- KLayout macOS needs Gatekeeper bypass: `sudo xattr -r -d com.apple.quarantine /Applications/KLayout/klayout.app`
- .lvsdb format is NOT XML — it's S-expression text (custom parser in lvs_parser.py)
- MOSFET min contactable W is ~0.26µm (licon_size + 2*licon_enc_by_diff), not 0.15µm
- m1.5 rule: 0.060µm on BOTH edges of ONE adjacent pair (not all 4 sides)
- Poly resistor licon.1: RPM layer extends beyond poly body → licons overlapping RPM get clipped by DRC
- Plan at `~/.claude/plans/idempotent-sniffing-beaver.md` was partially wrong about root causes

## Verification Command
```bash
.venv/bin/python -m pytest tests/integration/test_e2e_phase5.py -v -s 2>&1 | grep -E "(violations|match=)"
```

## What's Next (After E2E Fixes)
1. **Monte Carlo optimization** — klayout.db in-process for 10k+ geometric variants
2. **LLM-assisted DRC deck generator** — auto-generate rules from DRM tables
3. **CI/CD** — GitHub Actions for test + lint on PR
4. **More PDKs** — GF180, ASAP7 (last — solidify SKY130 framework first)
