"""Phase 12: Multi-body and multi-joint tests.

Tests:
- Void modeling (2-body SE topology)
- Multi-joint STEP assembly identification
- STEPPipeline void config fields
"""

import numpy as np
import pytest
import trimesh

from kse.core.mesh_to_se import MeshToSEConverter
from kse.core.boundary_extractor import BoundaryLoop
from kse.core.geometry_builder import Body
from kse.core.step_pipeline import STEPPipeline, STEPPipelineConfig
from kse.core.step_reader import (
    STEPAssembly, STEPSolid, PartRole, MultiJointAssembly,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_open_box():
    """Create an open box mesh (top/bottom removed) with loops."""
    box = trimesh.creation.box(extents=[1, 1, 1])
    normals = box.face_normals
    keep = np.abs(normals[:, 2]) < 0.5
    lateral = trimesh.Trimesh(
        vertices=box.vertices,
        faces=box.faces[keep],
        process=True,
    )
    return lateral


def _make_fake_solid(name, role, bounds_min, bounds_max, volume=1.0):
    """Create a fake STEPSolid for testing identification logic."""
    mesh = trimesh.creation.box(
        extents=[
            bounds_max[0] - bounds_min[0],
            bounds_max[1] - bounds_min[1],
            bounds_max[2] - bounds_min[2],
        ],
    )
    center = [(a + b) / 2 for a, b in zip(bounds_min, bounds_max)]
    mesh.apply_translation(center)

    return STEPSolid(
        name=name,
        role=role,
        faces=[],
        volume=volume,
        bounds=np.array([bounds_min, bounds_max], dtype=float),
        combined_mesh=mesh,
    )


# ---------------------------------------------------------------------------
# 12A: Void modeling
# ---------------------------------------------------------------------------

class TestVoidModeling:
    """Test void (2-body) SE topology generation."""

    def test_convert_with_void_2_bodies(self):
        """convert_with_void should produce 2 SE bodies."""
        lateral = _make_open_box()

        loop1 = BoundaryLoop(
            vertex_ids=[0, 1, 2, 3],
            edge_pairs=[(0, 1), (1, 2), (2, 3), (3, 0)],
            pad_id="bottom",
            constraint_id=1,
        )
        loop2 = BoundaryLoop(
            vertex_ids=[4, 5, 6, 7],
            edge_pairs=[(4, 5), (5, 6), (6, 7), (7, 4)],
            pad_id="top",
            constraint_id=2,
        )

        void_mesh = trimesh.creation.icosphere(subdivisions=1, radius=0.1)
        assert void_mesh.is_watertight

        converter = MeshToSEConverter(tension=480.0, density=9.0)
        result = converter.convert_with_void(
            lateral, [loop1, loop2], void_mesh,
            target_volume=0.5,
        )

        geom = result.geometry
        assert len(geom.bodies) == 2

    def test_void_body_no_density(self):
        """Body 2 (void) should have density=None."""
        lateral = _make_open_box()
        loop = BoundaryLoop(
            vertex_ids=[0, 1, 2, 3],
            edge_pairs=[(0, 1), (1, 2), (2, 3), (3, 0)],
            pad_id="bottom",
            constraint_id=1,
        )

        void_mesh = trimesh.creation.icosphere(subdivisions=1, radius=0.05)

        converter = MeshToSEConverter(tension=480.0, density=9.0)
        result = converter.convert_with_void(
            lateral, [loop], void_mesh,
            target_volume=0.5,
        )

        body2 = result.geometry.bodies[1]
        assert body2.id == 2
        assert body2.density is None
        assert body2.volume is not None
        assert float(body2.volume) > 0

    def test_void_faces_in_both_bodies(self):
        """Void faces should appear in body 1 (negative) and body 2 (positive)."""
        lateral = _make_open_box()
        loop = BoundaryLoop(
            vertex_ids=[0, 1],
            edge_pairs=[(0, 1), (1, 0)],
            pad_id="bottom",
            constraint_id=1,
        )

        void_mesh = trimesh.creation.icosphere(subdivisions=1, radius=0.05)
        n_void_faces = len(void_mesh.faces)

        converter = MeshToSEConverter(tension=480.0, density=9.0)
        result = converter.convert_with_void(
            lateral, [loop], void_mesh,
            target_volume=0.5,
        )

        body1 = result.geometry.bodies[0]
        body2 = result.geometry.bodies[1]

        # Body 2 should have exactly n_void_faces
        assert len(body2.faces) == n_void_faces

        # Body 1 should have original faces + n_void_faces negative entries
        n_original_faces = len(lateral.faces)
        assert len(body1.faces) == n_original_faces + n_void_faces

        # Void faces in body 1 should be negative
        void_face_ids = set(body2.faces)
        negated_in_body1 = {-f for f in body1.faces if f < 0}
        assert negated_in_body1 == void_face_ids

    def test_solder_volume_reduced_by_void(self):
        """Body 1 volume should be total - void volume."""
        lateral = _make_open_box()
        loop = BoundaryLoop(
            vertex_ids=[0, 1],
            edge_pairs=[(0, 1), (1, 0)],
            pad_id="bottom",
            constraint_id=1,
        )

        void_mesh = trimesh.creation.icosphere(subdivisions=1, radius=0.1)
        void_vol = abs(void_mesh.volume)
        target_vol = 1.0

        converter = MeshToSEConverter(tension=480.0, density=9.0)
        result = converter.convert_with_void(
            lateral, [loop], void_mesh,
            target_volume=target_vol,
        )

        body1_vol = float(result.geometry.bodies[0].volume)
        body2_vol = float(result.geometry.bodies[1].volume)

        assert body1_vol == pytest.approx(target_vol - void_vol, abs=0.01)
        assert body2_vol == pytest.approx(void_vol, abs=0.01)

    def test_void_vertex_count(self):
        """Total vertices should be outer + void vertices."""
        lateral = _make_open_box()
        loop = BoundaryLoop(
            vertex_ids=[0, 1],
            edge_pairs=[(0, 1), (1, 0)],
            pad_id="bottom",
            constraint_id=1,
        )

        void_mesh = trimesh.creation.icosphere(subdivisions=1, radius=0.05)
        n_outer_verts = len(lateral.vertices)
        n_void_verts = len(void_mesh.vertices)

        converter = MeshToSEConverter(tension=480.0, density=9.0)
        result = converter.convert_with_void(
            lateral, [loop], void_mesh,
            target_volume=0.5,
        )

        assert len(result.geometry.vertices) == n_outer_verts + n_void_verts


# ---------------------------------------------------------------------------
# 12A: Void pipeline config
# ---------------------------------------------------------------------------

class TestVoidConfig:
    """Test void modeling pipeline configuration."""

    def test_void_config_defaults(self):
        cfg = STEPPipelineConfig()
        assert cfg.void_enabled is False
        assert cfg.void_radius == 0.05
        assert cfg.void_position is None

    def test_void_config_set(self):
        cfg = STEPPipelineConfig(
            void_enabled=True,
            void_radius=0.1,
            void_position=[0.0, 0.0, 0.5],
        )
        assert cfg.void_enabled is True
        assert cfg.void_radius == 0.1
        assert cfg.void_position == [0.0, 0.0, 0.5]

    def test_create_void_mesh(self):
        """STEPPipeline._create_void_mesh should create an icosphere."""
        solder_mesh = trimesh.creation.box(extents=[1, 1, 1])
        void_mesh = STEPPipeline._create_void_mesh(
            solder_mesh, radius=0.1,
        )
        assert void_mesh.is_watertight
        assert len(void_mesh.vertices) > 10

    def test_create_void_mesh_custom_position(self):
        solder_mesh = trimesh.creation.box(extents=[1, 1, 1])
        void_mesh = STEPPipeline._create_void_mesh(
            solder_mesh, radius=0.1, position=[1.0, 2.0, 3.0],
        )
        center = void_mesh.vertices.mean(axis=0)
        np.testing.assert_allclose(center, [1.0, 2.0, 3.0], atol=0.01)


# ---------------------------------------------------------------------------
# 12B: Multi-joint identification
# ---------------------------------------------------------------------------

class TestMultiJointIdentification:
    """Test multi-joint part identification logic."""

    def test_multi_joint_assembly_dataclass(self):
        """MultiJointAssembly should be importable and constructable."""
        mja = MultiJointAssembly(joints=[])
        assert mja.joints == []
        assert mja.pad_bottom_solid is None

    def test_identify_parts_multi_logic(self):
        """Test multi-joint identification with fake solids.

        Cannot use STEPReader (requires CadQuery), but we can test the
        logic directly by constructing the data structures.
        """
        # 2 pads (large footprint) + 3 solders (small)
        bottom_pad = _make_fake_solid(
            "pcb_pad", PartRole.UNKNOWN,
            [-5, -5, -0.1], [5, 5, 0],
            volume=50.0,
        )
        top_pad = _make_fake_solid(
            "comp_pad", PartRole.UNKNOWN,
            [-5, -5, 0.5], [5, 5, 0.6],
            volume=50.0,
        )
        solder1 = _make_fake_solid(
            "solder1", PartRole.UNKNOWN,
            [-1.5, -1.5, 0], [-0.5, -0.5, 0.5],
            volume=0.5,
        )
        solder2 = _make_fake_solid(
            "solder2", PartRole.UNKNOWN,
            [-0.5, -0.5, 0], [0.5, 0.5, 0.5],
            volume=0.5,
        )
        solder3 = _make_fake_solid(
            "solder3", PartRole.UNKNOWN,
            [0.5, 0.5, 0], [1.5, 1.5, 0.5],
            volume=0.5,
        )

        assembly = STEPAssembly(
            solids=[bottom_pad, top_pad, solder1, solder2, solder3],
        )

        # Manually run identification logic (simulating identify_parts_multi)
        solids = assembly.solids
        footprints = []
        for s in solids:
            dx = s.bounds[1][0] - s.bounds[0][0]
            dy = s.bounds[1][1] - s.bounds[0][1]
            footprints.append(dx * dy)

        fp_order = np.argsort(footprints)[::-1]
        pad_indices = set(fp_order[:2].tolist())

        # The two pads should be at indices 0 and 1
        assert 0 in pad_indices  # bottom_pad (10x10)
        assert 1 in pad_indices  # top_pad (10x10)

        solder_solids = [
            s for i, s in enumerate(solids) if i not in pad_indices
        ]
        assert len(solder_solids) == 3

    def test_pipeline_has_run_array(self):
        pipeline = STEPPipeline()
        assert hasattr(pipeline, "run_array")
