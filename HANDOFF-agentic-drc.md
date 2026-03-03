# HANDOFF — agentic-drc

## What This Is
Open-source DRC (Design Rule Check) tool — PVS alternative for semiconductor layout verification. Deterministic rules-based expert system that checks GDSII layouts against PDK design rules, triages violations, and suggests geometric fixes.

## Current State
- **Phases 1-4**: ALL COMPLETE (19/19 stories)
- **Adaptive DRC**: COMPLETE — auto-selects threads/mode by GDS file size
- **KLayout integration**: WORKING — macOS app bundle auto-detected
- **303 tests** (286 unit + 17 integration), all passing
- **Frontend builds clean** (`cd frontend && npm run build`)
- Python 3.12 venv at `.venv/`, all deps installed

## How to Run
- Backend: `make run` (uvicorn on port 8000)
- Frontend: `make frontend` (Vite dev on 5173, proxies /api)
- Unit tests: `make test` | All tests: `make test-all`
- Docker: `docker compose up --build`

## Key Architecture
- **KLayout subprocess** for DRC — default flags enable feol/beol/offgrid/floating_met
- **Adaptive DRC**: <20MB=4t deep, 20-80MB=2t deep, >80MB=1t tiled(1000µm)
- **gdstk** for GDSII I/O, **pdk.json** for PDK-agnostic config
- **Fix priority**: shorts > off-grid > width > spacing > enclosure > area > density
- **SQLite WAL** for job persistence, versioned GDS export
- **Memory**: ~64 bytes/polygon in GDS, KLayout stays <2GB RSS in tests

## Hot Files
- `backend/core/drc_runner.py` — DRC runner, adaptive_strategy(), DEFAULT_DRC_FLAGS
- `backend/config.py` — DRCStrategy dataclass, thresholds, _find_klayout()
- `backend/pdk/configs/sky130/sky130A_mr.drc` — SKY130 DRC deck (vendored, tracked)
- `tests/integration/test_e2e_drc.py` — 8 e2e tests with real KLayout
- `tests/integration/test_memory_profiling.py` — 9 memory profiling tests

## Gotchas
- SKY130 DRC deck defaults ALL rule groups to disabled — `DEFAULT_DRC_FLAGS` in drc_runner.py fixes this
- KLayout macOS app bundle needs Gatekeeper bypass: `sudo xattr -r -d com.apple.quarantine /Applications/KLayout/klayout.app`
- No GitHub remote configured yet — local repo only

## What's Left
- PDK authoring guide (`docs/pdk-authoring.md`)
- Async DRC execution (currently blocks API thread)
- Additional PDKs (GF180, ASAP7)
- GitHub remote + CI pipeline setup
