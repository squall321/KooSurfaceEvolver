"""Generate initial solder joint geometry between two surface patches.

Creates the cylindrical/prismatic initial shape that Surface Evolver
will evolve into the equilibrium solder meniscus.
"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .surface_fitter import SurfaceFitResult


@dataclass
class Vertex:
    id: int
    x: float
    y: float
    z: float
    constraints: list = field(default_factory=list)
    boundary: Optional[int] = None
    boundary_param: Optional[float] = None
    fixed: bool = False
    extras: str = ""


@dataclass
class Edge:
    id: int
    v1: int
    v2: int
    constraints: list = field(default_factory=list)
    boundary: Optional[int] = None
    fixed: bool = False


@dataclass
class Face:
    id: int
    edges: list     # signed edge IDs
    tension: Optional[float] = None
    fixed: bool = False
    color: Optional[str] = None
    no_refine: bool = False


@dataclass
class Body:
    id: int
    faces: list     # signed face IDs
    volume: Optional[str] = None   # volume expression string
    density: Optional[float] = None


@dataclass
class InitialGeometry:
    """Complete initial geometry for a solder joint."""

    vertices: list
    edges: list
    faces: list
    bodies: list
    n_segments: int

    @property
    def n_vertices(self) -> int:
        return len(self.vertices)

    @property
    def n_edges(self) -> int:
        return len(self.edges)

    @property
    def n_faces(self) -> int:
        return len(self.faces)


class GeometryBuilder:
    """Build initial solder joint geometry between two fitted surfaces."""

    def __init__(self, n_segments: int = 8):
        """
        Args:
            n_segments: Number of vertices around each pad rim.
                        8 is good balance between smoothness and simplicity.
        """
        self.n_segments = n_segments

    def build(
        self,
        fit_A: SurfaceFitResult,
        fit_B: SurfaceFitResult,
        radius: float,
        volume: float,
        density: float = 9.0,
        tension: float = 480.0,
        constraint_A_id: int = 1,
        constraint_B_id: int = 2,
        rim_A_id: int = 3,
        boundary_B_id: int = 1,
        use_boundary_for_B: bool = True,
    ) -> InitialGeometry:
        """Build initial geometry for a solder joint.

        Surface A (bottom) uses CONSTRAINT, Surface B (top) uses BOUNDARY.
        This follows the bga-12.fe pattern where the upper pad is parametric.

        Args:
            fit_A: Surface fit for bottom surface.
            fit_B: Surface fit for top surface.
            radius: Solder pad radius.
            volume: Target solder volume.
            density: Solder density.
            tension: Surface tension.
            constraint_A_id: SE constraint ID for surface A.
            constraint_B_id: SE constraint ID for surface B.
            rim_A_id: SE constraint ID for rim of A.
            boundary_B_id: SE boundary ID for surface B rim.
            use_boundary_for_B: Use parametric boundary for B (recommended).
        """
        n = self.n_segments
        vertices = []
        edges = []
        faces = []

        # Generate angles for rim vertices
        angles = np.linspace(0, 2 * np.pi, n, endpoint=False)

        # --- Surface A (bottom) vertices ---
        for i, theta in enumerate(angles):
            u = radius * np.cos(theta)
            v = radius * np.sin(theta)

            # Project onto surface A in global coordinates
            pos = self._project_to_surface(fit_A, u, v)

            vertices.append(Vertex(
                id=i + 1,
                x=pos[0], y=pos[1], z=pos[2],
                constraints=[constraint_A_id, rim_A_id],
                fixed=True,
            ))

        # --- Surface B (top) vertices ---
        if use_boundary_for_B:
            for i, theta in enumerate(angles):
                vertices.append(Vertex(
                    id=n + i + 1,
                    x=0, y=0, z=0,  # coordinates come from boundary
                    boundary=boundary_B_id,
                    boundary_param=theta,
                    fixed=True,
                ))
        else:
            for i, theta in enumerate(angles):
                u = radius * np.cos(theta)
                v = radius * np.sin(theta)
                pos = self._project_to_surface(fit_B, u, v)

                vertices.append(Vertex(
                    id=n + i + 1,
                    x=pos[0], y=pos[1], z=pos[2],
                    constraints=[constraint_B_id],
                    fixed=True,
                ))

        # --- Bottom rim edges (fixed) ---
        edge_id = 1
        for i in range(n):
            j = (i + 1) % n
            edges.append(Edge(
                id=edge_id,
                v1=i + 1,
                v2=j + 1,
                constraints=[constraint_A_id, rim_A_id],
                fixed=True,
            ))
            edge_id += 1

        # --- Top rim edges (fixed, on boundary) ---
        for i in range(n):
            j = (i + 1) % n
            e = Edge(
                id=edge_id,
                v1=n + i + 1,
                v2=n + j + 1,
                fixed=True,
            )
            if use_boundary_for_B:
                e.boundary = boundary_B_id
            else:
                e.constraints = [constraint_B_id]
            edges.append(e)
            edge_id += 1

        # --- Vertical (lateral) edges (free) ---
        vert_edge_start = edge_id
        for i in range(n):
            edges.append(Edge(
                id=edge_id,
                v1=i + 1,
                v2=n + i + 1,
            ))
            edge_id += 1

        # --- Lateral faces (free surface with tension) ---
        face_id = 1
        for i in range(n):
            j = (i + 1) % n
            # Face edges: bottom[i], vertical[j], -top[i], -vertical[i]
            bottom_e = i + 1
            top_e = n + i + 1
            vert_i = vert_edge_start + i
            vert_j = vert_edge_start + j

            faces.append(Face(
                id=face_id,
                edges=[bottom_e, vert_j, -(top_e), -(vert_i)],
                tension=tension,
            ))
            face_id += 1

        # --- Body ---
        face_ids = list(range(1, face_id))
        bodies = [Body(
            id=1,
            faces=face_ids,
            volume=f"{volume}",
            density=density,
        )]

        return InitialGeometry(
            vertices=vertices,
            edges=edges,
            faces=faces,
            bodies=bodies,
            n_segments=n,
        )

    def build_rectangular(
        self,
        fit_A: SurfaceFitResult,
        fit_B: SurfaceFitResult,
        side_x: float,
        side_y: float,
        volume: float,
        density: float = 9.0,
        tension: float = 480.0,
        constraint_A_id: int = 1,
        constraint_B_id: int = 2,
    ) -> InitialGeometry:
        """Build initial geometry for a rectangular pad solder joint.

        Both surfaces use CONSTRAINTs (no parametric boundary).
        Caller must place energy/content integrals on the constraints.

        Args:
            fit_A: Surface fit for bottom surface.
            fit_B: Surface fit for top surface.
            side_x: Pad width in local coordinates.
            side_y: Pad height in local coordinates.
            volume: Target solder volume.
            density: Solder density.
            tension: Surface tension.
            constraint_A_id: SE constraint ID for surface A.
            constraint_B_id: SE constraint ID for surface B.
        """
        n = self.n_segments
        hx = side_x / 2
        hy = side_y / 2

        # Rectangle corners (CCW from bottom-left in local coordinates)
        corners = [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]
        side_lengths = [side_x, side_y, side_x, side_y]
        perimeter = 2 * (side_x + side_y)

        # Distribute n vertices uniformly along perimeter
        perimeter_pts = []
        for k in range(n):
            d = k / n * perimeter
            cumul = 0.0
            for i, sl in enumerate(side_lengths):
                if d < cumul + sl + 1e-12:
                    t = (d - cumul) / sl
                    x0, y0 = corners[i]
                    x1, y1 = corners[(i + 1) % 4]
                    perimeter_pts.append((
                        x0 + t * (x1 - x0),
                        y0 + t * (y1 - y0),
                    ))
                    break
                cumul += sl

        vertices = []
        edges = []
        faces = []

        # --- Surface A (bottom) vertices ---
        for i, (px, py) in enumerate(perimeter_pts):
            pos = self._project_to_surface(fit_A, px, py)
            vertices.append(Vertex(
                id=i + 1,
                x=pos[0], y=pos[1], z=pos[2],
                constraints=[constraint_A_id],
                fixed=True,
            ))

        # --- Surface B (top) vertices ---
        for i, (px, py) in enumerate(perimeter_pts):
            pos = self._project_to_surface(fit_B, px, py)
            vertices.append(Vertex(
                id=n + i + 1,
                x=pos[0], y=pos[1], z=pos[2],
                constraints=[constraint_B_id],
                fixed=True,
            ))

        # --- Bottom rim edges (fixed, on constraint A) ---
        edge_id = 1
        for i in range(n):
            j = (i + 1) % n
            edges.append(Edge(
                id=edge_id,
                v1=i + 1,
                v2=j + 1,
                constraints=[constraint_A_id],
                fixed=True,
            ))
            edge_id += 1

        # --- Top rim edges (fixed, on constraint B) ---
        for i in range(n):
            j = (i + 1) % n
            edges.append(Edge(
                id=edge_id,
                v1=n + i + 1,
                v2=n + j + 1,
                constraints=[constraint_B_id],
                fixed=True,
            ))
            edge_id += 1

        # --- Vertical (lateral) edges (free) ---
        vert_edge_start = edge_id
        for i in range(n):
            edges.append(Edge(
                id=edge_id,
                v1=i + 1,
                v2=n + i + 1,
            ))
            edge_id += 1

        # --- Lateral faces (free surface with tension) ---
        face_id = 1
        for i in range(n):
            j = (i + 1) % n
            bottom_e = i + 1
            top_e = n + i + 1
            vert_i = vert_edge_start + i
            vert_j = vert_edge_start + j

            faces.append(Face(
                id=face_id,
                edges=[bottom_e, vert_j, -(top_e), -(vert_i)],
                tension=tension,
            ))
            face_id += 1

        # --- Body ---
        face_ids = list(range(1, face_id))
        bodies = [Body(
            id=1,
            faces=face_ids,
            volume=f"{volume}",
            density=density,
        )]

        return InitialGeometry(
            vertices=vertices,
            edges=edges,
            faces=faces,
            bodies=bodies,
            n_segments=n,
        )

    def _project_to_surface(
        self, fit: SurfaceFitResult, u: float, v: float
    ) -> np.ndarray:
        """Project a point (u, v) in local tangent coordinates onto the fitted surface."""
        # Evaluate surface height at (u, v)
        w = float(fit.eval_local(np.array([u]), np.array([v]))[0])

        # Convert to global coordinates
        local_point = np.array([u, v, w])
        global_point = fit.center_global + local_point @ fit.local_axes

        return global_point
