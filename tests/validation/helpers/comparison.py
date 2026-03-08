"""Comparison utilities for A/B validation of KSE vs original results."""

from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.spatial import cKDTree
import trimesh

from kse.mesh.quality import assess_quality, QualityReport


@dataclass
class ComparisonResult:
    """Result of comparing KSE output to reference."""

    # Energy (SE total_energy)
    energy_ref: float
    energy_kse: float
    energy_rel_error: float
    energy_pass: bool

    # Volume
    volume_ref: float
    volume_kse: float
    volume_rel_error: float
    volume_pass: bool

    # Shape (using free faces only)
    hausdorff_distance: float
    hausdorff_normalized: float  # hausdorff / characteristic_length
    shape_pass: bool

    # Mesh quality
    quality_kse: Optional[QualityReport]
    quality_pass: bool

    # Overall
    tier: int
    pass_all: bool

    def summary(self) -> str:
        lines = [
            f"  Energy: ref={self.energy_ref:.6e}, kse={self.energy_kse:.6e}, "
            f"err={self.energy_rel_error:.4%} {'PASS' if self.energy_pass else 'FAIL'}",
            f"  Volume: ref={self.volume_ref:.6e}, kse={self.volume_kse:.6e}, "
            f"err={self.volume_rel_error:.4%} {'PASS' if self.volume_pass else 'FAIL'}",
            f"  Shape:  hausdorff={self.hausdorff_distance:.6e}, "
            f"norm={self.hausdorff_normalized:.6f} {'PASS' if self.shape_pass else 'FAIL'}",
            f"  Quality: {'PASS' if self.quality_pass else 'FAIL'}",
            f"  Overall: {'PASS' if self.pass_all else 'FAIL'} (Tier {self.tier})",
        ]
        return "\n".join(lines)


# Acceptance thresholds per tier
THRESHOLDS = {
    1: {"energy_rel": 0.05, "volume_rel": 0.02, "hausdorff_norm": 0.10},
    2: {"energy_rel": 0.10, "volume_rel": 0.05, "hausdorff_norm": 0.15},
    3: {"energy_rel": 0.15, "volume_rel": 0.10, "hausdorff_norm": 0.20},
}


def compare_results(
    ref_data: dict,
    kse_data: dict,
    tier: int,
    characteristic_length: float = 0.1,
) -> ComparisonResult:
    """Compare KSE results against reference data.

    Args:
        ref_data: dict with keys: energy, volume, vertex_positions,
                  free_face_triangles (preferred) or face_triangles
        kse_data: dict with same keys
        tier: 1, 2, or 3 (determines thresholds)
        characteristic_length: normalizing length for Hausdorff (usually radius)
    """
    thresholds = THRESHOLDS[tier]

    # Energy comparison (use SE total_energy directly)
    e_ref = ref_data.get("energy", 0) or 0
    e_kse = kse_data.get("energy", 0) or 0
    if abs(e_ref) > 1e-20:
        e_err = abs(e_kse - e_ref) / abs(e_ref)
    else:
        e_err = abs(e_kse - e_ref)
    e_pass = e_err <= thresholds["energy_rel"]

    # Volume comparison
    v_ref = ref_data.get("volume", 0) or 0
    v_kse = kse_data.get("volume", 0) or 0
    if abs(v_ref) > 1e-20:
        v_err = abs(v_kse - v_ref) / abs(v_ref)
    else:
        v_err = abs(v_kse - v_ref)
    v_pass = v_err <= thresholds["volume_rel"]

    # Shape comparison (Hausdorff distance) — use FREE faces only
    haus = 0.0
    haus_norm = 0.0
    s_pass = True

    verts_ref = ref_data.get("vertex_positions")
    verts_kse = kse_data.get("vertex_positions")
    # Prefer free_face_triangles over face_triangles
    tris_ref = ref_data.get("free_face_triangles", ref_data.get("face_triangles"))
    tris_kse = kse_data.get("free_face_triangles", kse_data.get("face_triangles"))

    if (verts_ref is not None and tris_ref is not None and
            verts_kse is not None and tris_kse is not None):
        verts_ref = np.asarray(verts_ref, dtype=float)
        tris_ref = np.asarray(tris_ref, dtype=int)
        verts_kse = np.asarray(verts_kse, dtype=float)
        tris_kse = np.asarray(tris_kse, dtype=int)

        if len(tris_ref) > 0 and len(tris_kse) > 0:
            haus = compute_hausdorff(verts_ref, tris_ref, verts_kse, tris_kse)
            haus_norm = haus / characteristic_length if characteristic_length > 0 else haus
            s_pass = haus_norm <= thresholds["hausdorff_norm"]

    # Mesh quality (using all KSE faces)
    quality = None
    q_pass = True
    all_tris_kse = kse_data.get("face_triangles")
    if verts_kse is not None and all_tris_kse is not None:
        all_tris_kse = np.asarray(all_tris_kse, dtype=int)
        verts_kse_arr = np.asarray(verts_kse, dtype=float)
        if len(all_tris_kse) > 0:
            quality = assess_quality(verts_kse_arr, all_tris_kse)
            q_pass = quality.fem_suitable

    pass_all = e_pass and v_pass and s_pass and q_pass

    return ComparisonResult(
        energy_ref=e_ref,
        energy_kse=e_kse,
        energy_rel_error=e_err,
        energy_pass=e_pass,
        volume_ref=v_ref,
        volume_kse=v_kse,
        volume_rel_error=v_err,
        volume_pass=v_pass,
        hausdorff_distance=haus,
        hausdorff_normalized=haus_norm,
        shape_pass=s_pass,
        quality_kse=quality,
        quality_pass=q_pass,
        tier=tier,
        pass_all=pass_all,
    )


def compute_hausdorff(
    verts_a: np.ndarray,
    tris_a: np.ndarray,
    verts_b: np.ndarray,
    tris_b: np.ndarray,
    n_samples: int = 5000,
) -> float:
    """Compute symmetric Hausdorff distance between two triangle meshes.

    Samples points uniformly on each mesh surface, then finds the
    maximum nearest-neighbor distance.
    """
    mesh_a = trimesh.Trimesh(vertices=verts_a, faces=tris_a)
    mesh_b = trimesh.Trimesh(vertices=verts_b, faces=tris_b)

    # Sample points on each surface
    try:
        pts_a = mesh_a.sample(n_samples)
        pts_b = mesh_b.sample(n_samples)
    except Exception:
        # Fallback: use vertex positions directly
        pts_a = verts_a
        pts_b = verts_b

    # A -> B
    tree_b = cKDTree(pts_b)
    dists_a2b, _ = tree_b.query(pts_a)
    max_a2b = np.max(dists_a2b)

    # B -> A
    tree_a = cKDTree(pts_a)
    dists_b2a, _ = tree_a.query(pts_b)
    max_b2a = np.max(dists_b2a)

    return max(max_a2b, max_b2a)


def compute_physical_energy(
    vertex_positions: np.ndarray,
    face_triangles: np.ndarray,
    tension: float,
    density: float = 0.0,
    gravity: float = 0.0,
    body_volume: float = 0.0,
) -> float:
    """Compute formulation-independent physical energy from FREE faces only.

    E = tension * total_free_area + gravity * density * volume * z_centroid

    IMPORTANT: Caller should pass only free (non-fixed) face triangles.
    Fixed faces (pad faces with tension=0) must be excluded.
    """
    verts = np.asarray(vertex_positions, dtype=float)
    tris = np.asarray(face_triangles, dtype=int)

    if len(tris) == 0:
        return 0.0

    # Total surface area of free faces
    v0 = verts[tris[:, 0]]
    v1 = verts[tris[:, 1]]
    v2 = verts[tris[:, 2]]
    cross = np.cross(v1 - v0, v2 - v0)
    areas = 0.5 * np.linalg.norm(cross, axis=1)
    surface_energy = tension * np.sum(areas)

    # Gravitational potential energy
    grav_energy = 0.0
    if gravity > 0 and density > 0 and body_volume > 0:
        # Approximate z-centroid from triangle centroids
        centroids = (v0 + v1 + v2) / 3.0
        z_centroid = np.mean(centroids[:, 2])
        grav_energy = gravity * density * body_volume * z_centroid

    return surface_energy + grav_energy
