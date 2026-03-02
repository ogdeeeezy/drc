# HANDOFF — agentic-drc

## What This Is
Open-source DRC (Design Rule Check) tool — PVS alternative for semiconductor layout verification. Deterministic rules-based expert system that checks GDSII layouts against PDK design rules, triages violations, and suggests geometric fixes.

## Current State
- **Phase 1 (Core DRC Engine)**: COMPLETE — 4/4 stories
- **Phase 2 (Fix Suggestion Engine)**: COMPLETE — 5/5 stories
- **214 unit tests**, all passing (`make test`)
- Python 3.12 venv at `.venv/`, all deps installed
- KLayout CLI NOT installed yet — unit tests mock subprocess, integration tests will need it

## Immediate Next Steps (Phase 3: Web API + Layout Viewer)
1. **P3-1: FastAPI scaffold + upload/job endpoints** — `main.py`, `api/routes/upload.py`, `jobs/manager.py`
2. **P3-2: DRC + violation API routes** — `api/routes/drc.py`, `jobs/worker.py`
3. **P3-3: Fix suggestion + preview API** — `api/routes/fix.py`
4. **P3-4: Layout geometry API + WebGL viewer** — `api/routes/layout.py`, `WebGLRenderer.ts`, `LayoutViewer.tsx`
5. **P3-5: Violation overlay + fix panel UI** — `ViolationList.tsx`, `ViolationOverlay.tsx`, `FixPanel.tsx`

Also still needed:
- **Install KLayout CLI**: `brew install klayout` — for integration tests
- **Vendor SKY130 DRC deck**: Get `sky130A_mr.drc` from efabless repo

## Key Architecture Decisions
- **KLayout subprocess** for DRC, custom XML parser for .lyrdb
- **gdstk** for GDSII read/write/modify
- **PDK-agnostic**: everything parameterized by `pdk.json`
- **Fix priority**: shorts > off-grid > width > spacing > enclosure > area
- **Fix strategies**: expand (width), move/shrink (spacing), extend metal (enclosure), extend wire (area), shrink overlap (short), conservative snap (offgrid)
- **Pre-validation**: grid alignment, degenerate polygon, min width/area/spacing checks before suggesting

## Hot Files
- `backend/pdk/schema.py` — PDK config models
- `backend/core/drc_runner.py` — KLayout subprocess wrapper
- `backend/core/violation_parser.py` — .lyrdb XML → DRCReport
- `backend/core/violation_models.py` — EdgePair, Violation, DRCReport
- `backend/core/spatial_index.py` — R-tree polygon lookups
- `backend/fix/engine.py` — Fix orchestrator (strategies + validator + ranking)
- `backend/fix/strategies/` — 6 strategies (width, spacing, enclosure, area, short, offgrid)
- `backend/fix/validator.py` — Pre-validation of fix suggestions
- `backend/fix/fix_models.py` — FixSuggestion, PolygonDelta
