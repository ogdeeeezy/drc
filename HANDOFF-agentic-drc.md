# HANDOFF — agentic-drc

## What This Is
Open-source DRC (Design Rule Check) tool — PVS alternative for semiconductor layout verification. Deterministic rules-based expert system that checks GDSII layouts against PDK design rules, triages violations, and suggests geometric fixes.

## Current State
- **Phase 1 (Core DRC Engine)**: 2 of 4 stories done (P1-1 PDK schema, P1-2 layout manager)
- **75 unit tests**, all passing (`make test`)
- Python 3.12 venv at `.venv/`, all deps installed
- KLayout CLI NOT installed yet — needed for P1-3

## Immediate Next Steps
1. **Install KLayout CLI**: `brew install klayout` — needed for batch DRC subprocess
2. **Vendor SKY130 DRC deck**: Get `sky130A_mr.drc` from `efabless/mpw_precheck` repo → `backend/pdk/configs/sky130/`
3. **P1-3: KLayout DRC runner** — `backend/core/drc_runner.py`: subprocess wrapper for `klayout -b -r rules.drc`, temp file management, stdout/stderr capture, .lyrdb output path
4. **P1-4: Violation parser** — `backend/core/violation_parser.py` + `violation_models.py`: parse .lyrdb XML into Python Violation objects, map violations to PDK rule IDs

## Key Architecture Decisions
- **KLayout subprocess** for DRC (not reimplementing rules in Python) — uses community-tested SKY130 deck
- **gdstk** for GDSII read/write/modify, **klayout.rdb** for .lyrdb violation parsing
- **PDK-agnostic**: everything parameterized by `pdk.json` config — layer maps, rule thresholds, fix weights
- **Fix priority**: shorts > off-grid > width > spacing > enclosure > area > density
- **MVP is suggest-only** — auto-apply is Phase 4+

## Context Needed
- Plan file with full architecture: `~/.claude/plans/delegated-hopping-pixel.md`
- SKY130 pdk.json has 22 layers, 51 rules — all from official SkyWater PDK docs
- Manufacturing grid: 0.005um (5nm)

## Hot Files
- `backend/pdk/schema.py` — PDK config Pydantic models (GDSLayer, DesignRule, PDKConfig)
- `backend/pdk/configs/sky130/pdk.json` — Complete SKY130 config (22 layers, 51 rules, 7 connectivity entries)
- `backend/pdk/registry.py` — PDK discovery and loading with caching
- `backend/core/layout.py` — GDSII I/O via gdstk (load, save, flatten, modify polygons)
- `backend/core/geometry_utils.py` — Grid snap, bbox, area, distance calculations
- `backend/config.py` — App-level paths and defaults
