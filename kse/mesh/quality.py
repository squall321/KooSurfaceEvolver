"""Mesh quality assessment for FEM suitability."""

from dataclasses import dataclass

import numpy as np


@dataclass
class TetQualityReport:
    """Tetrahedral mesh quality metrics."""

    n_tetrahedra: int
    min_dihedral_deg: float     # minimum dihedral angle across all tets
    max_dihedral_deg: float
    mean_dihedral_deg: float
    aspect_ratio_mean: float    # circumradius / (3 * inradius) per tet
    aspect_ratio_max: float
    volume_ratio: float         # max_vol / min_vol (uniformity)
    n_inverted: int             # tets with negative volume
    n_degenerate: int           # tets with near-zero volume
    fem_suitable: bool

    def summary(self) -> str:
        status = "PASS" if self.fem_suitable else "FAIL"
        return (
            f"Tet Mesh Quality [{status}]\n"
            f"  Tetrahedra: {self.n_tetrahedra}\n"
            f"  Dihedral: min={self.min_dihedral_deg:.1f}°, "
            f"max={self.max_dihedral_deg:.1f}°, "
            f"mean={self.mean_dihedral_deg:.1f}°\n"
            f"  Aspect ratio: mean={self.aspect_ratio_mean:.2f}, "
            f"max={self.aspect_ratio_max:.2f}\n"
            f"  Volume ratio: {self.volume_ratio:.1f}\n"
            f"  Inverted: {self.n_inverted}, Degenerate: {self.n_degenerate}"
        )


def assess_tet_quality(
    vertices: np.ndarray,
    tetrahedra: np.ndarray,
    min_dihedral_limit: float = 5.0,
    max_aspect_limit: float = 10.0,
) -> TetQualityReport:
    """Assess tetrahedral mesh quality.

    Args:
        vertices:    (N, 3) vertex coordinates.
        tetrahedra:  (K, 4) tetrahedron indices (0-based).
        min_dihedral_limit: Minimum acceptable dihedral angle (degrees).
        max_aspect_limit:   Maximum acceptable aspect ratio.
    """
    if len(tetrahedra) == 0:
        return TetQualityReport(
            n_tetrahedra=0, min_dihedral_deg=0, max_dihedral_deg=0,
            mean_dihedral_deg=0, aspect_ratio_mean=0, aspect_ratio_max=0,
            volume_ratio=0, n_inverted=0, n_degenerate=0, fem_suitable=False,
        )

    v0 = vertices[tetrahedra[:, 0]]
    v1 = vertices[tetrahedra[:, 1]]
    v2 = vertices[tetrahedra[:, 2]]
    v3 = vertices[tetrahedra[:, 3]]

    # Signed volumes: (1/6) * det([v1-v0, v2-v0, v3-v0])
    a = v1 - v0
    b = v2 - v0
    c = v3 - v0
    signed_vols = (
        a[:, 0] * (b[:, 1] * c[:, 2] - b[:, 2] * c[:, 1])
        - a[:, 1] * (b[:, 0] * c[:, 2] - b[:, 2] * c[:, 0])
        + a[:, 2] * (b[:, 0] * c[:, 1] - b[:, 1] * c[:, 0])
    ) / 6.0

    vols = np.abs(signed_vols)
    n_inverted = int(np.sum(signed_vols < 0))
    n_degenerate = int(np.sum(vols < 1e-30))

    safe_vols = np.where(vols > 1e-30, vols, np.nan)
    vol_ratio = float(np.nanmax(safe_vols) / np.nanmin(safe_vols)) if np.any(vols > 1e-30) else 0.0

    # Dihedral angles: 6 per tet, one per edge
    # Faces of tet (v0,v1,v2,v3):
    #   f0=(1,2,3), f1=(0,2,3), f2=(0,1,3), f3=(0,1,2)
    face_idx = [(1, 2, 3), (0, 2, 3), (0, 1, 3), (0, 1, 2)]

    def face_normal(pts, fi):
        p = pts[:, fi, :]
        return np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])

    pts = np.stack([v0, v1, v2, v3], axis=1)  # (K, 4, 3)
    normals = [face_normal(pts, fi) for fi in face_idx]

    # Normalize
    def norm_vecs(n):
        mag = np.linalg.norm(n, axis=1, keepdims=True)
        return n / np.where(mag > 1e-20, mag, 1e-20)

    normals = [norm_vecs(n) for n in normals]

    # Edge-face pairs (edge shared by two faces):
    # edge(0,1): faces f2,f3; edge(0,2): faces f1,f3; edge(0,3): faces f1,f2
    # edge(1,2): faces f0,f3; edge(1,3): faces f0,f2; edge(2,3): faces f0,f1
    edge_face_pairs = [(2, 3), (1, 3), (1, 2), (0, 3), (0, 2), (0, 1)]

    all_dihedrals = []
    for fi, fj in edge_face_pairs:
        cos_a = np.sum(normals[fi] * normals[fj], axis=1)
        cos_a = np.clip(cos_a, -1.0, 1.0)
        # Dihedral angle = π - angle between outward normals
        dihedral = np.degrees(np.pi - np.arccos(cos_a))
        all_dihedrals.append(dihedral)

    all_dihedrals = np.concatenate(all_dihedrals)

    # Aspect ratio: circumradius / (3 * inradius) per tet
    # circumradius R = abc/(8V) (simplified for tet)
    # Use edge-length based estimate: R / r where r = 3V / A_surface
    edge_lengths = np.array([
        np.linalg.norm(v1 - v0, axis=1),
        np.linalg.norm(v2 - v0, axis=1),
        np.linalg.norm(v3 - v0, axis=1),
        np.linalg.norm(v2 - v1, axis=1),
        np.linalg.norm(v3 - v1, axis=1),
        np.linalg.norm(v3 - v2, axis=1),
    ])  # (6, K)
    max_edge = edge_lengths.max(axis=0)
    min_edge = np.where(edge_lengths.min(axis=0) > 1e-20, edge_lengths.min(axis=0), 1e-20)
    aspect_ratios = max_edge / min_edge

    fem_suitable = (
        float(np.min(all_dihedrals)) >= min_dihedral_limit
        and float(np.max(aspect_ratios)) <= max_aspect_limit
        and n_inverted == 0
        and n_degenerate == 0
    )

    return TetQualityReport(
        n_tetrahedra=len(tetrahedra),
        min_dihedral_deg=float(np.min(all_dihedrals)),
        max_dihedral_deg=float(np.max(all_dihedrals)),
        mean_dihedral_deg=float(np.mean(all_dihedrals)),
        aspect_ratio_mean=float(np.mean(aspect_ratios)),
        aspect_ratio_max=float(np.max(aspect_ratios)),
        volume_ratio=vol_ratio,
        n_inverted=n_inverted,
        n_degenerate=n_degenerate,
        fem_suitable=fem_suitable,
    )


@dataclass
class QualityReport:
    """Mesh quality metrics."""

    n_triangles: int
    aspect_ratio_mean: float
    aspect_ratio_max: float
    aspect_ratio_min: float
    min_angle_deg: float
    max_angle_deg: float
    skewness_mean: float
    skewness_max: float
    n_degenerate: int               # triangles with near-zero area
    fem_suitable: bool              # passes all quality thresholds

    def summary(self) -> str:
        status = "PASS" if self.fem_suitable else "FAIL"
        return (
            f"Mesh Quality [{status}]\n"
            f"  Triangles: {self.n_triangles}\n"
            f"  Aspect ratio: mean={self.aspect_ratio_mean:.2f}, "
            f"max={self.aspect_ratio_max:.2f}\n"
            f"  Angles: min={self.min_angle_deg:.1f}°, "
            f"max={self.max_angle_deg:.1f}°\n"
            f"  Skewness: mean={self.skewness_mean:.3f}, "
            f"max={self.skewness_max:.3f}\n"
            f"  Degenerate faces: {self.n_degenerate}"
        )


def assess_quality(
    vertices: np.ndarray,
    triangles: np.ndarray,
    aspect_ratio_limit: float = 3.0,
    min_angle_limit: float = 20.0,
    max_angle_limit: float = 120.0,
    skewness_limit: float = 0.7,
) -> QualityReport:
    """Assess mesh quality for FEM suitability.

    Args:
        vertices: (N, 3) vertex coordinates.
        triangles: (M, 3) triangle vertex indices.
        aspect_ratio_limit: Maximum acceptable aspect ratio.
        min_angle_limit: Minimum acceptable angle (degrees).
        max_angle_limit: Maximum acceptable angle (degrees).
        skewness_limit: Maximum acceptable skewness.
    """
    if len(triangles) == 0:
        return QualityReport(
            n_triangles=0, aspect_ratio_mean=0, aspect_ratio_max=0,
            aspect_ratio_min=0, min_angle_deg=0, max_angle_deg=0,
            skewness_mean=0, skewness_max=0, n_degenerate=0,
            fem_suitable=False,
        )

    v0 = vertices[triangles[:, 0]]
    v1 = vertices[triangles[:, 1]]
    v2 = vertices[triangles[:, 2]]

    # Edge vectors and lengths
    e0 = v1 - v0
    e1 = v2 - v1
    e2 = v0 - v2
    l0 = np.linalg.norm(e0, axis=1)
    l1 = np.linalg.norm(e1, axis=1)
    l2 = np.linalg.norm(e2, axis=1)

    # Areas
    cross = np.cross(e0, -e2)
    areas = 0.5 * np.linalg.norm(cross, axis=1)
    degenerate = areas < 1e-20

    # Aspect ratio: longest edge / (2 * inradius)
    # inradius = area / semi-perimeter
    semi_p = (l0 + l1 + l2) / 2.0
    safe_area = np.where(areas > 1e-20, areas, 1e-20)
    inradius = safe_area / np.where(semi_p > 1e-20, semi_p, 1e-20)
    longest = np.maximum(np.maximum(l0, l1), l2)
    safe_inradius = np.where(inradius > 1e-20, inradius, 1e-20)
    aspect_ratios = longest / (2.0 * safe_inradius)

    # Angles (degrees)
    def _angle(a, b):
        dot = np.sum(a * b, axis=1)
        na = np.linalg.norm(a, axis=1)
        nb = np.linalg.norm(b, axis=1)
        cos_val = dot / np.where(na * nb > 1e-20, na * nb, 1e-20)
        cos_val = np.clip(cos_val, -1.0, 1.0)
        return np.degrees(np.arccos(cos_val))

    a0 = _angle(e0, -e2)   # angle at v0
    a1 = _angle(-e0, e1)   # angle at v1
    a2 = _angle(-e1, e2)   # angle at v2

    all_angles = np.concatenate([a0, a1, a2])

    # Skewness: 1 - (min_angle / 60) for equilateral reference
    min_angles = np.minimum(np.minimum(a0, a1), a2)
    skewness = np.where(min_angles > 0, 1.0 - min_angles / 60.0, 1.0)
    skewness = np.clip(skewness, 0.0, 1.0)

    # Quality check
    ar_ok = np.max(aspect_ratios[~degenerate]) <= aspect_ratio_limit if (~degenerate).any() else True
    angle_ok = np.min(all_angles) >= min_angle_limit and np.max(all_angles) <= max_angle_limit
    skew_ok = np.max(skewness[~degenerate]) <= skewness_limit if (~degenerate).any() else True
    no_degen = np.sum(degenerate) == 0

    fem_suitable = ar_ok and angle_ok and skew_ok and no_degen

    return QualityReport(
        n_triangles=len(triangles),
        aspect_ratio_mean=float(np.mean(aspect_ratios[~degenerate])) if (~degenerate).any() else 0,
        aspect_ratio_max=float(np.max(aspect_ratios[~degenerate])) if (~degenerate).any() else 0,
        aspect_ratio_min=float(np.min(aspect_ratios[~degenerate])) if (~degenerate).any() else 0,
        min_angle_deg=float(np.min(all_angles)),
        max_angle_deg=float(np.max(all_angles)),
        skewness_mean=float(np.mean(skewness[~degenerate])) if (~degenerate).any() else 0,
        skewness_max=float(np.max(skewness[~degenerate])) if (~degenerate).any() else 0,
        n_degenerate=int(np.sum(degenerate)),
        fem_suitable=fem_suitable,
    )
