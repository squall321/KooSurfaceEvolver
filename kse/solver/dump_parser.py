"""Parse Surface Evolver dump (.dmp) files into mesh data structures."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class DumpVertex:
    id: int
    coords: np.ndarray          # (3,) x, y, z
    constraints: list = field(default_factory=list)
    fixed: bool = False
    boundary: Optional[int] = None


@dataclass
class DumpEdge:
    id: int
    v1: int
    v2: int
    constraints: list = field(default_factory=list)
    fixed: bool = False
    no_refine: bool = False
    boundary: Optional[int] = None


@dataclass
class DumpFace:
    id: int
    edge_loop: list             # signed edge IDs
    area: Optional[float] = None
    original: Optional[int] = None
    density: Optional[float] = None
    fixed: bool = False
    no_refine: bool = False


@dataclass
class DumpBody:
    id: int
    face_list: list             # signed face IDs
    volume: Optional[float] = None
    actual_volume: Optional[float] = None
    lagrange_multiplier: Optional[float] = None
    density: Optional[float] = None


@dataclass
class ParsedMesh:
    """Complete mesh parsed from a dump file."""

    vertices: dict              # id -> DumpVertex
    edges: dict                 # id -> DumpEdge
    faces: dict                 # id -> DumpFace
    bodies: dict                # id -> DumpBody
    total_energy: Optional[float] = None

    @property
    def vertex_array(self) -> np.ndarray:
        """Get (N, 3) vertex coordinate array, sorted by ID."""
        ids = sorted(self.vertices.keys())
        return np.array([self.vertices[i].coords for i in ids])

    @property
    def face_triangles(self) -> np.ndarray:
        """Convert edge-loop faces to vertex-index triangles.

        Returns (M, 3) array of vertex indices (0-based).
        """
        id_to_idx = {}
        for idx, vid in enumerate(sorted(self.vertices.keys())):
            id_to_idx[vid] = idx

        triangles = []
        for fid in sorted(self.faces.keys()):
            face = self.faces[fid]
            # Resolve edge loop to vertex sequence
            verts = self._edge_loop_to_vertices(face.edge_loop)
            if verts is not None and len(verts) >= 3:
                # Triangulate (fan from first vertex)
                v0 = id_to_idx.get(verts[0])
                for i in range(1, len(verts) - 1):
                    v1 = id_to_idx.get(verts[i])
                    v2 = id_to_idx.get(verts[i + 1])
                    if v0 is not None and v1 is not None and v2 is not None:
                        triangles.append([v0, v1, v2])

        return np.array(triangles, dtype=int) if triangles else np.zeros((0, 3), dtype=int)

    @property
    def free_face_triangles(self) -> np.ndarray:
        """Convert only non-fixed faces to vertex-index triangles.

        Returns (M, 3) array of vertex indices (0-based).
        Excludes faces with fixed=True (e.g. pad faces with tension 0).
        """
        id_to_idx = {}
        for idx, vid in enumerate(sorted(self.vertices.keys())):
            id_to_idx[vid] = idx

        triangles = []
        for fid in sorted(self.faces.keys()):
            face = self.faces[fid]
            if face.fixed:
                continue
            verts = self._edge_loop_to_vertices(face.edge_loop)
            if verts is not None and len(verts) >= 3:
                v0 = id_to_idx.get(verts[0])
                for i in range(1, len(verts) - 1):
                    v1 = id_to_idx.get(verts[i])
                    v2 = id_to_idx.get(verts[i + 1])
                    if v0 is not None and v1 is not None and v2 is not None:
                        triangles.append([v0, v1, v2])

        return np.array(triangles, dtype=int) if triangles else np.zeros((0, 3), dtype=int)

    def _edge_loop_to_vertices(self, edge_loop: list) -> Optional[list]:
        """Convert signed edge IDs to ordered vertex list."""
        verts = []
        for eid in edge_loop:
            edge = self.edges.get(abs(eid))
            if edge is None:
                return None
            if eid > 0:
                if not verts or verts[-1] != edge.v1:
                    verts.append(edge.v1)
                verts.append(edge.v2)
            else:
                if not verts or verts[-1] != edge.v2:
                    verts.append(edge.v2)
                verts.append(edge.v1)

        # Remove duplicate last vertex if loop closes
        if len(verts) > 1 and verts[0] == verts[-1]:
            verts.pop()

        return verts


class DumpParser:
    """Parse Surface Evolver .dmp files."""

    def parse(self, dmp_path: str | Path) -> ParsedMesh:
        """Parse a dump file and return structured mesh data."""
        dmp_path = Path(dmp_path)
        text = dmp_path.read_text()

        mesh = ParsedMesh(
            vertices={},
            edges={},
            faces={},
            bodies={},
        )

        # Extract total energy
        m = re.search(r"Total energy:\s+([-\d.eE+]+)", text)
        if m:
            mesh.total_energy = float(m.group(1))

        # Split into sections
        sections = self._split_sections(text)

        if "vertices" in sections:
            mesh.vertices = self._parse_vertices(sections["vertices"])
        if "edges" in sections:
            mesh.edges = self._parse_edges(sections["edges"])
        if "faces" in sections:
            mesh.faces = self._parse_faces(sections["faces"])
        if "bodies" in sections:
            mesh.bodies = self._parse_bodies(sections["bodies"])

        return mesh

    def _split_sections(self, text: str) -> dict:
        """Split dump text into named sections."""
        sections = {}
        section_names = ["vertices", "edges", "faces", "bodies", "read"]
        current_section = None
        current_lines = []

        for line in text.splitlines():
            stripped = line.strip().lower()

            # Check for section headers
            matched = False
            for name in section_names:
                if stripped.startswith(name) and (
                    len(stripped) == len(name)
                    or stripped[len(name)] in " \t/"
                ):
                    if current_section:
                        sections[current_section] = "\n".join(current_lines)
                    current_section = name
                    current_lines = []
                    matched = True
                    break

            if not matched and current_section:
                current_lines.append(line)

        if current_section:
            sections[current_section] = "\n".join(current_lines)

        return sections

    def _parse_vertices(self, text: str) -> dict:
        """Parse vertex section.

        Handles two formats:
        - Standard: id  x  y  z  [constraints ...] [fixed]
        - Boundary: id  param  boundary N  /* (x y z) */  [fixed]
        """
        vertices = {}
        for line in text.splitlines():
            raw_line = line.strip()
            if not raw_line or not raw_line[0].isdigit():
                continue

            # Check for boundary vertex: "id  param  boundary N  /* (x y z) */"
            boundary = None
            bnd_match = re.match(
                r"(\d+)\s+([-\d.eE+]+)\s+boundary\s+(\d+)\s+/\*\s*\(\s*"
                r"([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s*\)\s*\*/\s*(.*)",
                raw_line,
            )
            if bnd_match:
                vid = int(bnd_match.group(1))
                boundary = int(bnd_match.group(3))
                x = float(bnd_match.group(4))
                y = float(bnd_match.group(5))
                z = float(bnd_match.group(6))
                rest = bnd_match.group(7).lower()
                fixed = "fixed" in rest
                vertices[vid] = DumpVertex(
                    id=vid, coords=np.array([x, y, z]),
                    constraints=[], fixed=fixed, boundary=boundary,
                )
                continue

            # Standard vertex: strip comments then parse
            line = self._strip_comments(raw_line).strip()
            if not line or not line[0].isdigit():
                continue

            parts = line.split()
            if len(parts) < 4:
                continue

            vid = int(parts[0])
            try:
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
            except ValueError:
                continue

            rest = " ".join(parts[4:]).lower()
            constraints = []
            fixed = False

            if "constraints" in rest:
                m = re.search(r"constraints\s+([\d,\s]+)", rest)
                if m:
                    constraints = [int(c.strip()) for c in m.group(1).split(",")
                                   if c.strip().isdigit()]

            if "fixed" in rest:
                fixed = True

            if "boundary" in rest:
                m = re.search(r"boundary\s+(\d+)", rest)
                if m:
                    boundary = int(m.group(1))

            vertices[vid] = DumpVertex(
                id=vid, coords=np.array([x, y, z]),
                constraints=constraints, fixed=fixed, boundary=boundary,
            )

        return vertices

    def _parse_edges(self, text: str) -> dict:
        """Parse edge section."""
        edges = {}
        for line in text.splitlines():
            line = self._strip_comments(line).strip()
            if not line or not line[0].isdigit():
                continue

            parts = line.split()
            if len(parts) < 3:
                continue

            eid = int(parts[0])
            v1, v2 = int(parts[1]), int(parts[2])

            rest = " ".join(parts[3:]).lower()
            constraints = []
            fixed = "fixed" in rest
            no_refine = "no_refine" in rest

            if "constraints" in rest:
                m = re.search(r"constraints\s+([\d,\s]+)", rest)
                if m:
                    constraints = [int(c.strip()) for c in m.group(1).split(",")
                                   if c.strip().isdigit()]

            boundary = None
            if "boundary" in rest:
                m = re.search(r"boundary\s+(\d+)", rest)
                if m:
                    boundary = int(m.group(1))

            edges[eid] = DumpEdge(
                id=eid, v1=v1, v2=v2,
                constraints=constraints, fixed=fixed, no_refine=no_refine,
                boundary=boundary,
            )

        return edges

    def _parse_faces(self, text: str) -> dict:
        """Parse face section."""
        faces = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or not line[0].isdigit() and not line[0] == " ":
                continue

            # Remove inline comments but preserve /*area*/ info
            area = None
            area_m = re.search(r"/\*area\s+([-\d.eE+]+)\*/", line)
            if area_m:
                area = float(area_m.group(1))

            original = None
            orig_m = re.search(r"original\s+(\d+)", line)
            if orig_m:
                original = int(orig_m.group(1))

            # Strip comments
            line = re.sub(r"/\*.*?\*/", "", line).strip()
            if not line or not line[0].isdigit():
                continue

            parts = line.split()
            fid = int(parts[0])

            # Parse edge loop (signed integers)
            edge_loop = []
            i = 1
            while i < len(parts):
                p = parts[i]
                try:
                    edge_loop.append(int(p))
                    i += 1
                except ValueError:
                    break

            rest = " ".join(parts[i:]).lower()
            fixed = "fixed" in rest
            no_refine = "no_refine" in rest
            density = None
            if "density" in rest:
                m = re.search(r"density\s+([-\d.eE+]+)", rest)
                if m:
                    density = float(m.group(1))

            faces[fid] = DumpFace(
                id=fid, edge_loop=edge_loop, area=area,
                original=original, density=density,
                fixed=fixed, no_refine=no_refine,
            )

        return faces

    def _parse_bodies(self, text: str) -> dict:
        """Parse body section."""
        bodies = {}
        # Bodies can span multiple lines with backslash continuation
        text = text.replace("\\\n", " ")

        for line in text.splitlines():
            line = line.strip()
            if not line or not line[0].isdigit():
                continue

            # Extract actual volume from comment
            actual_vol = None
            m = re.search(r"/\*actual:\s*([-\d.eE+]+)\*/", line)
            if m:
                actual_vol = float(m.group(1))

            line = re.sub(r"/\*.*?\*/", "", line).strip()
            parts = line.split()

            bid = int(parts[0])
            face_list = []
            i = 1
            while i < len(parts):
                try:
                    face_list.append(int(parts[i]))
                    i += 1
                except ValueError:
                    break

            rest = " ".join(parts[i:]).lower()

            volume = None
            m = re.search(r"volume\s+([-\d.eE+]+)", rest)
            if m:
                volume = float(m.group(1))

            lagrange = None
            m = re.search(r"lagrange_multiplier\s+([-\d.eE+]+)", rest)
            if m:
                lagrange = float(m.group(1))

            density = None
            m = re.search(r"density\s+([-\d.eE+]+)", rest)
            if m:
                density = float(m.group(1))

            bodies[bid] = DumpBody(
                id=bid, face_list=face_list, volume=volume,
                actual_volume=actual_vol, lagrange_multiplier=lagrange,
                density=density,
            )

        return bodies

    @staticmethod
    def _strip_comments(line: str) -> str:
        """Remove // and /* */ comments."""
        # Remove // comments
        idx = line.find("//")
        if idx >= 0:
            line = line[:idx]
        # Remove /* */ inline comments
        line = re.sub(r"/\*.*?\*/", "", line)
        return line
