"""Generate STL meshes from analytical surface definitions.

Converts the constraint equations from .fe files into triangulated
STL meshes that KSE can process as input.
"""

from pathlib import Path
from typing import Optional

import numpy as np
import trimesh


def generate_flat_pad_stl(
    center: np.ndarray,
    radius: float,
    extent: Optional[float] = None,
    n_radial: int = 20,
    n_angular: int = 32,
    output_path: Optional[Path] = None,
) -> trimesh.Trimesh:
    """Generate a flat circular pad STL (disk at z=center[2]).

    The disk extends to `extent` radius (default 2.5 * pad radius)
    so that KSE's patch extraction fully covers the pad area.
    """
    if extent is None:
        extent = 2.5 * radius

    center = np.asarray(center, dtype=float)
    verts = [center.copy()]  # center vertex at index 0

    for i_r in range(1, n_radial + 1):
        r = extent * i_r / n_radial
        for i_a in range(n_angular):
            theta = 2 * np.pi * i_a / n_angular
            pt = center + np.array([r * np.cos(theta), r * np.sin(theta), 0.0])
            verts.append(pt)

    verts = np.array(verts)
    faces = []

    # Center fan: vertex 0 to first ring
    for i_a in range(n_angular):
        v1 = 1 + i_a
        v2 = 1 + (i_a + 1) % n_angular
        faces.append([0, v1, v2])

    # Rings
    for i_r in range(1, n_radial):
        base_curr = 1 + (i_r - 1) * n_angular
        base_next = 1 + i_r * n_angular
        for i_a in range(n_angular):
            c0 = base_curr + i_a
            c1 = base_curr + (i_a + 1) % n_angular
            n0 = base_next + i_a
            n1 = base_next + (i_a + 1) % n_angular
            faces.append([c0, n0, n1])
            faces.append([c0, n1, c1])

    faces = np.array(faces)
    mesh = trimesh.Trimesh(vertices=verts, faces=faces)

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        mesh.export(str(output_path))

    return mesh


def generate_tilted_pad_stl(
    center: np.ndarray,
    radius: float,
    normal: np.ndarray,
    extent: Optional[float] = None,
    n_radial: int = 20,
    n_angular: int = 32,
    output_path: Optional[Path] = None,
) -> trimesh.Trimesh:
    """Generate a tilted planar pad STL.

    The disk lies on the plane passing through `center` with the given `normal`.
    """
    if extent is None:
        extent = 2.5 * radius

    center = np.asarray(center, dtype=float)
    normal = np.asarray(normal, dtype=float)
    normal = normal / np.linalg.norm(normal)

    # Build orthonormal frame on the tilted plane
    if abs(normal[2]) > 0.9:
        ref = np.array([1.0, 0.0, 0.0])
    else:
        ref = np.array([0.0, 0.0, 1.0])
    u = np.cross(normal, ref)
    u = u / np.linalg.norm(u)
    v = np.cross(normal, u)
    v = v / np.linalg.norm(v)

    verts = [center.copy()]

    for i_r in range(1, n_radial + 1):
        r = extent * i_r / n_radial
        for i_a in range(n_angular):
            theta = 2 * np.pi * i_a / n_angular
            pt = center + r * np.cos(theta) * u + r * np.sin(theta) * v
            verts.append(pt)

    verts = np.array(verts)
    faces = []

    # Center fan
    for i_a in range(n_angular):
        v1 = 1 + i_a
        v2 = 1 + (i_a + 1) % n_angular
        faces.append([0, v1, v2])

    # Rings
    for i_r in range(1, n_radial):
        base_curr = 1 + (i_r - 1) * n_angular
        base_next = 1 + i_r * n_angular
        for i_a in range(n_angular):
            c0 = base_curr + i_a
            c1 = base_curr + (i_a + 1) % n_angular
            n0 = base_next + i_a
            n1 = base_next + (i_a + 1) % n_angular
            faces.append([c0, n0, n1])
            faces.append([c0, n1, c1])

    faces = np.array(faces)
    mesh = trimesh.Trimesh(vertices=verts, faces=faces)

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        mesh.export(str(output_path))

    return mesh


def generate_spherical_cap_stl(
    sphere_center: np.ndarray,
    sphere_radius: float,
    cap_extent_angle: float = 60.0,
    n_lat: int = 20,
    n_lon: int = 32,
    output_path: Optional[Path] = None,
) -> trimesh.Trimesh:
    """Generate a spherical cap STL.

    The cap is the region of the sphere around its "south pole"
    (the point closest to z=0), extending cap_extent_angle degrees
    from the pole.
    """
    sphere_center = np.asarray(sphere_center, dtype=float)
    cap_rad = np.radians(cap_extent_angle)

    # Pole of the cap (bottom of the sphere, facing the pad)
    pole = sphere_center - np.array([0, 0, sphere_radius])

    verts = [pole.copy()]  # index 0: south pole

    for i_lat in range(1, n_lat + 1):
        phi = cap_rad * i_lat / n_lat  # angle from pole
        for i_lon in range(n_lon):
            theta = 2 * np.pi * i_lon / n_lon
            # Spherical coordinates from south pole
            x = sphere_center[0] + sphere_radius * np.sin(phi) * np.cos(theta)
            y = sphere_center[1] + sphere_radius * np.sin(phi) * np.sin(theta)
            z = sphere_center[2] - sphere_radius * np.cos(phi)
            verts.append([x, y, z])

    verts = np.array(verts)
    faces = []

    # Pole fan
    for i_lon in range(n_lon):
        v1 = 1 + i_lon
        v2 = 1 + (i_lon + 1) % n_lon
        faces.append([0, v1, v2])

    # Latitude rings
    for i_lat in range(1, n_lat):
        base_curr = 1 + (i_lat - 1) * n_lon
        base_next = 1 + i_lat * n_lon
        for i_lon in range(n_lon):
            c0 = base_curr + i_lon
            c1 = base_curr + (i_lon + 1) % n_lon
            n0 = base_next + i_lon
            n1 = base_next + (i_lon + 1) % n_lon
            faces.append([c0, n0, n1])
            faces.append([c0, n1, c1])

    faces = np.array(faces)
    mesh = trimesh.Trimesh(vertices=verts, faces=faces)

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        mesh.export(str(output_path))

    return mesh
