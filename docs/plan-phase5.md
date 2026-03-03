# Phase 5 Plan — Auto-Fix, PCell Generator, LVS

## Overview

Three features that take agentic-drc from "violation reporter" to "layout co-pilot":
1. **Auto-fix loop** — fully automated fix-apply-recheck with human audit trail
2. **PCell generator** — auto-generate DRC-clean GDS from component specs
3. **LVS checker** — schematic vs layout verification

---

## Feature 1: Auto-Fix Loop

### What
Endpoint that automatically applies high-confidence fixes and loops until clean or stalled. Human stays in the loop via flagging and audit trail.

### API
```
POST /api/jobs/{job_id}/fix/auto
Body: { "confidence_threshold": "high", "max_iterations": 10 }
```

### Design Requirements

**Human-in-the-loop flags** (every fix gets flagged for review if):
- Circuit intent unknown — fix may break connectivity or change device parameters
- Hallucination risk — fix engine's geometric suggestion hasn't been validated on this rule type before
- Cascading violation — fix touches multiple layers or has `creates_new_violations: true`
- Irreversible change — fix deletes polygons (cutting shorts, removing geometry)
- Low/medium confidence — below the user's confidence threshold

**Fix provenance log** (per fix, per iteration):
- Rule ID and violation category
- Before/after polygon coordinates
- Confidence level
- Iteration number
- Whether auto-applied or flagged for review
- Stored in SQLite alongside job data

**Regression detection**:
- Track violation count per category per iteration
- If same category oscillates (fix → new violation → fix → new violation), stop and flag as "oscillating — needs human"
- Max iteration cap (default 10) as hard stop

**Auto mode tiers**:
| Confidence | Action |
|-----------|--------|
| High + single layer + no new violations | Auto-apply |
| Medium OR multi-layer | Flag for review, skip in auto mode |
| Low OR deletion | Always flag, never auto-apply |

### Stories
- P5-AF-001: Auto-fix endpoint with iteration loop and confidence filtering
- P5-AF-002: Fix provenance log (SQLite table, queryable via API)
- P5-AF-003: Regression/oscillation detection with auto-stop
- P5-AF-004: Flagged fixes review endpoint (`GET /api/jobs/{id}/fix/flagged`)

### Effort: 3-5 days

---

## Feature 2: Parameterized Cell (PCell) Generator

### What
Generate DRC-clean GDS cells from component specifications. User says "NMOS W=1um L=0.15um fingers=4" and gets a GDS cell.

### API
```
POST /api/pcell/generate
Body: {
  "pdk": "sky130",
  "device_type": "nmos",
  "params": { "w_um": 1.0, "l_um": 0.15, "fingers": 4 }
}
Response: { "gds_url": "/api/pcell/{id}/download", "drc_clean": true, "violations": 0 }
```

### Supported Devices (SKY130 first)
1. **MOSFET** (nmos, pmos) — W, L, fingers, gate contacts (top/bottom/both)
2. **Poly resistor** — W, L, segments, head/tail contacts
3. **MIM capacitor** — W, L (area = capacitance)

### Design
- Each device type has a generator class that uses gdstk to build geometry
- Generator encodes PDK rules: poly pitch, diffusion extensions, contact placement, metal routing
- Output GDS is auto-checked against our DRC (self-validating)
- Templates are PDK-specific (one generator per device per PDK)

### Stories
- P5-PC-001: PCell framework + MOSFET generator (SKY130)
- P5-PC-002: Poly resistor generator (SKY130)
- P5-PC-003: MIM capacitor generator (SKY130)
- P5-PC-004: API endpoint + self-validation (generate → DRC → report)

### Effort: 2-3 weeks

---

## Feature 3: LVS Checker (Layout vs Schematic)

### What
Verify that a GDS layout implements the same circuit as a SPICE netlist. Uses KLayout's built-in LVS engine (same subprocess pattern as DRC).

### API
```
POST /api/jobs/{job_id}/lvs
Body: { "netlist_path": "circuit.spice" }  (or upload file)
Response: {
  "match": false,
  "mismatches": [
    { "type": "missing_device", "name": "M1", "expected": "nmos W=1u L=0.15u" },
    { "type": "net_mismatch", "layout_net": "net3", "schematic_net": "VDD" }
  ]
}
```

### Design
- KLayout LVS runs in batch mode: `klayout -b -r deck.lvs -rd input=layout.gds -rd schematic=circuit.spice -rd report=lvs.lvsdb`
- Need `.lvs` deck per PDK (defines device extraction rules — which layers form transistors, resistors, etc.)
- Parser reads `.lvsdb` report (XML, similar to `.lyrdb` for DRC)
- Frontend: mismatch list with device-level and net-level comparison

### Stories
- P5-LV-001: LVS runner (subprocess, same pattern as DRC runner)
- P5-LV-002: LVS report parser (.lvsdb XML)
- P5-LV-003: SKY130 LVS deck (extract devices from layout)
- P5-LV-004: API endpoints (upload netlist, run LVS, get mismatches)
- P5-LV-005: Frontend mismatch viewer

### Effort: 2-3 weeks

---

## Dependency: Lightweight In-Memory Geometry Engine

**Required for**: Monte Carlo optimization (future build), fast auto-fix validation

**Problem**: Current DRC shells out to KLayout (~minutes per run). Monte Carlo needs 10k+ checks. Can't subprocess 10k times.

**Options under research**:
- Existing Python geometry libraries with spatial indexing (Shapely, pygeos, rtree)
- KLayout's Python API (klayout.db) used in-process instead of subprocess
- Custom engine: rtree spatial index + width/spacing/enclosure checks on polygon edges
- Rust/C++ engine with Python bindings for speed

**Status**: Research agents dispatched — see results before committing to build-vs-buy.

---

## Execution Order

```
Phase 5a: Auto-Fix Loop (3-5 days)
  ├── No new dependencies
  └── Highest immediate value

Phase 5b: LVS Checker (2-3 weeks, can parallel with 5c)
  ├── Mirrors existing DRC architecture
  └── KLayout LVS engine is ready

Phase 5c: PCell Generator (2-3 weeks, can parallel with 5b)
  ├── Independent of DRC/LVS
  └── Feeds test cases into DRC

Phase 5d (future): Monte Carlo Optimization
  ├── Depends on: lightweight geometry engine (research pending)
  └── Builds on: auto-fix + PCell infrastructure
```

---

## Async DRC (Prerequisite)

DRC currently blocks the uvicorn worker thread. Before Phase 5, convert to async:
- Move KLayout subprocess to a background worker (asyncio.create_subprocess_exec or task queue)
- Return job_id immediately, poll for status
- Unblocks uploads and other API calls during DRC

**Effort**: 1-2 days. Should be done first.
