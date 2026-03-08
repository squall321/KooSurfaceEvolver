"""Fit analytical surfaces to local STL patches for SE constraint generation."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np
from scipy.optimize import least_squares

from .stl_reader import LocalPatch


class FitType(Enum):
    PLANE = "plane"
    QUADRATIC = "quadratic"
    QUARTIC = "quartic"


@dataclass
class SurfaceFitResult:
    """Result of fitting an analytical surface to a patch."""

    fit_type: FitType
    coefficients: np.ndarray    # polynomial coefficients
    residual_rms: float         # RMS fitting error
    residual_max: float         # max fitting error
    center_global: np.ndarray   # (3,) center in global coordinates
    normal_global: np.ndarray   # (3,) surface normal at center (global)
    local_axes: np.ndarray      # (3, 3) local frame [u, v, n]
    radius: float               # patch radius

    @property
    def is_planar(self) -> bool:
        return self.fit_type == FitType.PLANE

    def eval_local(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        """Evaluate z = f(u, v) in local coordinates."""
        c = self.coefficients
        if self.fit_type == FitType.PLANE:
            # z = c0 + c1*u + c2*v
            return c[0] + c[1] * u + c[2] * v
        elif self.fit_type == FitType.QUADRATIC:
            # z = c0 + c1*u + c2*v + c3*u^2 + c4*uv + c5*v^2
            return (c[0] + c[1] * u + c[2] * v
                    + c[3] * u**2 + c[4] * u * v + c[5] * v**2)
        else:  # QUARTIC
            # z = c0..c5 (quad) + c6*u^3 + c7*u^2v + c8*uv^2 + c9*v^3
            #   + c10*u^4 + c11*u^3v + c12*u^2v^2 + c13*uv^3 + c14*v^4
            q = (c[0] + c[1] * u + c[2] * v
                 + c[3] * u**2 + c[4] * u * v + c[5] * v**2)
            cubic = (c[6] * u**3 + c[7] * u**2 * v
                     + c[8] * u * v**2 + c[9] * v**3)
            quartic = (c[10] * u**4 + c[11] * u**3 * v
                       + c[12] * u**2 * v**2 + c[13] * u * v**3
                       + c[14] * v**4)
            return q + cubic + quartic

    def eval_global(self, points: np.ndarray) -> np.ndarray:
        """Evaluate the implicit surface value F(x,y,z) at global points.

        Returns values where F=0 means on-surface, F>0 means above, F<0 below.
        """
        rel = points - self.center_global
        local = rel @ self.local_axes.T
        u, v, w = local[:, 0], local[:, 1], local[:, 2]
        return w - self.eval_local(u, v)


class SurfaceFitter:
    """Fit analytical surfaces to STL patches."""

    def __init__(
        self,
        plane_tol: float = 1e-4,
        quad_tol: float = 1e-3,
    ):
        self.plane_tol = plane_tol
        self.quad_tol = quad_tol

    def fit(self, patch: LocalPatch) -> SurfaceFitResult:
        """Auto-fit the best surface to a patch.

        Strategy: try plane first, then quadratic, then quartic.
        """
        lc = patch.local_coords
        u, v, w = lc[:, 0], lc[:, 1], lc[:, 2]

        # Normalize to patch radius for numerical stability
        scale = patch.radius if patch.radius > 1e-12 else 1.0
        us, vs = u / scale, v / scale

        # Try plane fit
        result = self._fit_plane(us, vs, w, scale)
        if result.residual_rms < self.plane_tol * scale:
            return self._finalize(result, patch, scale)

        # Try quadratic fit
        result = self._fit_quadratic(us, vs, w, scale)
        if result.residual_rms < self.quad_tol * scale:
            return self._finalize(result, patch, scale)

        # Quartic fit
        result = self._fit_quartic(us, vs, w, scale)
        return self._finalize(result, patch, scale)

    def fit_plane(self, patch: LocalPatch) -> SurfaceFitResult:
        lc = patch.local_coords
        scale = patch.radius if patch.radius > 1e-12 else 1.0
        r = self._fit_plane(lc[:, 0] / scale, lc[:, 1] / scale, lc[:, 2], scale)
        return self._finalize(r, patch, scale)

    def fit_quadratic(self, patch: LocalPatch) -> SurfaceFitResult:
        lc = patch.local_coords
        scale = patch.radius if patch.radius > 1e-12 else 1.0
        r = self._fit_quadratic(lc[:, 0] / scale, lc[:, 1] / scale, lc[:, 2], scale)
        return self._finalize(r, patch, scale)

    def _fit_plane(self, us, vs, w, scale) -> SurfaceFitResult:
        """Fit z = c0 + c1*u + c2*v."""
        A = np.column_stack([np.ones_like(us), us, vs])
        coeffs, res, _, _ = np.linalg.lstsq(A, w, rcond=None)
        pred = A @ coeffs
        residuals = w - pred
        return SurfaceFitResult(
            fit_type=FitType.PLANE,
            coefficients=coeffs,
            residual_rms=float(np.sqrt(np.mean(residuals**2))),
            residual_max=float(np.max(np.abs(residuals))),
            center_global=np.zeros(3),  # filled in _finalize
            normal_global=np.zeros(3),
            local_axes=np.eye(3),
            radius=scale,
        )

    def _fit_quadratic(self, us, vs, w, scale) -> SurfaceFitResult:
        """Fit z = c0 + c1*u + c2*v + c3*u^2 + c4*uv + c5*v^2."""
        A = np.column_stack([
            np.ones_like(us), us, vs, us**2, us * vs, vs**2
        ])
        coeffs, res, _, _ = np.linalg.lstsq(A, w, rcond=None)
        pred = A @ coeffs
        residuals = w - pred
        return SurfaceFitResult(
            fit_type=FitType.QUADRATIC,
            coefficients=coeffs,
            residual_rms=float(np.sqrt(np.mean(residuals**2))),
            residual_max=float(np.max(np.abs(residuals))),
            center_global=np.zeros(3),
            normal_global=np.zeros(3),
            local_axes=np.eye(3),
            radius=scale,
        )

    def _fit_quartic(self, us, vs, w, scale) -> SurfaceFitResult:
        """Fit z = ... up to 4th order polynomial."""
        A = np.column_stack([
            np.ones_like(us), us, vs,
            us**2, us * vs, vs**2,
            us**3, us**2 * vs, us * vs**2, vs**3,
            us**4, us**3 * vs, us**2 * vs**2, us * vs**3, vs**4,
        ])
        coeffs, res, _, _ = np.linalg.lstsq(A, w, rcond=None)
        pred = A @ coeffs
        residuals = w - pred
        return SurfaceFitResult(
            fit_type=FitType.QUARTIC,
            coefficients=coeffs,
            residual_rms=float(np.sqrt(np.mean(residuals**2))),
            residual_max=float(np.max(np.abs(residuals))),
            center_global=np.zeros(3),
            normal_global=np.zeros(3),
            local_axes=np.eye(3),
            radius=scale,
        )

    def _finalize(
        self, result: SurfaceFitResult, patch: LocalPatch, scale: float
    ) -> SurfaceFitResult:
        """Rescale coefficients and attach patch metadata."""
        coeffs = result.coefficients.copy()

        # Undo the u/scale, v/scale normalization:
        # Original: z = f(u/s, v/s). We need z = g(u, v).
        if result.fit_type == FitType.PLANE:
            # c0 stays, c1 /= s, c2 /= s
            coeffs[1] /= scale
            coeffs[2] /= scale
        elif result.fit_type == FitType.QUADRATIC:
            coeffs[1] /= scale
            coeffs[2] /= scale
            coeffs[3] /= scale**2
            coeffs[4] /= scale**2
            coeffs[5] /= scale**2
        elif result.fit_type == FitType.QUARTIC:
            for i in range(1, 3):
                coeffs[i] /= scale
            for i in range(3, 6):
                coeffs[i] /= scale**2
            for i in range(6, 10):
                coeffs[i] /= scale**3
            for i in range(10, 15):
                coeffs[i] /= scale**4

        result.coefficients = coeffs
        result.center_global = patch.center.copy()
        result.normal_global = patch.avg_normal.copy()
        result.local_axes = patch.local_axes.copy()
        result.radius = patch.radius
        return result
