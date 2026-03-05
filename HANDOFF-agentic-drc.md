# HANDOFF — agentic-drc

## What This Is
Open-source DRC tool — PVS alternative for semiconductor layout verification. Checks GDSII layouts against PDK design rules, triages violations, suggests geometric fixes, auto-applies high-confidence fixes, runs LVS, and generates parameterized cells.

## Current State
- **Phases 1-5**: ALL COMPLETE (33/33 stories)
- **730 unit + 12 E2E tests passing**, 95% coverage, frontend builds clean
- **GitHub**: https://github.com/ogdeeeezy/drc — all pushed to main
- **Branch protection**: `lint`, `test`, `frontend` required on main (strict mode)
- **Tagged**: `pre-llm-deck-gen-pre-mc` on `affd54d`
- **LVS deck fixed**: mos4 extraction now works (pre-split SD, clipped gate, bridged connectivity)
- **Uncommitted changes**: database.py migration, sky130A.lvs deck fix, mosfet.py T-pad offset

## How to Run
- Backend: `make run` (uvicorn on port 8000)
- Frontend: `make frontend` (Vite dev on 5173, proxies /api)
- Tests: `.venv/bin/python -m pytest tests/unit/ -q --cov=backend` (730 tests, 95%)
- E2E: `.venv/bin/python -m pytest tests/integration/test_e2e_phase5.py -v -s` (requires KLayout)

## Immediate Next
1. **Test full LVS flow end-to-end** — restart server, generate NMOS, upload, DRC, upload netlist, run LVS, verify match
2. **Add substrate taps to PCells** — body terminal needs ptap/ntap for LVS net matching (body auto-named "$5" without taps)
3. **Revert T-pad offset in mosfet.py** — harmless but unnecessary change (lines ~185-200, the `snap(diff_h + r.grid)` / `snap(-r.grid)` offsets)
4. Monte Carlo optimization — klayout.db in-process
5. LLM-assisted DRC deck generator

## Key LVS Fix (Session 18)
Root cause: KLayout `mos4` extraction requires SD layer already split into separate S/D polygons. Fix in `sky130A.lvs`:
- `nsd = (diff & nsdm) - gate_poly` — pre-splits at gate edges
- `gate_in_active = gate_poly & active` — clips gate for correct L
- `connect(gate_in_active, gate_poly)` — bridges extraction to routing

## Gotchas
- SKY130 DRC deck defaults ALL rule groups to disabled — `DEFAULT_DRC_FLAGS` fixes this
- KLayout macOS needs Gatekeeper bypass: `sudo xattr -r -d com.apple.quarantine /Applications/KLayout/klayout.app`
- .lvsdb format is NOT XML — it's S-expression text (custom parser in lvs_parser.py)
- MOSFET min contactable W is ~0.26um (licon_size + 2*licon_enc_by_diff), not 0.15um
- **KLayout mos4 won't auto-split continuous diff** — SD layer must be pre-split by subtracting gate_poly
- **Gate L computed from gate area / W** — must clip gate to active area or endcaps inflate L
- DRC deck rule descriptions can lie — via2.5 says "m3 enclosure" but checks m2
