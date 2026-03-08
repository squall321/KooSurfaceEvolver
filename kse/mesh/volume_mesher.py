"""Tetrahedral volume mesh generation from surface mesh.

Pipeline:
  1. Find boundary edges (open loops at pad contacts)
  2. Chain into closed boundary loops
  3. Cap each loop with fan triangulation from centroid
  4. Verify watertight; flip cap winding if needed
  5. Tetrahedralize with TetGen

Usage:
    from kse.mesh.volume_mesher import generate_volume_mesh
    result = generate_volume_mesh(vertices, triangles)
    # result.vertices: (N, 3) tet mesh vertices
    # result.tetrahedra: (K, 4) tetrahedra (0-based indices)
"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class VolumeMeshResult:
    """Result of tetrahedral volume mesh generation."""

    vertices: np.ndarray        # (N, 3) tet mesh vertices
    tetrahedra: np.ndarray      # (K, 4) tetrahedra, 0-based vertex indices
    surface_triangles: np.ndarray  # watertight closed surface (input to TetGen)
    n_cap_triangles: int        # triangles added to close open boundaries
    n_surface_nodes: int = 0   # nodes that lie on the closed surface (fixed during smoothing)


# ── Public API ────────────────────────────────────────────────────────────────

def generate_volume_mesh(
    vertices: np.ndarray,
    triangles: np.ndarray,
    min_dihedral: float = 10.0,
    minratio: float = 1.5,
    maxvolume: float = -1.0,
    order: int = 1,
    quiet: bool = True,
    smooth_iterations: int = 0,
    smooth_omega: float = 0.2,
) -> VolumeMeshResult:
    """Generate tetrahedral volume mesh from a (possibly open) surface mesh.

    Main entry point. Closes any open boundary loops, tetrahedralizes, then
    applies Laplacian smoothing to interior Steiner nodes to improve quality.

    Args:
        vertices:          (N, 3) surface vertex coordinates.
        triangles:         (M, 3) surface triangle indices (0-based).
        min_dihedral:      Minimum dihedral angle in degrees (TetGen quality).
        minratio:          Max circumradius/shortest-edge ratio (quality control).
                           Lower = better quality, more Steiner points.
        maxvolume:         Maximum tetrahedron volume (-1 = no limit).
                           Set to limit large elements (e.g., 0.01 * total_vol).
        order:             1 for TET4 (linear), 2 for TET10 (quadratic).
        quiet:             Suppress TetGen output.
        smooth_iterations: Laplacian smoothing iterations for interior nodes.
                           0 = disabled. 10 iterations is a good default.
        smooth_omega:      Smoothing step size (0 < omega <= 1). 0.2 is safe.

    Returns:
        VolumeMeshResult with vertices and tetrahedra arrays.

    Raises:
        ImportError: if tetgen is not installed.
        RuntimeError: if TetGen fails.
    """
    # Merge near-duplicate vertices (SE constraint intersections can have fp gaps)
    vertices, triangles = _merge_vertices(vertices, triangles)

    # Close open boundary loops
    closed_verts, closed_tris, n_cap = close_surface_mesh(vertices, triangles)
    n_surface_nodes = len(closed_verts)

    # Repair surface mesh before TetGen.
    # 1) Non-manifold edges (count>2) cause TetGen to segfault — must fix first.
    # 2) Inconsistent face winding causes TetGen "self-intersections" error.
    # pymeshfix handles both; trimesh.fix_normals handles (2) alone.
    closed_verts, closed_tris, n_surface_nodes = _repair_surface(
        closed_verts, closed_tris,
    )

    # Tetrahedralize — with pymeshfix retry if TetGen still fails.
    try:
        result = _tetrahedralize(
            closed_verts, closed_tris,
            min_dihedral=min_dihedral,
            minratio=minratio,
            maxvolume=maxvolume,
            order=order,
            quiet=quiet,
        )
    except RuntimeError as _first_err:
        # Last resort: pymeshfix repair + retry (catches geometric face conflicts
        # that the pre-check missed).
        try:
            closed_verts, closed_tris = _pymeshfix_repair(closed_verts, closed_tris)
            n_surface_nodes = len(closed_verts)
        except Exception:
            raise _first_err
        result = _tetrahedralize(
            closed_verts, closed_tris,
            min_dihedral=min_dihedral,
            minratio=minratio,
            maxvolume=maxvolume,
            order=order,
            quiet=quiet,
        )
    result.n_cap_triangles = n_cap
    result.n_surface_nodes = n_surface_nodes

    # Laplacian smoothing of interior (Steiner) nodes — keeps surface fixed
    if smooth_iterations > 0 and len(result.vertices) > n_surface_nodes:
        result.vertices = _laplacian_smooth(
            result.vertices,
            result.tetrahedra,
            n_surface_nodes,
            iterations=smooth_iterations,
            omega=smooth_omega,
        )

    return result


def close_surface_mesh(
    vertices: np.ndarray,
    triangles: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Close an open surface mesh by capping all boundary loops.

    Args:
        vertices:  (N, 3) vertex coordinates.
        triangles: (M, 3) triangle indices (0-based).

    Returns:
        (closed_vertices, closed_triangles, n_cap_triangles)
        If already closed, returns originals with n_cap=0.
    """
    boundary_edges = _find_boundary_edges(triangles)
    if len(boundary_edges) == 0:
        return vertices, triangles, 0

    loops = _chain_boundary_loops(boundary_edges)
    if not loops:
        return vertices, triangles, 0

    # Build cap triangles for each loop.
    # Strategy: try constrained Delaunay (higher quality); if it creates
    # non-manifold edges when combined with the existing surface, fall back to
    # the safe centroid fan (always manifold for any boundary shape).
    extra_verts: list[np.ndarray] = []
    all_cap_tris: list[list[int]] = []

    # Build a set of all current surface edge counts (for non-manifold check)
    surface_edge_count: dict[tuple[int, int], int] = {}
    for tri in triangles:
        for k in range(3):
            key = (min(int(tri[k]), int(tri[(k + 1) % 3])),
                   max(int(tri[k]), int(tri[(k + 1) % 3])))
            surface_edge_count[key] = surface_edge_count.get(key, 0) + 1

    for loop in loops:
        base_idx = len(vertices) + len(extra_verts)
        new_verts, cap_tris = _triangulate_cap(vertices, loop, base_idx)

        # Verify: cap must not create edges with count > 2 when combined
        # with the surface (non-manifold = TetGen self-intersection error).
        cap_ok = _cap_is_manifold(cap_tris, surface_edge_count)

        if not cap_ok:
            # Fall back to safe centroid fan
            new_verts, cap_tris = _triangulate_cap_centroid(vertices, loop, base_idx)

        extra_verts.extend(new_verts)
        all_cap_tris.extend(cap_tris)

        # Update edge counts with the accepted cap triangles
        for tri in cap_tris:
            for k in range(3):
                key = (min(int(tri[k]), int(tri[(k + 1) % 3])),
                       max(int(tri[k]), int(tri[(k + 1) % 3])))
                surface_edge_count[key] = surface_edge_count.get(key, 0) + 1

    if extra_verts:
        closed_verts = np.vstack(
            [vertices] + [v.reshape(1, 3) for v in extra_verts]
        )
    else:
        closed_verts = vertices

    cap_array = np.array(all_cap_tris, dtype=np.int32)
    closed_tris = np.vstack([triangles, cap_array])
    n_cap = len(all_cap_tris)

    # Verify watertight; flip cap winding if needed
    if not _is_watertight(closed_verts, closed_tris):
        cap_array_flipped = cap_array[:, [0, 2, 1]]
        closed_tris_flipped = np.vstack([triangles, cap_array_flipped])
        if _is_watertight(closed_verts, closed_tris_flipped):
            closed_tris = closed_tris_flipped

    return closed_verts, closed_tris, n_cap


# ── Boundary edge detection ───────────────────────────────────────────────────

def _find_boundary_edges(triangles: np.ndarray) -> list[tuple[int, int]]:
    """Find edges appearing in exactly one triangle (open boundary).

    Returns list of (v1, v2) directed edges from the owning triangle,
    preserving the winding orientation of the free surface.
    """
    edge_count: dict[tuple[int, int], int] = {}
    edge_directed: dict[tuple[int, int], tuple[int, int]] = {}

    for tri in triangles:
        for i in range(3):
            v1, v2 = int(tri[i]), int(tri[(i + 1) % 3])
            key = (min(v1, v2), max(v1, v2))
            edge_count[key] = edge_count.get(key, 0) + 1
            if key not in edge_directed:
                edge_directed[key] = (v1, v2)

    return [
        edge_directed[key]
        for key, count in edge_count.items()
        if count == 1
    ]


def _chain_boundary_loops(
    boundary_edges: list[tuple[int, int]],
) -> list[list[int]]:
    """Chain boundary edges into closed vertex loops.

    Args:
        boundary_edges: List of (v1, v2) directed edges.

    Returns:
        List of loops; each loop is an ordered list of vertex indices.
    """
    # Build undirected adjacency from directed edges
    adj: dict[int, list[int]] = {}
    for v1, v2 in boundary_edges:
        adj.setdefault(v1, []).append(v2)
        adj.setdefault(v2, []).append(v1)

    edge_used: set[tuple[int, int]] = set()
    loops = []

    for start_v1, start_v2 in boundary_edges:
        key = (min(start_v1, start_v2), max(start_v1, start_v2))
        if key in edge_used:
            continue

        loop = [start_v1]
        curr = start_v2
        edge_used.add(key)

        while curr != start_v1:
            loop.append(curr)
            advanced = False
            for nb in adj[curr]:
                nkey = (min(curr, nb), max(curr, nb))
                if nkey not in edge_used:
                    edge_used.add(nkey)
                    curr = nb
                    advanced = True
                    break
            if not advanced:
                break  # broken loop (non-manifold mesh)

        if len(loop) >= 3:
            loops.append(loop)

    return loops


# ── Cap triangulation ─────────────────────────────────────────────────────────

def _triangulate_cap(
    vertices: np.ndarray,
    loop: list[int],
    base_idx: int,
    n_interior_rings: int = 2,
) -> tuple[list[np.ndarray], list[list[int]]]:
    """Triangulate a boundary loop cap using constrained Delaunay triangulation.

    Uses the `triangle` library (PSLG mode) to guarantee that all boundary loop
    edges are preserved in the output triangulation.  This is essential for
    non-circular boundaries (rectangles, LGA pads) where unconstrained Delaunay
    may replace boundary edges with interior diagonals, leaving holes in the cap.

    For N=128 boundary points, typical output: ~300 well-shaped triangles.

    Falls back to scipy unconstrained Delaunay (with centroid filter) if the
    `triangle` library is unavailable, and to centroid fan if projection fails.

    Args:
        vertices:         Global vertex array.
        loop:             Ordered list of boundary loop vertex indices.
        base_idx:         Starting global index for new interior vertices.
        n_interior_rings: Concentric rings of interior sample points.

    Returns:
        (new_verts, cap_tris) — new_verts are 3D positions of interior points,
        cap_tris are triangles as lists of global vertex indices (unoriented;
        winding is fixed by the watertight check in close_surface_mesh).
    """
    loop_pts = vertices[loop]
    n = len(loop)
    center = loop_pts.mean(axis=0)

    # ── Build local 2D coordinate frame ──────────────────────────────────────
    u = loop_pts[1] - loop_pts[0]
    u_len = float(np.linalg.norm(u))
    if u_len < 1e-20:
        return _triangulate_cap_centroid(vertices, loop, base_idx)
    u = u / u_len

    # Normal: accumulate cross products of consecutive edge pairs
    normal = np.zeros(3)
    for i in range(n):
        e1 = loop_pts[(i + 1) % n] - loop_pts[i]
        e2 = loop_pts[(i + 2) % n] - loop_pts[(i + 1) % n]
        c = np.cross(e1, e2)
        c_len = float(np.linalg.norm(c))
        if c_len > 1e-20:
            normal += c / c_len
    n_len = float(np.linalg.norm(normal))
    if n_len < 1e-20:
        return _triangulate_cap_centroid(vertices, loop, base_idx)
    normal = normal / n_len

    v_axis = np.cross(normal, u)
    v_len = float(np.linalg.norm(v_axis))
    if v_len < 1e-20:
        return _triangulate_cap_centroid(vertices, loop, base_idx)
    v_axis = v_axis / v_len

    # ── Project boundary loop to 2D ──────────────────────────────────────────
    loop_2d = np.array([
        ((pt - center) @ u, (pt - center) @ v_axis) for pt in loop_pts
    ])
    R = float(np.sqrt((loop_2d**2).sum(axis=1)).max())
    if R < 1e-20:
        return _triangulate_cap_centroid(vertices, loop, base_idx)

    # ── Interior sample points (inside polygon only) ──────────────────────────
    candidate_interior: list[np.ndarray] = [np.zeros(2)]   # center always inside
    for ring_i in range(1, n_interior_rings + 1):
        r = R * ring_i / (n_interior_rings + 1)
        n_pts = max(6, n >> (n_interior_rings - ring_i + 1))
        for j in range(n_pts):
            theta = 2.0 * np.pi * j / n_pts
            candidate_interior.append(np.array([r * np.cos(theta), r * np.sin(theta)]))

    candidate_arr = np.array(candidate_interior)
    inside_mask = _points_in_polygon_2d(candidate_arr, loop_2d)
    interior_2d_arr = candidate_arr[inside_mask]
    if len(interior_2d_arr) == 0:
        interior_2d_arr = np.zeros((1, 2))

    # ── Constrained Delaunay via `triangle` library (preferred) ──────────────
    # The boundary loop edges are specified as segments, guaranteeing they
    # appear in the output even when unconstrained Delaunay would skip them.
    try:
        import triangle as _trilib

        # Vertex layout: [interior_points... | boundary_loop_points...]
        n_interior = len(interior_2d_arr)
        all_2d = np.vstack([interior_2d_arr, loop_2d])

        # Boundary loop edges (constrained segments)
        segments = np.array([
            [n_interior + i, n_interior + (i + 1) % n]
            for i in range(n)
        ], dtype=np.int32)

        result = _trilib.triangulate(
            {"vertices": all_2d, "segments": segments},
            "p",    # p = PSLG (preserve all input segments, no Steiner points)
        )

        out_verts_2d = result["vertices"]
        out_tris = result["triangles"]

        # With 'p' only (no quality flags), the triangle library does NOT add
        # Steiner points, so out_verts_2d == all_2d (same n vertices, same order).
        # We verify this assumption: if extra vertices appear, skip them.
        n_out = len(out_verts_2d)
        n_expected = n_interior + n

        # Map output vertex indices to global indices
        def _local_to_global(idx: int) -> int:
            if idx < n_interior:
                return base_idx + idx          # interior ring vertex
            elif idx < n_expected:
                return loop[idx - n_interior]  # boundary loop vertex
            else:
                # Unexpected extra vertex (Steiner) — map as new interior
                return base_idx + n_interior + (idx - n_expected)

        # Collect extra vertices (should be empty for 'p' mode)
        new_verts_3d: list[np.ndarray] = []
        for pt in out_verts_2d[:n_interior]:
            new_verts_3d.append(center + float(pt[0]) * u + float(pt[1]) * v_axis)
        for pt in out_verts_2d[n_expected:]:  # any unexpected extras
            new_verts_3d.append(center + float(pt[0]) * u + float(pt[1]) * v_axis)

        cap_tris = [
            [_local_to_global(a), _local_to_global(b), _local_to_global(c)]
            for a, b, c in out_tris
        ]

        if cap_tris:
            return new_verts_3d, cap_tris

    except ImportError:
        pass   # fall through to scipy Delaunay

    # ── Fallback: scipy unconstrained Delaunay + centroid filter ─────────────
    try:
        from scipy.spatial import Delaunay as _Delaunay
    except ImportError:
        return _triangulate_cap_centroid(vertices, loop, base_idx)

    n_interior = len(interior_2d_arr)
    all_2d = np.vstack([interior_2d_arr, loop_2d])
    tri = _Delaunay(all_2d)

    centroids = all_2d[tri.simplices].mean(axis=1)
    keep = _points_in_polygon_2d(centroids, loop_2d)

    new_verts_3d = [
        center + float(pt[0]) * u + float(pt[1]) * v_axis
        for pt in interior_2d_arr
    ]
    cap_tris = []
    for simplex in tri.simplices[keep]:
        tri_global = []
        for idx in simplex:
            if idx < n_interior:
                tri_global.append(base_idx + idx)
            else:
                tri_global.append(loop[idx - n_interior])
        cap_tris.append(tri_global)

    if not cap_tris:
        return _triangulate_cap_centroid(vertices, loop, base_idx)

    return new_verts_3d, cap_tris


def _cap_is_manifold(
    cap_tris: list[list[int]],
    surface_edge_count: dict[tuple[int, int], int],
) -> bool:
    """Return True if the cap triangles don't create non-manifold edges.

    A cap triangle is non-manifold if it adds an edge that would result in
    count > 2 in the combined surface+cap mesh.  This happens when two
    non-adjacent boundary loop vertices are connected by both a surface interior
    edge (count=2 in surface) AND an interior cap edge (count=2 in cap) →
    total count=4, causing TetGen to report self-intersections.
    """
    cap_edge_count: dict[tuple[int, int], int] = {}
    for tri in cap_tris:
        for k in range(3):
            key = (min(int(tri[k]), int(tri[(k + 1) % 3])),
                   max(int(tri[k]), int(tri[(k + 1) % 3])))
            cap_edge_count[key] = cap_edge_count.get(key, 0) + 1

    for key, cap_cnt in cap_edge_count.items():
        surf_cnt = surface_edge_count.get(key, 0)
        if surf_cnt + cap_cnt > 2:
            return False
    return True


def _points_in_polygon_2d(points: np.ndarray, polygon: np.ndarray) -> np.ndarray:
    """Test which 2D points lie strictly inside a closed polygon.

    Uses the ray-casting algorithm (Jordan curve theorem), vectorized over
    all input points simultaneously.

    Args:
        points:  (N, 2) query points.
        polygon: (M, 2) ordered polygon vertices (closed implicitly).

    Returns:
        (N,) boolean array — True if the point is inside the polygon.
    """
    n_poly = len(polygon)
    inside = np.zeros(len(points), dtype=bool)
    j = n_poly - 1
    for i in range(n_poly):
        xi, yi = polygon[i, 0], polygon[i, 1]
        xj, yj = polygon[j, 0], polygon[j, 1]
        # Ray crosses edge i→j when the y-coordinates straddle the ray
        cross_y = (yi > points[:, 1]) != (yj > points[:, 1])
        # x-coordinate of intersection along the ray (y = points[:,1])
        x_intersect = (xj - xi) * (points[:, 1] - yi) / (yj - yi + 1e-30) + xi
        cross_x = points[:, 0] < x_intersect
        inside ^= cross_y & cross_x
        j = i
    return inside


def _triangulate_cap_centroid(
    vertices: np.ndarray,
    loop: list[int],
    base_idx: int,
) -> tuple[list[np.ndarray], list[list[int]]]:
    """Centroid fan cap (fallback for degenerate boundary loops)."""
    centroid = vertices[loop].mean(axis=0)
    n = len(loop)
    cap_tris = [
        [base_idx, loop[(i + 1) % n], loop[i]]
        for i in range(n)
    ]
    return [centroid], cap_tris


# ── TetGen wrapper ────────────────────────────────────────────────────────────

def _tetrahedralize(
    vertices: np.ndarray,
    triangles: np.ndarray,
    min_dihedral: float = 10.0,
    minratio: float = 1.5,
    maxvolume: float = -1.0,
    order: int = 1,
    quiet: bool = True,
) -> VolumeMeshResult:
    """Call TetGen to generate tetrahedral mesh from a watertight surface.

    Raises:
        ImportError: if tetgen package is not installed.
        RuntimeError: if TetGen fails (e.g. self-intersections).
    """
    try:
        import tetgen
    except ImportError:
        raise ImportError(
            "tetgen is required for volume meshing. "
            "Install with: pip install tetgen"
        )

    tet = tetgen.TetGen(
        vertices.astype(np.float64),
        triangles.astype(np.int32),
    )

    kwargs = dict(
        order=order,
        mindihedral=min_dihedral,
        minratio=minratio,
        quiet=quiet,
    )
    if maxvolume > 0:
        kwargs["maxvolume"] = maxvolume

    tet.tetrahedralize(**kwargs)

    return VolumeMeshResult(
        vertices=tet.node,
        tetrahedra=tet.elem,
        surface_triangles=triangles,
        n_cap_triangles=0,  # filled by caller
    )


# ── Surface repair helpers ────────────────────────────────────────────────────

def _has_nonmanifold_edges(triangles: np.ndarray) -> bool:
    """Return True if any edge is shared by more than 2 faces."""
    edge_count: dict[tuple[int, int], int] = {}
    for tri in triangles:
        for k in range(3):
            a, b = int(tri[k]), int(tri[(k + 1) % 3])
            key = (min(a, b), max(a, b))
            edge_count[key] = edge_count.get(key, 0) + 1
            if edge_count[key] > 2:
                return True
    return False


def _pymeshfix_repair(
    vertices: np.ndarray, triangles: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Repair a surface mesh using pymeshfix (MeshFix algorithm).

    Fixes non-manifold edges, self-intersections, and inconsistent normals.
    Requires pymeshfix and pyvista.
    """
    import pymeshfix
    mfix = pymeshfix.MeshFix(
        vertices.astype(np.float32),
        triangles.astype(np.int32),
    )
    mfix.repair()
    return mfix.points.astype(np.float64), mfix.faces.astype(np.int32)


def _repair_surface(
    vertices: np.ndarray, triangles: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Best-effort surface repair before TetGen.

    Strategy:
      1. If mesh has non-manifold edges (count>2) → pymeshfix (avoids TetGen segfault).
      2. Else if normals are inconsistent → trimesh.fix_normals.
      3. Otherwise → pass through unchanged.

    Returns (vertices, triangles, n_surface_nodes).
    """
    # Non-manifold edges cause TetGen to segfault — must fix first.
    if _has_nonmanifold_edges(triangles):
        try:
            vertices, triangles = _pymeshfix_repair(vertices, triangles)
            return vertices, triangles, len(vertices)
        except Exception:
            pass  # pymeshfix unavailable; fall through

    # Inconsistent normals cause TetGen "self-intersections" error.
    try:
        import trimesh
        tm = trimesh.Trimesh(vertices=vertices, faces=triangles, process=False)
        if not tm.is_volume:
            trimesh.repair.fix_normals(tm, multibody=False)
            vertices = np.array(tm.vertices, dtype=np.float64)
            triangles = np.array(tm.faces, dtype=np.int32)
    except Exception:
        pass  # best effort

    return vertices, triangles, len(vertices)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _merge_vertices(
    vertices: np.ndarray,
    triangles: np.ndarray,
    tol: float = 1e-10,
) -> tuple[np.ndarray, np.ndarray]:
    """Merge near-duplicate vertices within tolerance.

    Uses scipy cKDTree for efficiency.
    """
    try:
        from scipy.spatial import cKDTree
    except ImportError:
        return vertices, triangles  # skip if scipy not available

    tree = cKDTree(vertices)
    pairs = tree.query_pairs(tol)
    if not pairs:
        return vertices, triangles

    # Build union-find to identify canonical vertex for each group
    parent = list(range(len(vertices)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in pairs:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    canonical = [find(i) for i in range(len(vertices))]

    # Remap to dense indices
    unique_ids = sorted(set(canonical))
    remap = {old: new for new, old in enumerate(unique_ids)}
    new_verts = vertices[unique_ids]
    new_tris = np.array(
        [[remap[canonical[v]] for v in tri] for tri in triangles],
        dtype=np.int32,
    )

    # Remove degenerate triangles (vertices collapsed to same index)
    valid = np.array([len(set(tri)) == 3 for tri in new_tris])
    return new_verts, new_tris[valid]


def _laplacian_smooth(
    vertices: np.ndarray,
    tetrahedra: np.ndarray,
    n_surface_nodes: int,
    iterations: int = 10,
    omega: float = 0.2,
) -> np.ndarray:
    """Safe Laplacian smoothing of interior (Steiner) nodes.

    Surface nodes (indices < n_surface_nodes) are held fixed.
    Each proposed move is rejected if it would invert any adjacent tetrahedron
    (signed-volume check), making the algorithm inversion-safe.

    Args:
        vertices:        (N, 3) tet mesh vertex coordinates.
        tetrahedra:      (K, 4) tetrahedron vertex indices (0-based).
        n_surface_nodes: Number of surface nodes to keep fixed.
        iterations:      Number of smoothing passes.
        omega:           Relaxation factor (0 < omega <= 1).
                         Smaller values (0.1–0.3) are safer but slower.

    Returns:
        Smoothed vertex array (N, 3), same shape as input.
    """
    result = vertices.copy()
    n_all = len(result)

    if n_surface_nodes >= n_all:
        return result  # no interior nodes to smooth

    # ── Build per-vertex adjacency and tet membership ──────────────────────
    adj: list[list[int]] = [[] for _ in range(n_all)]
    v_tets: list[list[int]] = [[] for _ in range(n_all)]
    for k, tet in enumerate(tetrahedra):
        for i in range(4):
            vi = int(tet[i])
            v_tets[vi].append(k)
            for j in range(i + 1, 4):
                vj = int(tet[j])
                adj[vi].append(vj)
                adj[vj].append(vi)

    # Deduplicate and convert to arrays
    adj_arr: list[Optional[np.ndarray]] = [None] * n_all
    vtets_arr: list[Optional[np.ndarray]] = [None] * n_all
    for v in range(n_surface_nodes, n_all):
        if adj[v]:
            adj_arr[v] = np.unique(adj[v])
        if v_tets[v]:
            vtets_arr[v] = np.array(v_tets[v], dtype=np.int32)

    def _signed_vol(v: np.ndarray, tet_idx: int) -> float:
        """Signed volume of one tetrahedron (positive = correct orientation)."""
        t = tetrahedra[tet_idx]
        a, b, c, d = result[t[0]], result[t[1]], result[t[2]], result[t[3]]
        return float(np.dot(b - a, np.cross(c - a, d - a))) / 6.0

    for _ in range(iterations):
        for v in range(n_surface_nodes, n_all):
            nbrs = adj_arr[v]
            connected = vtets_arr[v]
            if nbrs is None or connected is None:
                continue

            centroid = result[nbrs].mean(axis=0)
            proposed = (1.0 - omega) * result[v] + omega * centroid

            # ── Inversion guard: only accept the move if no adjacent tet flips
            old_pos = result[v].copy()
            result[v] = proposed

            accept = all(_signed_vol(result, k) > 0.0 for k in connected)
            if not accept:
                result[v] = old_pos   # revert

    return result


def _is_watertight(vertices: np.ndarray, triangles: np.ndarray) -> bool:
    """Check if mesh is watertight (every edge shared by exactly 2 faces)."""
    edge_count: dict[tuple[int, int], int] = {}
    for tri in triangles:
        for i in range(3):
            key = (min(int(tri[i]), int(tri[(i + 1) % 3])),
                   max(int(tri[i]), int(tri[(i + 1) % 3])))
            edge_count[key] = edge_count.get(key, 0) + 1
    return all(c == 2 for c in edge_count.values())
