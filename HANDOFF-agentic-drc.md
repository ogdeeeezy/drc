# HANDOFF — agentic-drc

## What This Is
Open-source DRC tool — PVS alternative for semiconductor layout verification. Checks GDSII layouts against PDK design rules, triages violations, suggests geometric fixes, auto-applies high-confidence fixes, runs LVS, and generates parameterized cells.

## Current State
- **Phases 1-5**: ALL COMPLETE (33/33 stories)
- **730 unit tests passing**, 95% coverage, frontend builds clean
- **GitHub**: https://github.com/ogdeeeezy/drc — all pushed to main
- **LVS fully working**: NMOS + PMOS single-finger DRC-clean and LVS-match verified E2E
- **DEPLOYED**: https://sky130drc.duckdns.org — live with auto-SSL

## How to Run
- **Production**: https://sky130drc.duckdns.org (VPS at 104.156.154.153)
- **Local dev**: `make run` (backend 8000) + `make frontend` (Vite 5173)
- **Tests**: `.venv/bin/python -m pytest tests/unit/ -q --cov=backend` (730 tests, 95%)
- **Redeploy**: `ssh root@104.156.154.153 "cd /opt/drc && git pull && docker compose up -d --build"`

## VPS Details
- **IP**: 104.156.154.153 (SSH as root, key in ~/.ssh/id_ed25519)
- **OS**: Ubuntu 24.04, 8GB RAM
- **Stack**: Docker 29.2.1, Caddy v2.11.1 (auto-SSL), config at `/etc/caddy/Caddyfile`
- **Repo**: `/opt/drc` on VPS
- **Also running**: `gantamade.duckdns.org` on same Caddy

## Next
- **Multi-finger LVS** — S/D met1 pads disconnected for 2+ fingers (need met1 bus)
- Monte Carlo optimization
- LLM-assisted DRC deck generator

## Gotchas
- SKY130 DRC deck defaults ALL rule groups to disabled — `DEFAULT_DRC_FLAGS` fixes this
- KLayout macOS needs Gatekeeper bypass: `sudo xattr -r -d com.apple.quarantine /Applications/KLayout/klayout.app`
- .lvsdb format is NOT XML — S-expression text (custom parser in lvs_parser.py)
- **Multi-finger S/D pads are electrically disconnected** — needs met1 bus for LVS
- DRC deck rule descriptions can lie — via2.5 says "m3 enclosure" but checks m2
