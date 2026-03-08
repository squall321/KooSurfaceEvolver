"""Export mesh to GMSH .msh format (v4.1 ASCII)."""

from pathlib import Path
from typing import Optional

import numpy as np


def export_gmsh(
    vertices: np.ndarray,
    triangles: np.ndarray,
    filepath: str | Path,
    physical_groups: Optional[dict] = None,
) -> Path:
    """Export mesh as GMSH .msh v4.1 ASCII.

    Args:
        vertices: (N, 3) vertex coordinates.
        triangles: (M, 3) triangle vertex indices (0-based).
        filepath: Output .msh file path.
        physical_groups: Dict of group_name -> list of triangle indices.
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    n_verts = len(vertices)
    n_tris = len(triangles)

    # Build physical group tags (1-based)
    tri_tags = np.ones(n_tris, dtype=int)  # default group 1
    pg_list = [("solder", 1)]

    if physical_groups:
        pg_list = []
        for idx, (name, tri_indices) in enumerate(physical_groups.items()):
            tag = idx + 1
            pg_list.append((name, tag))
            for ti in tri_indices:
                tri_tags[ti] = tag

    with open(filepath, "w") as f:
        # Header
        f.write("$MeshFormat\n")
        f.write("4.1 0 8\n")
        f.write("$EndMeshFormat\n")

        # Physical names
        f.write("$PhysicalNames\n")
        f.write(f"{len(pg_list)}\n")
        for name, tag in pg_list:
            f.write(f"2 {tag} \"{name}\"\n")
        f.write("$EndPhysicalNames\n")

        # Entities (simplified: one surface entity per physical group)
        f.write("$Entities\n")
        f.write(f"0 0 {len(pg_list)} 0\n")  # 0 points, 0 curves, N surfaces, 0 volumes
        for name, tag in pg_list:
            # surface: tag, minX, minY, minZ, maxX, maxY, maxZ, numPhysicalTags, physTags
            bbox = vertices.min(axis=0)
            bbox_max = vertices.max(axis=0)
            f.write(f"{tag} {bbox[0]:.10g} {bbox[1]:.10g} {bbox[2]:.10g} "
                    f"{bbox_max[0]:.10g} {bbox_max[1]:.10g} {bbox_max[2]:.10g} "
                    f"1 {tag} 0\n")
        f.write("$EndEntities\n")

        # Nodes
        f.write("$Nodes\n")
        f.write(f"1 {n_verts} 1 {n_verts}\n")
        # One block: entity dim=2, tag=1
        f.write(f"2 1 0 {n_verts}\n")
        for i in range(n_verts):
            f.write(f"{i + 1}\n")
        for v in vertices:
            f.write(f"{v[0]:.10g} {v[1]:.10g} {v[2]:.10g}\n")
        f.write("$EndNodes\n")

        # Elements
        # Group elements by entity tag
        groups = {}
        for i, tag in enumerate(tri_tags):
            groups.setdefault(tag, []).append(i)

        total_blocks = len(groups)
        f.write("$Elements\n")
        f.write(f"{total_blocks} {n_tris} 1 {n_tris}\n")

        elem_id = 1
        for tag in sorted(groups.keys()):
            indices = groups[tag]
            f.write(f"2 {tag} 2 {len(indices)}\n")  # dim=2, entityTag, elemType=2 (triangle)
            for i in indices:
                tri = triangles[i]
                f.write(f"{elem_id} {tri[0]+1} {tri[1]+1} {tri[2]+1}\n")
                elem_id += 1

        f.write("$EndElements\n")

    return filepath


def export_gmsh_solid(
    vertices: np.ndarray,
    tetrahedra: np.ndarray,
    filepath: str | Path,
    physical_name: str = "solder",
) -> Path:
    """Export TET4 volume mesh as GMSH .msh v4.1 ASCII.

    Args:
        vertices:   (N, 3) vertex coordinates.
        tetrahedra: (K, 4) tetrahedron vertex indices (0-based).
        filepath:   Output .msh file path.
        physical_name: Physical group name for the solder volume.
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    n_verts = len(vertices)
    n_tets = len(tetrahedra)

    with open(filepath, "w") as f:
        f.write("$MeshFormat\n4.1 0 8\n$EndMeshFormat\n")

        # Physical names (volume = dim 3)
        f.write("$PhysicalNames\n1\n")
        f.write(f'3 1 "{physical_name}"\n')
        f.write("$EndPhysicalNames\n")

        # Entities: 1 volume entity
        bbox = vertices.min(axis=0)
        bmax = vertices.max(axis=0)
        f.write("$Entities\n0 0 0 1\n")
        f.write(f"1 {bbox[0]:.10g} {bbox[1]:.10g} {bbox[2]:.10g} "
                f"{bmax[0]:.10g} {bmax[1]:.10g} {bmax[2]:.10g} 1 1 0\n")
        f.write("$EndEntities\n")

        # Nodes (entity dim=3, tag=1)
        f.write("$Nodes\n")
        f.write(f"1 {n_verts} 1 {n_verts}\n")
        f.write(f"3 1 0 {n_verts}\n")
        for i in range(n_verts):
            f.write(f"{i + 1}\n")
        for v in vertices:
            f.write(f"{v[0]:.10g} {v[1]:.10g} {v[2]:.10g}\n")
        f.write("$EndNodes\n")

        # Elements: element type 4 = TET4, dim=3
        f.write("$Elements\n")
        f.write(f"1 {n_tets} 1 {n_tets}\n")
        f.write(f"3 1 4 {n_tets}\n")  # dim=3, entityTag=1, elemType=4 (TET4)
        for i, tet in enumerate(tetrahedra):
            f.write(f"{i + 1} {tet[0]+1} {tet[1]+1} {tet[2]+1} {tet[3]+1}\n")
        f.write("$EndElements\n")

    return filepath
