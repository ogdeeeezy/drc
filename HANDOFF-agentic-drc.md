# HANDOFF — agentic-drc

## What This Is
Open-source DRC (Design Rule Check) tool — PVS alternative for semiconductor layout verification. Deterministic rules-based expert system that checks GDSII layouts against PDK design rules, triages violations, and suggests geometric fixes.

## Current State
- **Phases 1-4**: ALL COMPLETE (19/19 stories)
- **Adaptive DRC**: COMPLETE — auto-selects threads/mode by GDS file size
- **CPU throttling**: COMPLETE — triple-layer (taskpolicy -b + nice + cpulimit at 60%)
- **KLayout integration**: WORKING — macOS app bundle auto-detected
- **286 unit tests + 17 integration**, all passing
- **Frontend builds clean** (`cd frontend && npm run build`)
- **E2E validated**: 142MB SKY130 ESD file → 11 violations found in 19 min (throttled)
- **GitHub**: https://github.com/ogdeeeezy/drc

## How to Run
- Backend: `make run` (uvicorn on port 8000)
- Frontend: `make frontend` (Vite dev on 5173, proxies /api)
- Unit tests: `make test` | All tests: `make test-all`
- Docker: `docker compose up --build`

## Key Architecture
- **KLayout subprocess** for DRC — default flags enable feol/beol/offgrid/floating_met
- **CPU throttling**: taskpolicy -b (macOS efficiency cores) + nice -n 10 + cpulimit -l 60%
- **Adaptive DRC**: <20MB=4t deep, 20-80MB=2t deep, >80MB=1t tiled(1000µm)
- **Timeout**: 2700s (45 min) — headroom for large files at throttled CPU
- **gdstk** for GDSII I/O, **pdk.json** for PDK-agnostic config
- **Fix priority**: shorts > off-grid > width > spacing > enclosure > area > density
- **SQLite WAL** for job persistence, versioned GDS export

## Hot Files
- `backend/core/drc_runner.py` — DRC runner, adaptive_strategy(), CPU throttling, DEFAULT_DRC_FLAGS
- `backend/config.py` — DRCStrategy, thresholds, _find_klayout(), DRC_CPU_LIMIT_PERCENT
- `backend/pdk/configs/sky130/sky130A_mr.drc` — SKY130 DRC deck (vendored, tracked)
- `docs/plan-phase5.md` — Phase 5 plan (auto-fix, PCell, LVS)
- `docs/pdk-authoring.md` — PDK authoring guide

## Gotchas
- SKY130 DRC deck defaults ALL rule groups to disabled — `DEFAULT_DRC_FLAGS` in drc_runner.py fixes this
- KLayout macOS app bundle needs Gatekeeper bypass: `sudo xattr -r -d com.apple.quarantine /Applications/KLayout/klayout.app`
- DRC runs synchronously — blocks the uvicorn worker thread (async is Phase 5 prerequisite)
- `cpulimit` must be installed separately: `brew install cpulimit` (auto-detected at runtime)
- cpulimit alone doesn't work well on Apple Silicon — needs taskpolicy -b alongside it

## What's Next (Phase 5)
Read `docs/plan-phase5.md` for full plan. Execution order:
1. **Async DRC** (prerequisite, 1-2 days) — unblock API thread during DRC runs
2. **Auto-fix loop** (3-5 days) — automated fix-apply-recheck with human audit trail
3. **LVS checker** (2-3 weeks) — layout vs schematic verification
4. **PCell generator** (2-3 weeks) — auto-generate DRC-clean GDS from component specs

## Key Research Finding
`pip install klayout` provides in-process DRC via `klayout.db` Region API — 100-1000x faster than subprocess. This enables Monte Carlo layout optimization (future build) without needing a custom geometry engine. See Session 8 notes in PROGRESS.

## Future Builds
- **LLM-assisted DRC deck generator** — feed DRM tables + KLayout API docs to auto-generate rules
- **Monte Carlo layout optimization** — 10k+ geometric variants via klayout.db in-process, scored by parasitics, validated with SPICE
