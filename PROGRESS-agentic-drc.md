# PROGRESS-agentic-drc

> Sessions 1-18 archived → `docs/archive/archive-progress-agentic-drc.md`

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

---

## Session 19: 2026-03-05 — Full LVS E2E verified

### Done
- **LVS E2E flow verified** — Generate PCell → upload GDS → DRC (0 violations) → upload SPICE netlist → run LVS → **match** (1 device, 4 nets). Both NMOS and PMOS single-finger pass clean.
- **Substrate taps added to PCells** — ptap for NMOS, ntap for PMOS. Full contact stack (tap → licon → li1 → mcon → met1 with "B" label). Placed left of diff with 0.130 µm implant clearance.
- **LVS deck device class mapping** — Added `same_device_classes("NMOS", "SKY130_FD_PR__NFET_01V8")` and PMOS equivalent.
- **Tests updated** — Implant assertions updated for tap presence. 730 tests, 95% coverage.

### Decisions
- Substrate tap placed LEFT of diffusion (not below) to avoid gate contact conflicts
- Implant gap = 0.130 µm between nsdm/psdm edges (matches difftap.10)

### Next
- Deploy to VPS (done in Session 20)
