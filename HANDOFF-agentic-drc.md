# HANDOFF — agentic-drc

## What This Is
Open-source DRC tool — PVS alternative for semiconductor layout verification. Checks GDSII layouts against PDK design rules, triages violations, suggests geometric fixes, auto-applies high-confidence fixes, runs LVS, and generates parameterized cells.

## Current State
- **Phases 1-5**: ALL COMPLETE (33/33 stories)
- **737 unit tests passing**, 95% coverage, frontend builds clean
- **GitHub**: https://github.com/ogdeeeezy/drc — all pushed to main
- **LVS fully working**: Single-finger NMOS + PMOS DRC-clean and LVS-match verified E2E
- **Multi-finger bus routing**: Met1 bus bars implemented (uncommitted) — connects S/D pads for LVS
- **DEPLOYED**: https://sky130drc.duckdns.org — live with auto-SSL via Caddy

## How to Run
- **Production**: https://sky130drc.duckdns.org
- **Redeploy**: `ssh root@104.156.154.153 "cd /opt/drc && git pull && docker compose up -d --build"`
- **Local dev**: `make run` (backend 8000) + `make frontend` (Vite 5173)
- **Tests**: `.venv/bin/python -m pytest tests/unit/ -q --cov=backend` (737 tests, 95%)

## VPS Details
- **IP**: 104.156.154.153 (SSH as root, key in ~/.ssh/id_ed25519)
- **OS**: Ubuntu 24.04, 8GB RAM, Docker 29.2.1
- **Caddy**: v2.11.1, config at `/etc/caddy/Caddyfile`, auto-SSL
- **Repo on VPS**: `/opt/drc`
- **Also running**: `gantamade.duckdns.org` on same Caddy instance

## Immediate Next
- **Commit + verify multi-finger LVS** — Bus routing code is written and tested. Generate 4-finger GDS, run DRC (expect 0), upload SPICE netlist, run LVS (expect match).
- **Monte Carlo optimization** — klayout.db in-process for 10k+ geometric variants
- **LLM-assisted DRC deck generator** — auto-generate rules from DRM tables

## Hot Files
- `backend/pcell/mosfet.py` — Met1 bus routing added (step 7b), gate clearance updated
- `tests/unit/test_pcell_mosfet.py` — New TestMultiFingerNMOS class + bus connectivity tests

## Gotchas
- SKY130 DRC deck defaults ALL rule groups to disabled — `DEFAULT_DRC_FLAGS` fixes this
- KLayout macOS needs Gatekeeper bypass: `sudo xattr -r -d com.apple.quarantine /Applications/KLayout/klayout.app`
- .lvsdb format is NOT XML — S-expression text (custom parser in lvs_parser.py)
- DRC deck rule descriptions can lie — via2.5 says "m3 enclosure" but checks m2
- Docker healthcheck uses Python urllib (not curl — python:3.12-slim doesn't have curl)
