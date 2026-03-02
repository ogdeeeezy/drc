# HANDOFF — agentic-drc

## What This Is
Open-source DRC (Design Rule Check) tool — PVS alternative for semiconductor layout verification. Deterministic rules-based expert system that checks GDSII layouts against PDK design rules, triages violations, and suggests geometric fixes.

## Current State
- **Phase 1 (Core DRC Engine)**: COMPLETE — 4/4 stories
- **Phase 2 (Fix Suggestion Engine)**: COMPLETE — 5/5 stories
- **Phase 3 (Web API + Layout Viewer)**: COMPLETE — 5/5 stories
- **Phase 4 (Production Hardening)**: COMPLETE — 5/5 stories
- **273 unit tests**, all passing (`make test`)
- **Frontend builds clean** (`cd frontend && npm run build`)
- **Lint clean** (`make lint`)
- Python 3.12 venv at `.venv/`, all deps installed
- KLayout CLI NOT installed yet — unit tests mock subprocess, integration tests will need it

## How to Run
- Backend: `make run` (uvicorn on port 8000)
- Frontend: `make frontend` (Vite dev server on port 5173, proxies /api to backend)
- Tests: `make test`
- Docker: `docker compose up --build`

## Key Architecture Decisions
- **KLayout subprocess** for DRC, custom XML parser for .lyrdb
- **gdstk** for GDSII read/write/modify
- **PDK-agnostic**: everything parameterized by `pdk.json`
- **Fix priority**: shorts > off-grid > width > spacing > enclosure > area > density
- **SQLite persistence**: `data/jobs/jobs.db` (WAL mode, thread-safe)
- **WebGL viewer**: earcut triangulation, camera transform shaders, pan/zoom
- **Fix preview**: SVG-based before/after polygon diff
- **Re-DRC loop**: apply fixes → re-run DRC → increment iteration → repeat until clean
- **Report export**: JSON, CSV, HTML formats via `/api/jobs/{id}/report/{format}`
- **Docker**: multi-stage build (Python + KLayout + frontend)

## Hot Files
- `backend/main.py` — FastAPI app with all route registrations
- `backend/api/deps.py` — Singleton managers
- `backend/jobs/manager.py` — Job lifecycle (SQLite persistence)
- `backend/jobs/database.py` — SQLite database backend
- `backend/api/routes/fix.py` — Fix suggest/preview/apply + re-DRC loop
- `backend/api/routes/drc.py` — DRC trigger + violation retrieval
- `backend/api/routes/export.py` — Report download (JSON/CSV/HTML)
- `backend/export/report.py` — Report generation
- `backend/export/gdsii.py` — Versioned GDSII export
- `backend/fix/engine.py` — Fix orchestrator (7 strategies)
- `backend/fix/strategies/density.py` — Density fill strategy
- `frontend/src/api/client.ts` — Typed API client

## What's Left
- Install KLayout CLI for integration tests (`brew install klayout`)
- Vendor SKY130 DRC deck (`sky130A_mr.drc` from efabless repo)
- Integration tests with real KLayout
- PDK authoring documentation (`docs/pdk-authoring.md`)
