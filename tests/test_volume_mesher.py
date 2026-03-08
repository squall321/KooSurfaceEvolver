"""Tests for tetrahedral volume mesh generation and solid FEA exporters."""

import numpy as np
import pytest
from pathlib import Path

from kse.mesh.volume_mesher import (
    _find_boundary_edges,
    _chain_boundary_loops,
    close_surface_mesh,
    generate_volume_mesh,
    _is_watertight,
    _merge_vertices,
)
from kse.mesh.quality import assess_tet_quality


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_cylinder(n=12, height=2.0):
    """Open cylinder: n-gon cross-section, no top/bottom caps."""
    theta = np.linspace(0, 2 * np.pi, n, endpoint=False)
    bottom = np.column_stack([np.cos(theta), np.sin(theta), np.zeros(n)])
    top = np.column_stack([np.cos(theta), np.sin(theta), np.full(n, height)])
    verts = np.vstack([bottom, top])
    tris = []
    for i in range(n):
        j = (i + 1) % n
        tris.append([i, j, n + i])
        tris.append([j, n + j, n + i])
    return verts, np.array(tris, dtype=np.int32)


def _make_closed_tet():
    """Single closed tetrahedron (4 triangles)."""
    verts = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.5, 0.866, 0.0],
        [0.5, 0.289, 0.816],
    ])
    tris = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [0, 3, 2]])
    return verts, tris


def _has_tetgen():
    try:
        import tetgen  # noqa: F401
        return True
    except ImportError:
        return False


# ── Boundary edge detection ───────────────────────────────────────────────────

class TestFindBoundaryEdges:

    def test_open_cylinder_has_boundary(self):
        verts, tris = _make_cylinder(n=12)
        boundary = _find_boundary_edges(tris)
        # 12 top + 12 bottom boundary edges
        assert len(boundary) == 24

    def test_closed_tet_no_boundary(self):
        _, tris = _make_closed_tet()
        boundary = _find_boundary_edges(tris)
        assert len(boundary) == 0

    def test_boundary_edges_directed(self):
        """Each returned edge is a (v1, v2) pair."""
        _, tris = _make_cylinder(n=6)
        boundary = _find_boundary_edges(tris)
        for e in boundary:
            assert len(e) == 2
            assert e[0] != e[1]


# ── Boundary loop chaining ────────────────────────────────────────────────────

class TestChainBoundaryLoops:

    def test_cylinder_gives_two_loops(self):
        _, tris = _make_cylinder(n=12)
        boundary = _find_boundary_edges(tris)
        loops = _chain_boundary_loops(boundary)
        assert len(loops) == 2

    def test_loop_sizes(self):
        n = 10
        _, tris = _make_cylinder(n=n)
        boundary = _find_boundary_edges(tris)
        loops = _chain_boundary_loops(boundary)
        sizes = sorted(len(l) for l in loops)
        assert sizes == [n, n]

    def test_each_loop_closed(self):
        """Chaining must visit all boundary edges exactly once."""
        n = 8
        _, tris = _make_cylinder(n=n)
        boundary = _find_boundary_edges(tris)
        loops = _chain_boundary_loops(boundary)
        total_verts = sum(len(l) for l in loops)
        assert total_verts == len(boundary)


# ── Close surface mesh ────────────────────────────────────────────────────────

class TestCloseSurface:

    def test_open_cylinder_becomes_watertight(self):
        verts, tris = _make_cylinder(n=12)
        closed_v, closed_t, n_cap = close_surface_mesh(verts, tris)
        assert n_cap > 0
        assert _is_watertight(closed_v, closed_t)

    def test_n_cap_equals_two_loops(self):
        n = 10
        verts, tris = _make_cylinder(n=n)
        _, _, n_cap = close_surface_mesh(verts, tris)
        # 2D Delaunay cap adds more triangles than a simple centroid fan.
        # At minimum: 2 loops × n boundary triangles; with interior points: much more.
        assert n_cap >= 2 * n

    def test_already_closed_unchanged(self):
        verts, tris = _make_closed_tet()
        closed_v, closed_t, n_cap = close_surface_mesh(verts, tris)
        assert n_cap == 0
        assert len(closed_v) == len(verts)
        assert len(closed_t) == len(tris)

    def test_extra_vertices_added(self):
        """Interior Delaunay sample vertices are added for each cap loop."""
        n = 8
        verts, tris = _make_cylinder(n=n)
        closed_v, _, _ = close_surface_mesh(verts, tris)
        # 2D Delaunay cap adds ≥ 1 vertex per loop (at minimum the centroid).
        assert len(closed_v) >= len(verts) + 2


# ── Merge vertices ────────────────────────────────────────────────────────────

class TestMergeVertices:

    def test_no_duplicates_unchanged(self):
        verts, tris = _make_closed_tet()
        mv, mt = _merge_vertices(verts, tris)
        assert len(mv) == len(verts)

    def test_near_duplicates_merged(self):
        verts, tris = _make_closed_tet()
        # Slightly perturb vertex 3 to near-duplicate of vertex 0
        v_dup = verts.copy()
        v_dup = np.vstack([verts, verts[0] + 1e-12])  # near-duplicate of v0
        t_dup = np.vstack([tris, [[len(verts), 1, 2]]])  # use the near-dup
        mv, mt = _merge_vertices(v_dup, t_dup, tol=1e-10)
        assert len(mv) < len(v_dup)


# ── Tetrahedralization ────────────────────────────────────────────────────────

@pytest.mark.skipif(not _has_tetgen(), reason="tetgen not installed")
class TestTetrahedralize:

    def test_cylinder_generates_tets(self):
        verts, tris = _make_cylinder(n=12, height=2.0)
        result = generate_volume_mesh(verts, tris)
        assert result.tetrahedra.shape[1] == 4
        assert len(result.tetrahedra) > 0
        assert result.n_cap_triangles > 0

    def test_tet_indices_valid(self):
        verts, tris = _make_cylinder(n=12)
        result = generate_volume_mesh(verts, tris)
        n_verts = len(result.vertices)
        assert result.tetrahedra.min() >= 0
        assert result.tetrahedra.max() < n_verts

    def test_closed_tet_input(self):
        """Already-closed surface should also tetrahedralize."""
        import trimesh
        sphere = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
        result = generate_volume_mesh(
            sphere.vertices.astype(np.float64),
            sphere.faces.astype(np.int32),
        )
        assert result.tetrahedra.shape[1] == 4
        assert len(result.tetrahedra) > 0
        assert result.n_cap_triangles == 0  # already closed


@pytest.mark.skipif(not _has_tetgen(), reason="tetgen not installed")
class TestTetQuality:

    def test_quality_report_fields(self):
        verts, tris = _make_cylinder(n=16)
        result = generate_volume_mesh(verts, tris)
        qr = assess_tet_quality(result.vertices, result.tetrahedra)
        assert qr.n_tetrahedra == len(result.tetrahedra)
        assert qr.min_dihedral_deg > 0
        assert qr.max_dihedral_deg <= 180
        assert qr.n_inverted == 0  # TetGen should not produce inverted tets

    def test_quality_summary_str(self):
        verts, tris = _make_cylinder(n=8)
        result = generate_volume_mesh(verts, tris)
        qr = assess_tet_quality(result.vertices, result.tetrahedra)
        s = qr.summary()
        assert "Tet Mesh Quality" in s
        assert "Dihedral" in s


# ── Solid exporters ───────────────────────────────────────────────────────────

@pytest.fixture
def single_tet():
    """Minimal tet mesh: 4 vertices, 1 tetrahedron."""
    verts = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.5, 0.866, 0.0],
        [0.5, 0.289, 0.816],
    ])
    tets = np.array([[0, 1, 2, 3]])
    return verts, tets


class TestGmshSolidExporter:

    def test_creates_file(self, single_tet, tmp_path):
        from kse.mesh.exporters.gmsh_export import export_gmsh_solid
        verts, tets = single_tet
        out = export_gmsh_solid(verts, tets, tmp_path / "test.msh")
        assert out.exists()

    def test_format_version(self, single_tet, tmp_path):
        from kse.mesh.exporters.gmsh_export import export_gmsh_solid
        verts, tets = single_tet
        out = export_gmsh_solid(verts, tets, tmp_path / "test.msh")
        content = out.read_text()
        assert "$MeshFormat" in content
        assert "4.1" in content

    def test_tet4_elements(self, single_tet, tmp_path):
        from kse.mesh.exporters.gmsh_export import export_gmsh_solid
        verts, tets = single_tet
        out = export_gmsh_solid(verts, tets, tmp_path / "test.msh")
        content = out.read_text()
        # Element type 4 = TET4 appears in the Elements block header
        assert "3 1 4 1" in content  # dim=3, entityTag=1, elemType=4, count=1

    def test_no_triangle_elements(self, single_tet, tmp_path):
        from kse.mesh.exporters.gmsh_export import export_gmsh_solid
        verts, tets = single_tet
        out = export_gmsh_solid(verts, tets, tmp_path / "test.msh")
        content = out.read_text()
        # Should not have surface triangles (elem type 2)
        assert "elemType=2" not in content

    def test_vertex_count(self, single_tet, tmp_path):
        from kse.mesh.exporters.gmsh_export import export_gmsh_solid
        verts, tets = single_tet
        out = export_gmsh_solid(verts, tets, tmp_path / "test.msh")
        content = out.read_text()
        assert f"1 {len(verts)} 1 {len(verts)}" in content


class TestAnsysSolidExporter:

    def test_creates_file(self, single_tet, tmp_path):
        from kse.mesh.exporters.ansys_export import export_ansys_cdb_solid
        verts, tets = single_tet
        out = export_ansys_cdb_solid(verts, tets, tmp_path / "test.cdb")
        assert out.exists()

    def test_solid285_element(self, single_tet, tmp_path):
        from kse.mesh.exporters.ansys_export import export_ansys_cdb_solid
        verts, tets = single_tet
        out = export_ansys_cdb_solid(verts, tets, tmp_path / "test.cdb")
        content = out.read_text()
        assert "SOLID285" in content

    def test_no_shell(self, single_tet, tmp_path):
        from kse.mesh.exporters.ansys_export import export_ansys_cdb_solid
        verts, tets = single_tet
        out = export_ansys_cdb_solid(verts, tets, tmp_path / "test.cdb")
        content = out.read_text()
        assert "SHELL" not in content

    def test_nblock_eblock(self, single_tet, tmp_path):
        from kse.mesh.exporters.ansys_export import export_ansys_cdb_solid
        verts, tets = single_tet
        out = export_ansys_cdb_solid(verts, tets, tmp_path / "test.cdb")
        content = out.read_text()
        assert "NBLOCK" in content
        assert "EBLOCK" in content

    def test_four_nodes_per_element(self, single_tet, tmp_path):
        from kse.mesh.exporters.ansys_export import export_ansys_cdb_solid
        verts, tets = single_tet
        out = export_ansys_cdb_solid(verts, tets, tmp_path / "test.cdb")
        content = out.read_text()
        # EBLOCK node count field = 4
        assert "        4" in content  # 9-wide field = "        4"


class TestLsDynaSolidExporter:

    def test_creates_file(self, single_tet, tmp_path):
        from kse.mesh.exporters.lsdyna_export import export_lsdyna_k_solid
        verts, tets = single_tet
        out = export_lsdyna_k_solid(verts, tets, tmp_path / "test.k")
        assert out.exists()

    def test_element_solid_keyword(self, single_tet, tmp_path):
        from kse.mesh.exporters.lsdyna_export import export_lsdyna_k_solid
        verts, tets = single_tet
        out = export_lsdyna_k_solid(verts, tets, tmp_path / "test.k")
        content = out.read_text()
        assert "*ELEMENT_SOLID" in content

    def test_no_element_shell(self, single_tet, tmp_path):
        from kse.mesh.exporters.lsdyna_export import export_lsdyna_k_solid
        verts, tets = single_tet
        out = export_lsdyna_k_solid(verts, tets, tmp_path / "test.k")
        content = out.read_text()
        assert "*ELEMENT_SHELL" not in content

    def test_section_solid(self, single_tet, tmp_path):
        from kse.mesh.exporters.lsdyna_export import export_lsdyna_k_solid
        verts, tets = single_tet
        out = export_lsdyna_k_solid(verts, tets, tmp_path / "test.k")
        content = out.read_text()
        assert "*SECTION_SOLID" in content

    def test_elform_13(self, single_tet, tmp_path):
        from kse.mesh.exporters.lsdyna_export import export_lsdyna_k_solid
        verts, tets = single_tet
        out = export_lsdyna_k_solid(verts, tets, tmp_path / "test.k")
        content = out.read_text()
        assert "13" in content  # elform=13

    def test_eight_node_fields(self, single_tet, tmp_path):
        from kse.mesh.exporters.lsdyna_export import export_lsdyna_k_solid
        verts, tets = single_tet
        out = export_lsdyna_k_solid(verts, tets, tmp_path / "test.k")
        lines = [l for l in out.read_text().splitlines()
                 if l.strip() and not l.startswith("$") and not l.startswith("*")]
        # Element line after ELEMENT_SOLID header: eid pid n1..n8 = 10 fields
        elem_section = False
        for line in out.read_text().splitlines():
            if "*ELEMENT_SOLID" in line:
                elem_section = True
                continue
            if elem_section and line.strip() and not line.startswith("$"):
                parts = line.split()
                assert len(parts) == 10  # eid pid n1 n2 n3 n4 0 0 0 0
                break


class TestVtkSolidExporter:

    def test_creates_file(self, single_tet, tmp_path):
        from kse.mesh.exporters.vtk_export import export_vtk_solid
        verts, tets = single_tet
        out = export_vtk_solid(verts, tets, tmp_path / "test.vtk")
        assert out.exists()

    def test_vtk_tetra_cell_type(self, single_tet, tmp_path):
        from kse.mesh.exporters.vtk_export import export_vtk_solid
        verts, tets = single_tet
        out = export_vtk_solid(verts, tets, tmp_path / "test.vtk")
        content = out.read_text()
        assert "CELL_TYPES" in content
        assert "\n10\n" in content  # VTK_TETRA = 10

    def test_four_nodes_per_cell(self, single_tet, tmp_path):
        from kse.mesh.exporters.vtk_export import export_vtk_solid
        verts, tets = single_tet
        out = export_vtk_solid(verts, tets, tmp_path / "test.vtk")
        content = out.read_text()
        # Each cell line starts with "4 " (4 nodes)
        assert "\n4 " in content

    def test_unstructured_grid_dataset(self, single_tet, tmp_path):
        from kse.mesh.exporters.vtk_export import export_vtk_solid
        verts, tets = single_tet
        out = export_vtk_solid(verts, tets, tmp_path / "test.vtk")
        content = out.read_text()
        assert "UNSTRUCTURED_GRID" in content


# ── Import error ──────────────────────────────────────────────────────────────

class TestImportError:

    def test_missing_tetgen_raises_importerror(self, monkeypatch):
        """If tetgen not installed, generate_volume_mesh raises ImportError."""
        import sys
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "tetgen":
                raise ImportError("No module named 'tetgen'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        verts, tris = _make_closed_tet()
        with pytest.raises(ImportError, match="tetgen"):
            generate_volume_mesh(verts, tris)
