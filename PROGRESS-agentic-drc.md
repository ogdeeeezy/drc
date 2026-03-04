# PROGRESS-agentic-drc

> Sessions 1-14 archived → `docs/archive/archive-progress-agentic-drc.md`

---

## Session 16: 2026-03-04 — Error hints plan + coverage gap analysis

### Done
- **Coverage gap analysis** — Identified all untested error paths in the 6% gap: OSError subprocess failures, timeouts, missing DRC decks, OS-specific config detection, PCell validation guards. Mapped each to user-facing impact (cryptic vs actionable).
- **Error hints plan** (`docs/tmp-error-hints-plan.md`) — Full implementation plan for centralized `error_hints.py` module (regex→hint mapping), `hint` field on Job model/DB, API wiring, and amber tooltip UI in frontend. ~270 lines across 10 files.

### Decisions
- Centralized hint mapping (single `error_hints.py`) over adding `hint` field to each error class — keeps presentation concerns separate, easier to maintain
- Always-visible hint box (amber below red error) over hover tooltip — more accessible, no hidden info

### Next
- **Implement error hints plan** — `docs/tmp-error-hints-plan.md` has full spec. Start with `error_hints.py` + tests, then Job model, then routes, then frontend.
- Branch protection — Enable in GitHub repo settings
- Monte Carlo optimization — klayout.db in-process for 10k+ geometric variants

---

## Session 15: 2026-03-04 — Fix strategy test coverage 91% → 94%

### Done
- **Fix strategy tests** — 38 new tests covering all 4 strategy files: shrink-fix path, extension directions, collision branches, degenerate polygon handling, polygon-finding fallbacks, edge-pair geometry. 703 unit tests passing.
- **Coverage pushed** — spacing.py 62→98%, area.py 67→96%, width.py 71→95%, short.py 72→95%. Overall 91% → 94%.

### Next
- Error hints + remaining coverage (done in Session 16 planning)

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
