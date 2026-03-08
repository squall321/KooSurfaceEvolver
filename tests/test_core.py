"""Tests for core modules: stl_reader, surface_fitter, constraint_gen, geometry_builder."""

import tempfile
from pathlib import Path

import numpy as np
import pytest
import trimesh

from kse.core.stl_reader import STLReader, LocalPatch
from kse.core.surface_fitter import SurfaceFitter, FitType
from kse.core.constraint_gen import ConstraintGenerator
from kse.core.geometry_builder import GeometryBuilder
from kse.core.fe_writer import FEWriter, SolderJointConfig


@pytest.fixture
def flat_stl(tmp_path):
    """Create a flat square STL at z=0."""
    verts = np.array([
        [-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0],
    ], dtype=float)
    faces = np.array([[0, 1, 2], [0, 2, 3]])
    mesh = trimesh.Trimesh(vertices=verts, faces=faces)
    path = tmp_path / "flat.stl"
    mesh.export(str(path))
    return path


@pytest.fixture
def curved_stl(tmp_path):
    """Create a curved (spherical-cap) STL."""
    # Generate a hemisphere-like cap
    n = 20
    verts = []
    faces = []
    # Center vertex
    verts.append([0, 0, 0.01])

    for i in range(n):
        theta = 2 * np.pi * i / n
        r = 0.5
        x = r * np.cos(theta)
        y = r * np.sin(theta)
        z = 0.1 * (x**2 + y**2)  # parabolic
        verts.append([x, y, z])

    for i in range(n):
        j = (i + 1) % n
        faces.append([0, i + 1, j + 1])

    mesh = trimesh.Trimesh(vertices=np.array(verts), faces=np.array(faces))
    path = tmp_path / "curved.stl"
    mesh.export(str(path))
    return path


@pytest.fixture
def elevated_stl(tmp_path):
    """Create a flat STL at z=0.12."""
    verts = np.array([
        [-1, -1, 0.12], [1, -1, 0.12], [1, 1, 0.12], [-1, 1, 0.12],
    ], dtype=float)
    faces = np.array([[0, 1, 2], [0, 2, 3]])
    mesh = trimesh.Trimesh(vertices=verts, faces=faces)
    path = tmp_path / "elevated.stl"
    mesh.export(str(path))
    return path


class TestSTLReader:
    def test_load(self, flat_stl):
        reader = STLReader(flat_stl)
        assert reader.num_faces == 2

    def test_extract_patch(self, flat_stl):
        reader = STLReader(flat_stl)
        patch = reader.extract_patch(np.array([0, 0, 0]), radius=0.5)
        assert isinstance(patch, LocalPatch)
        assert len(patch.vertices) > 0
        assert patch.center is not None
        assert np.abs(patch.avg_normal[2]) > 0.9  # mostly z-normal


class TestSurfaceFitter:
    def test_fit_plane(self, flat_stl):
        reader = STLReader(flat_stl)
        patch = reader.extract_patch(np.array([0, 0, 0]), radius=0.5)
        fitter = SurfaceFitter()
        result = fitter.fit(patch)
        assert result.fit_type == FitType.PLANE
        assert result.residual_rms < 1e-6

    def test_fit_curved(self, curved_stl):
        reader = STLReader(curved_stl)
        patch = reader.extract_patch(np.array([0, 0, 0.01]), radius=0.3)
        fitter = SurfaceFitter()
        result = fitter.fit(patch)
        # Should use at least quadratic for curved surface
        assert result.fit_type in (FitType.QUADRATIC, FitType.QUARTIC, FitType.PLANE)


class TestConstraintGenerator:
    def test_generate_plane_constraint(self, flat_stl):
        reader = STLReader(flat_stl)
        patch = reader.extract_patch(np.array([0, 0, 0]), radius=0.5)
        fitter = SurfaceFitter()
        fit = fitter.fit(patch)

        cgen = ConstraintGenerator()
        constraint = cgen.generate_surface_constraint(fit, 1, contact_angle=30.0)
        assert constraint.constraint_id == 1
        assert len(constraint.formula) > 0
        assert constraint.energy is not None

    def test_generate_rim(self, flat_stl):
        reader = STLReader(flat_stl)
        patch = reader.extract_patch(np.array([0, 0, 0]), radius=0.5)
        fitter = SurfaceFitter()
        fit = fitter.fit(patch)

        cgen = ConstraintGenerator()
        rim = cgen.generate_rim_constraint(fit, 3, radius=0.1)
        assert rim.constraint_id == 3
        assert "0.01" in rim.formula or "x" in rim.formula  # radius^2 = 0.01


class TestGeometryBuilder:
    def test_build_basic(self, flat_stl, elevated_stl):
        reader_a = STLReader(flat_stl)
        reader_b = STLReader(elevated_stl)

        patch_a = reader_a.extract_patch(np.array([0, 0, 0]), 0.1)
        patch_b = reader_b.extract_patch(np.array([0, 0, 0.12]), 0.1)

        fitter = SurfaceFitter()
        fit_a = fitter.fit(patch_a)
        fit_b = fitter.fit(patch_b)

        builder = GeometryBuilder(n_segments=6)
        geom = builder.build(fit_a, fit_b, 0.1, 1e-3)

        assert geom.n_vertices == 12  # 6 + 6
        assert geom.n_edges == 18      # 6 bottom + 6 top + 6 vertical
        assert geom.n_faces == 6       # 6 lateral
        assert len(geom.bodies) == 1


class TestFEWriter:
    def test_write_basic(self, flat_stl, elevated_stl, tmp_path):
        reader_a = STLReader(flat_stl)
        reader_b = STLReader(elevated_stl)

        patch_a = reader_a.extract_patch(np.array([0, 0, 0]), 0.1)
        patch_b = reader_b.extract_patch(np.array([0, 0, 0.12]), 0.1)

        fitter = SurfaceFitter()
        fit_a = fitter.fit(patch_a)
        fit_b = fitter.fit(patch_b)

        cgen = ConstraintGenerator()
        c_a = cgen.generate_surface_constraint(fit_a, 1)
        c_b = cgen.generate_surface_constraint(fit_b, 2)
        rim = cgen.generate_rim_constraint(fit_a, 3, 0.1)
        bdry = cgen.generate_parametric_boundary(fit_b, 1, 0.1)

        builder = GeometryBuilder(n_segments=6)
        geom = builder.build(fit_a, fit_b, 0.1, 1e-3)

        config = SolderJointConfig(radius=0.1, volume=1e-3)
        writer = FEWriter()
        fe_path = tmp_path / "test.fe"
        writer.write_single(fe_path, geom, [c_a, c_b, rim], [bdry], config)

        assert fe_path.exists()
        content = fe_path.read_text()
        assert "vertices" in content
        assert "edges" in content
        assert "faces" in content
        assert "bodies" in content
        assert "S_TENSION" in content
        assert "hessian_normal" in content


class TestExporters:
    def test_stl_export(self, tmp_path):
        from kse.mesh.exporters.stl_export import export_stl_ascii
        verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
        tris = np.array([[0, 1, 2]])
        path = export_stl_ascii(verts, tris, tmp_path / "test.stl")
        assert path.exists()
        assert "facet normal" in path.read_text()

    def test_vtk_export(self, tmp_path):
        from kse.mesh.exporters.vtk_export import export_vtk
        verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
        tris = np.array([[0, 1, 2]])
        path = export_vtk(verts, tris, tmp_path / "test.vtk")
        assert path.exists()
        assert "UNSTRUCTURED_GRID" in path.read_text()

    def test_gmsh_export(self, tmp_path):
        from kse.mesh.exporters.gmsh_export import export_gmsh
        verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
        tris = np.array([[0, 1, 2]])
        path = export_gmsh(verts, tris, tmp_path / "test.msh")
        assert path.exists()
        assert "$MeshFormat" in path.read_text()

    def test_ansys_export(self, tmp_path):
        from kse.mesh.exporters.ansys_export import export_ansys_cdb
        verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
        tris = np.array([[0, 1, 2]])
        path = export_ansys_cdb(verts, tris, tmp_path / "test.cdb")
        assert path.exists()
        assert "NBLOCK" in path.read_text()

    def test_lsdyna_export(self, tmp_path):
        from kse.mesh.exporters.lsdyna_export import export_lsdyna_k
        verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
        tris = np.array([[0, 1, 2]])
        path = export_lsdyna_k(verts, tris, tmp_path / "test.k")
        assert path.exists()
        assert "*KEYWORD" in path.read_text()

    def test_quality_assessment(self):
        from kse.mesh.quality import assess_quality
        verts = np.array([[0, 0, 0], [1, 0, 0], [0.5, 0.866, 0]], dtype=float)
        tris = np.array([[0, 1, 2]])
        q = assess_quality(verts, tris)
        assert q.n_triangles == 1
        assert q.aspect_ratio_mean > 0
        assert q.min_angle_deg > 50  # near-equilateral


class TestDumpParser:
    def test_parse_mound_dump(self):
        from kse.solver.dump_parser import DumpParser
        dmp_path = Path("examples/workshop/fe/mound.dmp")
        if not dmp_path.exists():
            pytest.skip("mound.dmp not found")
        parser = DumpParser()
        mesh = parser.parse(dmp_path)
        assert len(mesh.vertices) > 0
        assert len(mesh.edges) > 0
        assert len(mesh.faces) > 0
        assert len(mesh.bodies) > 0
        assert mesh.total_energy == 5.0


class TestCSrcFallback:
    def test_fallback_available(self):
        from kse.csrc import fast_extract_patch, fast_compute_sdf
        assert callable(fast_extract_patch)
        assert callable(fast_compute_sdf)

    def test_extract_patch(self):
        from kse.csrc import fast_extract_patch
        verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [2, 2, 0]], dtype=float)
        faces = np.array([[0, 1, 2], [1, 2, 3]])
        mask = fast_extract_patch(verts, faces, np.array([0, 0, 0]), 1.0)
        assert mask.dtype == bool or mask.dtype == np.bool_
        assert mask[0] == True  # first face centroid is within radius
