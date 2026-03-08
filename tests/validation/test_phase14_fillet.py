"""Phase 14: QFN and MLCC fillet topology tests.

Tests both Strategy A (pinned wall contact) and Strategy B (full contact angle)
for solder joints that wet both a horizontal pad and a vertical wall.

Covered scenarios:
- QFN: solder + bottom pad + one vertical lead wall
- MLCC: solder + bottom pad + two symmetric end-cap walls
"""

import numpy as np
import pytest

from kse.core.step_pipeline import STEPPipeline, STEPPipelineConfig

from .helpers.step_generators import (
    generate_qfn_assembly_step,
    generate_mlcc_assembly_step,
)

pytest.importorskip("cadquery")

# Geometry constants (CGS)
RADIUS = 0.010
PAD_RADIUS = 0.015
HEIGHT = 0.005
PAD_THICK = 0.002
TENSION = 480.0
DENSITY = 9.0
GRAVITY = 980.0


# ===========================================================================
# QFN – Strategy A (Pinned wall contact)
# ===========================================================================
class TestQFNPinned:
    """QFN fillet: solder + pad + lead wall, wall contact line pinned."""

    def _make_qfn(self, tmp_path):
        return generate_qfn_assembly_step(
            bottom_center=np.array([0.0, 0.0, 0.0]),
            solder_radius=RADIUS,
            solder_height=HEIGHT,
            pad_radius=PAD_RADIUS,
            pad_thickness=PAD_THICK,
            output_path=tmp_path / "qfn.step",
            lead_output_path=tmp_path / "lead.step",
        )

    def test_qfn_steps_generate(self, tmp_path):
        """QFN STEP files (solder assembly + lead wall) are created."""
        assy_path, lead_path = self._make_qfn(tmp_path)
        assert assy_path.exists()
        assert lead_path.exists()

    def test_qfn_pinned_generates_fe(self, tmp_path):
        """QFN pipeline (pinned strategy) produces a valid .fe file."""
        assy_path, lead_path = self._make_qfn(tmp_path)

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            joint_name="qfn_pinned",
            integration_level=2,
            wall_strategy="pinned",
        )
        pipeline = STEPPipeline(config)
        fe_path = tmp_path / "out" / "qfn_pinned.fe"
        result = pipeline.run_fillet(assy_path, [lead_path], fe_path,
                                     wall_strategy="pinned")

        assert result.exists()
        text = result.read_text()
        assert "constraint 1" in text
        assert "vertices" in text
        assert "bodies" in text
        print(f"QFN pinned .fe: {len(text)} chars")

    def test_qfn_pinned_has_wall_constraint(self, tmp_path):
        """QFN .fe includes a wall constraint block (even for pinned strategy)."""
        assy_path, lead_path = self._make_qfn(tmp_path)

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            joint_name="qfn_wc",
            integration_level=2,
        )
        pipeline = STEPPipeline(config)
        fe_path = tmp_path / "out" / "qfn_wc.fe"
        pipeline.run_fillet(assy_path, [lead_path], fe_path,
                            wall_strategy="pinned")

        text = fe_path.read_text()
        # Wall constraint should appear (constraint 3 = 3rd surface)
        assert "constraint 3" in text
        print("QFN: wall constraint present")

    def test_qfn_pinned_has_fixed_wall_vertices(self, tmp_path):
        """QFN .fe: wall contact vertices are marked fixed (pinned strategy)."""
        assy_path, lead_path = self._make_qfn(tmp_path)

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            joint_name="qfn_fv",
            integration_level=2,
        )
        pipeline = STEPPipeline(config)
        fe_path = tmp_path / "out" / "qfn_fv.fe"
        pipeline.run_fillet(assy_path, [lead_path], fe_path,
                            wall_strategy="pinned")

        text = fe_path.read_text()
        assert "fixed" in text
        print("QFN pinned: fixed vertices present")

    def test_qfn_pinned_se_converges(self, tmp_path, evolver_path):
        """QFN .fe (pinned) converges in Surface Evolver."""
        from tests.validation.helpers.se_runner import run_kse_fe

        assy_path, lead_path = self._make_qfn(tmp_path)

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            contact_angle_bottom=30.0,
            joint_name="qfn_se",
            integration_level=2,
        )
        pipeline = STEPPipeline(config)
        fe_path = tmp_path / "build" / "qfn_pinned.fe"
        pipeline.run_fillet(assy_path, [lead_path], fe_path,
                            wall_strategy="pinned")

        result = run_kse_fe(fe_path, evolver_path, tmp_path / "run", timeout=120)
        assert result.success, f"SE failed: {result.stderr[:500]}"
        assert result.energy is not None and result.energy > 0
        print(f"QFN SE: energy={result.energy:.6e}")


# ===========================================================================
# QFN – Strategy B (Full contact angle enforcement)
# ===========================================================================
class TestQFNFull:
    """QFN fillet: wall contact angle enforced by SE constraint."""

    def _make_qfn(self, tmp_path):
        return generate_qfn_assembly_step(
            bottom_center=np.array([0.0, 0.0, 0.0]),
            solder_radius=RADIUS,
            solder_height=HEIGHT,
            pad_radius=PAD_RADIUS,
            pad_thickness=PAD_THICK,
            output_path=tmp_path / "qfn_full.step",
            lead_output_path=tmp_path / "lead_full.step",
        )

    def test_qfn_full_generates_fe(self, tmp_path):
        """QFN pipeline (full strategy) generates .fe with wall energy integrals."""
        assy_path, lead_path = self._make_qfn(tmp_path)

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            contact_angle_bottom=30.0,
            joint_name="qfn_full",
            integration_level=2,
        )
        pipeline = STEPPipeline(config)
        fe_path = tmp_path / "out" / "qfn_full.fe"
        result = pipeline.run_fillet(assy_path, [lead_path], fe_path,
                                     wall_strategy="full")

        assert result.exists()
        text = result.read_text()
        assert "constraint 3" in text
        # Full strategy: wall constraint should have energy/content integrals
        assert "energy:" in text
        print(f"QFN full .fe: {len(text)} chars")

    def test_qfn_full_has_multi_constraint_vertices(self, tmp_path):
        """QFN full .fe: corner vertices have two constraints (constraints N M)."""
        assy_path, lead_path = self._make_qfn(tmp_path)

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            contact_angle_bottom=30.0,
            joint_name="qfn_mc",
            integration_level=2,
        )
        pipeline = STEPPipeline(config)
        fe_path = tmp_path / "out" / "qfn_mc.fe"
        pipeline.run_fillet(assy_path, [lead_path], fe_path,
                            wall_strategy="full")

        text = fe_path.read_text()
        # "constraints 1 3" or "constraints 1 2" etc — two constraint IDs
        import re
        multi = re.findall(r'constraints\s+\d+\s+\d+', text)
        assert len(multi) > 0, "No multi-constraint vertices found"
        print(f"QFN full: {len(multi)} multi-constraint vertices")

    def test_qfn_full_se_converges(self, tmp_path, evolver_path):
        """QFN .fe (full contact angle) converges in Surface Evolver."""
        from tests.validation.helpers.se_runner import run_kse_fe

        assy_path, lead_path = self._make_qfn(tmp_path)

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            contact_angle_bottom=30.0,
            joint_name="qfn_full_se",
            integration_level=2,
        )
        pipeline = STEPPipeline(config)
        fe_path = tmp_path / "build" / "qfn_full.fe"
        pipeline.run_fillet(assy_path, [lead_path], fe_path,
                            wall_strategy="full")

        result = run_kse_fe(fe_path, evolver_path, tmp_path / "run", timeout=120)
        assert result.success, f"SE failed: {result.stderr[:500]}"
        assert result.energy is not None and result.energy > 0
        print(f"QFN full SE: energy={result.energy:.6e}")


# ===========================================================================
# MLCC – Two symmetric walls
# ===========================================================================
class TestMLCCFillet:
    """MLCC fillet: solder + pad + two vertical end-cap walls."""

    def _make_mlcc(self, tmp_path):
        return generate_mlcc_assembly_step(
            bottom_center=np.array([0.0, 0.0, 0.0]),
            solder_radius=RADIUS,
            solder_height=HEIGHT,
            pad_radius=PAD_RADIUS,
            pad_thickness=PAD_THICK,
            output_path=tmp_path / "mlcc.step",
            left_wall_path=tmp_path / "mlcc_left.step",
            right_wall_path=tmp_path / "mlcc_right.step",
        )

    def test_mlcc_steps_generate(self, tmp_path):
        """MLCC STEP files generate: assembly + two wall files."""
        assy_path, left_path, right_path = self._make_mlcc(tmp_path)
        assert assy_path.exists()
        assert left_path.exists()
        assert right_path.exists()

    def test_mlcc_pinned_generates_fe(self, tmp_path):
        """MLCC pinned strategy produces .fe with constraints for both walls."""
        assy_path, left_path, right_path = self._make_mlcc(tmp_path)

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            joint_name="mlcc_pinned",
            integration_level=2,
        )
        pipeline = STEPPipeline(config)
        fe_path = tmp_path / "out" / "mlcc_pinned.fe"
        result = pipeline.run_fillet(
            assy_path, [left_path, right_path], fe_path,
            wall_strategy="pinned",
        )

        assert result.exists()
        text = result.read_text()
        # Two wall constraints expected (constraints 3 and 4)
        assert "constraint 3" in text
        assert "constraint 4" in text
        print(f"MLCC pinned .fe: {len(text)} chars, has constraints 3+4")

    def test_mlcc_full_generates_fe(self, tmp_path):
        """MLCC full strategy: both walls have energy+content integrals."""
        assy_path, left_path, right_path = self._make_mlcc(tmp_path)

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            contact_angle_bottom=30.0,
            joint_name="mlcc_full",
            integration_level=2,
        )
        pipeline = STEPPipeline(config)
        fe_path = tmp_path / "out" / "mlcc_full.fe"
        result = pipeline.run_fillet(
            assy_path, [left_path, right_path], fe_path,
            wall_strategy="full",
        )

        assert result.exists()
        text = result.read_text()
        assert "constraint 4" in text
        assert "energy:" in text
        print(f"MLCC full .fe: {len(text)} chars")

    def test_mlcc_pinned_se_converges(self, tmp_path, evolver_path):
        """MLCC .fe (pinned) converges in Surface Evolver."""
        from tests.validation.helpers.se_runner import run_kse_fe

        assy_path, left_path, right_path = self._make_mlcc(tmp_path)

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            contact_angle_bottom=30.0,
            joint_name="mlcc_se",
            integration_level=2,
        )
        pipeline = STEPPipeline(config)
        fe_path = tmp_path / "build" / "mlcc_pinned.fe"
        pipeline.run_fillet(
            assy_path, [left_path, right_path], fe_path,
            wall_strategy="pinned",
        )

        result = run_kse_fe(fe_path, evolver_path, tmp_path / "run", timeout=120)
        assert result.success, f"SE failed: {result.stderr[:500]}"
        assert result.energy is not None and result.energy > 0
        print(f"MLCC SE: energy={result.energy:.6e}")


# ===========================================================================
# Unit tests: BoundaryExtractor.classify_boundary_vertices
# ===========================================================================
class TestClassifyBoundaryVertices:
    """Unit tests for per-vertex constraint classification."""

    @staticmethod
    def _make_plane_fit(normal, center, constraint_id):
        """Build a SurfaceFitResult for a plane with given normal at center."""
        from kse.core.stl_reader import LocalPatch
        from kse.core.surface_fitter import SurfaceFitter, SurfaceFitResult, FitType
        import numpy as np

        n = np.asarray(normal, dtype=float)
        n /= np.linalg.norm(n)
        # Build local axes: find two orthogonal tangent vectors
        ref = np.array([0., 0., 1.]) if abs(n[2]) < 0.9 else np.array([1., 0., 0.])
        u = np.cross(n, ref); u /= np.linalg.norm(u)
        v = np.cross(n, u)
        local_axes = np.array([u, v, n])  # rows are u, v, n

        c = np.asarray(center, dtype=float)
        # Four vertices around center in tangent plane
        r = 0.01
        verts = np.array([
            c + r * u + r * v,
            c + r * u - r * v,
            c - r * u - r * v,
            c - r * u + r * v,
        ])
        # Local coords: (u_proj, v_proj, 0) for each vertex
        rel = verts - c
        lc = rel @ local_axes.T  # shape (4,3)

        patch = LocalPatch(
            vertices=verts,
            faces=np.array([[0,1,2],[0,2,3]]),
            normals=np.tile(n, (2,1)),
            center=c,
            avg_normal=n,
            local_axes=local_axes,
            radius=r * 2,
            local_coords=lc,
        )
        fitter = SurfaceFitter()
        return fitter.fit_plane(patch)

    def test_single_surface_classification(self):
        """All boundary vertices on one surface get that constraint only."""
        from kse.core.boundary_extractor import BoundaryExtractor

        # Flat horizontal surface at z = 0, normal = (0, 0, 1)
        fit = self._make_plane_fit([0, 0, 1], [0.005, 0.005, 0.0], 1)

        extractor = BoundaryExtractor(
            surfaces=[("bottom", 1, fit)],
            on_surface_tol=1e-4,
        )
        pts = np.array([
            [0.0, 0.0, 0.0],
            [0.01, 0.0, 0.0],
            [0.01, 0.01, 0.0],
            [0.0, 0.01, 0.0],
            [0.005, 0.005, 0.01],  # free vertex
        ])
        result = extractor.classify_boundary_vertices(pts, {0, 1, 2, 3})

        assert result[0] == [1]
        assert result[1] == [1]
        assert result[2] == [1]
        assert result[3] == [1]
        print("Single surface: all boundary verts classified to constraint 1")

    def test_corner_vertex_gets_two_constraints(self):
        """Vertex at intersection of two surfaces gets both constraint IDs."""
        from kse.core.boundary_extractor import BoundaryExtractor

        # Surface 1: horizontal plane z = 0, normal = (0, 0, 1)
        fit_pad = self._make_plane_fit([0, 0, 1], [0.005, 0.005, 0.0], 1)
        # Surface 2: vertical plane x = 0.01, normal = (1, 0, 0)
        fit_wall = self._make_plane_fit([1, 0, 0], [0.01, 0.005, 0.005], 3)

        extractor = BoundaryExtractor(
            surfaces=[("bottom", 1, fit_pad), ("wall_0", 3, fit_wall)],
            on_surface_tol=1e-4,
        )

        # Vertex at (0.01, 0, 0) is on BOTH surfaces
        vertices = np.array([
            [0.0, 0.0, 0.0],    # idx 0: pad only
            [0.01, 0.0, 0.0],   # idx 1: CORNER (on both)
            [0.01, 0.005, 0.005],  # idx 2: wall only
        ])

        result = extractor.classify_boundary_vertices(vertices, {0, 1, 2})

        assert result[0] == [1], f"Pad-only vertex: {result[0]}"
        assert set(result[1]) == {1, 3}, f"Corner should have both: {result[1]}"
        assert result[2] == [3], f"Wall-only vertex: {result[2]}"

        corners = extractor.get_corner_vertex_indices(result)
        assert 1 in corners
        print(f"Corner vertex detected at index 1 with constraints {result[1]}")
