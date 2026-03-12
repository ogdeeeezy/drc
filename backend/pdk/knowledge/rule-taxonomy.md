# Rule Taxonomy

How DRC rule types work across all semiconductor processes.

## RuleType Definitions

| RuleType | Geometric Meaning | What Violates |
|----------|-------------------|---------------|
| `min_width` | Minimum extent of a shape in its narrowest dimension | Shape narrower than threshold anywhere along its length |
| `min_spacing` | Minimum gap between two shapes on the same layer | Edge-to-edge distance between non-connected shapes < threshold |
| `min_area` | Minimum enclosed area of a shape | Polygon area (µm²) below threshold |
| `min_enclosure` | Minimum overlap of an outer layer around an inner layer | Inner shape extends beyond outer shape, or overlap < threshold |
| `min_extension` | Minimum overshoot of one layer beyond another | Layer A doesn't extend far enough past layer B edge |
| `exact_size` | Fixed width AND height requirement (typically vias/contacts) | Shape dimensions != exact value (both W and H must match) |
| `off_grid` | All vertices must lie on manufacturing grid | Any vertex coordinate not an integer multiple of grid_um |
| `min_density` | Minimum metal fill density in a window | Metal area / window area < threshold (per tile, usually 100µm×100µm) |

## Fix Priority Ordering

Priority determines the order in which violations are fixed. Lower number = fixed first.

```
1. shorts       — Electrical failure: two nets connected that shouldn't be
2. off_grid     — Manufacturing failure: shapes can't be printed
3. min_width    — Structural failure: lines too thin to survive etching
4. min_spacing  — Reliability failure: lines too close may short under variation
5. min_enclosure — Connection failure: via not fully covered by metal
6. min_area     — Manufacturability: small shapes may not print reliably
```

### Why This Order

- **Shorts first**: they affect electrical correctness and may invalidate other fixes
- **Off-grid early**: fixing off-grid often resolves downstream width/spacing issues
- **Width before spacing**: growing a narrow shape may push it into a neighbor's space (creating a spacing violation that gets fixed in the next pass)
- **Enclosure after spacing**: enclosure fixes grow metal, which could create new spacing violations — better to have spacing already resolved
- **Area last**: area fixes (growing shapes) are lowest risk and often self-resolve after other fixes

## Confidence Calibration

### What Makes High Confidence
- Single layer involved
- Fix direction is unambiguous (only one valid move)
- No neighboring shapes within 2× the rule threshold
- Shape is isolated (large clearance on all sides)
- Fix magnitude is small relative to shape size (< 20% change)

### What Makes Medium Confidence
- Two layers involved (enclosure, extension)
- Multiple valid fix directions exist
- Neighboring shapes present but not immediately adjacent
- Fix requires moving (not just growing) geometry
- Shape has moderate aspect ratio (2:1 to 5:1)

### What Makes Low Confidence
- Three or more layers affected
- Fix may create new violations on other layers
- Dense area with many nearby shapes
- Short between shapes on same net (may be intentional)
- Fix magnitude is large relative to shape (> 50% change)
- Human intent is ambiguous (is this a routing or a device?)

## Validation Upgrade/Downgrade Criteria

After applying a fix, confidence may be upgraded or downgraded based on post-fix DRC:

### Upgrade (medium → high)
- Post-fix DRC shows zero new violations
- No shapes within 1× threshold of modified geometry
- The fix was a simple grow operation (no repositioning)

### Downgrade (high → medium, medium → low)
- Post-fix DRC introduces new violations
- A neighboring shape is now within 1× threshold
- The fix required more than 1 grid unit of adjustment
- Multiple fix iterations were needed for the same violation
