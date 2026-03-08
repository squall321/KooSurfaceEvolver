"""Load STEP (.stp/.step) files and extract solder/pad geometry with B-rep face classification.

Uses CadQuery/OCP to:
1. Load STEP assemblies and enumerate solids/faces
2. Automatically identify solder vs pad parts
3. Classify each solder face as contact (touching pad) or free (lateral)
4. Tessellate B-rep faces to trimesh for SE pipeline input
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Union

import numpy as np
import trimesh

try:
    import cadquery as cq
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepGProp import BRepGProp_Face as BRepGPropFace
    from OCP.gp import gp_Pnt, gp_Vec
    HAS_CADQUERY = True
except ImportError:
    HAS_CADQUERY = False


class FaceRole(Enum):
    """Classification of a solder B-rep face."""
    CONTACT_BOTTOM = "contact_bottom"
    CONTACT_TOP = "contact_top"
    CONTACT_WALL = "contact_wall"
    FREE_LATERAL = "free_lateral"
    UNKNOWN = "unknown"


class PartRole(Enum):
    """Role of a solid in the assembly."""
    SOLDER = "solder"
    BOTTOM_PAD = "bottom_pad"
    TOP_PAD = "top_pad"
    WALL = "wall"
    UNKNOWN = "unknown"


@dataclass
class STEPFace:
    """A single B-rep face with classification metadata."""
    face_id: int
    role: FaceRole
    area: float
    center: np.ndarray
    normal: np.ndarray
    geom_type: str
    mesh: trimesh.Trimesh
    _brep_face: object = field(default=None, repr=False)


@dataclass
class STEPSolid:
    """A solid body from the STEP file."""
    name: str
    role: PartRole
    faces: list
    volume: float
    bounds: np.ndarray
    combined_mesh: Optional[trimesh.Trimesh] = None
    _brep_solid: object = field(default=None, repr=False)


@dataclass
class STEPAssembly:
    """Complete parsed STEP assembly."""
    solids: list
    solder: Optional[STEPSolid] = None
    bottom_pad: Optional[STEPSolid] = None
    top_pad: Optional[STEPSolid] = None
    walls: list = field(default_factory=list)  # additional wall solids (fillet)
    pads: list = field(default_factory=list)  # N pads for bridge mode
    source_path: Optional[Path] = None


@dataclass
class MultiJointAssembly:
    """Result of multi-joint identification from a STEP assembly."""
    joints: list  # list of STEPAssembly, one per solder joint
    pad_bottom_solid: Optional[STEPSolid] = None  # shared bottom pad
    pad_top_solid: Optional[STEPSolid] = None  # shared top pad
    source_path: Optional[Path] = None


@dataclass
class ClassifiedSolderMesh:
    """Tessellated solder with per-triangle B-rep face labels."""
    mesh: trimesh.Trimesh
    face_roles: np.ndarray
    lateral_mesh: trimesh.Trimesh
    contact_bottom_mask: np.ndarray
    contact_top_mask: np.ndarray
    contact_wall_mask: np.ndarray = field(default=None)
    solder_volume: float = 0.0
    pad_bottom_mesh: trimesh.Trimesh = None
    pad_top_mesh: trimesh.Trimesh = None
    wall_meshes: list = field(default_factory=list)
    # Bridge mode: per-pad contact masks and meshes
    contact_pad_masks: dict = field(default_factory=dict)
    pad_meshes_list: list = field(default_factory=list)


def _require_cadquery():
    if not HAS_CADQUERY:
        raise ImportError(
            "STEP support requires CadQuery. Install with: pip install cadquery"
        )


class STEPReader:
    """Read STEP files and extract classified geometry."""

    def __init__(
        self,
        tessellation_tolerance: float = 0.001,
        angular_tolerance: float = 0.1,
        contact_tolerance: float = 1e-4,
    ):
        _require_cadquery()
        self.tess_tol = tessellation_tolerance
        self.ang_tol = angular_tolerance
        self.contact_tol = contact_tolerance

    def load_assembly(self, step_path: Union[str, Path]) -> STEPAssembly:
        """Load a STEP file and enumerate all solids with their faces."""
        step_path = Path(step_path)
        result = cq.importers.importStep(str(step_path))
        compound = result.val()

        if hasattr(compound, "Solids"):
            raw_solids = compound.Solids()
        else:
            raw_solids = [compound]

        solids = []
        for idx, solid in enumerate(raw_solids):
            step_solid = self._parse_solid(solid, f"Solid_{idx}")
            solids.append(step_solid)

        return STEPAssembly(solids=solids, source_path=step_path)

    def load_separate(
        self,
        solder_path: Union[str, Path],
        bottom_pad_path: Union[str, Path],
        top_pad_path: Union[str, Path],
    ) -> STEPAssembly:
        """Load 3 separate STEP files with explicit role assignment."""
        solids = []
        for path, role, name in [
            (solder_path, PartRole.SOLDER, "solder"),
            (bottom_pad_path, PartRole.BOTTOM_PAD, "bottom_pad"),
            (top_pad_path, PartRole.TOP_PAD, "top_pad"),
        ]:
            result = cq.importers.importStep(str(path))
            compound = result.val()
            raw = compound.Solids() if hasattr(compound, "Solids") else [compound]
            # Take first solid from each file
            step_solid = self._parse_solid(raw[0], name)
            step_solid.role = role
            solids.append(step_solid)

        assy = STEPAssembly(solids=solids)
        assy.solder = solids[0]
        assy.bottom_pad = solids[1]
        assy.top_pad = solids[2]
        return assy

    def identify_parts(
        self, assembly: STEPAssembly, strategy: str = "auto",
    ) -> STEPAssembly:
        """Identify which solid is solder, bottom_pad, top_pad.

        Strategy 'auto': Z-position based (lowest=bottom_pad, middle=solder,
        highest=top_pad) with validation.
        """
        solids = assembly.solids
        if len(solids) < 2:
            raise ValueError(
                f"Need at least 2 solids in STEP, found {len(solids)}"
            )

        if len(solids) == 3:
            assembly = self._identify_three(assembly)
        elif len(solids) == 2:
            assembly = self._identify_two(assembly)
        else:
            assembly = self._identify_multi(assembly)

        return assembly

    def identify_parts_bridge(
        self, assembly: STEPAssembly,
    ) -> STEPAssembly:
        """Identify parts for bridge geometry: 1 solder + N pads.

        The solder is the largest-volume solid.
        All other solids become pads, sorted by Z-centroid.
        """
        solids = assembly.solids
        if len(solids) < 2:
            raise ValueError(
                f"Bridge needs at least 2 solids, found {len(solids)}"
            )

        volumes = [s.volume for s in solids]
        solder_idx = int(np.argmax(volumes))
        solids[solder_idx].role = PartRole.SOLDER
        assembly.solder = solids[solder_idx]

        # All others = pads, sorted by Z-centroid
        pad_items = [
            (i, s) for i, s in enumerate(solids) if i != solder_idx
        ]
        pad_items.sort(
            key=lambda x: (x[1].bounds[0][2] + x[1].bounds[1][2]) / 2,
        )
        pads = []
        for _, s in pad_items:
            s.role = PartRole.BOTTOM_PAD
            pads.append(s)

        assembly.pads = pads

        # Backward compat
        if len(pads) >= 1:
            assembly.bottom_pad = pads[0]
        if len(pads) >= 2:
            assembly.top_pad = pads[-1]
        else:
            assembly.top_pad = pads[0]

        return assembly

    def identify_parts_multi(
        self, assembly: STEPAssembly,
    ) -> MultiJointAssembly:
        """Identify parts for multi-joint BGA/CSP array.

        Strategy:
        - The two largest-area solids (by bounding box footprint) = pads
          (bottom and top, identified by Z-centroid).
        - Everything else = individual solder joints.
        - Each solder is paired with the shared bottom and top pad.

        Returns:
            MultiJointAssembly with one STEPAssembly per solder joint.
        """
        solids = assembly.solids
        if len(solids) < 3:
            raise ValueError(
                f"Multi-joint needs at least 3 solids (2 pads + 1+ solders), "
                f"found {len(solids)}"
            )

        # Estimate footprint area = dx * dy of bounding box
        footprints = []
        for s in solids:
            dx = s.bounds[1][0] - s.bounds[0][0]
            dy = s.bounds[1][1] - s.bounds[0][1]
            footprints.append(dx * dy)

        # Two largest footprints = pads
        fp_order = np.argsort(footprints)[::-1]
        pad_indices = set(fp_order[:2].tolist())

        pad_solids = [solids[i] for i in sorted(pad_indices)]
        z_centers = [
            (s.bounds[0][2] + s.bounds[1][2]) / 2 for s in pad_solids
        ]
        if z_centers[0] <= z_centers[1]:
            bottom_pad, top_pad = pad_solids[0], pad_solids[1]
        else:
            bottom_pad, top_pad = pad_solids[1], pad_solids[0]

        bottom_pad.role = PartRole.BOTTOM_PAD
        top_pad.role = PartRole.TOP_PAD

        # Remaining solids = solder joints
        solder_solids = [
            s for i, s in enumerate(solids) if i not in pad_indices
        ]
        for s in solder_solids:
            s.role = PartRole.SOLDER

        # Create per-joint assemblies sharing the same pads
        joints = []
        for s in solder_solids:
            joint_assy = STEPAssembly(
                solids=[s, bottom_pad, top_pad],
                solder=s,
                bottom_pad=bottom_pad,
                top_pad=top_pad,
                source_path=assembly.source_path,
            )
            joints.append(joint_assy)

        return MultiJointAssembly(
            joints=joints,
            pad_bottom_solid=bottom_pad,
            pad_top_solid=top_pad,
            source_path=assembly.source_path,
        )

    def classify_faces(self, assembly: STEPAssembly) -> ClassifiedSolderMesh:
        """Classify each solder face as contact or free using B-rep proximity.

        Uses two-step detection:
        1. Anti-parallel normal + face-to-face distance < tol
        2. Interior point sampling as fallback

        Supports additional wall solids for fillet geometry.
        """
        solder = assembly.solder
        bottom_pad = assembly.bottom_pad
        top_pad = assembly.top_pad
        if solder is None or bottom_pad is None or top_pad is None:
            raise ValueError("Parts not identified. Call identify_parts() first.")

        bot_faces = bottom_pad.faces
        top_faces = top_pad.faces
        wall_faces = []
        for wall in assembly.walls:
            wall_faces.extend(wall.faces)

        for sface in solder.faces:
            role = self._classify_single_face(
                sface, bot_faces, top_faces, wall_faces,
            )
            sface.role = role

        return self._build_classified_mesh(assembly)

    def classify_faces_bridge(
        self, assembly: STEPAssembly,
    ) -> ClassifiedSolderMesh:
        """Classify solder faces against N pads (bridge mode).

        Each solder face is tested against all pad face lists.
        Returns ClassifiedSolderMesh with per-pad contact_pad_masks.
        """
        solder = assembly.solder
        pads = assembly.pads
        if solder is None or not pads:
            raise ValueError("Bridge requires solder and at least 1 pad")

        pad_faces_list = [pad.faces for pad in pads]

        for sface in solder.faces:
            role, pad_idx = self._classify_face_against_pads(
                sface, pad_faces_list,
            )
            sface.role = role
            sface._bridge_pad_idx = pad_idx

        return self._build_classified_mesh_bridge(assembly)

    # ------------------------------------------------------------------
    # Internal: parsing
    # ------------------------------------------------------------------

    def _parse_solid(self, cq_solid, name: str) -> STEPSolid:
        """Parse a CadQuery solid into STEPSolid with tessellated faces."""
        faces = []
        for fi, face in enumerate(cq_solid.Faces()):
            verts, tris = face.tessellate(self.tess_tol, self.ang_tol)
            np_verts = np.array([[v.x, v.y, v.z] for v in verts])
            np_tris = np.array(tris) if tris else np.zeros((0, 3), dtype=int)

            if len(np_verts) == 0:
                continue

            face_mesh = trimesh.Trimesh(
                vertices=np_verts, faces=np_tris, process=False,
            )

            center = face.Center()
            normal = face.normalAt()

            faces.append(STEPFace(
                face_id=fi,
                role=FaceRole.UNKNOWN,
                area=face.Area(),
                center=np.array([center.x, center.y, center.z]),
                normal=np.array([normal.x, normal.y, normal.z]),
                geom_type=face.geomType(),
                mesh=face_mesh,
                _brep_face=face,
            ))

        bb = cq_solid.BoundingBox()
        bounds = np.array([
            [bb.xmin, bb.ymin, bb.zmin],
            [bb.xmax, bb.ymax, bb.zmax],
        ])

        combined = trimesh.util.concatenate([f.mesh for f in faces]) if faces else None

        return STEPSolid(
            name=name,
            role=PartRole.UNKNOWN,
            faces=faces,
            volume=cq_solid.Volume(),
            bounds=bounds,
            combined_mesh=combined,
            _brep_solid=cq_solid,
        )

    # ------------------------------------------------------------------
    # Internal: part identification
    # ------------------------------------------------------------------

    def _identify_three(self, assembly: STEPAssembly) -> STEPAssembly:
        """Identify 3 solids by Z-centroid: lowest=bottom_pad, mid=solder, top=top_pad."""
        solids = assembly.solids
        z_centers = [
            (s.bounds[0][2] + s.bounds[1][2]) / 2 for s in solids
        ]
        order = np.argsort(z_centers)

        solids[order[0]].role = PartRole.BOTTOM_PAD
        solids[order[1]].role = PartRole.SOLDER
        solids[order[2]].role = PartRole.TOP_PAD

        assembly.bottom_pad = solids[order[0]]
        assembly.solder = solids[order[1]]
        assembly.top_pad = solids[order[2]]
        return assembly

    def _identify_two(self, assembly: STEPAssembly) -> STEPAssembly:
        """Identify 2 solids: larger Z-extent = solder, other = pad."""
        solids = assembly.solids
        z_extents = [s.bounds[1][2] - s.bounds[0][2] for s in solids]

        if z_extents[0] > z_extents[1]:
            solids[0].role = PartRole.SOLDER
            solids[1].role = PartRole.BOTTOM_PAD
            assembly.solder = solids[0]
            assembly.bottom_pad = solids[1]
            assembly.top_pad = solids[1]  # same pad both sides
        else:
            solids[1].role = PartRole.SOLDER
            solids[0].role = PartRole.BOTTOM_PAD
            assembly.solder = solids[1]
            assembly.bottom_pad = solids[0]
            assembly.top_pad = solids[0]

        return assembly

    def _identify_multi(self, assembly: STEPAssembly) -> STEPAssembly:
        """Identify >3 solids: pick sandwich pattern by Z-position."""
        solids = assembly.solids
        z_centers = [
            (s.bounds[0][2] + s.bounds[1][2]) / 2 for s in solids
        ]
        order = np.argsort(z_centers)

        # Assume: first=bottom_pad, last=top_pad, largest volume in between=solder
        candidates = order[1:-1]
        volumes = [solids[i].volume for i in candidates]
        solder_idx = candidates[np.argmax(volumes)]

        solids[order[0]].role = PartRole.BOTTOM_PAD
        solids[solder_idx].role = PartRole.SOLDER
        solids[order[-1]].role = PartRole.TOP_PAD

        assembly.bottom_pad = solids[order[0]]
        assembly.solder = solids[solder_idx]
        assembly.top_pad = solids[order[-1]]
        return assembly

    # ------------------------------------------------------------------
    # Internal: face classification
    # ------------------------------------------------------------------

    def _classify_single_face(
        self,
        sface: STEPFace,
        bot_faces: list,
        top_faces: list,
        wall_faces: list = None,
    ) -> FaceRole:
        """Classify one solder face using normal alignment + distance check."""
        tol = self.contact_tol
        if wall_faces is None:
            wall_faces = []

        # Method 1: face-to-face with anti-parallel normal check
        for pface in bot_faces:
            if self._is_contact_pair(sface, pface, tol):
                return FaceRole.CONTACT_BOTTOM

        for pface in top_faces:
            if self._is_contact_pair(sface, pface, tol):
                return FaceRole.CONTACT_TOP

        for pface in wall_faces:
            if self._is_contact_pair(sface, pface, tol):
                return FaceRole.CONTACT_WALL

        # Method 2: interior point sampling fallback
        role = self._classify_by_interior_point(
            sface, bot_faces, top_faces, tol, wall_faces,
        )
        if role != FaceRole.UNKNOWN:
            return role

        return FaceRole.FREE_LATERAL

    def _is_contact_pair(
        self, sface: STEPFace, pface: STEPFace, tol: float,
    ) -> bool:
        """Check if solder face and pad face form a contact pair.

        Criteria:
        1. BRepExtrema distance < tol
        2. Normals are anti-parallel (dot product < -0.8)
        3. Area overlap ratio > 0.05
        """
        # Normal anti-parallel check (fast reject)
        dot = np.dot(sface.normal, pface.normal)
        if dot > -0.5:
            return False

        # BRepExtrema distance
        dss = BRepExtrema_DistShapeShape(
            sface._brep_face.wrapped, pface._brep_face.wrapped,
        )
        if not dss.IsDone() or dss.Value() > tol:
            return False

        # Area overlap ratio
        ratio = min(sface.area, pface.area) / max(sface.area, pface.area)
        if ratio < 0.05:
            return False

        return True

    def _classify_by_interior_point(
        self,
        sface: STEPFace,
        bot_faces: list,
        top_faces: list,
        tol: float,
        wall_faces: list = None,
    ) -> FaceRole:
        """Classify by sampling the face interior center point."""
        if wall_faces is None:
            wall_faces = []
        brep_face = sface._brep_face
        props = BRepGPropFace(brep_face.wrapped)
        u0, u1, v0, v1 = brep_face._uvBounds()
        u_mid = (u0 + u1) / 2
        v_mid = (v0 + v1) / 2
        pt = gp_Pnt()
        normal = gp_Vec()
        props.Normal(u_mid, v_mid, pt, normal)

        test_pt = gp_Pnt(pt.X(), pt.Y(), pt.Z())
        test_vertex = BRepBuilderAPI_MakeVertex(test_pt).Shape()

        # Distance from interior point to each pad
        for pface in bot_faces:
            dss = BRepExtrema_DistShapeShape(test_vertex, pface._brep_face.wrapped)
            if dss.IsDone() and dss.Value() < tol:
                return FaceRole.CONTACT_BOTTOM

        for pface in top_faces:
            dss = BRepExtrema_DistShapeShape(test_vertex, pface._brep_face.wrapped)
            if dss.IsDone() and dss.Value() < tol:
                return FaceRole.CONTACT_TOP

        for pface in wall_faces:
            dss = BRepExtrema_DistShapeShape(test_vertex, pface._brep_face.wrapped)
            if dss.IsDone() and dss.Value() < tol:
                return FaceRole.CONTACT_WALL

        return FaceRole.UNKNOWN

    # ------------------------------------------------------------------
    # Internal: mesh building
    # ------------------------------------------------------------------

    def _build_classified_mesh(
        self, assembly: STEPAssembly,
    ) -> ClassifiedSolderMesh:
        """Build combined solder mesh with per-triangle role labels."""
        solder = assembly.solder

        all_verts = []
        all_faces = []
        all_roles = []
        vert_offset = 0

        role_to_int = {
            FaceRole.CONTACT_BOTTOM: 0,
            FaceRole.CONTACT_TOP: 1,
            FaceRole.FREE_LATERAL: 2,
            FaceRole.UNKNOWN: 2,  # treat unknown as lateral
            FaceRole.CONTACT_WALL: 3,
        }

        for face in solder.faces:
            n_v = len(face.mesh.vertices)
            n_f = len(face.mesh.faces)
            if n_v == 0 or n_f == 0:
                continue
            all_verts.append(face.mesh.vertices)
            all_faces.append(face.mesh.faces + vert_offset)
            all_roles.extend([role_to_int[face.role]] * n_f)
            vert_offset += n_v

        combined_verts = np.vstack(all_verts)
        combined_faces = np.vstack(all_faces)
        face_roles = np.array(all_roles, dtype=int)

        full_mesh = trimesh.Trimesh(
            vertices=combined_verts, faces=combined_faces, process=False,
        )
        full_mesh.merge_vertices()

        # Masks
        contact_bottom_mask = face_roles == 0
        contact_top_mask = face_roles == 1
        lateral_mask = face_roles == 2
        contact_wall_mask = face_roles == 3

        # Extract lateral submesh
        lateral_faces = full_mesh.faces[lateral_mask]
        used_verts = np.unique(lateral_faces)
        new_idx = np.full(len(full_mesh.vertices), -1, dtype=int)
        new_idx[used_verts] = np.arange(len(used_verts))
        lateral_mesh = trimesh.Trimesh(
            vertices=full_mesh.vertices[used_verts],
            faces=new_idx[lateral_faces],
            process=False,
        )

        wall_meshes = [w.combined_mesh for w in assembly.walls if w.combined_mesh]

        return ClassifiedSolderMesh(
            mesh=full_mesh,
            face_roles=face_roles,
            lateral_mesh=lateral_mesh,
            contact_bottom_mask=contact_bottom_mask,
            contact_top_mask=contact_top_mask,
            contact_wall_mask=contact_wall_mask,
            solder_volume=solder.volume,
            pad_bottom_mesh=assembly.bottom_pad.combined_mesh,
            pad_top_mesh=assembly.top_pad.combined_mesh,
            wall_meshes=wall_meshes,
        )

    def _classify_face_against_pads(
        self,
        sface: STEPFace,
        pad_faces_list: list,
    ) -> tuple:
        """Classify a solder face against N pad face lists.

        Returns (FaceRole, pad_index) where pad_index is the index
        into the pads list, or -1 if free lateral.
        """
        tol = self.contact_tol

        # Method 1: Normal alignment + BRepExtrema distance
        for pi, pad_faces in enumerate(pad_faces_list):
            for pface in pad_faces:
                if self._is_contact_pair(sface, pface, tol):
                    return (FaceRole.CONTACT_BOTTOM, pi)

        # Method 2: Interior point sampling fallback
        brep_face = sface._brep_face
        props = BRepGPropFace(brep_face.wrapped)
        u0, u1, v0, v1 = brep_face._uvBounds()
        pt = gp_Pnt()
        normal = gp_Vec()
        props.Normal((u0 + u1) / 2, (v0 + v1) / 2, pt, normal)

        test_pt = gp_Pnt(pt.X(), pt.Y(), pt.Z())
        test_vertex = BRepBuilderAPI_MakeVertex(test_pt).Shape()

        for pi, pad_faces in enumerate(pad_faces_list):
            for pface in pad_faces:
                dss = BRepExtrema_DistShapeShape(
                    test_vertex, pface._brep_face.wrapped,
                )
                if dss.IsDone() and dss.Value() < tol:
                    return (FaceRole.CONTACT_BOTTOM, pi)

        return (FaceRole.FREE_LATERAL, -1)

    def _build_classified_mesh_bridge(
        self, assembly: STEPAssembly,
    ) -> ClassifiedSolderMesh:
        """Build combined mesh with per-pad masks for bridge mode."""
        solder = assembly.solder
        pads = assembly.pads
        n_pads = len(pads)

        all_verts = []
        all_faces = []
        all_pad_indices = []  # -1 = free lateral, 0..N-1 = pad index
        vert_offset = 0

        for face in solder.faces:
            n_v = len(face.mesh.vertices)
            n_f = len(face.mesh.faces)
            if n_v == 0 or n_f == 0:
                continue
            all_verts.append(face.mesh.vertices)
            all_faces.append(face.mesh.faces + vert_offset)
            pad_idx = getattr(face, '_bridge_pad_idx', -1)
            all_pad_indices.extend([pad_idx] * n_f)
            vert_offset += n_v

        combined_verts = np.vstack(all_verts)
        combined_faces = np.vstack(all_faces)
        pad_indices = np.array(all_pad_indices, dtype=int)

        full_mesh = trimesh.Trimesh(
            vertices=combined_verts, faces=combined_faces, process=False,
        )
        full_mesh.merge_vertices()

        # Per-pad masks
        contact_pad_masks = {}
        for pi in range(n_pads):
            contact_pad_masks[pi] = pad_indices == pi
        lateral_mask = pad_indices == -1

        # Backward-compat face_roles: 0=bottom, 1=top, 2=lateral
        face_roles = np.full(len(pad_indices), 2, dtype=int)
        if 0 in contact_pad_masks:
            face_roles[contact_pad_masks[0]] = 0
        if 1 in contact_pad_masks:
            face_roles[contact_pad_masks[1]] = 1

        # Extract lateral submesh
        lateral_faces_arr = full_mesh.faces[lateral_mask]
        used_verts = np.unique(lateral_faces_arr)
        new_idx = np.full(len(full_mesh.vertices), -1, dtype=int)
        new_idx[used_verts] = np.arange(len(used_verts))
        lateral_mesh = trimesh.Trimesh(
            vertices=full_mesh.vertices[used_verts],
            faces=new_idx[lateral_faces_arr],
            process=False,
        )

        pad_meshes_list = [
            p.combined_mesh for p in pads if p.combined_mesh
        ]

        return ClassifiedSolderMesh(
            mesh=full_mesh,
            face_roles=face_roles,
            lateral_mesh=lateral_mesh,
            contact_bottom_mask=contact_pad_masks.get(
                0, np.zeros(len(pad_indices), dtype=bool),
            ),
            contact_top_mask=contact_pad_masks.get(
                1, np.zeros(len(pad_indices), dtype=bool),
            ),
            solder_volume=solder.volume,
            pad_bottom_mesh=pads[0].combined_mesh if pads else None,
            pad_top_mesh=pads[-1].combined_mesh if len(pads) >= 2 else None,
            contact_pad_masks=contact_pad_masks,
            pad_meshes_list=pad_meshes_list,
        )
