"""Extract solder-pad contact boundaries from STL meshes.

Detects cap faces lying on pad surfaces, removes them to create
an open lateral surface, and extracts ordered boundary edge loops
classified by pad.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import trimesh

from .surface_fitter import SurfaceFitResult


@dataclass
class BoundaryLoop:
    """An ordered boundary loop on a pad surface."""

    vertex_ids: list  # ordered vertex indices into lateral_mesh.vertices
    edge_pairs: list  # ordered (v_start, v_end) pairs
    pad_id: str  # "bottom" or "top"
    constraint_id: int  # SE constraint ID to assign


@dataclass
class ExtractionResult:
    """Result of boundary extraction."""

    lateral_mesh: trimesh.Trimesh  # open mesh (caps removed)
    boundary_loops: list  # list of BoundaryLoop
    cap_faces_bottom: np.ndarray  # face indices on bottom pad
    cap_faces_top: np.ndarray  # face indices on top pad
    n_cap_faces_removed: int
    warnings: list = field(default_factory=list)


class BoundaryExtractor:
    """Extract solder-pad contact boundaries.

    Supports N-way surface classification via the ``surfaces`` parameter.
    Legacy 2-surface (bottom/top) construction is preserved for backward
    compatibility.
    """

    def __init__(
        self,
        fit_bottom: SurfaceFitResult = None,
        fit_top: SurfaceFitResult = None,
        constraint_bottom_id: int = 1,
        constraint_top_id: int = 2,
        on_surface_tol: Optional[float] = None,
        surfaces: Optional[list] = None,
    ):
        """
        Args:
            fit_bottom: Surface fit for bottom pad (legacy 2-surface mode).
            fit_top: Surface fit for top pad (legacy 2-surface mode).
            constraint_bottom_id: SE constraint ID for bottom.
            constraint_top_id: SE constraint ID for top.
            on_surface_tol: Tolerance for detecting vertices on a surface.
                If None, uses adaptive tolerance from fit residuals.
            surfaces: List of (pad_id, constraint_id, SurfaceFitResult) tuples
                for N-way classification.  Overrides fit_bottom/fit_top when set.
        """
        # N-way surface list: [(pad_id, constraint_id, fit), ...]
        if surfaces is not None:
            self._surfaces = list(surfaces)
        else:
            self._surfaces = []
            if fit_bottom is not None:
                self._surfaces.append(("bottom", constraint_bottom_id, fit_bottom))
            if fit_top is not None:
                self._surfaces.append(("top", constraint_top_id, fit_top))

        # Legacy accessors (kept for backward compat)
        self.fit_bottom = fit_bottom
        self.fit_top = fit_top
        self.constraint_bottom_id = constraint_bottom_id
        self.constraint_top_id = constraint_top_id

        if on_surface_tol is None:
            max_residual = 0
            for _, _, fit in self._surfaces:
                max_residual = max(max_residual, fit.residual_max or 0)
            self.on_surface_tol = max(max_residual * 3, 1e-4)
        else:
            self.on_surface_tol = on_surface_tol

    def extract(self, mesh: trimesh.Trimesh) -> ExtractionResult:
        """Main extraction: detect caps, remove, find boundaries, classify."""
        warnings = []

        # 1. Classify faces as cap (bottom/top) or lateral
        bottom_mask, top_mask = self._find_cap_faces(mesh)
        n_bottom = int(np.sum(bottom_mask))
        n_top = int(np.sum(top_mask))

        cap_faces_bottom = np.where(bottom_mask)[0]
        cap_faces_top = np.where(top_mask)[0]
        n_removed = n_bottom + n_top

        if n_removed == 0:
            # Mesh is already open (no caps)
            warnings.append("No cap faces detected; mesh may already be open")
            lateral_mesh = mesh
        else:
            # Remove cap faces
            keep_mask = ~(bottom_mask | top_mask)
            lateral_mesh = self._remove_faces(mesh, keep_mask)
            warnings.append(
                f"Removed {n_bottom} bottom + {n_top} top cap faces"
            )

        # 2. Extract boundary edge loops from the open mesh
        raw_loops = self._extract_boundary_loops(lateral_mesh)

        if len(raw_loops) == 0:
            warnings.append("No boundary loops found (mesh may be closed)")

        # 3. Classify each loop against all registered surfaces (N-way)
        boundary_loops = self._classify_loops(raw_loops, lateral_mesh.vertices, warnings)

        return ExtractionResult(
            lateral_mesh=lateral_mesh,
            boundary_loops=boundary_loops,
            cap_faces_bottom=cap_faces_bottom,
            cap_faces_top=cap_faces_top,
            n_cap_faces_removed=n_removed,
            warnings=warnings,
        )

    def _find_cap_faces(
        self, mesh: trimesh.Trimesh
    ) -> tuple:
        """Identify faces lying on each pad surface.

        A face is on a pad if ALL 3 vertices satisfy |F(x,y,z)| < tol.
        """
        verts = mesh.vertices
        tol = self.on_surface_tol

        # Evaluate all vertices against both surfaces
        dist_bottom = np.abs(self.fit_bottom.eval_global(verts))
        dist_top = np.abs(self.fit_top.eval_global(verts))

        on_bottom = dist_bottom < tol  # (N,) bool
        on_top = dist_top < tol

        # A face is a cap if all 3 vertices are on the surface
        f = mesh.faces
        bottom_mask = on_bottom[f[:, 0]] & on_bottom[f[:, 1]] & on_bottom[f[:, 2]]
        top_mask = on_top[f[:, 0]] & on_top[f[:, 1]] & on_top[f[:, 2]]

        # If a face is on both surfaces (very thin solder), assign to nearest
        both = bottom_mask & top_mask
        if np.any(both):
            centroids = mesh.triangles_center[both]
            d_b = np.abs(self.fit_bottom.eval_global(centroids))
            d_t = np.abs(self.fit_top.eval_global(centroids))
            closer_bottom = d_b <= d_t
            both_idx = np.where(both)[0]
            top_mask[both_idx[closer_bottom]] = False
            bottom_mask[both_idx[~closer_bottom]] = False

        return bottom_mask, top_mask

    def _remove_faces(
        self, mesh: trimesh.Trimesh, keep_mask: np.ndarray
    ) -> trimesh.Trimesh:
        """Remove faces and clean up unused vertices."""
        kept_faces = mesh.faces[keep_mask]
        # Remap vertex indices
        used_verts = np.unique(kept_faces)
        new_idx = np.full(len(mesh.vertices), -1, dtype=int)
        new_idx[used_verts] = np.arange(len(used_verts))
        new_faces = new_idx[kept_faces]
        new_verts = mesh.vertices[used_verts]
        return trimesh.Trimesh(vertices=new_verts, faces=new_faces)

    def _extract_boundary_loops(
        self, mesh: trimesh.Trimesh
    ) -> list:
        """Find boundary edges and chain them into ordered loops.

        A boundary edge is one that belongs to exactly one face.
        Returns list of loops, each loop = [(v1, v2), (v2, v3), ...].
        """
        # Count how many faces each edge belongs to
        edge_face_count = defaultdict(int)
        edge_to_directed = defaultdict(list)

        for fi, face in enumerate(mesh.faces):
            for i in range(3):
                v1, v2 = int(face[i]), int(face[(i + 1) % 3])
                key = (min(v1, v2), max(v1, v2))
                edge_face_count[key] += 1
                edge_to_directed[key].append((v1, v2))

        # Boundary edges: count == 1
        boundary_edges = []
        for key, count in edge_face_count.items():
            if count == 1:
                # Use the directed version from the face
                directed = edge_to_directed[key][0]
                boundary_edges.append(directed)

        if not boundary_edges:
            return []

        # Chain edges into ordered loops
        return self._chain_edges_into_loops(boundary_edges)

    def _chain_edges_into_loops(self, edges: list) -> list:
        """Chain directed edges into ordered closed loops."""
        # Build adjacency: vertex → list of (next_vertex, edge_index)
        adjacency = defaultdict(list)
        for idx, (v1, v2) in enumerate(edges):
            adjacency[v1].append((v2, idx))

        used = set()
        loops = []

        for start_v1, start_v2 in edges:
            edge_key = (start_v1, start_v2)
            if edge_key in used:
                continue

            loop = []
            current = start_v1
            while True:
                # Find unused edge from current vertex
                found = False
                for next_v, eidx in adjacency[current]:
                    ekey = (current, next_v)
                    if ekey not in used:
                        used.add(ekey)
                        loop.append(ekey)
                        current = next_v
                        found = True
                        break
                if not found or current == start_v1:
                    break

            if len(loop) >= 3:
                loops.append(loop)

        return loops

    def _edges_to_ordered_verts(self, edge_pairs: list) -> list:
        """Extract ordered vertex sequence from edge pairs."""
        return [e[0] for e in edge_pairs]

    def extract_preclassified(
        self,
        lateral_mesh: trimesh.Trimesh,
        contact_bottom_mask: np.ndarray,
        contact_top_mask: np.ndarray,
    ) -> ExtractionResult:
        """Extract boundaries from a pre-classified mesh (B-rep labels).

        Skips cap face detection entirely. Used by STEP pipeline (Level 2)
        where B-rep face classification already identifies contact vs lateral faces.

        Args:
            lateral_mesh: Open mesh with only lateral (free) faces.
            contact_bottom_mask: Not used directly but stored for reference.
            contact_top_mask: Not used directly but stored for reference.

        Returns:
            ExtractionResult with boundary loops from the open lateral mesh.
        """
        warnings = []

        # Extract boundary loops from the already-open mesh
        raw_loops = self._extract_boundary_loops(lateral_mesh)

        if len(raw_loops) == 0:
            warnings.append("No boundary loops found in pre-classified mesh")

        # Classify each loop against all registered surfaces (N-way)
        boundary_loops = self._classify_loops(raw_loops, lateral_mesh.vertices, warnings)

        return ExtractionResult(
            lateral_mesh=lateral_mesh,
            boundary_loops=boundary_loops,
            cap_faces_bottom=np.where(contact_bottom_mask)[0] if contact_bottom_mask is not None else np.array([]),
            cap_faces_top=np.where(contact_top_mask)[0] if contact_top_mask is not None else np.array([]),
            n_cap_faces_removed=0,
            warnings=warnings,
        )

    def _classify_loops(
        self, raw_loops: list, vertices: np.ndarray, warnings: list,
    ) -> list:
        """Classify all boundary loops against registered surfaces (N-way).

        For each loop, evaluates mean distance to every surface; the surface
        with the smallest mean distance wins.
        """
        boundary_loops = []
        for loop_edges in raw_loops:
            loop_verts = self._edges_to_ordered_verts(loop_edges)
            pad_id, cid = self._classify_single_loop(loop_verts, vertices)
            if pad_id == "unknown":
                warnings.append(
                    f"Boundary loop with {len(loop_verts)} verts "
                    f"could not be classified"
                )
            boundary_loops.append(BoundaryLoop(
                vertex_ids=loop_verts,
                edge_pairs=loop_edges,
                pad_id=pad_id,
                constraint_id=cid,
            ))
        return boundary_loops

    def _classify_single_loop(
        self, vertex_ids: list, vertices: np.ndarray,
    ) -> tuple:
        """Classify one boundary loop.

        Returns (pad_id, constraint_id).
        """
        if not self._surfaces:
            return ("unknown", 0)

        pts = vertices[vertex_ids]
        best_pad = "unknown"
        best_cid = 0
        best_dist = float("inf")

        for pad_id, cid, fit in self._surfaces:
            mean_dist = float(np.mean(np.abs(fit.eval_global(pts))))
            if mean_dist < best_dist:
                best_dist = mean_dist
                best_pad = pad_id
                best_cid = cid

        return (best_pad, best_cid)

    def classify_boundary_vertices(
        self,
        vertices: np.ndarray,
        boundary_vertex_ids,
        tol: float = None,
    ) -> dict:
        """Classify each boundary vertex to all matching constraint surfaces.

        Unlike loop-level classification (which assigns one constraint per
        entire loop), this method checks every vertex individually against
        every registered surface. Vertices near multiple surfaces (corner
        vertices at the intersection of pad and wall) receive multiple
        constraint IDs.

        Args:
            vertices: Mesh vertex array (N×3).
            boundary_vertex_ids: Iterable of vertex indices to classify.
            tol: Distance tolerance for surface membership. Defaults to
                self.on_surface_tol.

        Returns:
            dict mapping vertex_index → list[constraint_id].
            Corner vertices: e.g. {42: [1, 2]}.
            Regular vertices: e.g. {10: [1]}.
            Unclassified: {7: []}.
        """
        tol = tol if tol is not None else self.on_surface_tol
        result = {}
        for v_idx in boundary_vertex_ids:
            pos = vertices[v_idx].reshape(1, -1)
            matched = []
            for _pad_id, cid, fit in self._surfaces:
                dist = float(np.abs(fit.eval_global(pos))[0])
                if dist < tol:
                    matched.append(cid)
            result[int(v_idx)] = matched
        return result

    def get_corner_vertex_indices(
        self,
        vertex_multi_constraints: dict,
    ) -> list:
        """Return vertex indices that are on 2+ constraint surfaces (corners).

        Args:
            vertex_multi_constraints: Output of classify_boundary_vertices().

        Returns:
            List of vertex indices with len(constraint_ids) >= 2.
        """
        return [
            v_idx for v_idx, cids in vertex_multi_constraints.items()
            if len(cids) >= 2
        ]
