# HANDOFF — agentic-drc

## What This Is
Open-source DRC tool — PVS alternative for semiconductor layout verification. Checks GDSII layouts against PDK design rules, triages violations, suggests geometric fixes, auto-applies high-confidence fixes, runs LVS, and generates parameterized cells.

## Current State
- **Phases 1-5**: ALL COMPLETE (33/33 stories)
- **730 unit tests passing**, 95% coverage, frontend builds clean
- **GitHub**: https://github.com/ogdeeeezy/drc — all pushed to main
- **Branch protection**: `lint`, `test`, `frontend` required on main (strict mode)
- **Tagged**: `pre-llm-deck-gen-pre-mc` on `affd54d`
- **LVS fully working**: NMOS + PMOS single-finger DRC-clean and LVS-match verified E2E
- **Uncommitted**: mosfet.py (substrate taps), sky130A.lvs (same_device_classes), test assertions

## How to Run
- Backend: `make run` (uvicorn on port 8000)
- Frontend: `make frontend` (Vite dev on 5173, proxies /api)
- Tests: `.venv/bin/python -m pytest tests/unit/ -q --cov=backend` (730 tests, 95%)
- E2E: `.venv/bin/python -m pytest tests/integration/test_e2e_phase5.py -v -s` (requires KLayout)

## Immediate Next
1. **Commit substrate tap + LVS deck changes** — 3 modified files ready to commit
2. **Multi-finger LVS fix** — S/D met1 pads are disconnected for 2+ fingers; need met1 bus connecting shared S and D terminals
3. **Revert T-pad offset in mosfet.py** — harmless but unnecessary (lines ~185-200, `snap(diff_h + r.grid)` / `snap(-r.grid)` offsets)
4. Monte Carlo optimization — klayout.db in-process for 10k+ geometric variants
5. LLM-assisted DRC deck generator

## Key LVS Architecture
- **LVS deck** (`backend/pdk/configs/sky130/sky130A.lvs`): Pre-splits SD at gate, clips gate to active, bridges gate_in_active↔gate_poly, maps NMOS→SKY130_FD_PR__NFET_01V8
- **Substrate taps** (`backend/pcell/mosfet.py` section 10): ptap for NMOS / ntap for PMOS, placed left of diff with 0.130µm implant gap, full contact stack to met1 with "B" label
- **PMOS nwell**: Extended leftward to enclose ntap

## Gotchas
- SKY130 DRC deck defaults ALL rule groups to disabled — `DEFAULT_DRC_FLAGS` fixes this
- KLayout macOS needs Gatekeeper bypass: `sudo xattr -r -d com.apple.quarantine /Applications/KLayout/klayout.app`
- .lvsdb format is NOT XML — it's S-expression text (custom parser in lvs_parser.py)
- MOSFET min contactable W is ~0.26um (licon_size + 2*licon_enc_by_diff), not 0.15um
- **KLayout mos4 won't auto-split continuous diff** — SD layer must be pre-split by subtracting gate_poly
- **Gate L computed from gate area / W** — must clip gate to active area or endcaps inflate L
- **Multi-finger S/D pads are electrically disconnected** — each met1 pad is separate, needs bus for LVS
- DRC deck rule descriptions can lie — via2.5 says "m3 enclosure" but checks m2
