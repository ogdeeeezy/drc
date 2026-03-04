# PROGRESS-agentic-drc

> Sessions 1-14 archived → `docs/archive/archive-progress-agentic-drc.md`

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

---

## Session 15: 2026-03-04 — Fix strategy test coverage 91% → 94%

### Done
- **Fix strategy tests** — 38 new tests covering all 4 strategy files: shrink-fix path, extension directions, collision branches, degenerate polygon handling, polygon-finding fallbacks, edge-pair geometry. 703 unit tests passing.
- **Coverage pushed** — spacing.py 62→98%, area.py 67→96%, width.py 71→95%, short.py 72→95%. Overall 91% → 94%.

### Next
- Error hints + remaining coverage (done in Session 16 planning)
