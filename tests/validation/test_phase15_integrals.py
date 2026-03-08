"""Phase 15: Content/energy integral correctness tests.

Tests that _derive_content_integrals() and generate_wall_constraint()
produce numerically correct volume integrals for:
  - horizontal flat pad (regression: should be unchanged)
  - x-tilted flat pad  (new fix)
  - x-axis-aligned wall (regression)
  - y-axis-aligned wall (bug fix: was using x instead of y)
"""

import math
import numpy as np
import pytest
import sympy as sp

from kse.core.surface_fitter import SurfaceFitResult, FitType
from kse.core.constraint_gen import ConstraintGenerator


# ---------------------------------------------------------------------------
# Helpers: build minimal SurfaceFitResult for a flat plane
# ---------------------------------------------------------------------------

def _make_plane_fit(normal, center):
    """Create a SurfaceFitResult for a flat plane with the given unit normal."""
    normal = np.asarray(normal, dtype=float)
    center = np.asarray(center, dtype=float)
    normal = normal / np.linalg.norm(normal)

    # Build local axes: n = normal_global (axes[2])
    # Pick u perp to n in the xy-plane if possible
    if abs(normal[2]) < 0.99:
        u = np.cross(normal, [0, 0, 1])
    else:
        u = np.array([1.0, 0.0, 0.0])
    u = u / np.linalg.norm(u)
    v = np.cross(normal, u)
    axes = np.stack([u, v, normal])  # shape (3,3)

    # Plane: z_local = 0 (flat in local frame) → coefficients [0, 0, 0]
    coeffs = np.zeros(3)

    return SurfaceFitResult(
        fit_type=FitType.PLANE,
        coefficients=coeffs,
        residual_rms=0.0,
        residual_max=0.0,
        center_global=center,
        normal_global=normal,
        local_axes=axes,
        radius=0.1,
    )


def _line_integral_c2_circle(c2_str, cx, cy, cz, R, n_tilted_z=None, tilt_a=0.0, tilt_b=0.0):
    """Numerically integrate ∮ c2(x,y,z) dy along a circular loop.

    The loop lies on the tilted plane z = cz + tilt_a*(x-cx) + tilt_b*(y-cy)
    parametrised as:
        x = cx + R*cos(t)
        y = cy + R*sin(t)
        z = cz + tilt_a*R*cos(t) + tilt_b*R*sin(t)

    c2_str: sympy expression string for c2(x,y,z).
    Returns the integral value.
    """
    x_s, y_s, z_s = sp.symbols("x y z")
    c2_expr = sp.sympify(c2_str)

    t = sp.Symbol("t")
    R_s = sp.Float(R)
    cx_s, cy_s, cz_s = sp.Float(cx), sp.Float(cy), sp.Float(cz)
    a_s, b_s = sp.Float(tilt_a), sp.Float(tilt_b)

    x_t = cx_s + R_s * sp.cos(t)
    y_t = cy_s + R_s * sp.sin(t)
    z_t = cz_s + a_s * R_s * sp.cos(t) + b_s * R_s * sp.sin(t)
    dy_t = R_s * sp.cos(t)

    integrand = c2_expr.subs({x_s: x_t, y_s: y_t, z_s: z_t}) * dy_t
    result = sp.integrate(integrand, (t, 0, 2 * sp.pi))
    return float(result.evalf())


def _line_integral_c1c3_circle_yz(c1_str, c3_str, cy, cz, R, x_wall):
    """Numerically integrate ∮ (c1 dx + c3 dz) along a circular loop in the xz-plane.

    Loop at x = x_wall, in the y-z plane:
        y = cy + R*cos(t)
        z = cz + R*sin(t)
        x = x_wall (constant)
    """
    x_s, y_s, z_s = sp.symbols("x y z")
    c1_expr = sp.sympify(c1_str)
    c3_expr = sp.sympify(c3_str)

    t = sp.Symbol("t")
    y_t = sp.Float(cy) + sp.Float(R) * sp.cos(t)
    z_t = sp.Float(cz) + sp.Float(R) * sp.sin(t)
    x_t = sp.Float(x_wall)
    dy_t = -sp.Float(R) * sp.sin(t)
    dz_t = sp.Float(R) * sp.cos(t)

    subs = {x_s: x_t, y_s: y_t, z_s: z_t}
    integrand = (c1_expr.subs(subs) * dy_t + c3_expr.subs(subs) * dz_t)
    result = sp.integrate(integrand, (t, 0, 2 * sp.pi))
    return float(result.evalf())


def _line_integral_c2c3_circle_xz(c2_str, c3_str, cx, cz, R, y_wall):
    """Numerically integrate ∮ (c2 dy + c3 dz) along a loop in xz-plane at y=y_wall.

    Loop: x = cx + R*cos(t), z = cz + R*sin(t), y = y_wall (constant).
    """
    x_s, y_s, z_s = sp.symbols("x y z")
    c2_expr = sp.sympify(c2_str)
    c3_expr = sp.sympify(c3_str)

    t = sp.Symbol("t")
    x_t = sp.Float(cx) + sp.Float(R) * sp.cos(t)
    z_t = sp.Float(cz) + sp.Float(R) * sp.sin(t)
    y_t = sp.Float(y_wall)
    dx_t = -sp.Float(R) * sp.sin(t)
    dz_t = sp.Float(R) * sp.cos(t)

    subs = {x_s: x_t, y_s: y_t, z_s: z_t}
    # For y-wall: c1 dx + c3 dz  (c2 = 0)
    integrand = (c2_expr.subs(subs) * dx_t + c3_expr.subs(subs) * dz_t)
    result = sp.integrate(integrand, (t, 0, 2 * sp.pi))
    return float(result.evalf())


# ===========================================================================
# Tests: _derive_content_integrals (pad surfaces)
# ===========================================================================

class TestContentIntegralHorizontalPad:
    """Horizontal pad: c2 = x*z should give V_cap = z0 * π*R² exactly."""

    def test_circle_centered_at_origin(self):
        center = [0.0, 0.0, 0.2]
        fit = _make_plane_fit([0, 0, 1], center)
        cgen = ConstraintGenerator()
        c1, c2, c3 = cgen._derive_content_integrals(fit)

        R = 0.05
        # Loop at z = 0.2, center (0,0)
        integral = _line_integral_c2_circle(c2, 0, 0, 0.2, R)
        expected = 0.2 * math.pi * R**2
        assert abs(integral - expected) / expected < 1e-6, \
            f"c2={c2}: got {integral}, expected {expected}"

    def test_circle_off_center(self):
        center = [0.3, 0.1, 0.15]
        fit = _make_plane_fit([0, 0, 1], center)
        cgen = ConstraintGenerator()
        _, c2, _ = cgen._derive_content_integrals(fit)

        R = 0.04
        integral = _line_integral_c2_circle(c2, center[0], center[1], center[2], R)
        expected = center[2] * math.pi * R**2
        assert abs(integral - expected) / expected < 1e-6


class TestContentIntegralTiltedPad:
    """Tilted flat pad: corrected c2 = x*z + (n_x/n_z)/2*x² must give z0 * π*R²."""

    @pytest.mark.parametrize("tilt_deg", [10, 20, 30, 45])
    def test_x_tilted_plane(self, tilt_deg):
        """Plane tilted in x-direction by tilt_deg degrees."""
        theta = math.radians(tilt_deg)
        # Normal: rotate z-axis by theta around y-axis → n = (sin θ, 0, cos θ)
        normal = [math.sin(theta), 0.0, math.cos(theta)]
        center = [0.2, 0.0, 0.1]  # center of contact
        fit = _make_plane_fit(normal, center)

        cgen = ConstraintGenerator()
        _, c2, _ = cgen._derive_content_integrals(fit)

        R = 0.03
        # The plane is z = 0.1 + tan(θ)*(x - 0.2)  so at center z = 0.1
        z0 = center[2]
        # tilt_a = -n_x/n_z
        tilt_a = -normal[0] / normal[2]

        integral = _line_integral_c2_circle(
            c2, center[0], center[1], z0, R, tilt_a=tilt_a
        )
        expected = z0 * math.pi * R**2

        rel_err = abs(integral - expected) / expected
        assert rel_err < 1e-5, \
            f"tilt={tilt_deg}°: c2={c2}, got {integral:.8f}, expected {expected:.8f} (err={rel_err:.2e})"

    def test_horizontal_unchanged(self):
        """Horizontal pad (tilt=0): content integral is exact for flat pad."""
        fit = _make_plane_fit([0, 0, 1], [0.1, 0.1, 0.15])
        cgen = ConstraintGenerator()
        _, c2, _ = cgen._derive_content_integrals(fit)
        # Phase 16: c2 is now the x-antiderivative of z_surface(x,y).
        # For horizontal pad z=0.15: c2 = 0.15*x (equivalent to x*z on surface).
        # Verify numerically that it gives correct volume.
        R = 0.04
        integral = _line_integral_c2_circle(c2, 0.1, 0.1, 0.15, R)
        expected = 0.15 * math.pi * R**2
        assert abs(integral - expected) / expected < 1e-6, \
            f"c2={c2}: got {integral}, expected {expected}"


# ===========================================================================
# Tests: generate_wall_constraint (wall surfaces)
# ===========================================================================

class TestWallContentIntegralXWall:
    """x-wall at x = x_w: content integral should give x_w * π*R² (area in yz-plane)."""

    @pytest.mark.parametrize("x_w", [0.05, 0.1, 0.2])
    def test_x_wall_volume(self, x_w):
        """∮ (c2 dy + c3 dz) = x_w * A_yz for circular loop in yz-plane."""
        # Wall at x = x_w, normal = (1, 0, 0)
        normal = [1.0, 0.0, 0.0]
        center = [x_w, 0.0, 0.05]
        fit = _make_plane_fit(normal, center)

        cgen = ConstraintGenerator()
        c_wall = cgen.generate_wall_constraint(
            fit, constraint_id=3, strategy="full",
            contact_angle_wall=90.0, tension=480.0,
        )
        _, c2, c3 = c_wall.content

        R = 0.03
        # Loop at x=x_w in yz-plane
        integral = _line_integral_c1c3_circle_yz("0", c3, 0.0, center[2], R, x_w)
        # Also add c2 contribution: loop is at x=x_w, dy = R*cos(t)dt
        # but x is constant so ∮ c2 dy is non-zero if c2 depends on y,z
        x_s, y_s, z_s = sp.symbols("x y z")
        c2_expr = sp.sympify(c2)
        t = sp.Symbol("t")
        y_t = sp.Float(R) * sp.cos(t)
        z_t = sp.Float(center[2]) + sp.Float(R) * sp.sin(t)
        dy_t = -sp.Float(R) * sp.sin(t)
        integrand2 = c2_expr.subs({x_s: x_w, y_s: y_t, z_s: z_t}) * dy_t
        contrib2 = float(sp.integrate(integrand2, (t, 0, 2 * sp.pi)).evalf())

        # c1 contribution (dx = 0 since x = x_w = const)
        total = contrib2 + integral

        expected = x_w * math.pi * R**2
        rel_err = abs(total - expected) / expected
        assert rel_err < 1e-5, \
            f"x_w={x_w}: got {total:.8f}, expected {expected:.8f} (err={rel_err:.2e})"


class TestWallContentIntegralYWall:
    """y-wall at y = y_w: content integral should give y_w * π*R².

    Phase 16: uses general wall formula with ẑ × n̂ loop winding.
    For y-wall (n=(0,1,0)): ẑ × n̂ = (-1,0,0), so
    x(t) = xc - R*cos(t), y(t) = y_w, z(t) = zc + R*sin(t).
    """

    @pytest.mark.parametrize("y_w", [0.05, 0.1, 0.2])
    def test_y_wall_volume(self, y_w):
        """∮(c1 dx + c2 dy + c3 dz) = y_w * A using ẑ × n̂ winding."""
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
        # ẑ × n̂ = (0,0,1) × (0,1,0) = (-1,0,0)
        # x(t) = xc - R*cos(t), y(t) = y_w, z(t) = cz + R*sin(t)
        x_s, y_s, z_s = sp.symbols("x y z")
        c1_expr = sp.sympify(c1)
        c2_expr = sp.sympify(c2)
        c3_expr = sp.sympify(c3)
        t = sp.Symbol("t")
        x_t = sp.Float(center[0]) - sp.Float(R) * sp.cos(t)
        y_t = sp.Float(y_w)
        z_t = sp.Float(center[2]) + sp.Float(R) * sp.sin(t)
        dx_t = sp.Float(R) * sp.sin(t)
        dy_t = sp.S.Zero
        dz_t = sp.Float(R) * sp.cos(t)

        subs = {x_s: x_t, y_s: y_t, z_s: z_t}
        integrand = (c1_expr.subs(subs) * dx_t
                     + c2_expr.subs(subs) * dy_t
                     + c3_expr.subs(subs) * dz_t)
        total = float(sp.integrate(sp.expand(integrand), (t, 0, 2 * sp.pi)).evalf())

        expected = y_w * math.pi * R**2
        rel_err = abs(total - expected) / expected
        assert rel_err < 1e-5, \
            f"y_w={y_w}: c1={c1}, c2={c2}, c3={c3}, got {total:.8f}, expected {expected:.8f} (err={rel_err:.2e})"

    def test_y_wall_formula_uses_y(self):
        """Verify the general formula: c1 or c3 must contain 'y'."""
        normal = [0.0, 1.0, 0.0]
        fit = _make_plane_fit(normal, [0.0, 0.1, 0.05])
        cgen = ConstraintGenerator()
        c_wall = cgen.generate_wall_constraint(
            fit, constraint_id=3, strategy="full",
            contact_angle_wall=90.0, tension=480.0,
        )
        c1, c2, c3 = c_wall.content
        has_y = any("y" in ci for ci in [c1, c2, c3])
        assert has_y, f"Wall formula should contain 'y': c1={c1}, c2={c2}, c3={c3}"
        assert "y" in c3, f"c3 should contain 'y', got '{c3}'"
