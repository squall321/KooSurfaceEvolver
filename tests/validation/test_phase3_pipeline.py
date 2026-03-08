"""Phase 3: End-to-end KSE pipeline test (STL → .fe → SE → dump → mesh)."""

import math

import numpy as np
import pytest

from kse.core.stl_reader import STLReader
from kse.core.surface_fitter import SurfaceFitter
from kse.core.constraint_gen import ConstraintGenerator
from kse.core.geometry_builder import GeometryBuilder
from kse.core.fe_writer import FEWriter, SolderJointConfig
from kse.solver.dump_parser import DumpParser

from .conftest import EXAMPLE_REGISTRY
from .helpers.stl_from_constraints import generate_flat_pad_stl
from .helpers.se_runner import run_kse_fe


def _build_kse_fe(tmp_path, params, fe_name="kse_output.fe"):
    """Run the full KSE pipeline: STL → .fe file.

    Returns the path to the generated .fe file.
    """
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


class TestFEFileStructure:
    """Verify the generated .fe file has valid structure."""

    def test_bga1_fe_structure(self, tmp_path):
        """Check .fe structure for bga-1 equivalent."""
        params = EXAMPLE_REGISTRY["bga-1"]["params"]
        fe_path = _build_kse_fe(tmp_path, params)

        assert fe_path.exists()
        content = fe_path.read_text()

        # Required sections
        assert "vertices" in content.lower()
        assert "edges" in content.lower()
        assert "faces" in content.lower()
        assert "bodies" in content.lower()
        assert "hessian_normal" in content

        # Physical parameters
        assert "S_TENSION" in content
        assert "volume" in content.lower()

        # Evolution commands
        assert "gogo" in content
        assert "gomore" in content

    def test_bga3_fe_structure(self, tmp_path):
        """Check .fe structure for bga-3 (with gravity)."""
        params = EXAMPLE_REGISTRY["bga-3"]["params"]
        fe_path = _build_kse_fe(tmp_path, params)

        content = fe_path.read_text()
        assert "480" in content  # S_TENSION
        assert "gravity" in content.lower() or "980" in content
        assert "SOLDER_DENSITY" in content

    def test_vertex_count(self, tmp_path):
        """n_segments=6 should produce 12 vertices."""
        params = EXAMPLE_REGISTRY["bga-1"]["params"]
        fe_path = _build_kse_fe(tmp_path, params)

        content = fe_path.read_text()
        # Count vertex lines (lines starting with numbers after "vertices")
        in_verts = False
        vert_count = 0
        for line in content.splitlines():
            stripped = line.strip().lower()
            if stripped.startswith("vertices"):
                in_verts = True
                continue
            if in_verts:
                if stripped.startswith("edges"):
                    break
                if stripped and stripped[0].isdigit():
                    vert_count += 1
        assert vert_count == 12, f"Expected 12 vertices, got {vert_count}"


class TestSEExecution:
    """Run KSE-generated .fe through SE and verify results."""

    def test_bga1_se_runs(self, evolver_path, tmp_path):
        """KSE .fe for bga-1 should run in SE without errors."""
        params = EXAMPLE_REGISTRY["bga-1"]["params"]
        fe_path = _build_kse_fe(tmp_path / "build", params)

        result = run_kse_fe(fe_path, evolver_path, tmp_path / "run")

        if not result.success:
            # Print the .fe content for debugging
            content = fe_path.read_text()
            print(f"=== Generated .fe ===\n{content[:2000]}")
            print(f"=== SE stderr ===\n{result.stderr}")
            print(f"=== SE stdout ===\n{result.stdout}")

        assert result.success, f"SE failed on KSE .fe: {result.stderr}"
        assert result.energy is not None, "No energy in dump"
        assert result.energy > 0
        assert result.volume is not None

        # Volume should be conserved
        target_vol = params["volume"]
        assert abs(result.volume - target_vol) / target_vol < 0.05, \
            f"Volume: target={target_vol:.6e}, actual={result.volume:.6e}"

    def test_bga3_se_runs(self, evolver_path, tmp_path):
        """KSE .fe for bga-3 (gravity) should run in SE."""
        params = EXAMPLE_REGISTRY["bga-3"]["params"]
        fe_path = _build_kse_fe(tmp_path / "build", params)

        result = run_kse_fe(fe_path, evolver_path, tmp_path / "run")

        if not result.success:
            content = fe_path.read_text()
            print(f"=== Generated .fe ===\n{content[:2000]}")
            print(f"=== SE stderr ===\n{result.stderr}")

        assert result.success, f"SE failed: {result.stderr}"
        assert result.energy is not None
        assert result.energy > 0
        assert result.volume is not None

    def test_bga7_offset_se_runs(self, evolver_path, tmp_path):
        """KSE .fe for bga-7 (offset pads) should run in SE."""
        params = EXAMPLE_REGISTRY["bga-7"]["params"]
        fe_path = _build_kse_fe(tmp_path / "build", params)

        result = run_kse_fe(fe_path, evolver_path, tmp_path / "run")

        if not result.success:
            content = fe_path.read_text()
            print(f"=== Generated .fe ===\n{content[:2000]}")
            print(f"=== SE stderr ===\n{result.stderr}")

        assert result.success, f"SE failed: {result.stderr}"

    def test_mesh_quality(self, evolver_path, tmp_path):
        """Verify mesh quality after SE evolution."""
        from kse.mesh.quality import assess_quality

        params = EXAMPLE_REGISTRY["bga-1"]["params"]
        fe_path = _build_kse_fe(tmp_path / "build", params)
        result = run_kse_fe(fe_path, evolver_path, tmp_path / "run")

        assert result.success
        assert result.face_triangles is not None
        assert len(result.face_triangles) > 0

        quality = assess_quality(result.vertex_positions, result.face_triangles)
        assert quality.n_triangles > 0
        assert quality.aspect_ratio_mean < 5.0  # relaxed for evolved mesh
        assert quality.n_degenerate == 0
