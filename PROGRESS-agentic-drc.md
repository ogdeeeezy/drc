# PROGRESS-agentic-drc

> Sessions 1-12 archived → `docs/archive/archive-progress-agentic-drc.md`

---

## Session 15: 2026-03-04 — Fix strategy test coverage 91% → 94%

### Done
- **Fix strategy tests** — 38 new tests covering all 4 strategy files: shrink-fix path, extension directions, collision branches, degenerate polygon handling, polygon-finding fallbacks, edge-pair geometry. 703 unit tests passing.
- **Coverage pushed** — spacing.py 62→98%, area.py 67→96%, width.py 71→95%, short.py 72→95%. Overall 91% → 94%.

### Next
- **Branch protection** — Enable in GitHub repo settings: require `lint`, `test`, `frontend` to pass
- Monte Carlo optimization — klayout.db in-process for 10k+ geometric variants
- LLM-assisted DRC deck generator — auto-generate rules from DRM tables

---

## Session 14: 2026-03-04 — CI/CD enhancement + API test coverage

### Done
- **CI/CD enhanced** (`7881088`) — Split lint job, added pytest-cov, KLayout integration job (continue-on-error), concurrency group. `pytest-cov>=5.0` added to dev deps.
- **API route test coverage** (`01d1ef0`) — 69 new tests covering error paths across all API routes (drc, export, fix, layout, lvs, upload). Coverage 86% → 91%. 665 unit tests passing.
- **Coverage analysis documented** — Added practical limits note to `docs/tmp-cicd-plan.md`: 95% achievable, true 100% impractical due to KLayout subprocess paths and OS-specific config.

### Decisions
- Target 95% coverage floor, not 100% — remaining 9% is defensive error handling best verified by integration tests
- CI integration job uses `continue-on-error: true` — KLayout apt install may not work on all GitHub runners

### Next
- Fix strategy tests (done in Session 15)

---

## Session 13: 2026-03-04 — MIM cap DRC-clean + auto-fix confidence

### Done
- **MIM capacitor DRC-clean** (`b63629b`) — Root cause: via2.5 in SKY130 DRC deck checks `m2.enclosing(via2, 0.085)` (met2, not met3 as description says). Met2 pad margin was 0.040 (via2.4) instead of 0.085 (via2.5). Added `via2_enc_by_met2_adj` constant. **All PCells now 0 violations.**
- **Stream C: MinSpacingFix confidence promotion** (`ebaa65a`) — Move fixes promoted to `FixConfidence.high` when: (1) deficit <= rule value, (2) no same-layer polygon collision within min_spacing of moved position. Collision check uses `SpatialIndex.query_nearby()`. Shrink fixes stay at medium. 596 unit + 12 E2E passing.
- **CI/CD plan drafted** — `docs/tmp-cicd-plan.md` with full enhancement plan for `.github/workflows/ci.yml`. Was interrupted before implementation.

### Decisions
- via2.5 DRC deck bug: description says "m3 enclosure" but code checks m2. Documented in HANDOFF gotchas.
- Shrink fixes intentionally kept at medium confidence — shrinking polygons risks width/area violations

### Next
- CI/CD implementation (done in Session 14)
