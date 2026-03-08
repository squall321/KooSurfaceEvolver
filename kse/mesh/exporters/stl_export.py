"""Export mesh to STL format (ASCII and Binary)."""

import struct
from pathlib import Path

import numpy as np


def export_stl_ascii(
    vertices: np.ndarray,
    triangles: np.ndarray,
    filepath: str | Path,
    solid_name: str = "solder",
) -> Path:
    """Export mesh as ASCII STL.

    Args:
        vertices: (N, 3) vertex coordinates.
        triangles: (M, 3) triangle vertex indices.
        filepath: Output file path.
        solid_name: Name of the solid.
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    with open(filepath, "w") as f:
        f.write(f"solid {solid_name}\n")
        for tri in triangles:
            v0, v1, v2 = vertices[tri[0]], vertices[tri[1]], vertices[tri[2]]
            normal = np.cross(v1 - v0, v2 - v0)
            norm = np.linalg.norm(normal)
            if norm > 1e-20:
                normal /= norm
            f.write(f"  facet normal {normal[0]:.6e} {normal[1]:.6e} {normal[2]:.6e}\n")
            f.write("    outer loop\n")
            f.write(f"      vertex {v0[0]:.6e} {v0[1]:.6e} {v0[2]:.6e}\n")
            f.write(f"      vertex {v1[0]:.6e} {v1[1]:.6e} {v1[2]:.6e}\n")
            f.write(f"      vertex {v2[0]:.6e} {v2[1]:.6e} {v2[2]:.6e}\n")
            f.write("    endloop\n")
            f.write("  endfacet\n")
        f.write(f"endsolid {solid_name}\n")

    return filepath


def export_stl_binary(
    vertices: np.ndarray,
    triangles: np.ndarray,
    filepath: str | Path,
) -> Path:
    """Export mesh as Binary STL."""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    with open(filepath, "wb") as f:
        # 80-byte header
        header = b"KooSolderEvolver Binary STL" + b"\0" * 53
        f.write(header[:80])

        # Number of triangles
        f.write(struct.pack("<I", len(triangles)))

        for tri in triangles:
            v0, v1, v2 = vertices[tri[0]], vertices[tri[1]], vertices[tri[2]]
            normal = np.cross(v1 - v0, v2 - v0)
            norm = np.linalg.norm(normal)
            if norm > 1e-20:
                normal /= norm

            # Normal vector
            f.write(struct.pack("<3f", *normal.astype(np.float32)))
            # Vertices
            f.write(struct.pack("<3f", *v0.astype(np.float32)))
            f.write(struct.pack("<3f", *v1.astype(np.float32)))
            f.write(struct.pack("<3f", *v2.astype(np.float32)))
            # Attribute byte count
            f.write(struct.pack("<H", 0))

    return filepath
