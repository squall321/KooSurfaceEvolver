"""Convert trimesh triangulations to Surface Evolver signed-edge topology.

Transforms a triangle mesh (vertices + faces) into the Vertex/Edge/Face/Body
objects that FEWriter can render into a .fe file.
"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import trimesh

from .boundary_extractor import BoundaryLoop
from .geometry_builder import InitialGeometry, Vertex, Edge, Face, Body


@dataclass
class SETopologyResult:
    """Result of mesh-to-SE conversion."""

    geometry: InitialGeometry
    vertex_map: dict  # trimesh vertex idx → SE vertex ID (1-based)
    edge_map: dict  # canonical (min_v, max_v) → SE edge ID (1-based)
    boundary_vertex_ids: dict  # "bottom"/"top" → set of SE vertex IDs
    boundary_edge_ids: dict  # "bottom"/"top" → set of SE edge IDs
    computed_volume: float


class MeshToSEConverter:
    """Convert trimesh to SE InitialGeometry."""

    def __init__(
        self,
        tension: float = 480.0,
        density: float = 9.0,
        constraint_bottom_id: int = 1,
        constraint_top_id: int = 2,
    ):
        self.tension = tension
        self.density = density
        self.constraint_bottom_id = constraint_bottom_id
        self.constraint_top_id = constraint_top_id

    def convert(
        self,
        lateral_mesh: trimesh.Trimesh,
        boundary_loops: list,
        target_volume: Optional[float] = None,
        vertex_multi_constraints: Optional[dict] = None,
        wall_strategy: str = "none",
    ) -> SETopologyResult:
        """Convert open lateral mesh + boundary info to SE topology.

        Args:
            lateral_mesh: Open triangulated surface (caps removed).
            boundary_loops: List of BoundaryLoop from BoundaryExtractor.
            target_volume: Target solder volume. If None, estimates from mesh.
            vertex_multi_constraints: Optional dict from
                BoundaryExtractor.classify_boundary_vertices().
                When provided, corner vertices (on 2+ surfaces) get all their
                constraint IDs assigned.  Wall-only vertices are handled
                according to wall_strategy.
            wall_strategy: How to handle wall contact vertices.
                "none"   – no wall (default, standard BGA/CSP behaviour).
                "pinned" – wall vertices get fixed=True, no wall constraint.
                "full"   – wall vertices get their wall constraint_id (Strategy B).
        """
        # Build boundary vertex/edge sets indexed by pad (N-way)
        boundary_verts = {}
        boundary_edges_set = {}
        pad_constraint = {}

        for loop in boundary_loops:
            pad = loop.pad_id
            if pad not in boundary_verts:
                boundary_verts[pad] = set()
                boundary_edges_set[pad] = set()
            for vid in loop.vertex_ids:
                boundary_verts[pad].add(vid)
            for v1, v2 in loop.edge_pairs:
                canonical = (min(v1, v2), max(v1, v2))
                boundary_edges_set[pad].add(canonical)
            pad_constraint[pad] = loop.constraint_id

        # Step 1: Build SE vertices
        vertices, vertex_map = self._build_vertices(
            lateral_mesh, boundary_verts, pad_constraint,
            vertex_multi_constraints=vertex_multi_constraints,
            wall_strategy=wall_strategy,
        )

        # Step 2: Build SE edges
        edges, edge_map = self._build_edges(
            lateral_mesh, vertex_map, boundary_edges_set, pad_constraint,
        )

        # Step 3: Build SE faces with signed edge loops
        faces = self._build_faces(lateral_mesh, vertex_map, edge_map)

        # Step 4: Ensure consistent orientation
        faces = self._ensure_consistent_orientation(lateral_mesh, faces)

        # Step 5: Compute volume
        if target_volume is None:
            target_volume = self._estimate_volume(lateral_mesh)

        # Step 6: Build body
        body = Body(
            id=1,
            faces=list(range(1, len(faces) + 1)),
            volume=f"{target_volume}",
            density=self.density,
        )

        n_segments = sum(len(bv) for bv in boundary_verts.values())

        geometry = InitialGeometry(
            vertices=vertices,
            edges=edges,
            faces=faces,
            bodies=[body],
            n_segments=n_segments,
        )

        # Map boundary info to SE IDs (N-way)
        se_boundary_verts = {}
        se_boundary_edges = {}
        for pad in boundary_verts:
            se_boundary_verts[pad] = {
                vertex_map[v] for v in boundary_verts[pad]
                if v in vertex_map
            }
            se_boundary_edges[pad] = set()
            for canonical in boundary_edges_set[pad]:
                se_canonical = (
                    min(vertex_map.get(canonical[0], 0),
                        vertex_map.get(canonical[1], 0)),
                    max(vertex_map.get(canonical[0], 0),
                        vertex_map.get(canonical[1], 0)),
                )
                if se_canonical in edge_map:
                    se_boundary_edges[pad].add(edge_map[se_canonical])

        return SETopologyResult(
            geometry=geometry,
            vertex_map=vertex_map,
            edge_map=edge_map,
            boundary_vertex_ids=se_boundary_verts,
            boundary_edge_ids=se_boundary_edges,
            computed_volume=target_volume,
        )

    def convert_with_void(
        self,
        lateral_mesh: trimesh.Trimesh,
        boundary_loops: list,
        void_mesh: trimesh.Trimesh,
        target_volume: Optional[float] = None,
        void_volume: Optional[float] = None,
    ) -> SETopologyResult:
        """Convert outer mesh + void mesh to SE topology with 2 bodies.

        Body 1 (solder): outer faces + negative void faces.
        Body 2 (void): void faces, density=0.

        Args:
            lateral_mesh: Open outer solder surface.
            boundary_loops: Boundary loops from BoundaryExtractor.
            void_mesh: Closed mesh for the internal void (e.g. icosphere).
            target_volume: Target solder volume (excluding void).
            void_volume: Target void volume. If None, computed from void_mesh.
        """
        # Build outer solder topology first
        result = self.convert(lateral_mesh, boundary_loops, target_volume)
        geom = result.geometry

        v_offset = len(geom.vertices)
        e_offset = len(geom.edges)
        f_offset = len(geom.faces)

        # Add void vertices
        void_vertex_map = {}
        for idx in range(len(void_mesh.vertices)):
            se_id = v_offset + idx + 1
            void_vertex_map[idx] = se_id
            x, y, z = void_mesh.vertices[idx]
            geom.vertices.append(Vertex(
                id=se_id, x=float(x), y=float(y), z=float(z),
            ))

        # Add void edges
        void_edge_map = {}
        edge_id = e_offset + 1
        for face in void_mesh.faces:
            for i in range(3):
                v1_m = int(face[i])
                v2_m = int(face[(i + 1) % 3])
                se_v1 = void_vertex_map[v1_m]
                se_v2 = void_vertex_map[v2_m]
                canonical = (min(se_v1, se_v2), max(se_v1, se_v2))
                if canonical in void_edge_map:
                    continue
                geom.edges.append(Edge(
                    id=edge_id, v1=canonical[0], v2=canonical[1],
                ))
                void_edge_map[canonical] = edge_id
                edge_id += 1

        # Add void faces
        void_face_ids = []
        face_id = f_offset + 1
        for fi, face in enumerate(void_mesh.faces):
            signed_edges = []
            for i in range(3):
                v1_m = int(face[i])
                v2_m = int(face[(i + 1) % 3])
                se_v1 = void_vertex_map[v1_m]
                se_v2 = void_vertex_map[v2_m]
                canonical = (min(se_v1, se_v2), max(se_v1, se_v2))
                eid = void_edge_map[canonical]
                if se_v1 < se_v2:
                    signed_edges.append(eid)
                else:
                    signed_edges.append(-eid)

            geom.faces.append(Face(
                id=face_id,
                edges=signed_edges,
                tension=self.tension,
            ))
            void_face_ids.append(face_id)
            face_id += 1

        # Ensure void faces point outward from void body
        void_centroid = void_mesh.vertices.mean(axis=0)
        face_centers = void_mesh.triangles_center
        face_normals = void_mesh.face_normals
        to_face = face_centers - void_centroid
        dots = np.sum(to_face * face_normals, axis=1)

        if np.sum(dots < 0) > len(void_face_ids) / 2:
            for i in range(len(void_face_ids)):
                f = geom.faces[f_offset + i]
                f.edges = [-e for e in reversed(f.edges)]

        # Compute void volume
        if void_volume is None:
            if void_mesh.is_watertight:
                void_volume = abs(void_mesh.volume)
            else:
                r_mean = float(np.linalg.norm(
                    void_mesh.vertices - void_centroid, axis=1,
                ).mean())
                void_volume = 4 / 3 * np.pi * r_mean ** 3

        # Update body 1: add negative void faces
        solder_body = geom.bodies[0]
        solder_body.faces.extend([-fid for fid in void_face_ids])
        solder_vol = float(solder_body.volume) - void_volume
        solder_body.volume = str(solder_vol)

        # Add body 2: void (no density = no gravity)
        void_body = Body(
            id=2,
            faces=list(void_face_ids),
            volume=str(void_volume),
            density=None,
        )
        geom.bodies.append(void_body)

        return SETopologyResult(
            geometry=geom,
            vertex_map=result.vertex_map,
            edge_map=result.edge_map,
            boundary_vertex_ids=result.boundary_vertex_ids,
            boundary_edge_ids=result.boundary_edge_ids,
            computed_volume=result.computed_volume,
        )

    def _build_vertices(
        self,
        mesh: trimesh.Trimesh,
        boundary_verts: dict,
        pad_constraint: dict,
        vertex_multi_constraints: Optional[dict] = None,
        wall_strategy: str = "none",
    ) -> tuple:
        """Create SE Vertex objects from mesh vertices.

        Supports N-way pad classification and fillet corner vertices.

        Args:
            mesh: The lateral mesh.
            boundary_verts: dict pad_id → set of mesh vertex indices.
            pad_constraint: dict pad_id → constraint_id.
            vertex_multi_constraints: Optional per-vertex constraint list from
                BoundaryExtractor.classify_boundary_vertices(). When provided,
                vertices on multiple surfaces get all their constraint IDs.
            wall_strategy: "none" | "pinned" | "full".
                "pinned" – wall-only vertices are fixed with no constraint.
                "full"   – wall vertices carry their wall constraint ID.
        """
        # Default constraint IDs for legacy "bottom"/"top" keys
        _default_cid = {
            "bottom": self.constraint_bottom_id,
            "top": self.constraint_top_id,
        }

        # Collect pad-only constraint IDs (constraint 1, 2 = bottom/top pads)
        # Used to distinguish pad vs wall constraints for pinned strategy.
        pad_cids = set(pad_constraint.values())

        vertices = []
        vertex_map = {}

        for idx in range(len(mesh.vertices)):
            se_id = idx + 1  # SE is 1-based
            vertex_map[idx] = se_id
            x, y, z = mesh.vertices[idx]

            if vertex_multi_constraints is not None and idx in vertex_multi_constraints:
                # --- Fillet/QFN mode: use per-vertex constraint assignment ---
                cids = vertex_multi_constraints[idx]

                if len(cids) == 0:
                    # Free vertex
                    vertices.append(Vertex(
                        id=se_id, x=float(x), y=float(y), z=float(z),
                    ))
                elif len(cids) == 1:
                    cid = cids[0]
                    is_wall_only = cid not in pad_cids
                    if wall_strategy == "pinned" and is_wall_only:
                        # Wall-only vertex: pin in place, no constraint
                        vertices.append(Vertex(
                            id=se_id, x=float(x), y=float(y), z=float(z),
                            fixed=True,
                        ))
                    else:
                        vertices.append(Vertex(
                            id=se_id, x=float(x), y=float(y), z=float(z),
                            constraints=[cid], fixed=True,
                        ))
                else:
                    # Corner vertex: on 2+ surfaces
                    if wall_strategy == "pinned":
                        # Keep only pad constraints; wall contact is pinned
                        active_cids = [c for c in cids if c in pad_cids]
                        if not active_cids:
                            active_cids = [cids[0]]  # fallback
                        vertices.append(Vertex(
                            id=se_id, x=float(x), y=float(y), z=float(z),
                            constraints=active_cids, fixed=True,
                        ))
                    else:
                        # Strategy B "full": assign all constraints
                        vertices.append(Vertex(
                            id=se_id, x=float(x), y=float(y), z=float(z),
                            constraints=cids, fixed=True,
                        ))
            else:
                # --- Legacy mode: loop-level classification ---
                matched_pad = None
                for pad in boundary_verts:
                    if idx in boundary_verts[pad]:
                        matched_pad = pad
                        break

                if matched_pad is not None:
                    cid = pad_constraint.get(
                        matched_pad, _default_cid.get(matched_pad, 0)
                    )
                    vertices.append(Vertex(
                        id=se_id, x=float(x), y=float(y), z=float(z),
                        constraints=[cid], fixed=True,
                    ))
                else:
                    vertices.append(Vertex(
                        id=se_id, x=float(x), y=float(y), z=float(z),
                    ))

        return vertices, vertex_map

    def _build_edges(
        self,
        mesh: trimesh.Trimesh,
        vertex_map: dict,
        boundary_edges_set: dict,
        pad_constraint: dict,
    ) -> tuple:
        """Create SE Edge objects from unique mesh edges.

        Supports N-way pad classification (any number of pad surfaces).
        """
        _default_cid = {
            "bottom": self.constraint_bottom_id,
            "top": self.constraint_top_id,
        }

        edge_map = {}  # canonical SE (min,max) → SE edge ID
        edges = []
        edge_id = 1

        for face in mesh.faces:
            for i in range(3):
                v1_mesh = int(face[i])
                v2_mesh = int(face[(i + 1) % 3])
                se_v1 = vertex_map[v1_mesh]
                se_v2 = vertex_map[v2_mesh]
                canonical_se = (min(se_v1, se_v2), max(se_v1, se_v2))

                if canonical_se in edge_map:
                    continue

                canonical_mesh = (min(v1_mesh, v2_mesh), max(v1_mesh, v2_mesh))

                # Check all pads for boundary edge
                matched_pad = None
                for pad in boundary_edges_set:
                    if canonical_mesh in boundary_edges_set[pad]:
                        matched_pad = pad
                        break

                if matched_pad is not None:
                    cid = pad_constraint.get(
                        matched_pad, _default_cid.get(matched_pad, 0)
                    )
                    e = Edge(
                        id=edge_id,
                        v1=canonical_se[0], v2=canonical_se[1],
                        constraints=[cid], fixed=True,
                    )
                else:
                    e = Edge(
                        id=edge_id,
                        v1=canonical_se[0], v2=canonical_se[1],
                    )

                edges.append(e)
                edge_map[canonical_se] = edge_id
                edge_id += 1

        return edges, edge_map

    def _build_faces(
        self,
        mesh: trimesh.Trimesh,
        vertex_map: dict,
        edge_map: dict,
    ) -> list:
        """Create SE Face objects with signed edge loops."""
        faces = []

        for fi, face in enumerate(mesh.faces):
            signed_edges = []
            for i in range(3):
                v1_mesh = int(face[i])
                v2_mesh = int(face[(i + 1) % 3])
                se_v1 = vertex_map[v1_mesh]
                se_v2 = vertex_map[v2_mesh]
                canonical_se = (min(se_v1, se_v2), max(se_v1, se_v2))
                eid = edge_map[canonical_se]

                # Sign: positive if face traverses in canonical direction
                if se_v1 < se_v2:
                    signed_edges.append(eid)
                else:
                    signed_edges.append(-eid)

            faces.append(Face(
                id=fi + 1,
                edges=signed_edges,
                tension=self.tension,
            ))

        return faces

    def _ensure_consistent_orientation(
        self,
        mesh: trimesh.Trimesh,
        faces: list,
    ) -> list:
        """Verify face normals point outward from body centroid.

        Uses trimesh face normals and compares with centroid-to-face vectors.
        If majority point inward, flip all faces.
        """
        if len(mesh.faces) == 0:
            return faces

        centroid = mesh.vertices.mean(axis=0)
        face_centers = mesh.triangles_center
        face_normals = mesh.face_normals

        # Vector from centroid to each face center
        to_face = face_centers - centroid
        dots = np.sum(to_face * face_normals, axis=1)

        # If more than half point inward, we need to flip
        n_inward = np.sum(dots < 0)
        if n_inward > len(faces) / 2:
            # Flip all face edge signs
            for face in faces:
                face.edges = [-e for e in reversed(face.edges)]

        return faces

    def _estimate_volume(self, mesh: trimesh.Trimesh) -> float:
        """Estimate enclosed volume of an open mesh.

        Temporarily closes the mesh by adding cap faces, then computes volume.
        """
        if mesh.is_watertight:
            return abs(mesh.volume)

        # For open meshes, use a rough estimate from bounding box
        # The actual volume will be enforced by SE's volume constraint
        bounds = mesh.bounds
        bbox_vol = np.prod(bounds[1] - bounds[0])
        # Approximate solder volume as ~40% of bounding box
        return bbox_vol * 0.4
