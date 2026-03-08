"""Phase 6: Realistic solder joint examples.

Tests the KSE pipeline with practical BGA/LGA geometries:
  1. Simple solder ball (standard 0.3mm BGA)
  2. Elongated pad (chip component, circular approximation)
  3. Wide flat pad (LGA-like thin solder)
  4. 20x20 ball array with SMD/NSMD circular/square pads

Each case is tested with 80%, 100%, 120% solder volume.
"""

import math

import numpy as np
import pytest

from kse.core.stl_reader import STLReader
from kse.core.surface_fitter import SurfaceFitter
from kse.core.constraint_gen import ConstraintGenerator
from kse.core.geometry_builder import GeometryBuilder
from kse.core.fe_writer import FEWriter, SolderJointConfig

from .helpers.stl_from_constraints import generate_flat_pad_stl
from .helpers.realistic_stl import generate_square_pad_stl
from .helpers.se_runner import run_kse_fe

# ---------------------------------------------------------------------------
# Physical constants (CGS) — typical SAC305 solder at reflow
# ---------------------------------------------------------------------------
T_SOLDER = 480.0       # surface tension, erg/cm²
RHO_SOLDER = 8.5       # density, g/cm³
G = 980.0              # gravity, cm/s²
CONTACT_ANGLE = 90.0   # degrees (90° → cos=0, no wetting energy)

_PI = math.pi

# ---------------------------------------------------------------------------
# Nominal volume helper: V = factor * π * r² * h
# The factor 1.3 accounts for meniscus shape (from Brakke's BGA examples).
# ---------------------------------------------------------------------------
def _nominal_volume(r_bottom, r_top, height, factor=1.3):
    r_min = min(r_bottom, r_top)
    return factor * _PI * r_min**2 * height


# ===================================================================
# Single Joint Configurations
# ===================================================================
SINGLE_JOINTS = {
    # ---- Case 1: Simple solder ball (0.3mm BGA) ----
    "simple_ball": {
        "bottom": {"center": [0, 0, 0], "radius": 0.0125},       # 0.25mm dia
        "top":    {"center": [0, 0, 0.020], "radius": 0.0125},    # 0.20mm standoff
        "n_segments": 8,
        "description": "Standard 0.3mm BGA ball, 0.25mm NSMD pads",
    },
    # ---- Case 2: Elongated pad (chip component, 0.8mm × 0.25mm approx) ----
    # Actual rectangular 0.08cm × 0.025cm → equivalent circle r = √(A/π)
    "elongated_pad": {
        "bottom": {"center": [0, 0, 0], "radius": 0.02523},      # equiv r
        "top":    {"center": [0, 0, 0.010], "radius": 0.02523},   # 0.10mm standoff
        "n_segments": 8,
        "description": "Elongated chip pad 0.8×0.25mm (circular approximation)",
    },
    # ---- Case 3: Wide flat pad (LGA-like, 0.8mm dia) ----
    "wide_flat_pad": {
        "bottom": {"center": [0, 0, 0], "radius": 0.040},        # 0.8mm dia
        "top":    {"center": [0, 0, 0.005], "radius": 0.040},     # 0.05mm standoff
        "n_segments": 12,
        "description": "Wide LGA pad 0.8mm dia, very thin solder layer",
    },
}

VOLUME_FACTORS = [0.8, 1.0, 1.2]

# ===================================================================
# 20×20 Array Configuration
# ===================================================================
ARRAY_PITCH = 0.050    # 0.5mm pitch
ARRAY_ROWS = 20
ARRAY_COLS = 20
ARRAY_HEIGHT = 0.020   # 0.2mm standoff

# Four quadrant pad types
QUADRANT_PADS = {
    "smd_circle": {
        "radius": 0.0100,             # 0.2mm dia mask opening
        "stl_func": "circle",
        "quadrant": (range(0, 10), range(0, 10)),
    },
    "nsmd_circle": {
        "radius": 0.0135,             # 0.27mm dia copper pad
        "stl_func": "circle",
        "quadrant": (range(0, 10), range(10, 20)),
    },
    "smd_square": {
        "radius": 0.01015,            # equiv circle for 0.018cm square
        "actual_side": 0.018,
        "stl_func": "square",
        "quadrant": (range(10, 20), range(0, 10)),
    },
    "nsmd_square": {
        "radius": 0.01354,            # equiv circle for 0.024cm square
        "actual_side": 0.024,
        "stl_func": "square",
        "quadrant": (range(10, 20), range(10, 20)),
    },
}


def _get_pad_type_for_position(row, col):
    """Return the pad type name for a given array position."""
    for name, cfg in QUADRANT_PADS.items():
        rows, cols = cfg["quadrant"]
        if row in rows and col in cols:
            return name
    return "smd_circle"  # fallback


# ===================================================================
# Pipeline helper
# ===================================================================
def _build_joint_fe(
    tmp_path, r_bottom, r_top, h, volume,
    center_bottom=None, center_top=None,
    n_segments=8, fe_name="joint.fe",
    stl_func_bottom="circle", stl_func_top="circle",
    side_bottom=None, side_top=None,
):
    """Run the full KSE pipeline for one solder joint → .fe file."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    stl_dir = tmp_path / "stls"
    stl_dir.mkdir(parents=True, exist_ok=True)

    if center_bottom is None:
        center_bottom = np.array([0.0, 0.0, 0.0])
    else:
        center_bottom = np.asarray(center_bottom, dtype=float)
    if center_top is None:
        center_top = np.array([0.0, 0.0, h])
    else:
        center_top = np.asarray(center_top, dtype=float)

    is_rect = (stl_func_bottom == "square" and side_bottom is not None)

    # Generate bottom STL
    if is_rect:
        generate_square_pad_stl(
            center_bottom, side_bottom,
            output_path=stl_dir / "bottom.stl",
        )
    else:
        generate_flat_pad_stl(
            center_bottom, r_bottom,
            output_path=stl_dir / "bottom.stl",
        )

    # Generate top STL
    if stl_func_top == "square" and side_top is not None:
        generate_square_pad_stl(
            center_top, side_top or side_bottom,
            output_path=stl_dir / "top.stl",
        )
    else:
        generate_flat_pad_stl(
            center_top, r_top,
            output_path=stl_dir / "top.stl",
        )

    # Read + fit
    reader_a = STLReader(stl_dir / "bottom.stl")
    reader_b = STLReader(stl_dir / "top.stl")

    patch_a = reader_a.extract_patch(center_bottom, r_bottom)
    patch_b = reader_b.extract_patch(center_top, r_top)

    fitter = SurfaceFitter()
    fit_a = fitter.fit(patch_a)
    fit_b = fitter.fit(patch_b)

    cgen = ConstraintGenerator()

    if is_rect:
        # Rectangular pad: energy/content integrals on constraints, no boundary
        c_a = cgen.generate_surface_constraint(
            fit_a, 1,
            contact_angle=CONTACT_ANGLE, tension=T_SOLDER,
            solder_density=RHO_SOLDER, gravity=G,
            use_boundary_integrals=True,
        )
        c_b = cgen.generate_surface_constraint(
            fit_b, 2,
            contact_angle=CONTACT_ANGLE, tension=T_SOLDER,
            solder_density=RHO_SOLDER, gravity=G,
            use_boundary_integrals=True,
        )

        builder = GeometryBuilder(n_segments=n_segments)
        sy = side_top if side_top is not None else side_bottom
        geom = builder.build_rectangular(
            fit_a, fit_b, side_bottom, sy, volume,
        )

        config = SolderJointConfig(
            tension=T_SOLDER,
            density=RHO_SOLDER,
            gravity=G,
            radius=r_bottom,
            volume=volume,
            contact_angle_A=CONTACT_ANGLE,
            contact_angle_B=CONTACT_ANGLE,
        )

        writer = FEWriter()
        fe_path = tmp_path / fe_name
        writer.write_single(fe_path, geom, [c_a, c_b], [], config)
    else:
        # Circular pad: parametric boundary + rim constraint
        c_a = cgen.generate_surface_constraint(
            fit_a, 1,
            contact_angle=CONTACT_ANGLE, tension=T_SOLDER,
            solder_density=RHO_SOLDER, gravity=G,
            use_boundary_integrals=False,
        )
        c_b = cgen.generate_surface_constraint(
            fit_b, 2,
            contact_angle=CONTACT_ANGLE, tension=T_SOLDER,
            solder_density=RHO_SOLDER, gravity=G,
            use_boundary_integrals=False,
        )
        rim = cgen.generate_rim_constraint(fit_a, 3, r_bottom)
        bdry = cgen.generate_parametric_boundary(
            fit_b, 1, r_top,
            solder_density=RHO_SOLDER, gravity=G,
        )

        builder = GeometryBuilder(n_segments=n_segments)
        geom = builder.build(fit_a, fit_b, r_bottom, volume)

        config = SolderJointConfig(
            tension=T_SOLDER,
            density=RHO_SOLDER,
            gravity=G,
            radius=r_bottom,
            volume=volume,
            contact_angle_A=CONTACT_ANGLE,
            contact_angle_B=CONTACT_ANGLE,
        )

        writer = FEWriter()
        fe_path = tmp_path / fe_name
        writer.write_single(fe_path, geom, [c_a, c_b, rim], [bdry], config)

    return fe_path


# ===================================================================
# Test Classes
# ===================================================================

class TestSimpleBall:
    """Case 1: Standard 0.3mm BGA ball between 0.25mm circular pads."""

    @pytest.mark.parametrize("vol_factor", VOLUME_FACTORS,
                             ids=["80pct", "100pct", "120pct"])
    def test_generates_valid_fe(self, vol_factor, tmp_path):
        """Pipeline produces a valid .fe file."""
        cfg = SINGLE_JOINTS["simple_ball"]
        r = cfg["bottom"]["radius"]
        h = cfg["top"]["center"][2]
        vol = _nominal_volume(r, r, h) * vol_factor

        fe = _build_joint_fe(
            tmp_path / f"ball_{vol_factor}",
            r, r, h, vol,
            n_segments=cfg["n_segments"],
        )
        assert fe.exists()
        text = fe.read_text()
        assert "constraint 1" in text
        assert "boundary 1" in text
        assert "bodies" in text

        print(f"\nsimple_ball vol_factor={vol_factor}: volume={vol:.4e} cm³")

    @pytest.mark.parametrize("vol_factor", VOLUME_FACTORS,
                             ids=["80pct", "100pct", "120pct"])
    def test_se_runs(self, vol_factor, evolver_path, tmp_path):
        """SE evolves without errors."""
        cfg = SINGLE_JOINTS["simple_ball"]
        r = cfg["bottom"]["radius"]
        h = cfg["top"]["center"][2]
        vol = _nominal_volume(r, r, h) * vol_factor

        fe = _build_joint_fe(
            tmp_path / f"ball_{vol_factor}" / "build",
            r, r, h, vol,
            n_segments=cfg["n_segments"],
        )
        result = run_kse_fe(fe, evolver_path, tmp_path / f"ball_{vol_factor}" / "run")

        assert result.success, f"SE failed: {result.stderr}"
        assert result.energy is not None and result.energy > 0
        assert result.volume is not None

        vol_err = abs(result.volume - vol) / vol
        print(f"\nsimple_ball {vol_factor}: E={result.energy:.4e}, "
              f"V={result.volume:.4e} (target={vol:.4e}, err={vol_err:.2%}), "
              f"verts={result.n_vertices}, faces={result.n_faces}")

        assert vol_err < 0.05, f"Volume error {vol_err:.2%} > 5%"


class TestElongatedPad:
    """Case 2: Elongated chip pad (0.8mm × 0.25mm, circular approximation)."""

    @pytest.mark.parametrize("vol_factor", VOLUME_FACTORS,
                             ids=["80pct", "100pct", "120pct"])
    def test_generates_valid_fe(self, vol_factor, tmp_path):
        cfg = SINGLE_JOINTS["elongated_pad"]
        r = cfg["bottom"]["radius"]
        h = cfg["top"]["center"][2]
        vol = _nominal_volume(r, r, h) * vol_factor

        fe = _build_joint_fe(
            tmp_path / f"elong_{vol_factor}",
            r, r, h, vol,
            n_segments=cfg["n_segments"],
        )
        assert fe.exists()
        print(f"\nelongated_pad vol_factor={vol_factor}: volume={vol:.4e} cm³")

    @pytest.mark.parametrize("vol_factor", VOLUME_FACTORS,
                             ids=["80pct", "100pct", "120pct"])
    def test_se_runs(self, vol_factor, evolver_path, tmp_path):
        cfg = SINGLE_JOINTS["elongated_pad"]
        r = cfg["bottom"]["radius"]
        h = cfg["top"]["center"][2]
        vol = _nominal_volume(r, r, h) * vol_factor

        fe = _build_joint_fe(
            tmp_path / f"elong_{vol_factor}" / "build",
            r, r, h, vol,
            n_segments=cfg["n_segments"],
        )
        result = run_kse_fe(fe, evolver_path, tmp_path / f"elong_{vol_factor}" / "run")

        assert result.success, f"SE failed: {result.stderr}"
        assert result.energy is not None and result.energy > 0
        assert result.volume is not None

        vol_err = abs(result.volume - vol) / vol
        print(f"\nelongated_pad {vol_factor}: E={result.energy:.4e}, "
              f"V={result.volume:.4e} (err={vol_err:.2%}), "
              f"verts={result.n_vertices}, faces={result.n_faces}")
        assert vol_err < 0.05


class TestWideFlatPad:
    """Case 3: Wide LGA pad (0.8mm dia, 0.05mm standoff)."""

    @pytest.mark.parametrize("vol_factor", VOLUME_FACTORS,
                             ids=["80pct", "100pct", "120pct"])
    def test_generates_valid_fe(self, vol_factor, tmp_path):
        cfg = SINGLE_JOINTS["wide_flat_pad"]
        r = cfg["bottom"]["radius"]
        h = cfg["top"]["center"][2]
        vol = _nominal_volume(r, r, h) * vol_factor

        fe = _build_joint_fe(
            tmp_path / f"wide_{vol_factor}",
            r, r, h, vol,
            n_segments=cfg["n_segments"],
        )
        assert fe.exists()
        print(f"\nwide_flat_pad vol_factor={vol_factor}: volume={vol:.4e} cm³")

    @pytest.mark.parametrize("vol_factor", VOLUME_FACTORS,
                             ids=["80pct", "100pct", "120pct"])
    def test_se_runs(self, vol_factor, evolver_path, tmp_path):
        cfg = SINGLE_JOINTS["wide_flat_pad"]
        r = cfg["bottom"]["radius"]
        h = cfg["top"]["center"][2]
        vol = _nominal_volume(r, r, h) * vol_factor

        fe = _build_joint_fe(
            tmp_path / f"wide_{vol_factor}" / "build",
            r, r, h, vol,
            n_segments=cfg["n_segments"],
        )
        result = run_kse_fe(fe, evolver_path, tmp_path / f"wide_{vol_factor}" / "run")

        assert result.success, f"SE failed: {result.stderr}"
        assert result.energy is not None and result.energy > 0
        assert result.volume is not None

        vol_err = abs(result.volume - vol) / vol
        print(f"\nwide_flat_pad {vol_factor}: E={result.energy:.4e}, "
              f"V={result.volume:.4e} (err={vol_err:.2%}), "
              f"verts={result.n_vertices}, faces={result.n_faces}")
        assert vol_err < 0.05


class TestArray20x20:
    """Case 4: 20×20 BGA array with four pad types.

    Quadrant layout:
        rows 0-9,  cols 0-9:   SMD circular  (r=0.010)
        rows 0-9,  cols 10-19: NSMD circular (r=0.0135)
        rows 10-19, cols 0-9:  SMD square    (side=0.018, r_eq=0.01015)
        rows 10-19, cols 10-19: NSMD square  (side=0.024, r_eq=0.01354)
    """

    def _array_center(self, row, col):
        """Compute (x, y) center for array position."""
        # Array centered at origin
        x = (col - (ARRAY_COLS - 1) / 2.0) * ARRAY_PITCH
        y = (row - (ARRAY_ROWS - 1) / 2.0) * ARRAY_PITCH
        return x, y

    def _build_array_joint(self, row, col, vol_factor, tmp_path):
        """Build one joint from the array at (row, col)."""
        pad_name = _get_pad_type_for_position(row, col)
        pad_cfg = QUADRANT_PADS[pad_name]
        r = pad_cfg["radius"]
        side = pad_cfg.get("actual_side")
        stl_func = pad_cfg["stl_func"]

        x, y = self._array_center(row, col)
        center_b = [x, y, 0.0]
        center_t = [x, y, ARRAY_HEIGHT]

        vol = _nominal_volume(r, r, ARRAY_HEIGHT) * vol_factor

        fe = _build_joint_fe(
            tmp_path,
            r, r, ARRAY_HEIGHT, vol,
            center_bottom=center_b,
            center_top=center_t,
            n_segments=8,
            fe_name=f"arr_r{row:02d}_c{col:02d}.fe",
            stl_func_bottom=stl_func,
            stl_func_top=stl_func,
            side_bottom=side,
            side_top=side,
        )
        return fe, pad_name, vol

    def test_generate_all_fe_files(self, tmp_path):
        """Generate .fe files for all 400 positions (no SE run)."""
        count = 0
        for row in range(ARRAY_ROWS):
            for col in range(ARRAY_COLS):
                fe, pad_name, vol = self._build_array_joint(
                    row, col, 1.0, tmp_path / f"r{row:02d}_c{col:02d}",
                )
                assert fe.exists(), f"Failed to generate ({row},{col}) {pad_name}"
                count += 1

        print(f"\nGenerated {count} .fe files for {ARRAY_ROWS}×{ARRAY_COLS} array")
        assert count == ARRAY_ROWS * ARRAY_COLS

    @pytest.mark.parametrize("row,col,expected_type", [
        # Corners
        (0, 0, "smd_circle"),
        (0, 19, "nsmd_circle"),
        (19, 0, "smd_square"),
        (19, 19, "nsmd_square"),
        # Quadrant centers
        (5, 5, "smd_circle"),
        (5, 15, "nsmd_circle"),
        (15, 5, "smd_square"),
        (15, 15, "nsmd_square"),
        # Array center (row 10, col 10 → nsmd_square quadrant)
        (10, 10, "nsmd_square"),
    ])
    def test_array_sample_se_runs(self, row, col, expected_type,
                                   evolver_path, tmp_path):
        """Run SE on representative array positions."""
        fe, pad_name, vol = self._build_array_joint(
            row, col, 1.0, tmp_path / "build",
        )
        assert pad_name == expected_type

        result = run_kse_fe(fe, evolver_path, tmp_path / "run")

        assert result.success, f"SE failed at ({row},{col}) {pad_name}: {result.stderr}"
        assert result.energy is not None and result.energy > 0
        assert result.volume is not None

        vol_err = abs(result.volume - vol) / vol
        print(f"\narray({row},{col}) {pad_name}: E={result.energy:.4e}, "
              f"V={result.volume:.4e} (err={vol_err:.2%}), r={QUADRANT_PADS[pad_name]['radius']}")
        assert vol_err < 0.05

    @pytest.mark.parametrize("vol_factor", VOLUME_FACTORS,
                             ids=["80pct", "100pct", "120pct"])
    @pytest.mark.parametrize("pad_type", [
        "smd_circle", "nsmd_circle", "smd_square", "nsmd_square",
    ])
    def test_volume_variation(self, pad_type, vol_factor, evolver_path, tmp_path):
        """Each pad type works at 80%, 100%, 120% volume."""
        cfg = QUADRANT_PADS[pad_type]
        r = cfg["radius"]
        side = cfg.get("actual_side")
        stl_func = cfg["stl_func"]

        vol = _nominal_volume(r, r, ARRAY_HEIGHT) * vol_factor

        fe = _build_joint_fe(
            tmp_path / "build",
            r, r, ARRAY_HEIGHT, vol,
            n_segments=8,
            stl_func_bottom=stl_func,
            stl_func_top=stl_func,
            side_bottom=side,
            side_top=side,
        )

        result = run_kse_fe(fe, evolver_path, tmp_path / "run")

        assert result.success, f"SE failed: {pad_type} vol={vol_factor}: {result.stderr}"
        assert result.energy > 0
        assert result.volume is not None

        vol_err = abs(result.volume - vol) / vol
        print(f"\n{pad_type} vol={vol_factor}: E={result.energy:.4e}, "
              f"V={result.volume:.4e} (err={vol_err:.2%})")
        assert vol_err < 0.05, f"Volume error {vol_err:.2%}"


class TestDiagnosticSummary:
    """Print a summary table of all single-joint cases."""

    def test_summary_table(self, evolver_path, tmp_path):
        """Generate and run all single joints, print summary table."""
        rows = []
        for case_name, cfg in SINGLE_JOINTS.items():
            r = cfg["bottom"]["radius"]
            h = cfg["top"]["center"][2]
            n_seg = cfg["n_segments"]

            for vf in VOLUME_FACTORS:
                vol = _nominal_volume(r, r, h) * vf
                label = f"{case_name}_{int(vf*100)}pct"

                fe = _build_joint_fe(
                    tmp_path / label / "build",
                    r, r, h, vol,
                    n_segments=n_seg,
                )
                result = run_kse_fe(
                    fe, evolver_path, tmp_path / label / "run",
                )

                if result.success:
                    vol_err = abs(result.volume - vol) / vol if vol > 0 else 0
                    rows.append({
                        "case": label,
                        "r": r, "h": h, "vol": vol,
                        "energy": result.energy,
                        "vol_actual": result.volume,
                        "vol_err": vol_err,
                        "verts": result.n_vertices,
                        "faces": result.n_faces,
                        "status": "PASS" if vol_err < 0.05 else "WARN",
                    })
                else:
                    rows.append({
                        "case": label,
                        "r": r, "h": h, "vol": vol,
                        "energy": None, "vol_actual": None,
                        "vol_err": None, "verts": 0, "faces": 0,
                        "status": f"FAIL: {result.stderr[:60]}",
                    })

        # Print summary
        print(f"\n{'='*100}")
        print(f"{'Case':<30} {'r(cm)':>8} {'h(cm)':>8} {'V_target':>12} "
              f"{'Energy':>12} {'V_actual':>12} {'V_err':>8} {'Mesh':>12} {'Status':>6}")
        print(f"{'-'*100}")
        for r in rows:
            if r["energy"] is not None:
                print(f"{r['case']:<30} {r['r']:>8.4f} {r['h']:>8.4f} "
                      f"{r['vol']:>12.4e} {r['energy']:>12.4e} "
                      f"{r['vol_actual']:>12.4e} {r['vol_err']:>7.2%} "
                      f"{r['verts']:>5}v/{r['faces']:>5}f {r['status']:>6}")
            else:
                print(f"{r['case']:<30} {r['r']:>8.4f} {r['h']:>8.4f} "
                      f"{r['vol']:>12.4e} {'N/A':>12} {'N/A':>12} {'N/A':>8} "
                      f"{'0/0':>12} {r['status']}")
        print(f"{'='*100}")

        # At least all should succeed
        for r in rows:
            assert "FAIL" not in r["status"], f"{r['case']}: {r['status']}"
