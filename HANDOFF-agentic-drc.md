# HANDOFF — agentic-drc

## What This Is
Open-source DRC (Design Rule Check) tool — PVS alternative for semiconductor layout verification. Deterministic rules-based expert system that checks GDSII layouts against PDK design rules, triages violations, and suggests geometric fixes.

## Current State
- **Phase 1 (Core DRC Engine)**: COMPLETE — 4/4 stories
- **Phase 2 (Fix Suggestion Engine)**: COMPLETE — 5/5 stories
- **Phase 3 (Web API + Layout Viewer)**: COMPLETE — 5/5 stories
- **243 unit tests**, all passing (`make test`)
- **Frontend builds clean** (`cd frontend && npm run build`)
- Python 3.12 venv at `.venv/`, all deps installed
- KLayout CLI NOT installed yet — unit tests mock subprocess, integration tests will need it

## How to Run
- Backend: `make run` (uvicorn on port 8000)
- Frontend: `make frontend` (Vite dev server on port 5173, proxies /api to backend)
- Tests: `make test`

## Immediate Next Steps (Phase 4: Production Hardening)
1. **P4-1: Fix application + re-DRC loop** — `fix/engine.py`, `export/gdsii.py`
2. **P4-2: SQLite job persistence** — `jobs/database.py`
3. **P4-3: Report export (JSON, CSV, HTML)** — `export/report.py`
4. **P4-4: Docker + CI/CD** — `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`
5. **P4-5: Density fill strategy + PDK authoring docs** — `fix/strategies/density.py`, `docs/pdk-authoring.md`

Also still needed:
- **Install KLayout CLI**: `brew install klayout` — for integration tests
- **Vendor SKY130 DRC deck**: Get `sky130A_mr.drc` from efabless repo

## Key Architecture Decisions
- **KLayout subprocess** for DRC, custom XML parser for .lyrdb
- **gdstk** for GDSII read/write/modify
- **PDK-agnostic**: everything parameterized by `pdk.json`
- **Fix priority**: shorts > off-grid > width > spacing > enclosure > area
- **Job persistence**: JSON files in `data/jobs/<id>/` (SQLite planned for P4-2)
- **WebGL viewer**: earcut triangulation, camera transform shaders, pan/zoom
- **Fix preview**: SVG-based before/after polygon diff

## Hot Files
- `backend/main.py` — FastAPI app with all route registrations
- `backend/api/deps.py` — Singleton managers (JobManager, PDKRegistry)
- `backend/api/routes/upload.py` — GDSII upload + job creation
- `backend/api/routes/drc.py` — DRC trigger + violation retrieval
- `backend/api/routes/fix.py` — Fix suggest/preview/apply
- `backend/api/routes/layout.py` — Geometry data for WebGL viewer
- `backend/api/routes/pdk.py` — PDK listing/details
- `backend/jobs/manager.py` — Job lifecycle (JSON persistence)
- `backend/fix/engine.py` — Fix orchestrator
- `frontend/src/App.tsx` — Main app component (upload → DRC → fix flow)
- `frontend/src/components/Layout/WebGLRenderer.ts` — WebGL rendering engine
- `frontend/src/api/client.ts` — Typed API client
