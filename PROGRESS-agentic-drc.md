# PROGRESS-agentic-drc

> Sessions 1-19 archived → `docs/archive/archive-progress-agentic-drc.md`

---

## Session 22: 2026-03-10 — DRC marker visualization diagnosis + plan

### Done
- **Diagnosed marker navigation bug** — User reported m1.2 violations (5 markers) show no errors at listed coordinates. Root cause: frontend zooms to combined bbox of all markers, no individual marker rectangles rendered on layout.
- **Full coordinate chain traced** — DRC deck → .lyrdb edge-pair XML → violation_parser.py → API response → frontend. Data is correct; visualization is the gap.
- **Implementation plan designed** — WebGLRenderer marker rectangles, per-marker zoom navigation (prev/next), ViolationList expansion, overlay "Marker N of M" display. Plan at `~/.claude/plans/cryptic-snuggling-goose.md`.

### Decisions
- Markers rendered as filled rectangles in WebGL (not CSS overlay) so they pan/zoom with layout
- Zoom to individual marker bbox (not combined), auto-select first marker on violation click

### Next
- Implement marker visualization plan (5 files: WebGLRenderer, LayoutViewer, ViolationList, ViolationOverlay, App.tsx)
- Commit + verify multi-finger LVS (bus routing still uncommitted from Session 21)
- Monte Carlo optimization
- LLM-assisted DRC deck generator

---

## Session 21: 2026-03-06 — Multi-finger met1 S/D bus routing

### Done
- **Met1 bus bars for multi-finger LVS** (uncommitted) — Source bus above S/D pads, drain bus below. Horizontal bars span all same-terminal pad X positions. Vertical drops connect each pad to its bus. Single-finger devices unchanged.
- **Gate contact clearance updated** — Gate met1 pads now clear bus bars (not just S/D pads) with m1.2 spacing for multi-finger devices.
- **Tests added** — 3 new tests in `TestMultiFingerPMOS` (source bus, drain bus, single-finger no bus) + new `TestMultiFingerNMOS` class (4 tests). 41 mosfet tests, 737 total, all passing.

### Decisions
- Bus width = `met1_min_width` (0.140 µm), gap = `met1_min_spacing` (0.140 µm)
- Bus Y positions computed before gate contact placement so clearance accounts for bus metal

### Next
- Commit + redeploy multi-finger bus routing
- Generate 4-finger NMOS/PMOS via API and run DRC — verify 0 violations
- Upload multi-finger GDS + SPICE netlist, run LVS — verify match
- Monte Carlo optimization
- LLM-assisted DRC deck generator

---

## Session 20: 2026-03-05 — Deployed to VPS + production bugfixes

### Done
- **Deployed to production** (`614a181`) — Live at https://sky130drc.duckdns.org with auto-SSL via Caddy
- **Static file serving + CORS** — FastAPI serves `frontend/dist` at `/` with SPA catch-all, production domain in CORS
- **.dockerignore + feedback button** — Docker context trimmed, "Give Feedback" → GitHub Issues
- **Docker healthcheck fixed** — Replaced `curl` with Python `urllib` (curl not in python:3.12-slim)
- **DRC polling fix** (`ac8558e`) — Frontend was calling getViolations immediately after async runDRC. Added 2s polling loop matching LVS pattern.
- **Viewport clamping** (`2b2edd9`) — Pan clamped so 20% of viewport always overlaps layout bbox. Zoom bounded 0.1x–100x of fit. Double-click resets view.

### Decisions
- Static files mounted as `/assets` + SPA catch-all at `/{path:path}` (avoids conflict with `/api` routes)
- Caddy handles SSL termination — no cert management in app
- Redeploy: `ssh root@104.156.154.153 "cd /opt/drc && git pull && docker compose up -d --build"`

### Next
- Multi-finger LVS (done in Session 21)
