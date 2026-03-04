# HANDOFF — agentic-drc

## What This Is
Open-source DRC tool — PVS alternative for semiconductor layout verification. Checks GDSII layouts against PDK design rules, triages violations, suggests geometric fixes, auto-applies high-confidence fixes, runs LVS, and generates parameterized cells.

## Current State
- **Phases 1-5**: ALL COMPLETE (33/33 stories)
- **625 tests passing** (595 unit + 30 integration), frontend builds clean
- **GitHub**: https://github.com/ogdeeeezy/drc — all pushed to main
- **E2E validated** — PCell, auto-fix, LVS tested against real KLayout + SKY130

## How to Run
- Backend: `make run` (uvicorn on port 8000)
- Frontend: `make frontend` (Vite dev on 5173, proxies /api)
- Tests: `make test` (unit) | `make test-all` (all)
- Docker: `docker compose up --build`

## Immediate Next: Fix E2E Issues (Plan Ready)

Plan at `~/.claude/plans/idempotent-sniffing-beaver.md`. Execute in order:

### Stream A: LVS Deck (5 min)
- `backend/pdk/configs/sky130/sky130A.lvs` line 62: `.inverted` → `extent.not(nwell)`
- KLayout 0.30.6 doesn't support `.inverted`

### Stream B: PCell DRC Violations

| Device | Rule | Fix |
|--------|------|-----|
| MOSFET (all) | m1.2 (met1 spacing, 5 violations) | Cap met1 pad width so adjacent S/D pads have ≥0.140µm gap |
| PMOS 4-finger | m1.7 (met1 area, 4 violations) | Extend gate contact met1 pads to ≥0.14µm² |
| Poly resistor | licon.1 (exact size, 4 violations) | Fix floating-point in licon placement at terminal contacts |
| MIM capacitor | via2.5 (met3 enc, 4 violations) | Increase via2 margin from 0.065 to 0.085µm (adj edge rule) |

### Stream C: Auto-Fix Confidence
- `backend/fix/strategies/spacing.py`: Promote to high confidence when single-layer, small move, clear polygons
- Currently all spacing fixes = medium → flagged with high threshold → stall

## Hot Files
- `backend/pcell/mosfet.py` — MOSFET generator, met1 pad spacing (lines 340-358)
- `backend/pcell/resistor.py` — Poly resistor, licon sizing (lines 394-396)
- `backend/pcell/capacitor.py` — MIM cap, via2 margin (lines 228-237)
- `backend/pdk/configs/sky130/sky130A.lvs` — LVS deck, line 62
- `backend/fix/strategies/spacing.py` — Spacing fix confidence
- `backend/fix/autofix.py` — Auto-applicability filter (lines 70-99)
- `tests/integration/test_e2e_phase5.py` — E2E validation tests (12 tests)

## Gotchas
- SKY130 DRC deck defaults ALL rule groups to disabled — `DEFAULT_DRC_FLAGS` fixes this
- KLayout macOS needs Gatekeeper bypass: `sudo xattr -r -d com.apple.quarantine /Applications/KLayout/klayout.app`
- cpulimit alone doesn't work on Apple Silicon — needs taskpolicy -b alongside
- .lvsdb format is NOT XML — it's S-expression text (custom parser in lvs_parser.py)
- MOSFET min contactable W is ~0.26µm (licon_size + 2*licon_enc_by_diff), not 0.15µm (diff_min_width)
- "0 violations" categories in .lyrdb still appear as entries — parser includes them

## What's Next (After E2E Fixes)
1. **Monte Carlo optimization** — klayout.db in-process for 10k+ geometric variants
2. **LLM-assisted DRC deck generator** — auto-generate rules from DRM tables
3. **CI/CD** — GitHub Actions for test + lint on PR
4. **More PDKs** — GF180, ASAP7 (last — solidify SKY130 framework first)

## Key Research Finding
`pip install klayout` provides in-process DRC via `klayout.db` Region API — 100-1000x faster than subprocess. Enables Monte Carlo without custom geometry engine.
