"""STL generators for realistic solder joint pad geometries.

Supports circular and square pads at arbitrary positions,
for testing the KSE pipeline with practical BGA/LGA/QFN geometries.
"""

from pathlib import Path
from typing import Optional

import numpy as np
import trimesh


def generate_square_pad_stl(
    center: np.ndarray,
    side: float,
    extent: Optional[float] = None,
    n_grid: int = 30,
    output_path: Optional[Path] = None,
) -> trimesh.Trimesh:
    """Generate a flat square pad STL at z=center[2].

    Creates a square region of side `side` centered at `center`,
    embedded in a larger flat mesh of size `extent` for patch extraction.

    Args:
        center: [x, y, z] center of the pad.
        side: Side length of the square pad.
        extent: Total mesh extent (default 3 * side).
        n_grid: Grid resolution per side.
        output_path: If set, export the STL.
    """
    if extent is None:
        extent = 3.0 * side

    center = np.asarray(center, dtype=float)
    half = extent / 2.0

    # Regular grid on the XY plane at z=center[2]
    xs = np.linspace(center[0] - half, center[0] + half, n_grid)
    ys = np.linspace(center[1] - half, center[1] + half, n_grid)

    verts = []
    for y in ys:
        for x in xs:
            verts.append([x, y, center[2]])
    verts = np.array(verts)

    faces = []
    for j in range(n_grid - 1):
        for i in range(n_grid - 1):
            v00 = j * n_grid + i
            v10 = j * n_grid + (i + 1)
            v01 = (j + 1) * n_grid + i
            v11 = (j + 1) * n_grid + (i + 1)
            faces.append([v00, v10, v11])
            faces.append([v00, v11, v01])

    faces = np.array(faces)
    mesh = trimesh.Trimesh(vertices=verts, faces=faces)

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        mesh.export(str(output_path))

    return mesh
