# DRC Universal Knowledge

Process-independent DRC knowledge that applies to ANY PDK.

## Grid Precision & IEEE 754 Floating-Point

- All coordinates in GDSII are integer multiples of the database unit (typically 1nm or 0.001µm)
- Floating-point arithmetic introduces representation error: `0.1 + 0.2 != 0.3`
- Always convert to integer grid units before comparison. Snap to grid *before* writing GDS
- Edge case: a shape at 0.1749999µm on a 0.005µm grid can round to 0.170 or 0.175 depending on rounding mode
- Conservative rounding: always round violations UP to worst-case, and fixes DOWN to safe-case
- Use `round(value / grid) * grid` for grid snapping, never truncation

## Boolean Operation Pitfalls

- Subtraction (A NOT B) can clip geometry to zero-width slivers that trigger false DRC hits
- Slivers from boolean ops often have sub-grid vertices — snap results to grid after every boolean
- Union before subtraction reduces sliver risk
- KLayout's `sized(0)` is NOT a no-op: it cleans self-intersections and merges coincident edges

## Conservative Rounding Principles

- When computing a fix, round the final geometry to the nearest grid point that makes the violation *more* clean, not less
- Width fixes: round width UP to next grid multiple
- Spacing fixes: round gap UP to next grid multiple
- Enclosure fixes: round overlap UP to next grid multiple
- Off-grid fixes: snap to nearest grid point (this is exact)

## Rule Description Unreliability

- DRC deck descriptions are human-written and frequently inaccurate
- SKY130 example: via2.5 says "min enclosure of via2 by met2" but actually checks met3
- Always derive rule semantics from the deck code (which layers are referenced), not the description string
- The `rule_id` → `layer`/`related_layer` mapping in `pdk.json` is the authoritative source
- When parsing violation categories from `.lyrdb`, match on `rule_id` prefix, not description text

## Fix Confidence Framework

| Confidence | Criteria | Examples |
|-----------|----------|----------|
| **high** | Single-layer, removal-safe, no collision risk | Off-grid snap, width grow on isolated shape |
| **medium** | Multi-layer or needs collision check | Enclosure grow (might violate spacing on adjacent), spacing move |
| **low** | Requires human judgment | Short resolution, density fill, same-net merge |

- **Removal safe**: deleting the violating geometry cannot create a new violation (e.g., removing a sliver)
- **Multi-layer flagged**: any fix that changes geometry on layer A must re-check rules involving layer B
- **Collision detection**: before moving/growing a shape, check if the new footprint overlaps or violates spacing to neighbors

## KLayout Format Quirks

### .lyrdb (DRC report)
- XML-based, but category names use ` : ` (space-colon-space) as separator between rule_id and description
- Violation coordinates are in database units (need conversion to µm via the file's dbu attribute)
- Edge pairs encode *two* edges: the violating edge and the reference edge. Both are needed for fix direction
- Empty categories (0 violations) may or may not appear depending on deck — don't assume

### .lvsdb (LVS report)
- S-expression format (Lisp-like), NOT XML
- Device class names are not standardized across PDKs — "NMOS" vs "nmos" vs "sky130_fd_pr__nfet_01v8"
- Net names with special characters need quoting in the S-expression
- Cross-reference section maps extracted↔schematic devices; parse both sides

### Category Quoting
- KLayout sometimes wraps category names in quotes in newer versions
- Parser must handle both `<name>m1.1 : ...</name>` and `<name>"m1.1 : ..."</name>`

## LVS Extraction Universals

- **Device class mapping**: every PDK names transistor models differently. The `device_classes` field in pdk.json provides the canonical mapping
- **Diffusion pre-split**: LVS extractors often pre-split diffusion at poly crossings. A single drawn diff region may become 2+ extracted source/drain regions
- **Endcap inflation**: poly extensions beyond diff (endcaps) are geometric, not electrical. LVS ignores them but DRC checks them
- **Body tap requirement**: extracted devices need bulk/body connections. Missing taps → LVS mismatch, not DRC error
- **Parallel device merging**: two transistors sharing source, drain, and gate may be merged into one wider device by the extractor

## Aspect Ratio Branching

All fix strategies must consider aspect ratio:
- **Wide shapes** (W >> H): prefer vertical adjustment
- **Tall shapes** (H >> W): prefer horizontal adjustment
- **Square-ish shapes**: either direction works; prefer the one with more clearance to neighbors
- Threshold: use aspect ratio > 3:1 as the branching criterion
- This applies to width fixes, spacing moves, and enclosure grows
