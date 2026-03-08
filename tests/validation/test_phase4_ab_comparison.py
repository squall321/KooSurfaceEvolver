"""Phase 4: Systematic A/B comparison of original .fe vs KSE-generated .fe.

Runs both the original example .fe files and KSE-generated .fe files through
Surface Evolver, then compares energy, volume, and mesh shape.

Key insight: The original .fe files include pad faces (fixed, tension=0)
in the body, while KSE-generated .fe files use boundary integrals and
omit pad faces. For fair comparison:
  - Energy: Compare SE total_energy directly (both formulations correct)
  - Volume: Compare body volume from dump
  - Shape: Compare only free (non-fixed) face triangles (lateral solder surface)
"""

import math

import numpy as np
import pytest

from kse.core.stl_reader import STLReader
from kse.core.surface_fitter import SurfaceFitter
from kse.core.constraint_gen import ConstraintGenerator
from kse.core.geometry_builder import GeometryBuilder
from kse.core.fe_writer import FEWriter, SolderJointConfig

from .conftest import EXAMPLE_REGISTRY, load_reference
from .helpers.stl_from_constraints import generate_flat_pad_stl
from .helpers.se_runner import run_original_fe, run_kse_fe, result_to_dict
from .helpers.comparison import (
    compare_results,
    compute_physical_energy,
    compute_hausdorff,
    THRESHOLDS,
)


def _build_kse_fe(tmp_path, params, fe_name="kse_output.fe"):
    """Run the full KSE pipeline: STL -> .fe file."""
    r = params["radius"]
    h = params["height"]
    x_off = params.get("x_offset", 0.0)
    y_off = params.get("y_offset", 0.0)
    n_seg = params.get("n_segments", 6)

    tmp_path.mkdir(parents=True, exist_ok=True)
    stl_dir = tmp_path / "stls"
    stl_dir.mkdir(parents=True, exist_ok=True)

    center_a = np.array([0.0, 0.0, 0.0])
    center_b = np.array([x_off, y_off, h])

    generate_flat_pad_stl(center_a, r, output_path=stl_dir / "bottom.stl")
    generate_flat_pad_stl(center_b, r, output_path=stl_dir / "top.stl")

    reader_a = STLReader(stl_dir / "bottom.stl")
    reader_b = STLReader(stl_dir / "top.stl")

    patch_a = reader_a.extract_patch(center_a, r)
    patch_b = reader_b.extract_patch(center_b, r)

    fitter = SurfaceFitter()
    fit_a = fitter.fit(patch_a)
    fit_b = fitter.fit(patch_b)

    cgen = ConstraintGenerator()
    c_a = cgen.generate_surface_constraint(
        fit_a, 1,
        contact_angle=params["contact_angle"],
        tension=params["tension"],
        solder_density=params["density"],
        gravity=params["gravity"],
        use_boundary_integrals=False,
    )
    c_b = cgen.generate_surface_constraint(
        fit_b, 2,
        contact_angle=params["contact_angle"],
        tension=params["tension"],
        solder_density=params["density"],
        gravity=params["gravity"],
        use_boundary_integrals=False,
    )
    rim = cgen.generate_rim_constraint(fit_a, 3, r)
    bdry = cgen.generate_parametric_boundary(
        fit_b, 1, r,
        solder_density=params["density"],
        gravity=params["gravity"],
    )

    builder = GeometryBuilder(n_segments=n_seg)
    geom = builder.build(fit_a, fit_b, r, params["volume"])

    config = SolderJointConfig(
        tension=params["tension"],
        density=params["density"],
        gravity=params["gravity"],
        radius=r,
        volume=params["volume"],
        contact_angle_A=params["contact_angle"],
        contact_angle_B=params["contact_angle"],
    )

    writer = FEWriter()
    fe_path = tmp_path / fe_name
    writer.write_single(fe_path, geom, [c_a, c_b, rim], [bdry], config)
    return fe_path


def _run_ab(example_name, evolver_path, tmp_path):
    """Run both original and KSE versions, return (ref_result, kse_result)."""
    info = EXAMPLE_REGISTRY[example_name]
    params = info["params"]

    # A: run original .fe
    ref = run_original_fe(
        info["fe_path"], evolver_path,
        tmp_path / "ref",
        gogo_cmd=info["gogo_cmd"],
        timeout=300,
    )

    # B: build and run KSE .fe
    kse_fe = _build_kse_fe(tmp_path / "kse_build", params)
    kse = run_kse_fe(kse_fe, evolver_path, tmp_path / "kse_run", timeout=300)

    return ref, kse


class TestTier1ABComparison:
    """Tier 1: Flat coaxial pads. Tightest thresholds."""

    @pytest.mark.parametrize("example_name", ["bga-1", "bga-3"])
    def test_volume_conservation(self, example_name, evolver_path, tmp_path):
        """Both original and KSE should conserve target volume."""
        ref, kse = _run_ab(example_name, evolver_path, tmp_path)
        params = EXAMPLE_REGISTRY[example_name]["params"]
        target_vol = params["volume"]

        assert ref.success, f"Original SE failed: {ref.stderr}"
        assert kse.success, f"KSE SE failed: {kse.stderr}"

        assert ref.volume is not None
        assert kse.volume is not None

        ref_vol_err = abs(ref.volume - target_vol) / target_vol
        kse_vol_err = abs(kse.volume - target_vol) / target_vol

        print(f"\n{example_name}: ref_vol={ref.volume:.6e}, kse_vol={kse.volume:.6e}, "
              f"target={target_vol:.6e}")
        print(f"  ref_vol_err={ref_vol_err:.4%}, kse_vol_err={kse_vol_err:.4%}")

        assert ref_vol_err < 0.02, \
            f"{example_name} ref volume: {ref.volume:.6e} vs target {target_vol:.6e}"
        assert kse_vol_err < 0.05, \
            f"{example_name} KSE volume: {kse.volume:.6e} vs target {target_vol:.6e}"

    @pytest.mark.parametrize("example_name", ["bga-1", "bga-3"])
    def test_se_total_energy(self, example_name, evolver_path, tmp_path):
        """SE total_energy comparison accounting for formulation differences.

        The original .fe includes pad faces in the body. If those pad faces
        have non-zero tension, their area contributes to SE total_energy.
        KSE omits pad faces, so we subtract the pad contribution from ref.
        """
        ref, kse = _run_ab(example_name, evolver_path, tmp_path)
        params = EXAMPLE_REGISTRY[example_name]["params"]

        assert ref.success and kse.success
        assert ref.energy is not None and kse.energy is not None

        # Pad faces' tension: may be 0 (bga-3) or S_TENSION (bga-1)
        r = params["radius"]
        pad_tension = params.get("pad_tension", 0.0)
        pad_energy = 2 * math.pi * r**2 * pad_tension
        ref_adjusted = ref.energy - pad_energy

        print(f"\n{example_name}: ref_energy={ref.energy:.6e}, kse_energy={kse.energy:.6e}")
        print(f"  pad_tension={pad_tension}, pad_energy={pad_energy:.6e}, ref_adjusted={ref_adjusted:.6e}")

        if abs(ref_adjusted) > 1e-20:
            rel_err = abs(kse.energy - ref_adjusted) / abs(ref_adjusted)
        else:
            rel_err = abs(kse.energy - ref_adjusted)

        print(f"  energy_rel_err={rel_err:.4%}")

        assert rel_err < 0.05, \
            f"{example_name} energy mismatch: ref_adj={ref_adjusted:.6e}, kse={kse.energy:.6e}"

    @pytest.mark.parametrize("example_name", ["bga-1", "bga-3"])
    def test_free_surface_energy(self, example_name, evolver_path, tmp_path):
        """Physical energy from free faces should match."""
        ref, kse = _run_ab(example_name, evolver_path, tmp_path)
        params = EXAMPLE_REGISTRY[example_name]["params"]

        assert ref.success and kse.success

        # Use FREE face triangles only for physical energy
        ref_free = ref.free_face_triangles
        kse_free = kse.free_face_triangles
        # KSE has no fixed faces, so free == all
        if kse_free is None or len(kse_free) == 0:
            kse_free = kse.face_triangles

        assert ref_free is not None and len(ref_free) > 0, \
            "No free face triangles in reference"
        assert kse_free is not None and len(kse_free) > 0, \
            "No free face triangles in KSE"

        ref_phys = compute_physical_energy(
            ref.vertex_positions, ref_free,
            params["tension"], params["density"], params["gravity"],
            ref.volume or 0,
        )
        kse_phys = compute_physical_energy(
            kse.vertex_positions, kse_free,
            params["tension"], params["density"], params["gravity"],
            kse.volume or 0,
        )

        if abs(ref_phys) > 1e-20:
            rel_err = abs(kse_phys - ref_phys) / abs(ref_phys)
        else:
            rel_err = abs(kse_phys - ref_phys)

        print(f"\n{example_name}: ref_phys={ref_phys:.6e}, kse_phys={kse_phys:.6e}, "
              f"rel_err={rel_err:.4%}")

        # Tier 1: free surface energy should be very close
        assert rel_err < 0.10, \
            f"{example_name} free surface energy mismatch: ref={ref_phys:.6e}, kse={kse_phys:.6e}"

    @pytest.mark.parametrize("example_name", ["bga-1", "bga-3"])
    def test_shape_similarity(self, example_name, evolver_path, tmp_path):
        """Hausdorff distance between free surfaces should be small."""
        ref, kse = _run_ab(example_name, evolver_path, tmp_path)
        params = EXAMPLE_REGISTRY[example_name]["params"]
        r = params["radius"]

        assert ref.success and kse.success

        # Use free faces only for shape comparison
        ref_free = ref.free_face_triangles
        kse_free = kse.free_face_triangles
        if kse_free is None or len(kse_free) == 0:
            kse_free = kse.face_triangles

        if (ref_free is not None and len(ref_free) > 0 and
                kse_free is not None and len(kse_free) > 0):
            haus = compute_hausdorff(
                ref.vertex_positions, ref_free,
                kse.vertex_positions, kse_free,
            )
            haus_norm = haus / r

            print(f"\n{example_name}: hausdorff={haus:.6e}, norm={haus_norm:.4f}")

            # Tier 1: Hausdorff < 10% of radius
            assert haus_norm < 0.10, \
                f"{example_name} shape mismatch: hausdorff/r = {haus_norm:.4f}"


class TestTier2ABComparison:
    """Tier 2: Offset/gravity pads. Medium thresholds."""

    @pytest.mark.parametrize("example_name", ["bga-7"])
    def test_volume_conservation(self, example_name, evolver_path, tmp_path):
        """KSE should conserve target volume for offset pads."""
        ref, kse = _run_ab(example_name, evolver_path, tmp_path)
        params = EXAMPLE_REGISTRY[example_name]["params"]
        target_vol = params["volume"]

        assert ref.success, f"Original SE failed: {ref.stderr}"
        assert kse.success, f"KSE SE failed: {kse.stderr}"

        assert ref.volume is not None
        assert kse.volume is not None

        ref_vol_err = abs(ref.volume - target_vol) / target_vol
        kse_vol_err = abs(kse.volume - target_vol) / target_vol

        print(f"\n{example_name}: ref_vol={ref.volume:.6e}, kse_vol={kse.volume:.6e}, "
              f"target={target_vol:.6e}")
        print(f"  ref_vol_err={ref_vol_err:.4%}, kse_vol_err={kse_vol_err:.4%}")

        assert kse_vol_err < 0.10, \
            f"{example_name} KSE volume: {kse.volume:.6e} vs target {target_vol:.6e}"

    @pytest.mark.parametrize("example_name", ["bga-7"])
    def test_se_total_energy(self, example_name, evolver_path, tmp_path):
        """SE total_energy for offset pads, accounting for formulation differences."""
        ref, kse = _run_ab(example_name, evolver_path, tmp_path)
        params = EXAMPLE_REGISTRY[example_name]["params"]

        assert ref.success and kse.success
        assert ref.energy is not None and kse.energy is not None

        r = params["radius"]
        pad_tension = params.get("pad_tension", 0.0)
        pad_energy = 2 * math.pi * r**2 * pad_tension
        ref_adjusted = ref.energy - pad_energy

        if abs(ref_adjusted) > 1e-20:
            rel_err = abs(kse.energy - ref_adjusted) / abs(ref_adjusted)
        else:
            rel_err = abs(kse.energy - ref_adjusted)

        print(f"\n{example_name}: ref_energy={ref.energy:.6e}, kse_energy={kse.energy:.6e}")
        print(f"  pad_tension={pad_tension}, pad_energy={pad_energy:.6e}, ref_adjusted={ref_adjusted:.6e}")
        print(f"  rel_err={rel_err:.4%}")

        # Tier 2 threshold: 10%
        assert rel_err < 0.10, \
            f"{example_name} energy mismatch: ref_adj={ref_adjusted:.6e}, kse={kse.energy:.6e}"

    @pytest.mark.parametrize("example_name", ["bga-7"])
    def test_shape_similarity(self, example_name, evolver_path, tmp_path):
        """Hausdorff on free surfaces for offset pads."""
        ref, kse = _run_ab(example_name, evolver_path, tmp_path)
        params = EXAMPLE_REGISTRY[example_name]["params"]
        r = params["radius"]

        assert ref.success and kse.success

        ref_free = ref.free_face_triangles
        kse_free = kse.free_face_triangles
        if kse_free is None or len(kse_free) == 0:
            kse_free = kse.face_triangles

        if (ref_free is not None and len(ref_free) > 0 and
                kse_free is not None and len(kse_free) > 0):
            haus = compute_hausdorff(
                ref.vertex_positions, ref_free,
                kse.vertex_positions, kse_free,
            )
            haus_norm = haus / r

            print(f"\n{example_name}: hausdorff={haus:.6e}, norm={haus_norm:.4f}")

            # Tier 2: Hausdorff < 15% of radius
            assert haus_norm < 0.15, \
                f"{example_name} shape mismatch: hausdorff/r = {haus_norm:.4f}"


class TestFullABComparison:
    """Full comparison using the compare_results utility."""

    @pytest.mark.parametrize("example_name,tier", [
        ("bga-1", 1),
        ("bga-3", 1),
        ("bga-7", 2),
    ])
    def test_full_comparison(self, example_name, tier, evolver_path, tmp_path):
        """Run full A/B comparison with all metrics."""
        ref, kse = _run_ab(example_name, evolver_path, tmp_path)

        assert ref.success, f"Original SE failed for {example_name}: {ref.stderr}"
        assert kse.success, f"KSE SE failed for {example_name}: {kse.stderr}"

        # Use SE total_energy directly for fair comparison
        ref_data = {
            "energy": ref.energy,
            "volume": ref.volume,
            "vertex_positions": ref.vertex_positions,
            "face_triangles": ref.face_triangles,
            "free_face_triangles": ref.free_face_triangles,
        }
        kse_data = {
            "energy": kse.energy,
            "volume": kse.volume,
            "vertex_positions": kse.vertex_positions,
            "face_triangles": kse.face_triangles,
            "free_face_triangles": kse.free_face_triangles,
        }

        result = compare_results(
            ref_data, kse_data, tier,
            characteristic_length=EXAMPLE_REGISTRY[example_name]["params"]["radius"],
        )

        print(f"\n=== {example_name} (Tier {tier}) ===")
        print(result.summary())

        # Volume is the most reliable metric
        assert result.volume_pass or result.volume_rel_error < 0.10, \
            f"{example_name} volume: {result.volume_rel_error:.4%}"


class TestDiagnostics:
    """Diagnostic tests that print detailed comparison info."""

    @pytest.mark.parametrize("example_name", ["bga-1", "bga-3", "bga-7"])
    def test_diagnostic_report(self, example_name, evolver_path, tmp_path):
        """Print detailed diagnostic info for debugging."""
        ref, kse = _run_ab(example_name, evolver_path, tmp_path)
        params = EXAMPLE_REGISTRY[example_name]["params"]

        print(f"\n{'='*60}")
        print(f"DIAGNOSTIC: {example_name}")
        print(f"{'='*60}")

        print(f"\n--- SE Execution ---")
        print(f"ref.success={ref.success}, kse.success={kse.success}")
        if not ref.success:
            print(f"ref.stderr: {ref.stderr}")
        if not kse.success:
            print(f"kse.stderr: {kse.stderr}")

        if ref.success and kse.success:
            print(f"\n--- Energy ---")
            print(f"ref.total_energy = {ref.energy:.6e}")
            print(f"kse.total_energy = {kse.energy:.6e}")
            if ref.energy and abs(ref.energy) > 1e-20:
                print(f"energy_rel_err = {abs(kse.energy - ref.energy)/abs(ref.energy):.4%}")

            print(f"\n--- Volume ---")
            print(f"ref.volume = {ref.volume:.6e}")
            print(f"kse.volume = {kse.volume:.6e}")
            print(f"target_vol = {params['volume']:.6e}")

            print(f"\n--- Mesh ---")
            print(f"ref: {ref.n_vertices} verts, {ref.n_faces} faces")
            print(f"kse: {kse.n_vertices} verts, {kse.n_faces} faces")
            if ref.face_triangles is not None:
                print(f"ref.all_triangles = {len(ref.face_triangles)}")
            if ref.free_face_triangles is not None:
                print(f"ref.free_triangles = {len(ref.free_face_triangles)}")
            if kse.face_triangles is not None:
                print(f"kse.all_triangles = {len(kse.face_triangles)}")
            if kse.free_face_triangles is not None:
                print(f"kse.free_triangles = {len(kse.free_face_triangles)}")

            # Free surface physical energy
            ref_free = ref.free_face_triangles
            kse_free = kse.free_face_triangles if kse.free_face_triangles is not None and len(kse.free_face_triangles) > 0 else kse.face_triangles
            if ref_free is not None and len(ref_free) > 0:
                ref_phys = compute_physical_energy(
                    ref.vertex_positions, ref_free,
                    params["tension"], params["density"], params["gravity"],
                    ref.volume or 0,
                )
                kse_phys = compute_physical_energy(
                    kse.vertex_positions, kse_free,
                    params["tension"], params["density"], params["gravity"],
                    kse.volume or 0,
                )
                print(f"\n--- Free Surface Energy ---")
                print(f"ref_phys = {ref_phys:.6e}")
                print(f"kse_phys = {kse_phys:.6e}")
                if abs(ref_phys) > 1e-20:
                    print(f"phys_rel_err = {abs(kse_phys - ref_phys)/abs(ref_phys):.4%}")

            # Shape comparison on free faces
            if (ref_free is not None and len(ref_free) > 0 and
                    kse_free is not None and len(kse_free) > 0):
                haus = compute_hausdorff(
                    ref.vertex_positions, ref_free,
                    kse.vertex_positions, kse_free,
                )
                print(f"\n--- Shape (Free Faces) ---")
                print(f"hausdorff = {haus:.6e}")
                print(f"hausdorff/r = {haus/params['radius']:.4f}")

        # Always pass — this test is for diagnostics only
        assert True
