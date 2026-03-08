"""Export mesh to ANSYS .cdb (CDWRITE) format."""

from pathlib import Path
from typing import Optional

import numpy as np


def export_ansys_cdb(
    vertices: np.ndarray,
    triangles: np.ndarray,
    filepath: str | Path,
    component_name: str = "SOLDER",
) -> Path:
    """Export mesh as ANSYS .cdb format (CDWRITE compatible).

    Uses SHELL181 element type (4-node shell, degenerated to 3-node triangle).

    Args:
        vertices: (N, 3) vertex coordinates.
        triangles: (M, 3) triangle vertex indices (0-based).
        filepath: Output .cdb file path.
        component_name: ANSYS component name.
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    n_verts = len(vertices)
    n_tris = len(triangles)

    with open(filepath, "w") as f:
        f.write("/PREP7\n")
        f.write(f"! KooSolderEvolver ANSYS export\n")
        f.write(f"! {n_verts} nodes, {n_tris} elements\n\n")

        # Element type
        f.write("ET,1,SHELL181\n")
        f.write("KEYOPT,1,3,2  ! Full integration\n\n")

        # Nodes
        f.write("NBLOCK,6,SOLID\n")
        f.write("(1i9,3e20.13)\n")
        for i, v in enumerate(vertices):
            node_id = i + 1
            f.write(f"{node_id:9d}{v[0]:20.13e}{v[1]:20.13e}{v[2]:20.13e}\n")
        f.write("N,R5.3,LOC,-1,\n\n")

        # Elements (SHELL181 with 3 nodes: n1, n2, n3, n3 repeated)
        f.write("EBLOCK,19,SOLID\n")
        f.write("(15i9)\n")
        for i, tri in enumerate(triangles):
            elem_id = i + 1
            mat_id = 1
            etype = 1
            real_const = 1
            sec_id = 1
            n1, n2, n3 = tri[0] + 1, tri[1] + 1, tri[2] + 1
            # EBLOCK format: material, etype, real, section, 0, 0, 0, 0, n_nodes, 0, elem_id, nodes...
            f.write(f"{mat_id:9d}{etype:9d}{real_const:9d}{sec_id:9d}"
                    f"{'':9s}{'':9s}{'':9s}{'':9s}"
                    f"{3:9d}{'':9s}{elem_id:9d}"
                    f"{n1:9d}{n2:9d}{n3:9d}\n")
        f.write("-1\n\n")

        # Component
        f.write(f"CMBLOCK,{component_name},ELEM,{n_tris}\n")
        f.write("(8i10)\n")
        for i in range(0, n_tris, 8):
            chunk = list(range(i + 1, min(i + 9, n_tris + 1)))
            f.write("".join(f"{e:10d}" for e in chunk) + "\n")
        f.write("\n")

        f.write("FINISH\n")

    return filepath


def export_ansys_cdb_solid(
    vertices: np.ndarray,
    tetrahedra: np.ndarray,
    filepath: str | Path,
    component_name: str = "SOLDER",
) -> Path:
    """Export TET4 volume mesh as ANSYS .cdb format.

    Uses SOLID285 element type (4-node tetrahedral solid).

    Args:
        vertices:    (N, 3) vertex coordinates.
        tetrahedra:  (K, 4) tetrahedron vertex indices (0-based).
        filepath:    Output .cdb file path.
        component_name: ANSYS component name.
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    n_verts = len(vertices)
    n_tets = len(tetrahedra)

    with open(filepath, "w") as f:
        f.write("/PREP7\n")
        f.write(f"! KooSolderEvolver ANSYS solid export\n")
        f.write(f"! {n_verts} nodes, {n_tets} TET4 elements\n\n")

        # SOLID285: 4-node tetrahedral with mixed u-P formulation
        f.write("ET,1,SOLID285\n\n")

        # Nodes
        f.write("NBLOCK,6,SOLID\n")
        f.write("(1i9,3e20.13)\n")
        for i, v in enumerate(vertices):
            f.write(f"{i+1:9d}{v[0]:20.13e}{v[1]:20.13e}{v[2]:20.13e}\n")
        f.write("N,R5.3,LOC,-1,\n\n")

        # Elements: SOLID285 has 4 nodes (no degeneration needed)
        f.write("EBLOCK,19,SOLID\n")
        f.write("(15i9)\n")
        for i, tet in enumerate(tetrahedra):
            mat_id, etype, real_const, sec_id = 1, 1, 1, 1
            n1, n2, n3, n4 = tet[0]+1, tet[1]+1, tet[2]+1, tet[3]+1
            f.write(
                f"{mat_id:9d}{etype:9d}{real_const:9d}{sec_id:9d}"
                f"{'':9s}{'':9s}{'':9s}{'':9s}"
                f"{4:9d}{'':9s}{i+1:9d}"
                f"{n1:9d}{n2:9d}{n3:9d}{n4:9d}\n"
            )
        f.write("-1\n\n")

        # Component
        f.write(f"CMBLOCK,{component_name},ELEM,{n_tets}\n")
        f.write("(8i10)\n")
        for i in range(0, n_tets, 8):
            chunk = list(range(i + 1, min(i + 9, n_tets + 1)))
            f.write("".join(f"{e:10d}" for e in chunk) + "\n")
        f.write("\nFINISH\n")

    return filepath
