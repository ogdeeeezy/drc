# PROGRESS-agentic-drc

> Sessions 1-6 archived → `docs/archive/archive-progress-agentic-drc.md`

---

## Session 8: 2026-03-03 — CPU throttling, GitHub repo, PDK guide, Phase 5 plan

### Done
- **CPU throttling** (`1ef1730`) — Triple-layer: taskpolicy -b (macOS efficiency cores) + nice -n 10 + cpulimit -l 60%. Switched subprocess.run → Popen for PID access. Tested on 142MB ESD file.
- **DRC timeout bumped** — 300s → 2700s (45 min) for throttled large file runs.
- **E2E validated** — Full flow: upload 142MB SKY130 ESD → DRC (19 min throttled, tiled mode) → 11 violations found. All stages working.
- **PDK authoring guide** — `docs/pdk-authoring.md`: schema reference, DRC deck template, validation steps, checklist.
- **GitHub repo** — Created ogdeeeezy/drc, all commits pushed.
- **Phase 5 plan** — `docs/plan-phase5.md`: auto-fix loop, PCell generator, LVS checker. 3 features, 13 stories.
- **KLayout Python API research** — `pip install klayout` provides in-process DRC via Region API. 100-1000x faster than subprocess. Eliminates need for custom geometry engine for Monte Carlo.

### Decisions
- cpulimit alone ineffective on Apple Silicon — needs taskpolicy -b alongside it
- DRC blocks API thread — async execution is prerequisite for Phase 5
- Monte Carlo feasible via `klayout.db` Region.*_check() methods (no subprocess per sample)
- Auto-fix needs human flags for: circuit intent, hallucination risk, cascading violations, irreversible changes, low confidence

### Next
- **Phase 5a**: Auto-fix loop (3-5 days) — see `docs/plan-phase5.md`
- **Async DRC** prerequisite — move KLayout to background worker
- **Phase 5b/5c** in parallel: LVS checker + PCell generator
- Future: Monte Carlo layout optimization using klayout.db in-process

---

## Session 7: 2026-03-03 — KLayout integration, e2e tests, memory profiling, DRC flag fix

### Done
- **KLayout CLI confirmed** — Already installed at macOS app bundle, `_find_klayout()` auto-detects. Fixed 4 pre-existing unit tests that assumed KLayout was absent.
- **Latent DRC bug fixed** — SKY130 deck defaults all rule groups (feol/beol/offgrid) to disabled. Added `DEFAULT_DRC_FLAGS` dict to `DRCRunner.build_command()` so checks actually run. Configurable via `drc_flags` parameter.
- **E2E integration tests** — 8 tests in `tests/integration/test_e2e_drc.py`: clean/violating/multi-layer GDS, PDK mapping, adaptive strategy. All pass against real KLayout.
- **Memory profiling tests** — 9 tests in `tests/integration/test_memory_profiling.py`: RSS measurement across 10→20k polygon files, scaling data (~64 bytes/poly), 2GB budget guard.
- **Vendored SKY130 DRC deck** — `git add backend/pdk/configs/sky130/sky130A_mr.drc`, now tracked.
- **303 total tests** (286 unit + 17 integration), all passing. Lint clean.

### Decisions
- DRC runner enables feol/beol/offgrid/floating_met by default (overridable via `drc_flags` kwarg)
- Unit tests use explicit `klayout_binary=` arg to avoid depending on install state
- Memory profiling uses `resource.RUSAGE_CHILDREN` (peak RSS of subprocess), not parent process

### Next
- Write PDK authoring guide (`docs/pdk-authoring.md`)
- Consider async DRC execution (currently sync, blocks API thread)
- Add more PDKs beyond SKY130 (GF180, ASAP7)
- GitHub remote + CI setup
