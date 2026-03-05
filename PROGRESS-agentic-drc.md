# PROGRESS-agentic-drc

> Sessions 1-16 archived → `docs/archive/archive-progress-agentic-drc.md`

---

## Session 19: 2026-03-05 — Full LVS E2E verified

### Done
- **LVS E2E flow verified** — Generate PCell → upload GDS → DRC (0 violations) → upload SPICE netlist → run LVS → **match** (1 device, 4 nets). Both NMOS and PMOS single-finger pass clean.
- **Substrate taps added to PCells** — ptap for NMOS, ntap for PMOS. Full contact stack (tap → licon → li1 → mcon → met1 with "B" label). Placed left of diff with 0.130 µm implant clearance.
- **LVS deck device class mapping** — Added `same_device_classes("NMOS", "SKY130_FD_PR__NFET_01V8")` and PMOS equivalent. Maps extraction names to SPICE model names.
- **Tests updated** — Implant assertions updated for tap presence. 730 tests, 95% coverage.

### Decisions
- Substrate tap placed LEFT of diffusion (not below) to avoid gate contact conflicts
- Implant gap = 0.130 µm between nsdm/psdm edges (matches difftap.10)
- PMOS nwell extended leftward to enclose ntap

### Next
- **Multi-finger LVS** — S/D pads disconnected for 2+ fingers (need met1 bus connecting shared terminals)
- **Revert T-pad offset in mosfet.py** — harmless but unnecessary (lines ~185-200)
- Monte Carlo optimization — klayout.db in-process for 10k+ geometric variants
- LLM-assisted DRC deck generator

---

## Session 18: 2026-03-05 — LVS deck fix + end-to-end testing

### Done
- **PCell generation E2E** — Tested all 5 device types via API: NMOS, PMOS, poly resistor, MIM capacitor, minimum NMOS. All DRC-clean (0 violations).
- **SQLite migration fix** — Added migration for `netlist_path` and `lvs_report_path` columns in `database.py` (was only migrating `hint`).
- **LVS deck root cause found** — KLayout mos4 extraction requires SD layer pre-split at gate edges. Continuous diff rectangle fails with "Expected two polygons on diff interacting with one gate shape." Tested 6 hypotheses to isolate.
- **sky130A.lvs rewritten** — Pre-split SD (`nsd = (diff & nsdm) - gate_poly`), clip gate to active area (`gate_in_active = gate_poly & active`), bridge connectivity (`connect(gate_in_active, gate_poly)`). Device extracts with correct L=0.15, W=0.42.

### Decisions
- Gate clipped to active area for extraction (not full poly) — prevents endcap area from inflating L computation
- `connect(gate_in_active, gate_poly)` bridges extraction layer to routing layer for connectivity

### Next
- Test full LVS flow end-to-end (done in Session 19)

---

## Session 17: 2026-03-04 — Error hints implementation + branch protection

### Done
- **Error hints implemented** (`affd54d`) — Centralized `error_hints.py` with 14 regex→hint rules, `hint` field on Job model + DB schema (with ALTER TABLE migration), route wiring in drc.py/lvs.py, amber hint box UI in frontend. 730 tests, 95% coverage.
- **OSError runner tests** — 4 new tests each for DRC/LVS runners covering exec format error and permission denied paths (sync + async).
- **Error hints test suite** — 19 tests covering all regex patterns, edge cases, first-match-wins behavior.
- **Branch protection enabled** — GitHub API: `lint`, `test`, `frontend` required checks on `main`, strict mode, force push blocked.
- **Tagged release** — `pre-llm-deck-gen-pre-mc` tag on `affd54d`.

### Decisions
- Branch protection enforce_admins left OFF so owner can push directly when needed
- `integration` check excluded from required checks (uses continue-on-error due to KLayout availability)

### Next
- Monte Carlo optimization — klayout.db in-process for 10k+ geometric variants
- LLM-assisted DRC deck generator — auto-generate rules from DRM tables
- More PDKs — GF180, ASAP7 (solidify SKY130 framework first)
