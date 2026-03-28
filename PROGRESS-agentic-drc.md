# PROGRESS-agentic-drc

> Sessions 1-23 archived → `docs/archive/archive-progress-agentic-drc.md`

---

## Session 26: 2026-03-28 — All-markers-at-once UX overhaul

### Done
- **All-markers view** (`3a24b8a`) — Replaced Prev/Next navigation with showing all markers simultaneously. Numbered circle labels on canvas, clickable marker list in sidebar, tooltip with rule/coords on selection.
- **Canvas click-to-select** (`3a24b8a`) — Hit-test in WebGLRenderer lets users click markers directly on canvas. Edge pairs now render for all markers (dim cyan), not just selected.
- **Deployed to production** — Rebuilt and deployed via Docker on VPS.

### Next
- Wire KnowledgeBase.get_context() into LLM-assisted deck generation
- Monte Carlo optimization
- More PDKs (GF180, ASAP7)

---

## Session 25: 2026-03-25 — Production recovery + marker visualization UX

### Done
- **Production recovery** — Caddy was stopped, port 8000 hijacked by Agent Mixing. Fixed: DRC remapped to port 8001, Caddy restarted+enabled, Caddyfile updated.
- **Firewall hardening** (`ufw`) — Port 443 locked to user IP + Cloudflare ranges. Investigated Cloudflare Tunnel (requires owned domain, deferred — DuckDNS can't be added to CF).
- **Double-click zoom-in** (`5bbf1ab`) — Double-click now zooms 3x at cursor. Press R to reset view.
- **Coordinate readout** (`5bbf1ab`) — Shows X/Y µm at cursor position (bottom-left overlay).
- **Pulsing crosshair + marker coords** (`d606676`) — Cyan pulsing crosshair at selected marker center. Coordinates shown in overlay badge and sidebar.
- **Edge pair rendering** (`d606676`) — Violating edges drawn as cyan lines on canvas.
- **Minimum marker size** (`9e8345b`) — Marker rectangles expand to 3% of viewport width minimum. Sub-micron violations now visible.
- **Sandbox memory fix** (`b0f2ef3`) — Increased from 512MB to 2GB. ESD GDS file was segfaulting gdstk.
- **Gitignore cleanup** (`73f21d3`) — Removed .DS_Store, data/, uv.lock from tracking.

### Decisions
- DuckDNS stays (no domain purchase until DRC project has revenue)
- DRC on port 8001 (Agent Mixing owns 8000 on VPS)
- Cloudflare Tunnel deferred — requires owned domain zone

### Next
- Marker visualization may need further refinement (user testing edge pair rendering)
- Wire KnowledgeBase.get_context() into LLM-assisted deck generation
- Monte Carlo optimization
- More PDKs (GF180, ASAP7)

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
