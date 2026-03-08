"""Export mesh to LS-DYNA keyword (.k) format."""

from pathlib import Path
from typing import Optional

import numpy as np


def export_lsdyna_k(
    vertices: np.ndarray,
    triangles: np.ndarray,
    filepath: str | Path,
    part_name: str = "SOLDER",
    part_id: int = 1,
) -> Path:
    """Export mesh as LS-DYNA keyword (.k) file.

    Uses *ELEMENT_SHELL with 3-node triangles.

    Args:
        vertices: (N, 3) vertex coordinates.
        triangles: (M, 3) triangle vertex indices (0-based).
        filepath: Output .k file path.
        part_name: LS-DYNA part name.
        part_id: Part ID number.
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    n_verts = len(vertices)
    n_tris = len(triangles)

    with open(filepath, "w") as f:
        f.write("*KEYWORD\n")
        f.write("$# KooSolderEvolver LS-DYNA export\n")
        f.write(f"$# {n_verts} nodes, {n_tris} elements\n")

        # Title
        f.write("*TITLE\n")
        f.write(f"KooSolderEvolver - {part_name}\n")

        # Part
        f.write("*PART\n")
        f.write(f"$#{'title':>72s}\n")
        f.write(f"{part_name}\n")
        f.write("$#     pid     secid       mid     eosid      hgid      grav    adpopt      tmid\n")
        f.write(f"{part_id:10d}{1:10d}{1:10d}{0:10d}{0:10d}{0:10d}{0:10d}{0:10d}\n")

        # Section (shell)
        f.write("*SECTION_SHELL\n")
        f.write("$#   secid    elform      shrf       nip     propt   qr/irid     icomp     setyp\n")
        f.write(f"{1:10d}{2:10d}{1.0:10.1f}{2:10d}{0:10d}{0:10d}{0:10d}{0:10d}\n")
        f.write("$#      t1        t2        t3        t4      nloc     marea      idof    edgset\n")
        f.write(f"{0.001:10.4f}{0.001:10.4f}{0.001:10.4f}{0.001:10.4f}{0:10d}{0:10d}{0:10d}{0:10d}\n")

        # Material (elastic placeholder)
        f.write("*MAT_ELASTIC\n")
        f.write("$#     mid        ro         e        pr        da        db  not used\n")
        f.write(f"{1:10d}{9.0:10.3f}{1e6:10.3e}{0.35:10.3f}{0:10d}{0:10d}{0:10d}\n")

        # Nodes
        f.write("*NODE\n")
        f.write("$#   nid               x               y               z      tc      rc\n")
        for i, v in enumerate(vertices):
            nid = i + 1
            f.write(f"{nid:8d}{v[0]:16.8e}{v[1]:16.8e}{v[2]:16.8e}{0:8d}{0:8d}\n")

        # Elements
        f.write("*ELEMENT_SHELL\n")
        f.write("$#   eid     pid      n1      n2      n3      n4\n")
        for i, tri in enumerate(triangles):
            eid = i + 1
            n1, n2, n3 = tri[0] + 1, tri[1] + 1, tri[2] + 1
            # For triangles, n4 = n3 (degenerated quad)
            f.write(f"{eid:8d}{part_id:8d}{n1:8d}{n2:8d}{n3:8d}{n3:8d}\n")

        f.write("*END\n")

    return filepath


def export_lsdyna_k_solid(
    vertices: np.ndarray,
    tetrahedra: np.ndarray,
    filepath: str | Path,
    part_name: str = "SOLDER",
    part_id: int = 1,
) -> Path:
    """Export TET4 volume mesh as LS-DYNA keyword (.k) file.

    Uses *ELEMENT_SOLID with 4-node tetrahedra (elform=13: improved tet).

    Args:
        vertices:   (N, 3) vertex coordinates.
        tetrahedra: (K, 4) tetrahedron vertex indices (0-based).
        filepath:   Output .k file path.
        part_name:  LS-DYNA part name.
        part_id:    Part ID number.
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    n_verts = len(vertices)
    n_tets = len(tetrahedra)

    with open(filepath, "w") as f:
        f.write("*KEYWORD\n")
        f.write("$# KooSolderEvolver LS-DYNA solid export\n")
        f.write(f"$# {n_verts} nodes, {n_tets} TET4 elements\n")

        f.write("*TITLE\n")
        f.write(f"KooSolderEvolver - {part_name}\n")

        # Part
        f.write("*PART\n")
        f.write(f"$#{'title':>72s}\n")
        f.write(f"{part_name}\n")
        f.write("$#     pid     secid       mid     eosid      hgid      grav    adpopt      tmid\n")
        f.write(f"{part_id:10d}{1:10d}{1:10d}{0:10d}{0:10d}{0:10d}{0:10d}{0:10d}\n")

        # Section solid: elform=13 (improved constant stress tetrahedron)
        f.write("*SECTION_SOLID\n")
        f.write("$#   secid    elform       aet\n")
        f.write(f"{1:10d}{13:10d}{0:10d}\n")

        # Material (elastic placeholder)
        f.write("*MAT_ELASTIC\n")
        f.write("$#     mid        ro         e        pr        da        db  not used\n")
        f.write(f"{1:10d}{9.0:10.3f}{1e6:10.3e}{0.35:10.3f}{0:10d}{0:10d}{0:10d}\n")

        # Nodes
        f.write("*NODE\n")
        f.write("$#   nid               x               y               z      tc      rc\n")
        for i, v in enumerate(vertices):
            f.write(f"{i+1:8d}{v[0]:16.8e}{v[1]:16.8e}{v[2]:16.8e}{0:8d}{0:8d}\n")

        # Elements: *ELEMENT_SOLID has 8 node fields; n5-n8 = 0 for TET4
        f.write("*ELEMENT_SOLID\n")
        f.write("$#   eid     pid      n1      n2      n3      n4      n5      n6      n7      n8\n")
        for i, tet in enumerate(tetrahedra):
            n1, n2, n3, n4 = tet[0]+1, tet[1]+1, tet[2]+1, tet[3]+1
            f.write(f"{i+1:8d}{part_id:8d}"
                    f"{n1:8d}{n2:8d}{n3:8d}{n4:8d}"
                    f"{0:8d}{0:8d}{0:8d}{0:8d}\n")

        f.write("*END\n")

    return filepath
