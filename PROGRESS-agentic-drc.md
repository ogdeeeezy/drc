# PROGRESS-agentic-drc

> Sessions 1-15 archived → `docs/archive/archive-progress-agentic-drc.md`

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
- **Test full LVS flow end-to-end** via API with updated deck (server restart + generate + upload + DRC + LVS)
- **Add substrate taps to PCells** — body terminal needs ptap/ntap for proper LVS net matching (currently auto-named "$5")
- **Revert T-pad offset in mosfet.py** — change was harmless but unnecessary (LVS fix was in deck, not geometry)
- Monte Carlo optimization — klayout.db in-process for 10k+ geometric variants
- LLM-assisted DRC deck generator

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

---

## Session 16: 2026-03-04 — Error hints plan + coverage gap analysis

### Done
- **Coverage gap analysis** — Identified all untested error paths in the 6% gap: OSError subprocess failures, timeouts, missing DRC decks, OS-specific config detection, PCell validation guards. Mapped each to user-facing impact (cryptic vs actionable).
- **Error hints plan** (`docs/tmp-error-hints-plan.md`) — Full implementation plan for centralized `error_hints.py` module (regex→hint mapping), `hint` field on Job model/DB, API wiring, and amber tooltip UI in frontend. ~270 lines across 10 files.

### Decisions
- Centralized hint mapping (single `error_hints.py`) over adding `hint` field to each error class — keeps presentation concerns separate, easier to maintain
- Always-visible hint box (amber below red error) over hover tooltip — more accessible, no hidden info

### Next
- Implement error hints plan (done in Session 17)
