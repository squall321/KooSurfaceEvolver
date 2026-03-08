"""STL file reader with local patch extraction around solder joint centers."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import trimesh


@dataclass
class LocalPatch:
    """A local patch extracted from an STL surface around a center point."""

    vertices: np.ndarray          # (N, 3) patch vertex coordinates
    faces: np.ndarray             # (M, 3) face indices into vertices
    normals: np.ndarray           # (M, 3) face normals
    center: np.ndarray            # (3,) projected center on surface
    avg_normal: np.ndarray        # (3,) average surface normal at center
    local_axes: np.ndarray        # (3, 3) local coordinate frame [u, v, n]
    radius: float                 # extraction radius
    local_coords: np.ndarray = field(default=None)  # (N, 3) in local frame


class STLReader:
    """Read STL files and extract local patches around specified points."""

    def __init__(self, stl_path: str | Path):
        self.path = Path(stl_path)
        self.mesh = trimesh.load(str(self.path), force="mesh")

    @classmethod
    def from_mesh(cls, mesh: trimesh.Trimesh) -> "STLReader":
        """Create an STLReader directly from a trimesh object (no file I/O)."""
        instance = object.__new__(cls)
        instance.path = None
        instance.mesh = mesh
        return instance

    @property
    def bounds(self) -> np.ndarray:
        return self.mesh.bounds

    @property
    def num_faces(self) -> int:
        return len(self.mesh.faces)

    def extract_patch(
        self,
        center: np.ndarray,
        radius: float,
        margin: float = 1.3,
    ) -> LocalPatch:
        """Extract a circular patch from the STL surface.

        Args:
            center: Approximate center point (will be projected onto surface).
            radius: Radius of the circular patch to extract.
            margin: Multiplier on radius for initial triangle collection.

        Returns:
            LocalPatch with vertices, faces, normals, and local coordinate system.
        """
        center = np.asarray(center, dtype=np.float64)

        # Project center onto nearest surface point
        closest_point, _, face_id = trimesh.proximity.closest_point(
            self.mesh, center.reshape(1, 3)
        )
        proj_center = closest_point[0]
        center_normal = self.mesh.face_normals[face_id[0]]

        # Collect faces within margin * radius of projected center
        face_centroids = self.mesh.triangles_center
        dists = np.linalg.norm(face_centroids - proj_center, axis=1)
        mask = dists < radius * margin

        if mask.sum() < 3:
            # Fallback: take nearest N faces
            n_fallback = max(20, int(self.num_faces * 0.01))
            idx = np.argsort(dists)[:n_fallback]
            mask = np.zeros(len(dists), dtype=bool)
            mask[idx] = True

        # Extract sub-mesh
        patch_faces_global = self.mesh.faces[mask]
        patch_normals = self.mesh.face_normals[mask]

        # Remap vertex indices
        unique_verts, inverse = np.unique(patch_faces_global, return_inverse=True)
        patch_vertices = self.mesh.vertices[unique_verts]
        patch_faces = inverse.reshape(-1, 3)

        # Compute weighted average normal (weighted by face area)
        face_verts = patch_vertices[patch_faces]
        areas = 0.5 * np.linalg.norm(
            np.cross(
                face_verts[:, 1] - face_verts[:, 0],
                face_verts[:, 2] - face_verts[:, 0],
            ),
            axis=1,
        )
        avg_normal = (patch_normals * areas[:, None]).sum(axis=0)
        norm = np.linalg.norm(avg_normal)
        if norm > 1e-12:
            avg_normal /= norm
        else:
            avg_normal = center_normal.copy()

        # Build local coordinate frame: n = avg_normal, u/v = tangent plane
        local_axes = _build_local_frame(avg_normal)

        # Compute local coordinates
        rel = patch_vertices - proj_center
        local_coords = rel @ local_axes.T  # columns are u, v, n

        # Trim to circular patch in local tangent plane
        planar_dist = np.sqrt(local_coords[:, 0] ** 2 + local_coords[:, 1] ** 2)
        vert_mask = planar_dist <= radius * margin
        if vert_mask.sum() < 3:
            vert_mask[:] = True  # keep all if too few

        # Keep faces where all vertices are within radius
        face_vert_in = vert_mask[patch_faces]
        face_mask = face_vert_in.all(axis=1)
        if face_mask.sum() < 1:
            face_mask = face_vert_in.any(axis=1)

        kept_faces = patch_faces[face_mask]
        kept_normals = patch_normals[face_mask]

        # Remap again
        unique2, inv2 = np.unique(kept_faces, return_inverse=True)
        final_verts = patch_vertices[unique2]
        final_faces = inv2.reshape(-1, 3)
        final_local = local_coords[unique2]

        return LocalPatch(
            vertices=final_verts,
            faces=final_faces,
            normals=kept_normals,
            center=proj_center,
            avg_normal=avg_normal,
            local_axes=local_axes,
            radius=radius,
            local_coords=final_local,
        )


def _build_local_frame(normal: np.ndarray) -> np.ndarray:
    """Build orthonormal frame [u, v, n] from a normal vector.

    Returns (3, 3) matrix where rows are u, v, n axes.
    """
    n = normal / np.linalg.norm(normal)

    # Pick a non-parallel reference vector
    ref = np.array([1.0, 0.0, 0.0])
    if abs(np.dot(n, ref)) > 0.9:
        ref = np.array([0.0, 1.0, 0.0])

    u = np.cross(n, ref)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    v /= np.linalg.norm(v)

    return np.array([u, v, n])
