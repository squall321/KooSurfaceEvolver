"""Pure Python fallback implementations for C extension functions.

These provide identical functionality to the C extensions but run in pure Python.
Used when C extension is not compiled or not available on the platform.
"""

import numpy as np


def fast_extract_patch(
    vertices: np.ndarray,
    faces: np.ndarray,
    center: np.ndarray,
    radius: float,
) -> np.ndarray:
    """Extract face indices within radius of center point.

    Pure Python implementation using vectorized numpy operations.

    Args:
        vertices: (N, 3) mesh vertices.
        faces: (M, 3) triangle face indices.
        center: (3,) center point.
        radius: Extraction radius.

    Returns:
        Boolean mask (M,) indicating faces within radius.
    """
    center = np.asarray(center, dtype=np.float64)

    # Compute face centroids
    v0 = vertices[faces[:, 0]]
    v1 = vertices[faces[:, 1]]
    v2 = vertices[faces[:, 2]]
    centroids = (v0 + v1 + v2) / 3.0

    # Distance from center
    dists = np.linalg.norm(centroids - center, axis=1)
    return dists <= radius


def fast_compute_sdf(
    query_points: np.ndarray,
    vertices: np.ndarray,
    faces: np.ndarray,
    face_normals: np.ndarray,
) -> np.ndarray:
    """Compute signed distance from query points to triangle mesh.

    Pure Python implementation. For each query point, finds the nearest
    triangle and computes signed distance using the face normal.

    Args:
        query_points: (Q, 3) points to evaluate.
        vertices: (N, 3) mesh vertices.
        faces: (M, 3) triangle face indices.
        face_normals: (M, 3) face normal vectors.

    Returns:
        (Q,) signed distances (positive = outside, negative = inside).
    """
    query_points = np.asarray(query_points, dtype=np.float64)
    n_queries = len(query_points)
    distances = np.zeros(n_queries)

    # Pre-compute triangle data
    v0 = vertices[faces[:, 0]]
    v1 = vertices[faces[:, 1]]
    v2 = vertices[faces[:, 2]]
    centroids = (v0 + v1 + v2) / 3.0

    for qi in range(n_queries):
        p = query_points[qi]

        # Find nearest centroid (approximate nearest triangle)
        dists = np.linalg.norm(centroids - p, axis=1)
        nearest_idx = np.argmin(dists)

        # Compute distance to nearest triangle plane
        tri_v0 = v0[nearest_idx]
        n = face_normals[nearest_idx]

        # Signed distance = dot(p - v0, normal)
        d = np.dot(p - tri_v0, n)

        # Unsigned distance to triangle (approximate: use centroid distance)
        # For better accuracy, project to triangle plane
        proj = p - d * n
        unsigned = np.linalg.norm(p - proj)

        # Sign from normal direction
        distances[qi] = d if abs(d) > 1e-20 else unsigned

    return distances
