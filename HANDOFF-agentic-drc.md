# HANDOFF — agentic-drc

## What This Is
Open-source DRC tool — PVS alternative for semiconductor layout verification. Checks GDSII layouts against PDK design rules, triages violations, suggests geometric fixes, auto-applies high-confidence fixes, runs LVS, and generates parameterized cells.

## Current State
- **Phases 1-5**: ALL COMPLETE (33/33 stories)
- **762 unit tests passing**, 95% coverage, frontend builds clean
- **GitHub**: https://github.com/ogdeeeezy/drc — all pushed to main
- **LVS fully working**: Single + multi-finger NMOS/PMOS
- **Marker visualization**: Shipped — WebGL red rectangles, per-marker zoom, Prev/Next nav
- **PDK knowledge layer**: 3-tier system (universal → taxonomy → PDK-specific) for LLM context
- **DEPLOYED**: https://sky130drc.duckdns.org — live with auto-SSL via Caddy

## Immediate Next
- Wire `KnowledgeBase.get_context()` into LLM-assisted deck generation pipeline
- Monte Carlo optimization — klayout.db in-process for 10k+ geometric variants
- LLM-assisted DRC deck generator — auto-generate rules from DRM tables
- More PDKs — GF180, ASAP7 (adding a PDK = adding files, not code)

## How to Run
- **Production**: https://sky130drc.duckdns.org
- **Redeploy**: `ssh root@104.156.154.153 "cd /opt/drc && git pull && docker compose up -d --build"`
- **Local dev**: `make run` (backend 8000) + `cd frontend && npx vite` (Vite 5173)
- **Tests**: `.venv/bin/python -m pytest tests/unit/ -q --cov=backend` (762 tests, 95%)

## VPS Details
- **IP**: 104.156.154.153 (SSH as root, key in ~/.ssh/id_ed25519)
- **OS**: Ubuntu 24.04, 8GB RAM, Docker 29.2.1
- **Caddy**: v2.11.1, config at `/etc/caddy/Caddyfile`, auto-SSL
- **Repo on VPS**: `/opt/drc`

## Gotchas
- SKY130 DRC deck flags now in `pdk.json` (`drc_flags` field) — `DEFAULT_DRC_FLAGS` is fallback for PDKs without it
- KLayout macOS needs Gatekeeper bypass: `sudo xattr -r -d com.apple.quarantine /Applications/KLayout/klayout.app`
- .lvsdb format is NOT XML — S-expression text (custom parser in lvs_parser.py)
- DRC deck rule descriptions can lie — via2.5 says "m3 enclosure" but checks m2
- Docker healthcheck uses Python urllib (not curl — python:3.12-slim doesn't have curl)
- WebGL renderer uses single shader program with `gl.TRIANGLES` — markers use same pattern
- .lyrdb edge-pair separator: KLayout uses both `/` and `|` depending on rule (parser handles both now)
- React `onWheel` is passive — use native `addEventListener({ passive: false })` to prevent browser zoom
