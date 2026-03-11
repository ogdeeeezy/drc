# PROGRESS-agentic-drc

> Sessions 1-20 archived → `docs/archive/archive-progress-agentic-drc.md`

---

## Session 23: 2026-03-10 — DRC marker visualization implementation

### Done
- **Marker visualization implemented** (uncommitted) — Red filled rectangles rendered in WebGL at each marker bbox. Selected marker bright (0.6 alpha), others dim (0.25 alpha). Zoom targets individual marker bbox instead of combined violation bbox.
- **Per-marker navigation** — Prev/Next buttons in ViolationList cycle through markers with wrap-around. "Marker N of M" displayed in both ViolationList and ViolationOverlay.
- **5 files changed** — WebGLRenderer (setMarkers/clearMarkers), LayoutViewer (per-marker zoom), ViolationList (nav UI), ViolationOverlay (marker info), App.tsx (selectedMarkerIndex state).
- **Frontend builds clean** — TypeScript `--noEmit` and Vite production build pass with 0 errors.

### Next
- Commit marker visualization + test in browser with real DRC violations
- Commit + redeploy multi-finger bus routing (uncommitted from Session 21)
- Monte Carlo optimization
- LLM-assisted DRC deck generator

---

## Session 22: 2026-03-10 — DRC marker visualization diagnosis + plan

### Done
- **Diagnosed marker navigation bug** — User reported m1.2 violations (5 markers) show no errors at listed coordinates. Root cause: frontend zooms to combined bbox of all markers, no individual marker rectangles rendered on layout.
- **Full coordinate chain traced** — DRC deck → .lyrdb edge-pair XML → violation_parser.py → API response → frontend. Data is correct; visualization is the gap.
- **Implementation plan designed** — WebGLRenderer marker rectangles, per-marker zoom navigation (prev/next), ViolationList expansion, overlay "Marker N of M" display. Plan at `~/.claude/plans/cryptic-snuggling-goose.md`.

### Decisions
- Markers rendered as filled rectangles in WebGL (not CSS overlay) so they pan/zoom with layout
- Zoom to individual marker bbox (not combined), auto-select first marker on violation click

### Next
- Implement marker visualization plan (done in Session 23)

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
