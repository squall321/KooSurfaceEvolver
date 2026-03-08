"""Preprocess solder STL meshes for Surface Evolver conversion.

Cleans, repairs, and validates triangle meshes from CAD exports
before converting them to SE topology.
"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import trimesh

from kse.mesh.quality import assess_quality, QualityReport
from kse.mesh.refiner import laplacian_smooth, subdivide_long_edges


@dataclass
class PreprocessResult:
    """Result of mesh preprocessing."""

    mesh: trimesh.Trimesh
    is_watertight: bool
    n_removed_degenerate: int
    n_fixed_normals: int
    quality: Optional[QualityReport]
    warnings: list = field(default_factory=list)


class MeshPreprocessor:
    """Clean and validate solder STL meshes for SE conversion."""

    def __init__(
        self,
        min_area: float = 1e-20,
        smooth_iterations: int = 0,
        smooth_factor: float = 0.3,
        max_edge_length: float = 0.0,
    ):
        self.min_area = min_area
        self.smooth_iterations = smooth_iterations
        self.smooth_factor = smooth_factor
        self.max_edge_length = max_edge_length

    def preprocess(self, mesh: trimesh.Trimesh) -> PreprocessResult:
        """Full preprocessing pipeline."""
        warnings = []

        # 1. Remove degenerate faces
        n_before = len(mesh.faces)
        mesh = self._remove_degenerate_faces(mesh)
        n_degenerate = n_before - len(mesh.faces)
        if n_degenerate > 0:
            warnings.append(f"Removed {n_degenerate} degenerate faces")

        # 2. Fix normals for consistency
        n_fixed = self._fix_normals(mesh)
        if n_fixed > 0:
            warnings.append(f"Fixed {n_fixed} face normals")

        # 3. Check watertight status
        is_watertight = mesh.is_watertight

        # 4. Optional Laplacian smoothing
        if self.smooth_iterations > 0:
            verts = mesh.vertices.copy()
            verts = laplacian_smooth(
                verts,
                mesh.faces,
                iterations=self.smooth_iterations,
                factor=self.smooth_factor,
            )
            mesh = trimesh.Trimesh(vertices=verts, faces=mesh.faces)
            warnings.append(
                f"Applied {self.smooth_iterations} smoothing iterations"
            )

        # 5. Optional edge subdivision
        if self.max_edge_length > 0:
            verts, faces = subdivide_long_edges(
                mesh.vertices,
                mesh.faces,
                self.max_edge_length,
            )
            mesh = trimesh.Trimesh(vertices=verts, faces=faces)

        # 6. Quality assessment
        quality = None
        if len(mesh.faces) > 0:
            quality = assess_quality(mesh.vertices, mesh.faces)

        return PreprocessResult(
            mesh=mesh,
            is_watertight=is_watertight,
            n_removed_degenerate=n_degenerate,
            n_fixed_normals=n_fixed,
            quality=quality,
            warnings=warnings,
        )

    def _remove_degenerate_faces(
        self, mesh: trimesh.Trimesh
    ) -> trimesh.Trimesh:
        """Remove faces with area below threshold."""
        areas = mesh.area_faces
        keep = areas > self.min_area
        if keep.all():
            return mesh
        return trimesh.Trimesh(
            vertices=mesh.vertices,
            faces=mesh.faces[keep],
        )

    def _fix_normals(self, mesh: trimesh.Trimesh) -> int:
        """Ensure consistent face winding. Returns count of flipped faces."""
        if len(mesh.faces) == 0:
            return 0
        # trimesh tracks broken normals internally
        try:
            broken_before = mesh.face_normals.copy()
            trimesh.repair.fix_normals(mesh)
            broken_after = mesh.face_normals
            # Count faces whose normal direction changed significantly
            dots = np.sum(broken_before * broken_after, axis=1)
            n_flipped = int(np.sum(dots < 0))
            return n_flipped
        except Exception:
            return 0
