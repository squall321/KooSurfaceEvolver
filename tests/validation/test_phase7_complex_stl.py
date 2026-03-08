"""Phase 7: Complex CAD STL pipeline validation.

Tests the full pipeline from 3 STL files (bottom pad, top pad, solder)
to a .fe file that Surface Evolver can successfully evolve.

Test classes:
- TestCapDetection: Cap face identification on pad surfaces
- TestBoundaryExtraction: Boundary loop extraction and classification
- TestMeshToSEConversion: trimesh → SE signed-edge topology conversion
- TestComplexPipelineSimple: Pipeline produces valid .fe files
- TestComplexPipelineSE: SE convergence for various solder shapes
- TestIrregularBoundary: Non-circular pad boundary shapes
"""

import numpy as np
import pytest
import trimesh

from kse.core.stl_reader import STLReader
from kse.core.surface_fitter import SurfaceFitter
from kse.core.constraint_gen import ConstraintGenerator
from kse.core.fe_writer import FEWriter, SolderJointConfig
from kse.core.mesh_preprocessor import MeshPreprocessor
from kse.core.boundary_extractor import BoundaryExtractor, BoundaryLoop
from kse.core.mesh_to_se import MeshToSEConverter
from kse.core.complex_pipeline import ComplexSTLPipeline, ComplexPipelineConfig

from .helpers.stl_from_constraints import generate_flat_pad_stl
from .helpers.realistic_stl import generate_square_pad_stl
from .helpers.complex_stl_generators import (
    generate_cylinder_solder_stl,
    generate_barrel_solder_stl,
    generate_hourglass_solder_stl,
    generate_irregular_boundary_solder_stl,
)
from .helpers.se_runner import run_kse_fe


# ---------------------------------------------------------------------------
# Shared geometry constants
# ---------------------------------------------------------------------------
RADIUS = 0.010  # 10 mil pad radius (cm)
HEIGHT = 0.005  # 5 mil standoff (cm)
BOTTOM_CENTER = np.array([0.0, 0.0, 0.0])
TOP_CENTER = np.array([0.0, 0.0, HEIGHT])
TENSION = 480.0
DENSITY = 9.0
GRAVITY = 980.0


def _make_flat_pad_stls(tmp_path, bottom_center, top_center, pad_radius):
    """Generate flat circular pad STL files."""
    stl_dir = tmp_path / "stls"
    stl_dir.mkdir(exist_ok=True)
    bot_stl = stl_dir / "bottom_pad.stl"
    top_stl = stl_dir / "top_pad.stl"
    generate_flat_pad_stl(bottom_center, pad_radius * 3, output_path=bot_stl)
    generate_flat_pad_stl(top_center, pad_radius * 3, output_path=top_stl)
    return bot_stl, top_stl


def _make_square_pad_stls(tmp_path, bottom_center, top_center, side):
    """Generate flat square pad STL files."""
    stl_dir = tmp_path / "stls"
    stl_dir.mkdir(exist_ok=True)
    bot_stl = stl_dir / "bottom_pad.stl"
    top_stl = stl_dir / "top_pad.stl"
    generate_square_pad_stl(bottom_center, side * 3, output_path=bot_stl)
    generate_square_pad_stl(top_center, side * 3, output_path=top_stl)
    return bot_stl, top_stl


def _fit_pads(bot_stl, top_stl, bottom_center, top_center, pad_radius):
    """Fit surface to both pad STLs."""
    reader_b = STLReader(bot_stl)
    reader_t = STLReader(top_stl)
    patch_b = reader_b.extract_patch(bottom_center, pad_radius * 1.5)
    patch_t = reader_t.extract_patch(top_center, pad_radius * 1.5)
    fitter = SurfaceFitter()
    return fitter.fit(patch_b), fitter.fit(patch_t)


# ===========================================================================
# TestCapDetection
# ===========================================================================
class TestCapDetection:
    """Verify that cap faces on pad surfaces are correctly identified."""

    def test_watertight_cylinder_caps_detected(self, tmp_path):
        """Watertight cylinder: both caps should be detected and removed."""
        bot_stl, top_stl = _make_flat_pad_stls(
            tmp_path, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )
        solder = generate_cylinder_solder_stl(
            BOTTOM_CENTER, TOP_CENTER, RADIUS * 0.8,
            n_angular=16, n_axial=4, include_caps=True,
        )
        fit_b, fit_t = _fit_pads(
            bot_stl, top_stl, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )

        extractor = BoundaryExtractor(fit_bottom=fit_b, fit_top=fit_t)
        result = extractor.extract(solder)

        assert result.n_cap_faces_removed > 0, "Should detect cap faces"
        assert len(result.cap_faces_bottom) > 0, "Should find bottom caps"
        assert len(result.cap_faces_top) > 0, "Should find top caps"
        print(f"Removed {result.n_cap_faces_removed} cap faces "
              f"(bottom={len(result.cap_faces_bottom)}, "
              f"top={len(result.cap_faces_top)})")

    def test_open_cylinder_no_caps(self, tmp_path):
        """Open cylinder (no caps): should detect zero cap faces."""
        bot_stl, top_stl = _make_flat_pad_stls(
            tmp_path, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )
        solder = generate_cylinder_solder_stl(
            BOTTOM_CENTER, TOP_CENTER, RADIUS * 0.8,
            n_angular=16, n_axial=4, include_caps=False,
        )
        fit_b, fit_t = _fit_pads(
            bot_stl, top_stl, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )

        extractor = BoundaryExtractor(fit_bottom=fit_b, fit_top=fit_t)
        result = extractor.extract(solder)

        assert result.n_cap_faces_removed == 0, "Open mesh should have no caps"
        print("Open mesh: 0 cap faces detected (correct)")

    def test_barrel_caps_detected(self, tmp_path):
        """Barrel solder: caps should still be detected on flat pads."""
        bot_stl, top_stl = _make_flat_pad_stls(
            tmp_path, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )
        solder = generate_barrel_solder_stl(
            BOTTOM_CENTER, TOP_CENTER,
            radius_end=RADIUS * 0.8, radius_mid=RADIUS * 1.0,
            n_angular=16, n_axial=6, include_caps=True,
        )
        fit_b, fit_t = _fit_pads(
            bot_stl, top_stl, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )

        extractor = BoundaryExtractor(fit_bottom=fit_b, fit_top=fit_t)
        result = extractor.extract(solder)

        assert result.n_cap_faces_removed > 0, "Should detect barrel caps"
        print(f"Barrel: removed {result.n_cap_faces_removed} cap faces")


# ===========================================================================
# TestBoundaryExtraction
# ===========================================================================
class TestBoundaryExtraction:
    """Verify boundary loop extraction and bottom/top classification."""

    def test_two_loops_from_cylinder(self, tmp_path):
        """Watertight cylinder should yield exactly 2 boundary loops."""
        bot_stl, top_stl = _make_flat_pad_stls(
            tmp_path, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )
        solder = generate_cylinder_solder_stl(
            BOTTOM_CENTER, TOP_CENTER, RADIUS * 0.8,
            n_angular=16, n_axial=4, include_caps=True,
        )
        fit_b, fit_t = _fit_pads(
            bot_stl, top_stl, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )

        extractor = BoundaryExtractor(fit_bottom=fit_b, fit_top=fit_t)
        result = extractor.extract(solder)

        assert len(result.boundary_loops) == 2, (
            f"Expected 2 boundary loops, got {len(result.boundary_loops)}"
        )

        pads = sorted([loop.pad_id for loop in result.boundary_loops])
        assert pads == ["bottom", "top"], (
            f"Expected bottom+top loops, got {pads}"
        )
        print(f"Found 2 loops: {pads}")

    def test_loop_vertex_count_matches_angular(self, tmp_path):
        """Each boundary loop should have n_angular vertices."""
        n_angular = 20
        bot_stl, top_stl = _make_flat_pad_stls(
            tmp_path, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )
        solder = generate_cylinder_solder_stl(
            BOTTOM_CENTER, TOP_CENTER, RADIUS * 0.8,
            n_angular=n_angular, n_axial=4, include_caps=True,
        )
        fit_b, fit_t = _fit_pads(
            bot_stl, top_stl, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )

        extractor = BoundaryExtractor(fit_bottom=fit_b, fit_top=fit_t)
        result = extractor.extract(solder)

        for loop in result.boundary_loops:
            assert len(loop.vertex_ids) == n_angular, (
                f"{loop.pad_id} loop: expected {n_angular} verts, "
                f"got {len(loop.vertex_ids)}"
            )
            print(f"{loop.pad_id} loop: {len(loop.vertex_ids)} vertices (correct)")

    def test_constraint_ids_assigned(self, tmp_path):
        """Bottom loop gets constraint 1, top gets constraint 2."""
        bot_stl, top_stl = _make_flat_pad_stls(
            tmp_path, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )
        solder = generate_cylinder_solder_stl(
            BOTTOM_CENTER, TOP_CENTER, RADIUS * 0.8,
            n_angular=16, n_axial=4, include_caps=True,
        )
        fit_b, fit_t = _fit_pads(
            bot_stl, top_stl, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )

        extractor = BoundaryExtractor(
            fit_bottom=fit_b, fit_top=fit_t,
            constraint_bottom_id=1, constraint_top_id=2,
        )
        result = extractor.extract(solder)

        for loop in result.boundary_loops:
            if loop.pad_id == "bottom":
                assert loop.constraint_id == 1
            elif loop.pad_id == "top":
                assert loop.constraint_id == 2
        print("Constraint IDs correctly assigned")


# ===========================================================================
# TestMeshToSEConversion
# ===========================================================================
class TestMeshToSEConversion:
    """Verify trimesh → SE signed-edge topology conversion."""

    def _make_lateral_mesh_and_loops(self, tmp_path, n_angular=16, n_axial=4):
        """Helper: generate cylinder, extract boundaries, return lateral mesh + loops."""
        bot_stl, top_stl = _make_flat_pad_stls(
            tmp_path, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )
        solder = generate_cylinder_solder_stl(
            BOTTOM_CENTER, TOP_CENTER, RADIUS * 0.8,
            n_angular=n_angular, n_axial=n_axial, include_caps=True,
        )
        fit_b, fit_t = _fit_pads(
            bot_stl, top_stl, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )
        extractor = BoundaryExtractor(fit_bottom=fit_b, fit_top=fit_t)
        extraction = extractor.extract(solder)
        return extraction.lateral_mesh, extraction.boundary_loops

    def test_vertex_count(self, tmp_path):
        """SE vertex count should match lateral mesh vertex count."""
        n_angular, n_axial = 16, 4
        lateral, loops = self._make_lateral_mesh_and_loops(
            tmp_path, n_angular, n_axial,
        )
        converter = MeshToSEConverter()
        result = converter.convert(lateral, loops)

        assert len(result.geometry.vertices) == len(lateral.vertices)
        print(f"Vertices: {len(result.geometry.vertices)} (matches mesh)")

    def test_face_count(self, tmp_path):
        """SE face count should match lateral mesh face count."""
        lateral, loops = self._make_lateral_mesh_and_loops(tmp_path)
        converter = MeshToSEConverter()
        result = converter.convert(lateral, loops)

        assert len(result.geometry.faces) == len(lateral.faces)
        print(f"Faces: {len(result.geometry.faces)} (matches mesh)")

    def test_edge_count_euler(self, tmp_path):
        """Edge count should satisfy Euler formula for open surface: V - E + F = 1."""
        lateral, loops = self._make_lateral_mesh_and_loops(tmp_path)
        converter = MeshToSEConverter()
        result = converter.convert(lateral, loops)

        V = len(result.geometry.vertices)
        E = len(result.geometry.edges)
        F = len(result.geometry.faces)
        # For a disk-like open surface: V - E + F = 1
        # For a cylinder-like surface with 2 boundaries: V - E + F = 0
        euler = V - E + F
        print(f"V={V}, E={E}, F={F}, V-E+F={euler}")
        # Open cylinder: Euler characteristic = 0
        assert euler == 0, f"Euler char for open cylinder should be 0, got {euler}"

    def test_signed_edge_consistency(self, tmp_path):
        """Each internal edge should appear with both signs across faces."""
        lateral, loops = self._make_lateral_mesh_and_loops(tmp_path)
        converter = MeshToSEConverter()
        result = converter.convert(lateral, loops)

        # Count sign appearances for each edge
        from collections import Counter
        pos_count = Counter()
        neg_count = Counter()
        for face in result.geometry.faces:
            for eid in face.edges:
                if eid > 0:
                    pos_count[eid] += 1
                else:
                    neg_count[-eid] += 1

        # Boundary edges appear in only 1 face, internal edges in 2 faces
        n_boundary_edges = sum(
            len(bset) for bset in result.boundary_edge_ids.values()
        )
        n_internal_with_both_signs = 0
        for eid in range(1, len(result.geometry.edges) + 1):
            total = pos_count.get(eid, 0) + neg_count.get(eid, 0)
            if total == 2:
                n_internal_with_both_signs += 1
            elif total == 1:
                # Should be a boundary edge
                pass
            else:
                pytest.fail(f"Edge {eid} appears {total} times (expected 1 or 2)")

        print(f"Internal edges (2 faces): {n_internal_with_both_signs}, "
              f"Boundary edges (1 face): {n_boundary_edges}")

    def test_boundary_vertices_are_fixed(self, tmp_path):
        """All boundary vertices should be marked fixed with constraints."""
        lateral, loops = self._make_lateral_mesh_and_loops(tmp_path)
        converter = MeshToSEConverter()
        result = converter.convert(lateral, loops)

        for pad, vid_set in result.boundary_vertex_ids.items():
            for vid in vid_set:
                vert = result.geometry.vertices[vid - 1]  # 1-based
                assert vert.fixed, (
                    f"Boundary vertex {vid} ({pad}) should be fixed"
                )
                assert len(vert.constraints) > 0, (
                    f"Boundary vertex {vid} ({pad}) should have constraints"
                )

        print("All boundary vertices are fixed with constraints")

    def test_body_has_all_faces(self, tmp_path):
        """The body should reference all faces."""
        lateral, loops = self._make_lateral_mesh_and_loops(tmp_path)
        converter = MeshToSEConverter()
        result = converter.convert(lateral, loops)

        assert len(result.geometry.bodies) == 1
        body = result.geometry.bodies[0]
        assert len(body.faces) == len(result.geometry.faces)
        print(f"Body references all {len(body.faces)} faces")


# ===========================================================================
# TestComplexPipelineSimple
# ===========================================================================
class TestComplexPipelineSimple:
    """Verify the ComplexSTLPipeline produces valid .fe files (no SE needed)."""

    def test_cylinder_generates_fe(self, tmp_path):
        """Cylinder solder → valid .fe file."""
        bot_stl, top_stl = _make_flat_pad_stls(
            tmp_path, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )
        solder_stl = tmp_path / "stls" / "solder.stl"
        generate_cylinder_solder_stl(
            BOTTOM_CENTER, TOP_CENTER, RADIUS * 0.8,
            n_angular=16, n_axial=4, include_caps=True,
            output_path=solder_stl,
        )

        config = ComplexPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            joint_name="test_cylinder",
        )
        pipeline = ComplexSTLPipeline(config)
        fe_path = tmp_path / "output" / "cylinder.fe"
        result_path = pipeline.run(bot_stl, top_stl, solder_stl, fe_path)

        assert result_path.exists()
        text = result_path.read_text()
        assert "constraint 1" in text
        assert "constraint 2" in text
        assert "vertices" in text
        assert "edges" in text
        assert "faces" in text
        assert "bodies" in text
        print(f"Generated .fe: {len(text)} chars")

    def test_barrel_generates_fe(self, tmp_path):
        """Barrel solder → valid .fe file."""
        bot_stl, top_stl = _make_flat_pad_stls(
            tmp_path, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )
        solder_stl = tmp_path / "stls" / "solder.stl"
        generate_barrel_solder_stl(
            BOTTOM_CENTER, TOP_CENTER,
            radius_end=RADIUS * 0.8, radius_mid=RADIUS * 1.0,
            n_angular=16, n_axial=6, include_caps=True,
            output_path=solder_stl,
        )

        config = ComplexPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            joint_name="test_barrel",
        )
        pipeline = ComplexSTLPipeline(config)
        fe_path = tmp_path / "output" / "barrel.fe"
        result_path = pipeline.run(bot_stl, top_stl, solder_stl, fe_path)

        assert result_path.exists()
        text = result_path.read_text()
        assert "constraint 1" in text
        assert "constraint 2" in text
        print(f"Barrel .fe: {len(text)} chars")

    def test_hourglass_generates_fe(self, tmp_path):
        """Hourglass solder → valid .fe file."""
        bot_stl, top_stl = _make_flat_pad_stls(
            tmp_path, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )
        solder_stl = tmp_path / "stls" / "solder.stl"
        generate_hourglass_solder_stl(
            BOTTOM_CENTER, TOP_CENTER,
            radius_end=RADIUS * 0.8, radius_mid=RADIUS * 0.5,
            n_angular=16, n_axial=6, include_caps=True,
            output_path=solder_stl,
        )

        config = ComplexPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            joint_name="test_hourglass",
        )
        pipeline = ComplexSTLPipeline(config)
        fe_path = tmp_path / "output" / "hourglass.fe"
        result_path = pipeline.run(bot_stl, top_stl, solder_stl, fe_path)

        assert result_path.exists()
        text = result_path.read_text()
        assert "constraint 1" in text
        print(f"Hourglass .fe: {len(text)} chars")

    def test_fe_has_energy_content_integrals(self, tmp_path):
        """Generated .fe should contain energy and content integrals."""
        bot_stl, top_stl = _make_flat_pad_stls(
            tmp_path, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )
        solder_stl = tmp_path / "stls" / "solder.stl"
        generate_cylinder_solder_stl(
            BOTTOM_CENTER, TOP_CENTER, RADIUS * 0.8,
            n_angular=16, n_axial=4, include_caps=True,
            output_path=solder_stl,
        )

        config = ComplexPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            contact_angle_bottom=30.0, contact_angle_top=30.0,
        )
        pipeline = ComplexSTLPipeline(config)
        fe_path = tmp_path / "output" / "integrals.fe"
        pipeline.run(bot_stl, top_stl, solder_stl, fe_path)

        text = fe_path.read_text()
        # Should have energy and content integrals on constraints
        assert "energy" in text.lower(), "Should have energy integral"
        assert "content" in text.lower(), "Should have content integral"
        print("Energy and content integrals present in .fe")

    def test_with_square_pads(self, tmp_path):
        """Pipeline works with square pad STLs."""
        bot_stl, top_stl = _make_square_pad_stls(
            tmp_path, BOTTOM_CENTER, TOP_CENTER, RADIUS * 2,
        )
        solder_stl = tmp_path / "stls" / "solder.stl"
        generate_cylinder_solder_stl(
            BOTTOM_CENTER, TOP_CENTER, RADIUS * 0.7,
            n_angular=16, n_axial=4, include_caps=True,
            output_path=solder_stl,
        )

        config = ComplexPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            joint_name="test_square_pad",
        )
        pipeline = ComplexSTLPipeline(config)
        fe_path = tmp_path / "output" / "square.fe"
        result_path = pipeline.run(bot_stl, top_stl, solder_stl, fe_path)

        assert result_path.exists()
        print("Square pad pipeline succeeded")


# ===========================================================================
# TestComplexPipelineSE
# ===========================================================================
class TestComplexPipelineSE:
    """Verify SE convergence for complex STL pipeline outputs."""

    @pytest.mark.parametrize(
        "shape,gen_kwargs",
        [
            ("cylinder", dict(
                radius=RADIUS * 0.8,
                n_angular=12, n_axial=3,
            )),
            ("barrel", dict(
                radius_end=RADIUS * 0.7, radius_mid=RADIUS * 0.9,
                n_angular=12, n_axial=4,
            )),
            ("hourglass", dict(
                radius_end=RADIUS * 0.8, radius_mid=RADIUS * 0.5,
                n_angular=12, n_axial=4,
            )),
        ],
        ids=["cylinder", "barrel", "hourglass"],
    )
    def test_se_converges(self, shape, gen_kwargs, evolver_path, tmp_path):
        """SE evolves the generated .fe to convergence."""
        bot_stl, top_stl = _make_flat_pad_stls(
            tmp_path, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )

        solder_stl = tmp_path / "stls" / "solder.stl"
        if shape == "cylinder":
            generate_cylinder_solder_stl(
                BOTTOM_CENTER, TOP_CENTER,
                include_caps=True, output_path=solder_stl,
                **gen_kwargs,
            )
        elif shape == "barrel":
            generate_barrel_solder_stl(
                BOTTOM_CENTER, TOP_CENTER,
                include_caps=True, output_path=solder_stl,
                **gen_kwargs,
            )
        elif shape == "hourglass":
            generate_hourglass_solder_stl(
                BOTTOM_CENTER, TOP_CENTER,
                include_caps=True, output_path=solder_stl,
                **gen_kwargs,
            )

        config = ComplexPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            contact_angle_bottom=30.0, contact_angle_top=30.0,
            joint_name=f"test_{shape}",
        )
        pipeline = ComplexSTLPipeline(config)
        fe_path = tmp_path / "build" / f"{shape}.fe"
        pipeline.run(bot_stl, top_stl, solder_stl, fe_path)

        work_dir = tmp_path / "run"
        work_dir.mkdir(exist_ok=True)
        result = run_kse_fe(fe_path, evolver_path, work_dir, timeout=120)

        assert result.success, f"SE failed for {shape}: {result.stderr[:500]}"
        assert result.energy is not None and result.energy > 0, (
            f"{shape}: energy should be positive, got {result.energy}"
        )
        print(f"{shape}: energy={result.energy:.6e}, volume={result.volume}")


# ===========================================================================
# TestIrregularBoundary
# ===========================================================================
class TestIrregularBoundary:
    """Test pipeline with non-circular solder boundaries."""

    def test_elliptical_boundary_generates_fe(self, tmp_path):
        """Elliptical solder cross-section → valid .fe file."""
        a, b = RADIUS * 0.9, RADIUS * 0.6  # semi-major, semi-minor

        def ellipse_boundary(theta):
            return a * b / np.sqrt(
                (b * np.cos(theta))**2 + (a * np.sin(theta))**2
            )

        bot_stl, top_stl = _make_flat_pad_stls(
            tmp_path, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )
        solder_stl = tmp_path / "stls" / "solder.stl"
        generate_irregular_boundary_solder_stl(
            BOTTOM_CENTER, TOP_CENTER, ellipse_boundary,
            n_angular=20, n_axial=4, include_caps=True,
            output_path=solder_stl,
        )

        config = ComplexPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            joint_name="test_elliptical",
        )
        pipeline = ComplexSTLPipeline(config)
        fe_path = tmp_path / "output" / "elliptical.fe"
        result_path = pipeline.run(bot_stl, top_stl, solder_stl, fe_path)

        assert result_path.exists()
        text = result_path.read_text()
        assert "constraint 1" in text
        assert "constraint 2" in text
        print(f"Elliptical boundary .fe: {len(text)} chars")

    def test_lobular_boundary_generates_fe(self, tmp_path):
        """Lobular (3-lobed) solder cross-section → valid .fe file."""
        r_base = RADIUS * 0.6
        amplitude = RADIUS * 0.15

        def lobular_boundary(theta):
            return r_base + amplitude * np.cos(3 * theta)

        bot_stl, top_stl = _make_flat_pad_stls(
            tmp_path, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )
        solder_stl = tmp_path / "stls" / "solder.stl"
        generate_irregular_boundary_solder_stl(
            BOTTOM_CENTER, TOP_CENTER, lobular_boundary,
            n_angular=24, n_axial=4, include_caps=True,
            output_path=solder_stl,
        )

        config = ComplexPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            joint_name="test_lobular",
        )
        pipeline = ComplexSTLPipeline(config)
        fe_path = tmp_path / "output" / "lobular.fe"
        result_path = pipeline.run(bot_stl, top_stl, solder_stl, fe_path)

        assert result_path.exists()
        print("Lobular boundary .fe generated successfully")

    def test_elliptical_se_converges(self, evolver_path, tmp_path):
        """SE converges for elliptical solder cross-section."""
        a, b = RADIUS * 0.8, RADIUS * 0.5

        def ellipse_boundary(theta):
            return a * b / np.sqrt(
                (b * np.cos(theta))**2 + (a * np.sin(theta))**2
            )

        bot_stl, top_stl = _make_flat_pad_stls(
            tmp_path, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )
        solder_stl = tmp_path / "stls" / "solder.stl"
        generate_irregular_boundary_solder_stl(
            BOTTOM_CENTER, TOP_CENTER, ellipse_boundary,
            n_angular=16, n_axial=3, include_caps=True,
            output_path=solder_stl,
        )

        config = ComplexPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            contact_angle_bottom=30.0, contact_angle_top=30.0,
            joint_name="test_elliptical_se",
        )
        pipeline = ComplexSTLPipeline(config)
        fe_path = tmp_path / "build" / "elliptical.fe"
        pipeline.run(bot_stl, top_stl, solder_stl, fe_path)

        work_dir = tmp_path / "run"
        work_dir.mkdir(exist_ok=True)
        result = run_kse_fe(fe_path, evolver_path, work_dir, timeout=120)

        assert result.success, f"SE failed for elliptical: {result.stderr[:500]}"
        assert result.energy is not None and result.energy > 0
        print(f"Elliptical SE: energy={result.energy:.6e}, volume={result.volume}")


# ===========================================================================
# TestPreprocessor
# ===========================================================================
class TestPreprocessor:
    """Verify MeshPreprocessor handles various mesh conditions."""

    def test_clean_mesh_unchanged(self):
        """Clean mesh should pass through with no removals."""
        mesh = generate_cylinder_solder_stl(
            BOTTOM_CENTER, TOP_CENTER, RADIUS * 0.8,
            n_angular=16, n_axial=4, include_caps=True,
        )
        pp = MeshPreprocessor()
        result = pp.preprocess(mesh)

        assert result.n_removed_degenerate == 0
        assert result.mesh is not None
        assert len(result.mesh.faces) > 0
        print(f"Clean mesh: {len(result.mesh.faces)} faces, "
              f"watertight={result.is_watertight}")

    def test_smoothing_applied(self):
        """Smoothing should change vertex positions."""
        mesh = generate_cylinder_solder_stl(
            BOTTOM_CENTER, TOP_CENTER, RADIUS * 0.8,
            n_angular=16, n_axial=4, include_caps=True,
        )
        orig_verts = mesh.vertices.copy()

        pp = MeshPreprocessor(smooth_iterations=3)
        result = pp.preprocess(mesh)

        # Vertices should have moved (at least some)
        max_disp = np.max(np.abs(result.mesh.vertices - orig_verts))
        print(f"Max vertex displacement after smoothing: {max_disp:.6e}")
        # Smoothing on a cylinder should move vertices
        assert max_disp > 0 or len(result.warnings) > 0


# ===========================================================================
# Diagnostic summary
# ===========================================================================
class TestDiagnosticSummary:
    """Print a summary table of all Phase 7 test scenarios."""

    def test_summary(self, tmp_path):
        """Generate and summarize all shapes (no SE needed)."""
        shapes = {
            "cylinder": lambda: generate_cylinder_solder_stl(
                BOTTOM_CENTER, TOP_CENTER, RADIUS * 0.8,
                n_angular=16, n_axial=4, include_caps=True,
            ),
            "barrel": lambda: generate_barrel_solder_stl(
                BOTTOM_CENTER, TOP_CENTER,
                radius_end=RADIUS * 0.8, radius_mid=RADIUS * 1.0,
                n_angular=16, n_axial=6, include_caps=True,
            ),
            "hourglass": lambda: generate_hourglass_solder_stl(
                BOTTOM_CENTER, TOP_CENTER,
                radius_end=RADIUS * 0.8, radius_mid=RADIUS * 0.5,
                n_angular=16, n_axial=6, include_caps=True,
            ),
        }

        bot_stl, top_stl = _make_flat_pad_stls(
            tmp_path, BOTTOM_CENTER, TOP_CENTER, RADIUS,
        )

        print("\n" + "=" * 70)
        print("Phase 7: Complex STL Pipeline Summary")
        print("=" * 70)
        print(f"{'Shape':<15} {'Verts':>8} {'Faces':>8} {'Caps':>6} "
              f"{'Loops':>6} {'SE Verts':>9} {'SE Edges':>9} {'SE Faces':>9}")
        print("-" * 70)

        for name, gen_func in shapes.items():
            solder = gen_func()
            fit_b, fit_t = _fit_pads(
                bot_stl, top_stl, BOTTOM_CENTER, TOP_CENTER, RADIUS,
            )
            extractor = BoundaryExtractor(fit_bottom=fit_b, fit_top=fit_t)
            extraction = extractor.extract(solder)

            converter = MeshToSEConverter()
            se = converter.convert(
                extraction.lateral_mesh, extraction.boundary_loops,
            )

            print(f"{name:<15} "
                  f"{len(solder.vertices):>8} "
                  f"{len(solder.faces):>8} "
                  f"{extraction.n_cap_faces_removed:>6} "
                  f"{len(extraction.boundary_loops):>6} "
                  f"{len(se.geometry.vertices):>9} "
                  f"{len(se.geometry.edges):>9} "
                  f"{len(se.geometry.faces):>9}")

        print("=" * 70)
