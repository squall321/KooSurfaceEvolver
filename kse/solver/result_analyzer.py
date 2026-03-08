"""Analyze converged Surface Evolver results.

Extracts physical quantities from SE dump files or mesh data:
standoff height, maximum radius, volume, surface area, centroid.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .dump_parser import DumpParser


@dataclass
class JointResult:
    """Physical quantities extracted from a converged SE result."""

    standoff_height: float
    max_radius: float
    volume: float
    surface_area: float
    centroid: np.ndarray
    z_min: float
    z_max: float


class ResultAnalyzer:
    """Analyze SE simulation results."""

    def __init__(self):
        self.parser = DumpParser()

    def analyze(self, dump_path: str | Path) -> JointResult:
        """Analyze a dump file and extract physical quantities.

        Args:
            dump_path: Path to SE dump (.dmp) file.

        Returns:
            JointResult with standoff height, radius, volume, etc.
        """
        mesh = self.parser.parse(dump_path)
        vertices = mesh.vertex_array
        triangles = mesh.face_triangles
        return self.analyze_mesh(vertices, triangles)

    def analyze_mesh(
        self, vertices: np.ndarray, triangles: np.ndarray,
    ) -> JointResult:
        """Analyze mesh arrays directly.

        Args:
            vertices: (N, 3) vertex coordinates.
            triangles: (M, 3) face vertex indices.

        Returns:
            JointResult with physical quantities.
        """
        z_min = float(vertices[:, 2].min())
        z_max = float(vertices[:, 2].max())
        standoff = z_max - z_min

        centroid = vertices.mean(axis=0)

        # Max XY radius from centroid
        dx = vertices[:, 0] - centroid[0]
        dy = vertices[:, 1] - centroid[1]
        max_radius = float(np.max(np.sqrt(dx**2 + dy**2)))

        # Surface area from triangles
        v0 = vertices[triangles[:, 0]]
        v1 = vertices[triangles[:, 1]]
        v2 = vertices[triangles[:, 2]]
        cross = np.cross(v1 - v0, v2 - v0)
        areas = 0.5 * np.linalg.norm(cross, axis=1)
        surface_area = float(areas.sum())

        # Volume estimate via divergence theorem (sum of signed tetrahedra)
        # V = (1/6) * sum_faces( n . v0 * area * 2 )
        normals = cross  # unnormalized (magnitude = 2 * area)
        volume = abs(float(np.sum(
            v0[:, 0] * normals[:, 0]
            + v0[:, 1] * normals[:, 1]
            + v0[:, 2] * normals[:, 2]
        ) / 6.0))

        return JointResult(
            standoff_height=standoff,
            max_radius=max_radius,
            volume=volume,
            surface_area=surface_area,
            centroid=centroid,
            z_min=z_min,
            z_max=z_max,
        )
