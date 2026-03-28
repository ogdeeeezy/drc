# HANDOFF — agentic-drc

## What This Is
Open-source DRC tool — PVS alternative for semiconductor layout verification. Checks GDSII layouts against PDK design rules, triages violations, suggests geometric fixes, auto-applies high-confidence fixes, runs LVS, and generates parameterized cells.

## Current State
- **Phases 1-5**: ALL COMPLETE (33/33 stories)
- **772 unit tests passing**, 95% coverage, frontend builds clean
- **GitHub**: https://github.com/ogdeeeezy/drc — all pushed to main
- **DEPLOYED**: https://sky130drc.duckdns.org — live with auto-SSL via Caddy
- **Marker visualization**: All markers shown at once with numbered labels, click-to-select on canvas, tooltips with rule/coords, edge pairs for all markers
- **PDK knowledge layer**: 3-tier system (universal → taxonomy → PDK-specific) for LLM context

## Immediate Next
- Wire `KnowledgeBase.get_context()` into LLM-assisted deck generation pipeline
- Monte Carlo optimization — klayout.db in-process for 10k+ geometric variants
- More PDKs — GF180, ASAP7 (adding a PDK = adding files, not code)

## How to Run
- **Production**: https://sky130drc.duckdns.org
- **Redeploy**: `ssh root@100.118.0.91 "cd /opt/drc && git pull && docker compose up -d --build"`
- **Local dev**: `make run` (backend 8000) + `cd frontend && npx vite` (Vite 5173)
- **Tests**: `.venv/bin/python -m pytest tests/unit/ -q --cov=backend` (772 tests, 95%)

## VPS Details (ExtraVM)
- **Tailscale**: `ssh root@100.118.0.91` (use this for SSH)
- **Public IP**: 104.156.154.153 — port 22 BLOCKED, 443 whitelisted to user IP + Cloudflare ranges
- **DRC port**: 8001 (NOT 8000 — Agent Mixing owns 8000)
- **Caddy**: v2.11.1, config at `/etc/caddy/Caddyfile`, `sky130drc.duckdns.org → localhost:8001`

## Gotchas
- **Port 8001**: DRC runs on 8001, Agent Mixing on 8000. Caddyfile routes sky130drc → 8001
- **Firewall**: 443 locked to user IP (68.226.101.34) + Cloudflare ranges. Update if ISP changes IP
- **Sandbox**: GDS parser runs in subprocess with 2GB memory limit. Was 512MB, segfaulted on ESD files
- **Cloudflare Tunnel**: Investigated but deferred — DuckDNS can't be added as CF zone. Needs owned domain
- KLayout macOS needs Gatekeeper bypass: `sudo xattr -r -d com.apple.quarantine /Applications/KLayout/klayout.app`
- .lvsdb format is NOT XML — S-expression text (custom parser in lvs_parser.py)
- .lyrdb edge-pair separator: KLayout uses both `/` and `|` (parser handles both)
- React `onWheel` is passive — use native `addEventListener({ passive: false })` to prevent browser zoom
