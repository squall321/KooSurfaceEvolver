"""Export mesh to VTK legacy format (UnstructuredGrid)."""

from pathlib import Path
from typing import Optional

import numpy as np


def export_vtk(
    vertices: np.ndarray,
    triangles: np.ndarray,
    filepath: str | Path,
    point_data: Optional[dict] = None,
    cell_data: Optional[dict] = None,
    title: str = "KooSolderEvolver output",
) -> Path:
    """Export mesh as VTK legacy unstructured grid.

    Args:
        vertices: (N, 3) vertex coordinates.
        triangles: (M, 3) triangle vertex indices.
        filepath: Output file path (.vtk).
        point_data: Dict of name -> (N,) arrays for per-vertex data.
        cell_data: Dict of name -> (M,) arrays for per-triangle data.
        title: VTK file title.
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    n_verts = len(vertices)
    n_tris = len(triangles)

    with open(filepath, "w") as f:
        f.write("# vtk DataFile Version 3.0\n")
        f.write(f"{title}\n")
        f.write("ASCII\n")
        f.write("DATASET UNSTRUCTURED_GRID\n")

        # Points
        f.write(f"POINTS {n_verts} double\n")
        for v in vertices:
            f.write(f"{v[0]:.10g} {v[1]:.10g} {v[2]:.10g}\n")

        # Cells
        f.write(f"CELLS {n_tris} {n_tris * 4}\n")
        for tri in triangles:
            f.write(f"3 {tri[0]} {tri[1]} {tri[2]}\n")

        # Cell types (5 = VTK_TRIANGLE)
        f.write(f"CELL_TYPES {n_tris}\n")
        for _ in range(n_tris):
            f.write("5\n")

        # Point data
        if point_data:
            f.write(f"POINT_DATA {n_verts}\n")
            for name, data in point_data.items():
                f.write(f"SCALARS {name} double 1\n")
                f.write("LOOKUP_TABLE default\n")
                for val in data:
                    f.write(f"{val:.10g}\n")

        # Cell data
        if cell_data:
            f.write(f"CELL_DATA {n_tris}\n")
            for name, data in cell_data.items():
                f.write(f"SCALARS {name} double 1\n")
                f.write("LOOKUP_TABLE default\n")
                for val in data:
                    f.write(f"{val:.10g}\n")

    return filepath


def export_vtk_solid(
    vertices: np.ndarray,
    tetrahedra: np.ndarray,
    filepath: str | Path,
    title: str = "KooSolderEvolver solid output",
) -> Path:
    """Export TET4 volume mesh as VTK legacy unstructured grid.

    VTK cell type 10 = VTK_TETRA (4-node tetrahedral element).

    Args:
        vertices:   (N, 3) vertex coordinates.
        tetrahedra: (K, 4) tetrahedron vertex indices (0-based).
        filepath:   Output .vtk file path.
        title:      VTK file title.
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    n_verts = len(vertices)
    n_tets = len(tetrahedra)

    with open(filepath, "w") as f:
        f.write("# vtk DataFile Version 3.0\n")
        f.write(f"{title}\n")
        f.write("ASCII\n")
        f.write("DATASET UNSTRUCTURED_GRID\n")

        f.write(f"POINTS {n_verts} double\n")
        for v in vertices:
            f.write(f"{v[0]:.10g} {v[1]:.10g} {v[2]:.10g}\n")

        # Each tet: 4 nodes + count prefix = 5 values
        f.write(f"CELLS {n_tets} {n_tets * 5}\n")
        for tet in tetrahedra:
            f.write(f"4 {tet[0]} {tet[1]} {tet[2]} {tet[3]}\n")

        # Cell type 10 = VTK_TETRA
        f.write(f"CELL_TYPES {n_tets}\n")
        for _ in range(n_tets):
            f.write("10\n")

    return filepath
