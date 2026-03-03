# PROGRESS-agentic-drc

> Sessions 1-4 archived → `docs/archive/archive-progress-agentic-drc.md`

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

---

## Session 6: 2026-03-03 — Adaptive DRC for resource-constrained environments

### Done
- **Adaptive DRC strategy** — Auto-selects thread count and DRC mode (deep vs tiled) based on GDS file size. Three tiers: <20MB (4 threads, deep), 20-80MB (2 threads, deep), >80MB (1 thread, tiled 1000µm).
- **DRC deck updated** — Conditional tiling in `sky130A_mr.drc` reads `$drc_mode` param.
- **API response** — Includes `strategy` block with mode/threads/tile_size_um.
- **12 new tests** — `TestAdaptiveStrategy` (7), `TestBuildCommandWithStrategy` (4), `TestRunIncludesStrategy` (1).

### Decisions
- Strategy computed from `gds_path.stat().st_size` — no user input needed
- DRC deck backward-compatible (defaults to deep if `$drc_mode` not set)

### Next
- Integration tests with real KLayout
- Memory profiling
- Vendor DRC deck

---

## Session 5: 2026-03-02 — Phase 4 complete (Production Hardening)

### Done
- **P4-1 through P4-5** — Fix-apply re-DRC loop, SQLite persistence (WAL), report export (JSON/CSV/HTML), Docker+CI/CD, density fill strategy.
- **273 unit tests total**, all passing.

### Decisions
- SQLite WAL mode for concurrent reads during DRC
- `apply-and-recheck` endpoint auto-sets `complete` if violations reach 0
- Density fill uses PDK spacing/width rules, 25% default target

### Next
- KLayout CLI for integration tests
- Vendor SKY130 DRC deck
- PDK authoring guide
