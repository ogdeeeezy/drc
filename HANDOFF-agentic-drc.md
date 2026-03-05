# HANDOFF — agentic-drc

## What This Is
Open-source DRC tool — PVS alternative for semiconductor layout verification. Checks GDSII layouts against PDK design rules, triages violations, suggests geometric fixes, auto-applies high-confidence fixes, runs LVS, and generates parameterized cells.

## Current State
- **Phases 1-5**: ALL COMPLETE (33/33 stories)
- **730 unit tests passing**, 95% coverage, frontend builds clean
- **GitHub**: https://github.com/ogdeeeezy/drc — all pushed to main
- **LVS fully working**: NMOS + PMOS single-finger DRC-clean and LVS-match verified E2E
- **Deploy plan ready**: `docs/tmp-deploy-plan.md` — next instance should execute this

## How to Run
- Backend: `make run` (uvicorn on port 8000)
- Frontend: `make frontend` (Vite dev on 5173, proxies /api)
- Tests: `.venv/bin/python -m pytest tests/unit/ -q --cov=backend` (730 tests, 95%)

## Immediate Next: DEPLOY TO VPS
**Execute `docs/tmp-deploy-plan.md` — 5 steps:**

1. **Fix static serving** (`backend/main.py`) — mount `frontend/dist` as StaticFiles at `/`, add SPA catch-all
2. **Fix CORS** (`backend/main.py`) — add `https://sky130drc.duckdns.org` to allow_origins
3. **Add .dockerignore** — exclude .venv, node_modules, tests, .git
4. **Add feedback button** (`frontend/src/App.tsx`) — fixed-position link → `github.com/ogdeeeezy/drc/issues/new`
5. **Deploy on VPS** — SSH to `root@104.156.154.153`, clone to `/opt/drc`, `docker compose up -d --build`, add Caddy entry for `sky130drc.duckdns.org → localhost:8000`, reload Caddy

### VPS Details
- **IP**: 104.156.154.153 (SSH as root, key in ~/.ssh/id_ed25519)
- **OS**: Ubuntu 24.04, 8GB RAM, 59GB free disk
- **Docker**: 29.2.1 + Compose 5.1.0
- **Caddy**: v2.11.1 on ports 80/443, config at `/etc/caddy/Caddyfile`
- **Existing**: `gantamade.duckdns.org` already served by Caddy
- **Domain**: `sky130drc.duckdns.org` → 104.156.154.153 (DNS confirmed)

## After Deploy
- **Multi-finger LVS** — S/D met1 pads disconnected for 2+ fingers (need met1 bus)
- Monte Carlo optimization
- LLM-assisted DRC deck generator

## Gotchas
- SKY130 DRC deck defaults ALL rule groups to disabled — `DEFAULT_DRC_FLAGS` fixes this
- KLayout macOS needs Gatekeeper bypass: `sudo xattr -r -d com.apple.quarantine /Applications/KLayout/klayout.app`
- .lvsdb format is NOT XML — S-expression text (custom parser in lvs_parser.py)
- **Multi-finger S/D pads are electrically disconnected** — needs met1 bus for LVS
- DRC deck rule descriptions can lie — via2.5 says "m3 enclosure" but checks m2
