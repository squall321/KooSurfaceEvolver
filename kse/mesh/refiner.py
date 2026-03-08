"""Post-processing mesh refinement for FEM quality improvement."""

import numpy as np


def laplacian_smooth(
    vertices: np.ndarray,
    triangles: np.ndarray,
    iterations: int = 5,
    factor: float = 0.3,
    fixed_mask: np.ndarray = None,
) -> np.ndarray:
    """Laplacian smoothing of a triangle mesh.

    Args:
        vertices: (N, 3) vertex positions.
        triangles: (M, 3) triangle indices.
        iterations: Number of smoothing iterations.
        factor: Smoothing factor (0-1), higher = more smoothing.
        fixed_mask: (N,) boolean, True = vertex cannot move.

    Returns:
        Smoothed vertex positions (N, 3).
    """
    verts = vertices.copy()
    n = len(verts)

    if fixed_mask is None:
        fixed_mask = np.zeros(n, dtype=bool)

    # Build adjacency
    neighbors = [set() for _ in range(n)]
    for tri in triangles:
        for i in range(3):
            for j in range(3):
                if i != j:
                    neighbors[tri[i]].add(tri[j])

    for _ in range(iterations):
        new_verts = verts.copy()
        for i in range(n):
            if fixed_mask[i] or not neighbors[i]:
                continue
            nbrs = list(neighbors[i])
            avg = verts[nbrs].mean(axis=0)
            new_verts[i] = verts[i] + factor * (avg - verts[i])
        verts = new_verts

    return verts


def subdivide_long_edges(
    vertices: np.ndarray,
    triangles: np.ndarray,
    max_edge_length: float,
) -> tuple:
    """Subdivide edges longer than threshold.

    Returns:
        (new_vertices, new_triangles) after midpoint subdivision.
    """
    verts = list(vertices)
    new_tris = []
    midpoint_cache = {}

    def get_midpoint(v1, v2):
        key = (min(v1, v2), max(v1, v2))
        if key in midpoint_cache:
            return midpoint_cache[key]
        mid = (np.array(verts[v1]) + np.array(verts[v2])) / 2.0
        idx = len(verts)
        verts.append(mid)
        midpoint_cache[key] = idx
        return idx

    for tri in triangles:
        a, b, c = tri
        la = np.linalg.norm(np.array(verts[b]) - np.array(verts[c]))
        lb = np.linalg.norm(np.array(verts[a]) - np.array(verts[c]))
        lc = np.linalg.norm(np.array(verts[a]) - np.array(verts[b]))

        long_edges = []
        if la > max_edge_length:
            long_edges.append(0)
        if lb > max_edge_length:
            long_edges.append(1)
        if lc > max_edge_length:
            long_edges.append(2)

        if len(long_edges) == 0:
            new_tris.append([a, b, c])
        elif len(long_edges) == 3:
            # Split all three edges
            mab = get_midpoint(a, b)
            mbc = get_midpoint(b, c)
            mca = get_midpoint(c, a)
            new_tris.extend([
                [a, mab, mca],
                [mab, b, mbc],
                [mca, mbc, c],
                [mab, mbc, mca],
            ])
        else:
            # Split longest edge only
            if la >= lb and la >= lc:
                m = get_midpoint(b, c)
                new_tris.extend([[a, b, m], [a, m, c]])
            elif lb >= lc:
                m = get_midpoint(a, c)
                new_tris.extend([[a, b, m], [b, c, m]])
            else:
                m = get_midpoint(a, b)
                new_tris.extend([[a, m, c], [m, b, c]])

    return np.array(verts), np.array(new_tris, dtype=int)
