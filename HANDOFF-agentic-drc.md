# HANDOFF — agentic-drc

## What This Is
Open-source DRC (Design Rule Check) tool — PVS alternative for semiconductor layout verification. Deterministic rules-based expert system that checks GDSII layouts against PDK design rules, triages violations, and suggests geometric fixes.

## Immediate Next Steps
1. Initialize Python project: `pyproject.toml`, venv with Python 3.12, install deps (gdstk, klayout, fastapi, pydantic, rtree)
2. Build Phase 1 (Core DRC Engine) — 4 stories in order: PDK schema → Layout manager → DRC runner → Violation parser
3. Install KLayout CLI (`brew install klayout`) — needed for batch DRC execution
4. Vendor the SKY130 DRC deck from `efabless/mpw_precheck` (`sky130A_mr.drc`)

## Key Architecture Decisions
- **KLayout subprocess** for DRC (not reimplementing rules in Python) — uses community-tested SKY130 deck
- **gdstk** for GDSII read/write/modify, **klayout.rdb** for .lyrdb violation parsing
- **PDK-agnostic**: everything parameterized by `pdk.json` config — layer maps, rule thresholds, fix weights
- **Fix priority**: shorts > off-grid > width > spacing > enclosure > area > density
- **MVP is suggest-only** — auto-apply is Phase 4+

## Context Needed
- Plan file with full architecture: `~/.claude/plans/delegated-hopping-pixel.md`
- Contains: directory structure, PDK schema, class hierarchy, API endpoints, fix algorithms, testing strategy
- SKY130 rules reference: https://skywater-pdk.readthedocs.io/en/main/rules/periphery.html

## Open Questions
- None — scope is clear, plan is approved

## Hot Files
- `~/.claude/plans/delegated-hopping-pixel.md` — the full implementation plan (READ THIS FIRST)
- `~/agentic-drc/` — empty project directory, ready for scaffolding
