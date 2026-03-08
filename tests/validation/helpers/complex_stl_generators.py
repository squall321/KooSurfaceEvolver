"""Generate synthetic solder STL meshes for testing the complex STL pipeline.

Creates cylinder, barrel, hourglass, and irregular-boundary solder shapes
between two pad centers.
"""

from pathlib import Path
from typing import Callable, Optional

import numpy as np
import trimesh


def generate_cylinder_solder_stl(
    bottom_center: np.ndarray,
    top_center: np.ndarray,
    radius: float,
    n_angular: int = 16,
    n_axial: int = 4,
    include_caps: bool = True,
    output_path: Optional[Path] = None,
) -> trimesh.Trimesh:
    """Generate a cylindrical solder mesh between two pad centers.

    Args:
        bottom_center: [x, y, z] bottom pad center.
        top_center: [x, y, z] top pad center.
        radius: Cylinder radius.
        n_angular: Vertices around circumference.
        n_axial: Vertex rings along the axis (including top/bottom).
        include_caps: If True, add triangulated cap faces on both ends.
        output_path: If set, export the STL.
    """
    bottom = np.asarray(bottom_center, dtype=float)
    top = np.asarray(top_center, dtype=float)

    def _radius_func(t):
        return radius

    return _generate_surface_of_revolution(
        bottom, top, _radius_func, n_angular, n_axial,
        include_caps, output_path,
    )


def generate_barrel_solder_stl(
    bottom_center: np.ndarray,
    top_center: np.ndarray,
    radius_end: float,
    radius_mid: float,
    n_angular: int = 16,
    n_axial: int = 8,
    include_caps: bool = True,
    output_path: Optional[Path] = None,
) -> trimesh.Trimesh:
    """Generate a barrel-shaped solder (wider at middle).

    Uses a parabolic radius profile: r(t) = r_end + (r_mid - r_end) * 4*t*(1-t)
    """
    bottom = np.asarray(bottom_center, dtype=float)
    top = np.asarray(top_center, dtype=float)

    def _radius_func(t):
        return radius_end + (radius_mid - radius_end) * 4 * t * (1 - t)

    return _generate_surface_of_revolution(
        bottom, top, _radius_func, n_angular, n_axial,
        include_caps, output_path,
    )


def generate_hourglass_solder_stl(
    bottom_center: np.ndarray,
    top_center: np.ndarray,
    radius_end: float,
    radius_mid: float,
    n_angular: int = 16,
    n_axial: int = 8,
    include_caps: bool = True,
    output_path: Optional[Path] = None,
) -> trimesh.Trimesh:
    """Generate an hourglass-shaped solder (narrower at middle).

    Same as barrel but radius_mid < radius_end.
    """
    bottom = np.asarray(bottom_center, dtype=float)
    top = np.asarray(top_center, dtype=float)

    def _radius_func(t):
        return radius_end + (radius_mid - radius_end) * 4 * t * (1 - t)

    return _generate_surface_of_revolution(
        bottom, top, _radius_func, n_angular, n_axial,
        include_caps, output_path,
    )


def generate_irregular_boundary_solder_stl(
    bottom_center: np.ndarray,
    top_center: np.ndarray,
    boundary_func: Callable[[float], float],
    n_angular: int = 24,
    n_axial: int = 8,
    include_caps: bool = True,
    output_path: Optional[Path] = None,
) -> trimesh.Trimesh:
    """Generate solder with arbitrary boundary function r(theta).

    Args:
        boundary_func: r(theta) where theta in [0, 2*pi), returns radius.
    """
    bottom = np.asarray(bottom_center, dtype=float)
    top = np.asarray(top_center, dtype=float)
    axis = top - bottom
    height = np.linalg.norm(axis)
    axis_dir = axis / height

    # Build orthonormal frame
    if abs(axis_dir[2]) > 0.9:
        ref = np.array([1.0, 0.0, 0.0])
    else:
        ref = np.array([0.0, 0.0, 1.0])
    u = np.cross(axis_dir, ref)
    u /= np.linalg.norm(u)
    v = np.cross(axis_dir, u)

    verts = []
    faces = []
    angles = np.linspace(0, 2 * np.pi, n_angular, endpoint=False)

    # Generate lateral vertices
    for j in range(n_axial + 1):
        t = j / n_axial
        pt_axis = bottom + t * axis
        for i, theta in enumerate(angles):
            r = boundary_func(theta)
            pt = pt_axis + r * np.cos(theta) * u + r * np.sin(theta) * v
            verts.append(pt)

    verts = np.array(verts)

    # Lateral faces
    for j in range(n_axial):
        for i in range(n_angular):
            i_next = (i + 1) % n_angular
            v00 = j * n_angular + i
            v10 = j * n_angular + i_next
            v01 = (j + 1) * n_angular + i
            v11 = (j + 1) * n_angular + i_next
            faces.append([v00, v10, v11])
            faces.append([v00, v11, v01])

    if include_caps:
        # Bottom cap (fan from centroid)
        bot_center_idx = len(verts)
        verts = np.vstack([verts, bottom.reshape(1, 3)])
        for i in range(n_angular):
            i_next = (i + 1) % n_angular
            faces.append([bot_center_idx, i_next, i])

        # Top cap (fan from centroid)
        top_center_idx = len(verts)
        verts = np.vstack([verts, top.reshape(1, 3)])
        top_base = n_axial * n_angular
        for i in range(n_angular):
            i_next = (i + 1) % n_angular
            faces.append([top_center_idx, top_base + i, top_base + i_next])

    faces = np.array(faces)
    mesh = trimesh.Trimesh(vertices=verts, faces=faces)

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        mesh.export(str(output_path))

    return mesh


def _generate_surface_of_revolution(
    bottom: np.ndarray,
    top: np.ndarray,
    radius_func: Callable[[float], float],
    n_angular: int,
    n_axial: int,
    include_caps: bool,
    output_path: Optional[Path],
) -> trimesh.Trimesh:
    """Generate a surface of revolution along the axis bottom→top.

    radius_func(t) gives the radius at parameter t in [0, 1].
    """
    axis = top - bottom
    height = np.linalg.norm(axis)
    axis_dir = axis / height

    # Build orthonormal frame
    if abs(axis_dir[2]) > 0.9:
        ref = np.array([1.0, 0.0, 0.0])
    else:
        ref = np.array([0.0, 0.0, 1.0])
    u = np.cross(axis_dir, ref)
    u /= np.linalg.norm(u)
    v = np.cross(axis_dir, u)

    verts = []
    faces = []
    angles = np.linspace(0, 2 * np.pi, n_angular, endpoint=False)

    # Generate lateral vertices: (n_axial+1) rings of n_angular vertices
    for j in range(n_axial + 1):
        t = j / n_axial
        r = radius_func(t)
        pt_axis = bottom + t * axis
        for theta in angles:
            pt = pt_axis + r * np.cos(theta) * u + r * np.sin(theta) * v
            verts.append(pt)

    verts = np.array(verts)

    # Lateral faces (quads split into 2 triangles)
    for j in range(n_axial):
        for i in range(n_angular):
            i_next = (i + 1) % n_angular
            v00 = j * n_angular + i
            v10 = j * n_angular + i_next
            v01 = (j + 1) * n_angular + i
            v11 = (j + 1) * n_angular + i_next
            faces.append([v00, v10, v11])
            faces.append([v00, v11, v01])

    if include_caps:
        # Bottom cap: fan from centroid
        bot_center_idx = len(verts)
        verts = np.vstack([verts, bottom.reshape(1, 3)])
        for i in range(n_angular):
            i_next = (i + 1) % n_angular
            faces.append([bot_center_idx, i_next, i])

        # Top cap: fan from centroid
        top_center_idx = len(verts)
        verts = np.vstack([verts, top.reshape(1, 3)])
        top_base = n_axial * n_angular
        for i in range(n_angular):
            i_next = (i + 1) % n_angular
            faces.append([top_center_idx, top_base + i, top_base + i_next])

    faces = np.array(faces)
    mesh = trimesh.Trimesh(vertices=verts, faces=faces)

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        mesh.export(str(output_path))

    return mesh
