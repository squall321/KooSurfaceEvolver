"""Phase 11: Advanced geometry tests (N-way classification, fillet, bridge).

Tests:
- N-way boundary classification (arbitrary number of surfaces)
- MeshToSEConverter with N-way constraints
- STEPPipeline fillet and bridge entry points (code-level, no CadQuery)
- STEPPipelineConfig new fields
"""

from collections import defaultdict

import numpy as np
import pytest
import trimesh

from kse.core.boundary_extractor import BoundaryExtractor, BoundaryLoop
from kse.core.mesh_to_se import MeshToSEConverter
from kse.core.surface_fitter import SurfaceFitter, SurfaceFitResult, FitType
from kse.core.step_pipeline import STEPPipeline, STEPPipelineConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_flat_fit(z_val: float) -> SurfaceFitResult:
    """Create a SurfaceFitResult for a flat surface at z=z_val."""
    return SurfaceFitResult(
        fit_type=FitType.PLANE,
        coefficients=np.array([0.0, 0.0, 0.0]),
        residual_rms=1e-10,
        residual_max=1e-10,
        center_global=np.array([0.0, 0.0, z_val]),
        normal_global=np.array([0.0, 0.0, 1.0]),
        local_axes=np.eye(3),
        radius=1.0,
    )


def _make_open_cylinder(radius, height, sections=16, z_offset=0.0):
    """Create an open cylinder (no caps) mesh with boundary loops."""
    cyl = trimesh.creation.cylinder(
        radius=radius, height=height, sections=sections,
    )
    cyl.apply_translation([0, 0, z_offset + height / 2])

    # Remove top and bottom cap faces
    normals = cyl.face_normals
    keep = np.abs(normals[:, 2]) < 0.9
    lateral = trimesh.Trimesh(
        vertices=cyl.vertices,
        faces=cyl.faces[keep],
        process=True,
    )
    return lateral


def _extract_boundary_loops(mesh):
    """Extract boundary edge loops from an open mesh."""
    edge_face_count = defaultdict(int)
    edge_to_directed = defaultdict(list)

    for fi, face in enumerate(mesh.faces):
        for i in range(3):
            v1, v2 = int(face[i]), int(face[(i + 1) % 3])
            key = (min(v1, v2), max(v1, v2))
            edge_face_count[key] += 1
            edge_to_directed[key].append((v1, v2))

    boundary_edges = []
    for key, count in edge_face_count.items():
        if count == 1:
            boundary_edges.append(edge_to_directed[key][0])

    return boundary_edges


# ---------------------------------------------------------------------------
# 11A: N-way boundary classification
# ---------------------------------------------------------------------------

class TestNWayClassification:
    """Test N-way surface classification in BoundaryExtractor."""

    def test_two_surface_via_surfaces_param(self):
        """N-way with 2 surfaces should work like legacy mode."""
        fit_bottom = _make_flat_fit(0.0)
        fit_top = _make_flat_fit(0.5)

        surfaces = [
            ("bottom", 1, fit_bottom),
            ("top", 2, fit_top),
        ]

        extractor = BoundaryExtractor(surfaces=surfaces)
        assert len(extractor._surfaces) == 2

    def test_three_surface_classification(self):
        """With 3 surfaces, loop should classify to nearest."""
        fit_bot = _make_flat_fit(0.0)
        fit_mid = _make_flat_fit(0.5)
        fit_top = _make_flat_fit(1.0)

        surfaces = [
            ("bottom", 1, fit_bot),
            ("middle", 2, fit_mid),
            ("top", 3, fit_top),
        ]
        extractor = BoundaryExtractor(surfaces=surfaces)

        # Create a loop near z=0 (should classify as "bottom")
        pad_id, cid = extractor._classify_single_loop(
            [0, 1, 2, 3],
            np.array([
                [0.0, 0.0, 0.01],
                [0.1, 0.0, 0.02],
                [0.1, 0.1, 0.01],
                [0.0, 0.1, 0.02],
            ]),
        )
        assert pad_id == "bottom"
        assert cid == 1

    def test_loop_near_top(self):
        """Loop near z=1.0 should classify as top."""
        fit_bot = _make_flat_fit(0.0)
        fit_top = _make_flat_fit(1.0)

        surfaces = [("bottom", 1, fit_bot), ("top", 2, fit_top)]
        extractor = BoundaryExtractor(surfaces=surfaces)

        pad_id, cid = extractor._classify_single_loop(
            [0, 1, 2, 3],
            np.array([
                [0.0, 0.0, 0.98],
                [0.1, 0.0, 0.99],
                [0.1, 0.1, 0.98],
                [0.0, 0.1, 0.99],
            ]),
        )
        assert pad_id == "top"
        assert cid == 2

    def test_no_surfaces_returns_unknown(self):
        """Empty surfaces list → unknown classification."""
        extractor = BoundaryExtractor(surfaces=[])

        pad_id, cid = extractor._classify_single_loop(
            [0, 1], np.array([[0, 0, 0], [1, 1, 1]]),
        )
        assert pad_id == "unknown"


class TestMeshToSENWay:
    """Test MeshToSEConverter with N-way pad classification."""

    def test_dynamic_pad_keys(self):
        """Converter should handle arbitrary pad_id strings."""
        mesh = _make_open_cylinder(0.1, 0.5, sections=8)
        n_verts = len(mesh.vertices)

        # Fake boundary loops with custom pad_ids
        loop1 = BoundaryLoop(
            vertex_ids=[0, 1, 2, 3],
            edge_pairs=[(0, 1), (1, 2), (2, 3), (3, 0)],
            pad_id="pad_0",
            constraint_id=1,
        )
        loop2 = BoundaryLoop(
            vertex_ids=[4, 5, 6, 7],
            edge_pairs=[(4, 5), (5, 6), (6, 7), (7, 4)],
            pad_id="pad_1",
            constraint_id=2,
        )
        loop3 = BoundaryLoop(
            vertex_ids=[8, 9, 10, 11],
            edge_pairs=[(8, 9), (9, 10), (10, 11), (11, 8)],
            pad_id="wall_0",
            constraint_id=3,
        )

        converter = MeshToSEConverter(tension=480.0, density=9.0)
        result = converter.convert(mesh, [loop1, loop2, loop3], target_volume=0.01)

        # Check boundary vertex IDs include all 3 pads
        assert "pad_0" in result.boundary_vertex_ids
        assert "pad_1" in result.boundary_vertex_ids
        assert "wall_0" in result.boundary_vertex_ids

    def test_fixed_vertices_on_boundary(self):
        """Boundary vertices should be marked as fixed with constraints."""
        mesh = _make_open_cylinder(0.1, 0.5, sections=8)

        loop = BoundaryLoop(
            vertex_ids=[0, 1, 2],
            edge_pairs=[(0, 1), (1, 2), (2, 0)],
            pad_id="bottom",
            constraint_id=1,
        )

        converter = MeshToSEConverter(tension=480.0, density=9.0)
        result = converter.convert(mesh, [loop], target_volume=0.01)

        # Check that SE vertex 1 (mapped from mesh vertex 0) is fixed
        v1 = result.geometry.vertices[0]
        assert v1.fixed is True
        assert 1 in v1.constraints


# ---------------------------------------------------------------------------
# 11B: Fillet pipeline config
# ---------------------------------------------------------------------------

class TestFilletConfig:
    """Test STEPPipeline fillet configuration."""

    def test_wall_step_paths_default(self):
        cfg = STEPPipelineConfig()
        assert cfg.wall_step_paths == []

    def test_wall_step_paths_set(self):
        cfg = STEPPipelineConfig(wall_step_paths=["wall1.stp", "wall2.stp"])
        assert len(cfg.wall_step_paths) == 2

    def test_pipeline_has_run_fillet(self):
        """STEPPipeline should have run_fillet method."""
        pipeline = STEPPipeline()
        assert hasattr(pipeline, "run_fillet")
        assert callable(pipeline.run_fillet)


# ---------------------------------------------------------------------------
# 11C: Bridge pad config
# ---------------------------------------------------------------------------

class TestBridgeConfig:
    """Test bridge pad pipeline configuration."""

    def test_pipeline_has_run_bridge(self):
        """STEPPipeline should have run_bridge method."""
        pipeline = STEPPipeline()
        assert hasattr(pipeline, "run_bridge")
        assert callable(pipeline.run_bridge)

    def test_pipeline_has_run_array(self):
        """STEPPipeline should have run_array method."""
        pipeline = STEPPipeline()
        assert hasattr(pipeline, "run_array")
        assert callable(pipeline.run_array)
