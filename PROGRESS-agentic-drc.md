# PROGRESS-agentic-drc

> Sessions 1-22 archived → `docs/archive/archive-progress-agentic-drc.md`

---

## Session 24: 2026-03-11 — Three-tier PDK knowledge system

### Done
- **PDK knowledge layer** — Created `KnowledgeBase` class (`backend/pdk/knowledge.py`) that assembles universal + PDK-specific knowledge files for LLM-assisted features.
- **Universal knowledge docs** — `drc-universal.md` (grid precision, boolean ops, fix confidence, KLayout quirks, LVS universals) + `rule-taxonomy.md` (rule types, fix priority, confidence calibration).
- **SKY130 knowledge doc** — `sky130-knowledge.md` with DRM errata, device class mappings, contact stack, layer gotchas, multi-finger spacing.
- **Schema extension** — Added `drc_flags`, `device_classes`, `layer_stack` optional fields to `PDKConfig` in `schema.py`. Backward compatible (all default None).
- **DRC runner flag resolution** — `build_command()` now prefers `pdk.drc_flags` over hardcoded `DEFAULT_DRC_FLAGS`, with per-call override support.
- **Singleton accessor** — `get_knowledge_base()` in `deps.py` (same pattern as `get_pdk_registry()`).
- **25 new tests** — `test_knowledge.py` (11), `test_schema_extended.py` (10), `test_drc_runner_flags.py` (4). All pass. 762 total tests, 0 regressions.
- **Docs updated** — `pdk-authoring.md` now documents new fields, knowledge.md template, and updated checklist.

### Decisions
- Knowledge files are Markdown (not JSON) — optimized for LLM context injection, easy to author
- Flag priority: per-call override > pdk.drc_flags > DEFAULT_DRC_FLAGS — preserves backward compat
- `task` param in `get_context()` reserved for future filtering but currently passes all content

### Next
- Wire `KnowledgeBase.get_context()` into LLM-assisted deck generation pipeline
- Monte Carlo optimization
- More PDKs (GF180, ASAP7) — adding a PDK now means adding files, not code

---

## Session 23: 2026-03-11 — Marker visualization shipped + parser fix + UX improvements

### Done
- **Marker visualization** (`d62e65b`) — WebGL red filled rectangles at each marker bbox. Selected marker bright (0.6 alpha), others dim (0.25 alpha). Per-marker zoom, Prev/Next navigation, "Marker N of M" display. 5 frontend files.
- **Parser pipe separator fix** (`8dcf249`) — KLayout uses `|` (not just `/`) as edge-pair separator. ct.2, psdm.1, MR_licon.SP.1 went from 0 to correct marker counts. 29 total markers now parse from ESD .lyrdb.
- **Minimum zoom span** (`7e89df2`) — Added 3µm floor so sub-micron edge-pair markers are visible in context. Fixed trackpad pinch distortion via non-passive wheel handler.
- **Logo reset** (`f83133d`) — Clicking "Agentic DRC" resets all state and returns to upload screen.
- **All deployed to production** — 4 deploys to VPS, all live at sky130drc.duckdns.org.

### Decisions
- MIN_ZOOM_SPAN = 3µm — balances seeing the marker vs surrounding context
- Non-passive wheel listener via native `addEventListener` (React `onWheel` is passive, can't preventDefault)

### Next
- Monte Carlo optimization
- LLM-assisted DRC deck generator
- More PDKs (GF180, ASAP7)

---

## Session 22: 2026-03-10 — DRC marker visualization diagnosis + plan

### Done
- **Diagnosed marker navigation bug** — User reported m1.2 violations (5 markers) show no errors at listed coordinates. Root cause: frontend zooms to combined bbox of all markers, no individual marker rectangles rendered on layout.
- **Full coordinate chain traced** — DRC deck → .lyrdb edge-pair XML → violation_parser.py → API response → frontend. Data is correct; visualization is the gap.
- **Implementation plan designed** — Plan at `~/.claude/plans/cryptic-snuggling-goose.md`.

### Decisions
- Markers rendered as filled rectangles in WebGL (not CSS overlay) so they pan/zoom with layout
- Zoom to individual marker bbox (not combined), auto-select first marker on violation click

### Next
- Implement marker visualization plan (done in Session 23)
