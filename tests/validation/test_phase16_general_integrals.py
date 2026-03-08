"""Phase 16: Fully general content/energy integral correctness tests.

Tests that _derive_content_integrals() and generate_wall_constraint()
produce numerically correct volume integrals for:
  - quadratic (parabolic) curved pad
  - quadratic saddle-shaped pad
  - y-curvature-only pad (should need no correction)
  - diagonal (45°) wall
  - arbitrary-angle (30°) wall
  - axis-aligned walls (regression from Phase 15)
"""

import math
import numpy as np
import pytest
import sympy as sp

from kse.core.surface_fitter import SurfaceFitResult, FitType
from kse.core.constraint_gen import ConstraintGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_quadratic_fit(normal, center, quad_coeffs):
    """Create a SurfaceFitResult for a quadratic surface.

    quad_coeffs = (c0, c1, c2, c3, c4, c5) for
    z_local = c0 + c1*u + c2*v + c3*u^2 + c4*u*v + c5*v^2
    """
    normal = np.asarray(normal, dtype=float)
    center = np.asarray(center, dtype=float)
    normal = normal / np.linalg.norm(normal)

    if abs(normal[2]) < 0.99:
        u = np.cross(normal, [0, 0, 1])
    else:
        u = np.array([1.0, 0.0, 0.0])
    u = u / np.linalg.norm(u)
    v = np.cross(normal, u)
    axes = np.stack([u, v, normal])

    return SurfaceFitResult(
        fit_type=FitType.QUADRATIC,
        coefficients=np.array(quad_coeffs, dtype=float),
        residual_rms=0.0,
        residual_max=0.0,
        center_global=center,
        normal_global=normal,
        local_axes=axes,
        radius=0.1,
    )


def _make_plane_fit(normal, center):
    """Create a SurfaceFitResult for a flat plane."""
    normal = np.asarray(normal, dtype=float)
    center = np.asarray(center, dtype=float)
    normal = normal / np.linalg.norm(normal)

    if abs(normal[2]) < 0.99:
        u = np.cross(normal, [0, 0, 1])
    else:
        u = np.array([1.0, 0.0, 0.0])
    u = u / np.linalg.norm(u)
    v = np.cross(normal, u)
    axes = np.stack([u, v, normal])

    return SurfaceFitResult(
        fit_type=FitType.PLANE,
        coefficients=np.zeros(3),
        residual_rms=0.0,
        residual_max=0.0,
        center_global=center,
        normal_global=normal,
        local_axes=axes,
        radius=0.1,
    )


def _line_integral_c2_circle(c2_str, cx, cy, cz, R,
                              z_func=None):
    """Numerically integrate ∮ c2(x,y,z) dy along a circular loop.

    Loop: x = cx + R*cos(t), y = cy + R*sin(t)
    z is determined by z_func(x,y) if provided, else z = cz (flat).
    dy = R*cos(t) dt  (counterclockwise).
    """
    x_s, y_s, z_s = sp.symbols("x y z")
    c2_expr = sp.sympify(c2_str)
    t = sp.Symbol("t")

    x_t = sp.Float(cx) + sp.Float(R) * sp.cos(t)
    y_t = sp.Float(cy) + sp.Float(R) * sp.sin(t)

    if z_func is not None:
        z_t = z_func(x_t, y_t)
    else:
        z_t = sp.Float(cz)

    dy_t = sp.Float(R) * sp.cos(t)

    integrand = c2_expr.subs({x_s: x_t, y_s: y_t, z_s: z_t}) * dy_t
    result = sp.integrate(sp.expand(integrand), (t, 0, 2 * sp.pi))
    return float(result.evalf())


def _general_line_integral_circle(c1_str, c2_str, c3_str,
                                   cx, cy, cz, R, z_func=None):
    """Compute ∮(c1 dx + c2 dy + c3 dz) along a circular loop in xy-plane.

    Loop: x = cx + R*cos(t), y = cy + R*sin(t), z from z_func or cz.
    """
    x_s, y_s, z_s = sp.symbols("x y z")
    c1_expr = sp.sympify(c1_str)
    c2_expr = sp.sympify(c2_str)
    c3_expr = sp.sympify(c3_str)
    t = sp.Symbol("t")

    x_t = sp.Float(cx) + sp.Float(R) * sp.cos(t)
    y_t = sp.Float(cy) + sp.Float(R) * sp.sin(t)
    if z_func is not None:
        z_t = z_func(x_t, y_t)
    else:
        z_t = sp.Float(cz)

    dx_t = -sp.Float(R) * sp.sin(t)
    dy_t = sp.Float(R) * sp.cos(t)
    if z_func is not None:
        dz_t = sp.diff(z_t, t)
    else:
        dz_t = sp.S.Zero

    subs = {x_s: x_t, y_s: y_t, z_s: z_t}
    integrand = (c1_expr.subs(subs) * dx_t
                 + c2_expr.subs(subs) * dy_t
                 + c3_expr.subs(subs) * dz_t)
    result = sp.integrate(sp.expand(integrand), (t, 0, 2 * sp.pi))
    return float(result.evalf())


def _wall_line_integral(c1_str, c2_str, c3_str,
                        nx, ny, xc, yc, zc, R):
    """Compute ∮(c1 dx + c2 dy + c3 dz) on a wall loop with ẑ × n̂ winding.

    Wall normal = (nx, ny, 0). Loop uses t2 = ẑ × n̂ = (-ny, nx, 0):
      x(t) = xc - ny*R*cos(t)
      y(t) = yc + nx*R*cos(t)
      z(t) = zc + R*sin(t)
    """
    x_s, y_s, z_s = sp.symbols("x y z")
    c1_expr = sp.sympify(c1_str)
    c2_expr = sp.sympify(c2_str)
    c3_expr = sp.sympify(c3_str)
    t = sp.Symbol("t")
    R_s = sp.Float(R)

    x_t = sp.Float(xc) - sp.Float(ny) * R_s * sp.cos(t)
    y_t = sp.Float(yc) + sp.Float(nx) * R_s * sp.cos(t)
    z_t = sp.Float(zc) + R_s * sp.sin(t)
    dx_t = sp.Float(ny) * R_s * sp.sin(t)
    dy_t = -sp.Float(nx) * R_s * sp.sin(t)
    dz_t = R_s * sp.cos(t)

    subs = {x_s: x_t, y_s: y_t, z_s: z_t}
    integrand = (c1_expr.subs(subs) * dx_t
                 + c2_expr.subs(subs) * dy_t
                 + c3_expr.subs(subs) * dz_t)
    result = sp.integrate(sp.expand(integrand), (t, 0, 2 * sp.pi))
    return float(result.evalf())


# ===========================================================================
# Tests: Curved pad content integrals
# ===========================================================================

class TestQuadraticPadContentIntegral:
    """Quadratic pads: verify content integral gives correct cap volume."""

    def test_parabolic_x_curvature(self):
        """z = z0 + c3*(x-cx)^2: x-direction curvature."""
        cx, cy, cz = 0.2, 0.1, 0.15
        c3 = 50.0  # strong curvature for measurable effect
        # Axes aligned: normal = (0,0,1)
        fit = _make_quadratic_fit([0, 0, 1], [cx, cy, cz],
                                   [0, 0, 0, c3, 0, 0])
        cgen = ConstraintGenerator()
        c1, c2, c3_str = cgen._derive_content_integrals(fit)

        R = 0.03
        # z_surface(x,y) = cz + c3*(x-cx)^2
        def z_func(x_t, y_t):
            return sp.Float(cz) + sp.Float(c3) * (x_t - sp.Float(cx))**2

        integral = _general_line_integral_circle(
            c1, c2, c3_str, cx, cy, cz, R, z_func=z_func
        )
        # Expected: ∫∫ z_s dA = cz*pi*R^2 + c3*pi*R^4/4
        expected = cz * math.pi * R**2 + c3 * math.pi * R**4 / 4
        rel_err = abs(integral - expected) / expected
        assert rel_err < 1e-5, \
            f"parabolic: c2={c2}, got {integral:.10f}, expected {expected:.10f} (err={rel_err:.2e})"

    def test_saddle_surface(self):
        """z = z0 + c4*(x-cx)*(y-cy): saddle shape."""
        cx, cy, cz = 0.2, 0.1, 0.15
        c4 = 100.0
        fit = _make_quadratic_fit([0, 0, 1], [cx, cy, cz],
                                   [0, 0, 0, 0, c4, 0])
        cgen = ConstraintGenerator()
        c1, c2, c3_str = cgen._derive_content_integrals(fit)

        R = 0.03

        def z_func(x_t, y_t):
            return (sp.Float(cz) + sp.Float(c4)
                    * (x_t - sp.Float(cx)) * (y_t - sp.Float(cy)))

        integral = _general_line_integral_circle(
            c1, c2, c3_str, cx, cy, cz, R, z_func=z_func
        )
        # c4 cross term integrates to zero over symmetric circle
        expected = cz * math.pi * R**2
        rel_err = abs(integral - expected) / expected
        assert rel_err < 1e-5, \
            f"saddle: got {integral:.10f}, expected {expected:.10f} (err={rel_err:.2e})"

    def test_y_curvature_only(self):
        """z = z0 + c5*(y-cy)^2: only y-curvature (should be exact)."""
        cx, cy, cz = 0.2, 0.1, 0.15
        c5 = 50.0
        fit = _make_quadratic_fit([0, 0, 1], [cx, cy, cz],
                                   [0, 0, 0, 0, 0, c5])
        cgen = ConstraintGenerator()
        c1, c2, c3_str = cgen._derive_content_integrals(fit)

        R = 0.03

        def z_func(x_t, y_t):
            return sp.Float(cz) + sp.Float(c5) * (y_t - sp.Float(cy))**2

        integral = _general_line_integral_circle(
            c1, c2, c3_str, cx, cy, cz, R, z_func=z_func
        )
        expected = cz * math.pi * R**2 + c5 * math.pi * R**4 / 4
        rel_err = abs(integral - expected) / expected
        assert rel_err < 1e-5, \
            f"y-curvature: got {integral:.10f}, expected {expected:.10f} (err={rel_err:.2e})"

    def test_mixed_quadratic(self):
        """z = z0 + c1*(x-cx) + c3*(x-cx)^2 + c5*(y-cy)^2: tilt + curvature."""
        cx, cy, cz = 0.2, 0.1, 0.15
        c1_coeff = 0.1  # slope
        c3 = 30.0
        c5 = 20.0
        fit = _make_quadratic_fit([0, 0, 1], [cx, cy, cz],
                                   [0, c1_coeff, 0, c3, 0, c5])
        cgen = ConstraintGenerator()
        c1_s, c2_s, c3_s = cgen._derive_content_integrals(fit)

        R = 0.03

        def z_func(x_t, y_t):
            X = x_t - sp.Float(cx)
            Y = y_t - sp.Float(cy)
            return (sp.Float(cz) + sp.Float(c1_coeff) * X
                    + sp.Float(c3) * X**2 + sp.Float(c5) * Y**2)

        integral = _general_line_integral_circle(
            c1_s, c2_s, c3_s, cx, cy, cz, R, z_func=z_func
        )
        expected = cz * math.pi * R**2 + (c3 + c5) * math.pi * R**4 / 4
        rel_err = abs(integral - expected) / expected
        assert rel_err < 1e-5, \
            f"mixed: got {integral:.10f}, expected {expected:.10f} (err={rel_err:.2e})"


# ===========================================================================
# Tests: Horizontal/tilted plane content integrals (regression)
# ===========================================================================

class TestPlaneContentIntegralRegression:
    """Regression: plane content integrals should still work after generalization."""

    def test_horizontal_pad(self):
        """Horizontal pad: content integral gives z0*pi*R^2."""
        center = [0.2, 0.1, 0.15]
        fit = _make_plane_fit([0, 0, 1], center)
        cgen = ConstraintGenerator()
        _, c2, _ = cgen._derive_content_integrals(fit)

        R = 0.04
        integral = _line_integral_c2_circle(c2, center[0], center[1], center[2], R)
        expected = center[2] * math.pi * R**2
        assert abs(integral - expected) / expected < 1e-6

    @pytest.mark.parametrize("tilt_deg", [10, 20, 30, 45])
    def test_tilted_plane(self, tilt_deg):
        """Tilted plane: content integral still gives z0*pi*R^2."""
        theta = math.radians(tilt_deg)
        normal = [math.sin(theta), 0.0, math.cos(theta)]
        center = [0.2, 0.0, 0.1]
        fit = _make_plane_fit(normal, center)

        cgen = ConstraintGenerator()
        c1_s, c2_s, c3_s = cgen._derive_content_integrals(fit)

        R = 0.03
        tilt_a = -normal[0] / normal[2]

        def z_func(x_t, y_t):
            return sp.Float(center[2]) + sp.Float(tilt_a) * (x_t - sp.Float(center[0]))

        integral = _general_line_integral_circle(
            c1_s, c2_s, c3_s, center[0], center[1], center[2], R,
            z_func=z_func,
        )
        expected = center[2] * math.pi * R**2
        rel_err = abs(integral - expected) / expected
        assert rel_err < 1e-5, \
            f"tilt={tilt_deg}°: got {integral:.8f}, expected {expected:.8f} (err={rel_err:.2e})"


# ===========================================================================
# Tests: General wall content integrals
# ===========================================================================

class TestWallContentIntegralGeneral:
    """Test general wall content integral for arbitrary normal (nx, ny, 0)."""

    @pytest.mark.parametrize("angle_deg", [0, 30, 45, 60, 90])
    def test_wall_at_angle(self, angle_deg):
        """Wall with normal at angle_deg from x-axis."""
        theta = math.radians(angle_deg)
        nx = math.cos(theta)
        ny = math.sin(theta)
        xc, yc, zc = 0.1, 0.1, 0.05
        R = 0.03

        normal = [nx, ny, 0.0]
        center = [xc, yc, zc]
        fit = _make_plane_fit(normal, center)

        cgen = ConstraintGenerator()
        c_wall = cgen.generate_wall_constraint(
            fit, constraint_id=3, strategy="full",
            contact_angle_wall=90.0, tension=480.0,
        )
        c1, c2, c3 = c_wall.content

        integral = _wall_line_integral(c1, c2, c3, nx, ny, xc, yc, zc, R)
        expected = (nx * xc + ny * yc) * math.pi * R**2
        if abs(expected) < 1e-15:
            assert abs(integral) < 1e-10
        else:
            rel_err = abs(integral - expected) / abs(expected)
            assert rel_err < 1e-5, \
                f"angle={angle_deg}°: got {integral:.10f}, expected {expected:.10f} (err={rel_err:.2e})"

    @pytest.mark.parametrize("angle_deg", [0, 30, 45, 60, 90])
    def test_wall_energy_at_angle(self, angle_deg):
        """Wall energy integral = -sigma_cos * A for any angle."""
        theta = math.radians(angle_deg)
        nx = math.cos(theta)
        ny = math.sin(theta)
        xc, yc, zc = 0.1, 0.1, 0.05
        R = 0.03

        normal = [nx, ny, 0.0]
        center = [xc, yc, zc]
        fit = _make_plane_fit(normal, center)

        cgen = ConstraintGenerator()
        c_wall = cgen.generate_wall_constraint(
            fit, constraint_id=3, strategy="full",
            contact_angle_wall=60.0, tension=480.0,
        )
        e1, e2, e3 = c_wall.energy

        integral = _wall_line_integral(e1, e2, e3, nx, ny, xc, yc, zc, R)
        sigma_cos = 480.0 * math.cos(math.radians(60.0))
        expected = -sigma_cos * math.pi * R**2
        rel_err = abs(integral - expected) / abs(expected)
        assert rel_err < 1e-5, \
            f"energy angle={angle_deg}°: got {integral:.10f}, expected {expected:.10f} (err={rel_err:.2e})"


class TestWallAxisAlignedRegression:
    """Regression: axis-aligned walls must still work after generalization."""

    @pytest.mark.parametrize("x_w", [0.05, 0.1, 0.2])
    def test_x_wall_volume(self, x_w):
        """x-wall content integral gives x_w * pi*R^2."""
        normal = [1.0, 0.0, 0.0]
        center = [x_w, 0.0, 0.05]
        fit = _make_plane_fit(normal, center)

        cgen = ConstraintGenerator()
        c_wall = cgen.generate_wall_constraint(
            fit, constraint_id=3, strategy="full",
            contact_angle_wall=90.0, tension=480.0,
        )
        c1, c2, c3 = c_wall.content

        R = 0.03
        integral = _wall_line_integral(c1, c2, c3, 1.0, 0.0, x_w, 0.0, 0.05, R)
        expected = x_w * math.pi * R**2
        rel_err = abs(integral - expected) / expected
        assert rel_err < 1e-5, \
            f"x_w={x_w}: got {integral:.10f}, expected {expected:.10f} (err={rel_err:.2e})"

    @pytest.mark.parametrize("y_w", [0.05, 0.1, 0.2])
    def test_y_wall_volume(self, y_w):
        """y-wall content integral gives y_w * pi*R^2."""
        normal = [0.0, 1.0, 0.0]
        center = [0.0, y_w, 0.05]
        fit = _make_plane_fit(normal, center)

        cgen = ConstraintGenerator()
        c_wall = cgen.generate_wall_constraint(
            fit, constraint_id=3, strategy="full",
            contact_angle_wall=90.0, tension=480.0,
        )
        c1, c2, c3 = c_wall.content

        R = 0.03
        integral = _wall_line_integral(c1, c2, c3, 0.0, 1.0, 0.0, y_w, 0.05, R)
        expected = y_w * math.pi * R**2
        rel_err = abs(integral - expected) / expected
        assert rel_err < 1e-5, \
            f"y_w={y_w}: got {integral:.10f}, expected {expected:.10f} (err={rel_err:.2e})"
