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

## Immediate Next — Marker Visualization (TOP PRIORITY)
User-reported bug: clicking DRC violations (e.g., m1.2) zooms to combined bbox of all markers but shows NO visual markers on layout. Root cause diagnosed, implementation plan ready.

**Plan file**: `~/.claude/plans/cryptic-snuggling-goose.md`

**Summary of changes needed** (5 frontend files, backend unchanged):
1. `WebGLRenderer.ts` — Add `setMarkers()` to render filled red rectangles at each marker bbox
2. `LayoutViewer.tsx` — Zoom to individual marker bbox, pass markers to renderer
3. `ViolationList.tsx` — Add prev/next marker navigation below selected violation
4. `ViolationOverlay.tsx` — Show "Marker N of M" when navigating
5. `App.tsx` — Add `selectedMarkerIndex` state, wire through props

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

## Hot Files
- `frontend/src/components/Layout/WebGLRenderer.ts` — Needs marker rendering added
- `frontend/src/components/Layout/LayoutViewer.tsx` — Needs per-marker zoom
- `frontend/src/components/DRC/ViolationList.tsx` — Needs marker sub-navigation
- `backend/pcell/mosfet.py` — Met1 bus routing (uncommitted from Session 21)

## Gotchas
- SKY130 DRC deck defaults ALL rule groups to disabled — `DEFAULT_DRC_FLAGS` fixes this
- KLayout macOS needs Gatekeeper bypass: `sudo xattr -r -d com.apple.quarantine /Applications/KLayout/klayout.app`
- .lvsdb format is NOT XML — S-expression text (custom parser in lvs_parser.py)
- DRC deck rule descriptions can lie — via2.5 says "m3 enclosure" but checks m2
- Docker healthcheck uses Python urllib (not curl — python:3.12-slim doesn't have curl)
- WebGL renderer uses single shader program with `gl.TRIANGLES` — markers should use same pattern (not LINES, line width unreliable)
