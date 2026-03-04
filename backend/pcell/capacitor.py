"""MIM capacitor parameterized cell generator for SKY130."""

from __future__ import annotations

from dataclasses import dataclass

import gdstk

from backend.pcell.base import PCellGenerator, PCellResult


# ---------------------------------------------------------------------------
# SKY130 design rules relevant to MIM capacitor layout
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _SKY130MIMRules:
    """SKY130 design rules for MIM capacitor construction.

    Values in microns sourced from the SKY130 DRM.
    SKY130 MIM cap: bottom plate = met3, top plate = CAPM (cap metal).
    Routing: bottom plate via met3 → via2 → met2, top plate via CAPM → via3 → met4.
    """

    grid: float = 0.005

    # MIM capacitance density
    cap_per_um2_fF: float = 2.0  # ~2 fF/um^2

    # CAPM (89/44) — capacitor metal layer (top plate)
    capm_min_width: float = 1.000  # capm.1 (conservative)
    capm_min_spacing: float = 0.840  # capm.2 (conservative)
    capm_enc_by_met3: float = 0.140  # m3 must extend beyond CAPM edges

    # Met3 (70/20) — bottom plate
    met3_min_width: float = 0.300  # m3.1
    met3_min_spacing: float = 0.300  # m3.2

    # Via2 (69/44) — met2 to met3
    via2_size: float = 0.200  # via2.1a
    via2_spacing: float = 0.200  # via2.2
    via2_enc_by_met2: float = 0.040  # via2.4 (met2 enclosure of via2)
    via2_enc_by_met3: float = 0.065  # m3.4 (met3 enclosure of via2)
    via2_enc_by_met3_adj: float = 0.085  # via2.5 (met3 enc of via2 on 2 adj edges)

    # Via3 (70/44) — met3 to met4
    via3_size: float = 0.200  # via3.1
    via3_spacing: float = 0.200  # via3.2
    via3_enc_by_met3: float = 0.060  # via3.4 (met3 enclosure of via3)
    via3_enc_by_met4: float = 0.065  # m4.3 (met4 enclosure of via3)

    # Met2 (69/20) — bottom plate routing
    met2_min_width: float = 0.140  # m2.1
    met2_enc_via: float = 0.055  # m2.4 (met2 enclosure of via)

    # Met4 (71/20) — top plate routing
    met4_min_width: float = 0.300  # m4.1
    met4_min_spacing: float = 0.300  # m4.2


SKY130_MIM = _SKY130MIMRules()

# ---------------------------------------------------------------------------
# GDS layer numbers (layer, datatype)
# ---------------------------------------------------------------------------
LYR_MET2 = (69, 20)
LYR_VIA2 = (69, 44)
LYR_MET3 = (70, 20)
LYR_VIA3 = (70, 44)
LYR_MET4 = (71, 20)
LYR_CAPM = (89, 44)  # capacitor metal (MIM top plate)

LYR_MET3_PIN = (70, 16)
LYR_MET3_LBL = (70, 5)
LYR_MET4_PIN = (71, 16)
LYR_MET4_LBL = (71, 5)


class MIMCapGenerator(PCellGenerator):
    """Generate a SKY130 MIM capacitor layout.

    Structure (bottom to top):
        met3 (bottom plate) — via2 array → met2 (BOT pin routing)
        CAPM (top plate, on met3) — via3 array → met4 (TOP pin routing)

    The CAPM layer sits on top of met3 with met3 extending beyond CAPM
    on all sides (enclosure rule). Via3 contacts on the CAPM plate
    connect up to met4 for the TOP terminal. Via2 contacts outside the
    CAPM region on met3 connect down to met2 for the BOT terminal.
    """

    def param_schema(self) -> dict:
        return {
            "w_um": {
                "type": "float",
                "description": "Capacitor width in microns",
                "min": SKY130_MIM.capm_min_width,
            },
            "l_um": {
                "type": "float",
                "description": "Capacitor length in microns",
                "min": SKY130_MIM.capm_min_width,
            },
        }

    def validate_params(self, params: dict) -> None:
        w_um = params.get("w_um")
        if w_um is None or w_um < SKY130_MIM.capm_min_width:
            raise ValueError(
                f"w_um must be >= {SKY130_MIM.capm_min_width} um "
                f"(SKY130 min CAPM width), got {w_um}"
            )

        l_um = params.get("l_um")
        if l_um is None or l_um < SKY130_MIM.capm_min_width:
            raise ValueError(
                f"l_um must be >= {SKY130_MIM.capm_min_width} um "
                f"(SKY130 min CAPM length), got {l_um}"
            )

    def generate(self, params: dict) -> PCellResult:
        self.validate_params(params)

        w_um: float = params["w_um"]
        l_um: float = params["l_um"]

        snap = self.snap_to_grid
        r = SKY130_MIM

        w = snap(w_um)
        gl = snap(l_um)

        # CAPM plate dimensions (the capacitor area)
        capm_w = w
        capm_l = gl

        # Met3 bottom plate: extends beyond CAPM by enclosure rule on all sides.
        # Additionally, extend met3 below CAPM to create a landing pad for via2
        # (BOT terminal connection to met2). The enclosure strip alone (0.14um)
        # is too narrow for via2 (0.2um) + margins.
        enc = snap(r.capm_enc_by_met3)

        # BOT landing pad height: enough for via2 array + met3 enclosure
        bot_pad_h = snap(
            r.via2_enc_by_met3
            + r.via2_size
            + r.via2_enc_by_met3
            + r.capm_min_spacing  # extra spacing from CAPM to via2 region
        )

        met3_x0 = snap(-enc)
        met3_y0 = snap(-enc - bot_pad_h)
        met3_x1 = snap(capm_w + enc)
        met3_y1 = snap(capm_l + enc)

        cell_name = self.cell_name_format("sky130", "mimcap", W=w, L=gl)
        cell = gdstk.Cell(cell_name)

        # 1. Met3 — bottom plate (includes landing pad below CAPM) ---------------
        cell.add(
            gdstk.rectangle(
                (met3_x0, met3_y0),
                (met3_x1, met3_y1),
                layer=LYR_MET3[0],
                datatype=LYR_MET3[1],
            )
        )

        # 2. CAPM — top plate (capacitor metal) ---------------------------------
        cell.add(
            gdstk.rectangle(
                (0, 0),
                (capm_w, capm_l),
                layer=LYR_CAPM[0],
                datatype=LYR_CAPM[1],
            )
        )

        # 3. Via3 array on CAPM → met4 (TOP terminal) ---------------------------
        via3_positions = self._via_array(
            0,
            0,
            capm_w,
            capm_l,
            r.via3_size,
            r.via3_spacing,
            margin=snap(r.via3_enc_by_met3),  # via3 inset from CAPM edge
        )
        for vx, vy in via3_positions:
            self._add_contact_square(cell, vx, vy, r.via3_size, LYR_VIA3)

        # 4. Met4 — TOP pin routing (covers via3 array) -------------------------
        if via3_positions:
            met4_margin = snap(r.via3_enc_by_met4)
            met4_x0 = snap(via3_positions[0][0] - r.via3_size / 2 - met4_margin)
            met4_y0 = snap(via3_positions[0][1] - r.via3_size / 2 - met4_margin)
            met4_x1 = snap(via3_positions[-1][0] + r.via3_size / 2 + met4_margin)
            met4_y1 = snap(via3_positions[-1][1] + r.via3_size / 2 + met4_margin)

            # Enforce met4 min width
            if (met4_x1 - met4_x0) < r.met4_min_width:
                cx = snap((met4_x0 + met4_x1) / 2)
                met4_x0 = snap(cx - r.met4_min_width / 2)
                met4_x1 = snap(cx + r.met4_min_width / 2)
            if (met4_y1 - met4_y0) < r.met4_min_width:
                cy = snap((met4_y0 + met4_y1) / 2)
                met4_y0 = snap(cy - r.met4_min_width / 2)
                met4_y1 = snap(cy + r.met4_min_width / 2)

            cell.add(
                gdstk.rectangle(
                    (met4_x0, met4_y0),
                    (met4_x1, met4_y1),
                    layer=LYR_MET4[0],
                    datatype=LYR_MET4[1],
                )
            )

            # TOP pin label
            cell.add(
                gdstk.Label(
                    "TOP",
                    (snap((met4_x0 + met4_x1) / 2), snap((met4_y0 + met4_y1) / 2)),
                    layer=LYR_MET4_LBL[0],
                    texttype=LYR_MET4_LBL[1],
                )
            )

        # 5. Via2 array on met3 landing pad → met2 (BOT terminal) ---------------
        # Place via2s in the extended met3 area below the CAPM region.
        via2_positions = self._via_array(
            met3_x0,
            met3_y0,
            met3_x1,
            snap(-enc),
            r.via2_size,
            r.via2_spacing,
            margin=snap(r.via2_enc_by_met3_adj),
        )

        for vx, vy in via2_positions:
            self._add_contact_square(cell, vx, vy, r.via2_size, LYR_VIA2)

        # 6. Met2 — BOT pin routing (covers via2 array) -------------------------
        if via2_positions:
            met2_margin = snap(r.via2_enc_by_met2)
            met2_x0 = snap(via2_positions[0][0] - r.via2_size / 2 - met2_margin)
            met2_y0 = snap(via2_positions[0][1] - r.via2_size / 2 - met2_margin)
            met2_x1 = snap(via2_positions[-1][0] + r.via2_size / 2 + met2_margin)
            met2_y1 = snap(via2_positions[-1][1] + r.via2_size / 2 + met2_margin)

            # Enforce met2 min width
            if (met2_x1 - met2_x0) < r.met2_min_width:
                cx = snap((met2_x0 + met2_x1) / 2)
                met2_x0 = snap(cx - r.met2_min_width / 2)
                met2_x1 = snap(cx + r.met2_min_width / 2)
            if (met2_y1 - met2_y0) < r.met2_min_width:
                cy = snap((met2_y0 + met2_y1) / 2)
                met2_y0 = snap(cy - r.met2_min_width / 2)
                met2_y1 = snap(cy + r.met2_min_width / 2)

            cell.add(
                gdstk.rectangle(
                    (met2_x0, met2_y0),
                    (met2_x1, met2_y1),
                    layer=LYR_MET2[0],
                    datatype=LYR_MET2[1],
                )
            )

            # BOT pin label on met2
            cell.add(
                gdstk.Label(
                    "BOT",
                    (snap((met2_x0 + met2_x1) / 2), snap((met2_y0 + met2_y1) / 2)),
                    layer=LYR_MET3_LBL[0],
                    texttype=LYR_MET3_LBL[1],
                )
            )

        # Calculate capacitance
        area_um2 = w * gl
        cap_fF = area_um2 * r.cap_per_um2_fF

        return PCellResult(
            cell=cell,
            cell_name=cell_name,
            params={"w_um": w, "l_um": gl},
            metadata={
                "capacitance_fF": round(cap_fF, 3),
                "area_um2": round(area_um2, 6),
                "cap_density_fF_per_um2": r.cap_per_um2_fF,
                "n_via3": len(via3_positions),
                "n_via2": len(via2_positions),
            },
        )

    # ---- helpers ---------------------------------------------------------------

    @staticmethod
    def _via_array(
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        via_size: float,
        via_spacing: float,
        margin: float,
    ) -> list[tuple[float, float]]:
        """Compute a 2D array of via center positions within a rectangle.

        Args:
            x0, y0, x1, y1: Bounding rectangle.
            via_size: Square via dimension.
            via_spacing: Min spacing between vias.
            margin: Inset from rectangle edges (enclosure).

        Returns:
            List of (cx, cy) via center positions.
        """
        snap = PCellGenerator.snap_to_grid

        # Available area after margin
        ax0 = snap(min(x0, x1) + margin)
        ay0 = snap(min(y0, y1) + margin)
        ax1 = snap(max(x0, x1) - margin)
        ay1 = snap(max(y0, y1) - margin)

        avail_w = ax1 - ax0
        avail_h = ay1 - ay0

        if avail_w < via_size or avail_h < via_size:
            return []

        pitch = snap(via_size + via_spacing)

        # Number of vias in each direction
        nx = 1 + int((avail_w - via_size) / pitch)
        ny = 1 + int((avail_h - via_size) / pitch)

        # Center the array
        span_x = (nx - 1) * pitch
        span_y = (ny - 1) * pitch
        start_x = snap(ax0 + (avail_w - span_x) / 2)
        start_y = snap(ay0 + (avail_h - span_y) / 2)

        positions = []
        for iy in range(ny):
            for ix in range(nx):
                cx = snap(start_x + ix * pitch)
                cy = snap(start_y + iy * pitch)
                positions.append((cx, cy))

        return positions

    @staticmethod
    def _add_contact_square(
        cell: gdstk.Cell,
        cx: float,
        cy: float,
        size: float,
        layer_dt: tuple[int, int],
    ) -> None:
        """Add a square contact centered at (cx, cy)."""
        snap = PCellGenerator.snap_to_grid
        half = snap(size / 2)
        cell.add(
            gdstk.rectangle(
                (snap(cx - half), snap(cy - half)),
                (snap(cx + half), snap(cy + half)),
                layer=layer_dt[0],
                datatype=layer_dt[1],
            )
        )
