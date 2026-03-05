# PROGRESS-agentic-drc

> Sessions 1-17 archived → `docs/archive/archive-progress-agentic-drc.md`

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
- **Multi-finger LVS** — S/D met1 pads disconnected for 2+ fingers (need met1 bus)
- Monte Carlo optimization
- LLM-assisted DRC deck generator

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

---

## Session 18: 2026-03-05 — LVS deck fix + end-to-end testing

### Done
- **PCell generation E2E** — Tested all 5 device types via API: NMOS, PMOS, poly resistor, MIM capacitor, minimum NMOS. All DRC-clean (0 violations).
- **SQLite migration fix** — Added migration for `netlist_path` and `lvs_report_path` columns in `database.py`.
- **LVS deck root cause found** — KLayout mos4 extraction requires SD layer pre-split at gate edges.
- **sky130A.lvs rewritten** — Pre-split SD, clip gate to active area, bridge connectivity. Device extracts with correct L=0.15, W=0.42.

### Decisions
- Gate clipped to active area for extraction (not full poly) — prevents endcap area from inflating L computation

### Next
- Test full LVS flow end-to-end (done in Session 19)
