# HANDOFF — agentic-drc

## What This Is
Open-source DRC tool — PVS alternative for semiconductor layout verification. Checks GDSII layouts against PDK design rules, triages violations, suggests geometric fixes, auto-applies high-confidence fixes, runs LVS, and generates DRC-clean parameterized cells.

## Current State
- **Phases 1-5**: ALL COMPLETE (33/33 stories)
- **613 tests passing** (unit + integration), frontend builds clean
- **GitHub**: https://github.com/ogdeeeezy/drc — all pushed to main

## How to Run
- Backend: `make run` (uvicorn on port 8000)
- Frontend: `make frontend` (Vite dev on 5173, proxies /api)
- Tests: `make test` (unit) | `make test-all` (all)
- Docker: `docker compose up --build`

## Key Architecture
- **Async DRC** — `asyncio.create_subprocess_exec`, non-blocking uvicorn
- **Auto-fix loop** — `POST /api/jobs/{id}/fix/auto` with confidence filtering, provenance log, oscillation detection
- **LVS** — KLayout LVS subprocess, .lvsdb S-expression parser, SKY130 device extraction
- **PCell** — MOSFET/resistor/capacitor generators via gdstk, self-validated with DRC
- **CPU throttling** — taskpolicy -b + nice + cpulimit at 60%
- **SQLite WAL** — jobs + fix_provenance tables

## Hot Files
- `backend/core/drc_runner.py` — DRC runner (sync + async), adaptive_strategy(), CPU throttling
- `backend/core/lvs_runner.py` — LVS runner, same subprocess pattern as DRC
- `backend/core/lvs_parser.py` — .lvsdb S-expression parser
- `backend/fix/autofix.py` — AutoFixRunner, confidence tiers, oscillation detection
- `backend/pcell/mosfet.py` — MOSFET generator (most complex PCell)
- `backend/jobs/database.py` — SQLite schema: jobs + fix_provenance tables
- `prds/` — Phase 5 modular PRDs (completed, for reference)

## Gotchas
- SKY130 DRC deck defaults ALL rule groups to disabled — `DEFAULT_DRC_FLAGS` fixes this
- KLayout macOS needs Gatekeeper bypass: `sudo xattr -r -d com.apple.quarantine /Applications/KLayout/klayout.app`
- `cpulimit` needs `brew install cpulimit` — auto-detected at runtime
- cpulimit alone doesn't work on Apple Silicon — needs taskpolicy -b alongside
- .lvsdb format is NOT XML — it's S-expression text (custom parser in lvs_parser.py)
- 4 pre-existing lint errors in drc_runner.py (E402 import order + E501 line length) — not from Phase 5

## What's Next
1. **Manual E2E validation** — test auto-fix loop, LVS, PCell on real SKY130 layouts
2. **More PDKs** — GF180, ASAP7 (DRC decks, LVS decks, PCell generators)
3. **Monte Carlo optimization** — klayout.db in-process for 10k+ geometric variants
4. **LLM-assisted DRC deck generator** — auto-generate rules from DRM tables
5. **CI/CD** — GitHub Actions for test + lint on PR

## Key Research Finding
`pip install klayout` provides in-process DRC via `klayout.db` Region API — 100-1000x faster than subprocess. Enables Monte Carlo without custom geometry engine.
