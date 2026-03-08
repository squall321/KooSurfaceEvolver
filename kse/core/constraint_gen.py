"""Generate Surface Evolver constraint formulas from fitted surfaces.

Converts SurfaceFitResult into SE constraint blocks including:
- CONSTRAINT formula (implicit surface equation)
- ENERGY integrals (contact angle via Young's equation)
- CONTENT integrals (volume accounting for omitted pad facets)
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np
import sympy as sp

from .surface_fitter import SurfaceFitResult, FitType


@dataclass
class SEConstraint:
    """A complete SE constraint definition."""

    constraint_id: int
    formula: str           # SE formula string
    energy: tuple          # (e1, e2, e3) energy integral strings
    content: tuple         # (c1, c2, c3) content integral strings
    is_boundary: bool      # True if using BOUNDARY instead of CONSTRAINT
    boundary_params: Optional[str] = None  # parametric boundary definition


@dataclass
class SERimConstraint:
    """Rim constraint to keep pad edges circular during refinement."""

    constraint_id: int
    formula: str           # circle equation in appropriate plane


class ConstraintGenerator:
    """Generate SE constraint formulas from surface fit results."""

    def __init__(self):
        # Symbolic variables for derivation
        self._x, self._y, self._z = sp.symbols("x y z")
        self._u, self._v = sp.symbols("u v")

    @staticmethod
    def _clean_coeff(v):
        """Clean a numeric value: round near-zero, near-integer, and STL float32 noise."""
        if abs(v) < 1e-12:
            return 0
        # Round to 8 decimal places to eliminate float32 STL noise
        v = round(float(v), 8)
        if abs(v) < 1e-12:
            return 0
        if abs(v - round(v)) < 1e-12:
            return int(round(v))
        return v

    def generate_surface_constraint(
        self,
        fit: SurfaceFitResult,
        constraint_id: int,
        contact_angle: float = 90.0,
        tension: float = 480.0,
        solder_density: float = 9.0,
        gravity: float = 980.0,
        use_boundary_integrals: bool = True,
    ) -> SEConstraint:
        """Generate a complete SE constraint for a fitted surface.

        Args:
            fit: Surface fit result from SurfaceFitter.
            constraint_id: SE constraint number.
            contact_angle: Solder contact angle on this surface (degrees).
            tension: Surface tension (erg/cm^2).
            solder_density: Solder density (g/cm^3).
            gravity: Gravitational acceleration (cm/s^2).
            use_boundary_integrals: If True, generate energy/content integrals.

        Returns:
            SEConstraint with all formula strings.
        """
        x, y, z = self._x, self._y, self._z

        # Build implicit surface F(x,y,z) = 0 in global coordinates
        F_expr = self._build_implicit_formula(fit)
        formula_str = _sympy_to_se(F_expr)

        energy = ("0", "0", "0")
        content = ("0", "0", "0")

        if use_boundary_integrals:
            energy = self._derive_energy_integrals(
                fit, contact_angle, tension, solder_density, gravity
            )
            content = self._derive_content_integrals(fit)

        return SEConstraint(
            constraint_id=constraint_id,
            formula=formula_str,
            energy=energy,
            content=content,
            is_boundary=False,
        )

    def generate_rim_constraint(
        self,
        fit: SurfaceFitResult,
        constraint_id: int,
        radius: float,
    ) -> SERimConstraint:
        """Generate a rim constraint (circle on the surface).

        Keeps pad edges circular during mesh refinement.
        """
        cx, cy, cz = fit.center_global
        u_ax = fit.local_axes[0]  # tangent u
        v_ax = fit.local_axes[1]  # tangent v
        _c = self._clean_coeff

        x, y, z = self._x, self._y, self._z

        # Project (x,y,z) onto tangent plane, compute distance from center
        dx = x - _c(cx)
        dy = y - _c(cy)
        dz = z - _c(cz)
        u_proj = _c(u_ax[0]) * dx + _c(u_ax[1]) * dy + _c(u_ax[2]) * dz
        v_proj = _c(v_ax[0]) * dx + _c(v_ax[1]) * dy + _c(v_ax[2]) * dz

        circle_eq = sp.expand(u_proj**2 + v_proj**2 - radius**2)
        formula_str = _sympy_to_se(circle_eq)

        return SERimConstraint(
            constraint_id=constraint_id,
            formula=formula_str,
        )

    def generate_parametric_boundary(
        self,
        fit: SurfaceFitResult,
        boundary_id: int,
        radius: float,
        solder_density: float = 9.0,
        gravity: float = 980.0,
    ) -> SEConstraint:
        """Generate a parametric boundary for the rim (bga-12 pattern).

        The rim is parameterized as a circle on the fitted surface:
            x(p1) = center + radius*cos(p1)*u + radius*sin(p1)*v + surface_offset*n
        """
        cx, cy, cz = fit.center_global
        u_ax = fit.local_axes[0]
        v_ax = fit.local_axes[1]
        n_ax = fit.local_axes[2]
        _c = self._clean_coeff

        p1 = sp.Symbol("p1")

        # Point on rim circle in tangent plane
        rim_u = radius * sp.cos(p1)
        rim_v = radius * sp.sin(p1)

        # Evaluate surface height at this (u, v) point
        z_offset = self._eval_fit_symbolic(fit, rim_u, rim_v)

        # Global coordinates (cleaned axes for nice output)
        x_expr = _c(cx) + rim_u * _c(u_ax[0]) + rim_v * _c(v_ax[0]) + z_offset * _c(n_ax[0])
        y_expr = _c(cy) + rim_u * _c(u_ax[1]) + rim_v * _c(v_ax[1]) + z_offset * _c(n_ax[1])
        z_expr = _c(cz) + rim_u * _c(u_ax[2]) + rim_v * _c(v_ax[2]) + z_offset * _c(n_ax[2])

        x1 = _sympy_to_se(sp.simplify(x_expr))
        x2 = _sympy_to_se(sp.simplify(y_expr))
        x3 = _sympy_to_se(sp.simplify(z_expr))

        param_str = f"x1: {x1}\nx2: {x2}\nx3: {x3}"

        # Gravity energy on boundary: E2 = G*SOLDER_DENSITY*x*z^2/2
        # Use SE parameter references for flexibility
        e1 = "0"
        if gravity != 0 and solder_density != 0:
            e2 = "G*SOLDER_DENSITY*x*z^2/2"
        else:
            e2 = "0"
        e3 = "0"

        # Content integral for volume: C2 = x*z
        # Positive sign: boundary edges appear negated in body faces,
        # so SE negates this, correctly adding the cap's volume.
        c1 = "0"
        c2 = "x*z"
        c3 = "0"

        return SEConstraint(
            constraint_id=boundary_id,
            formula=param_str,
            energy=(e1, e2, e3),
            content=(c1, c2, c3),
            is_boundary=True,
            boundary_params="parameters 1",
        )

    def _build_implicit_formula(self, fit: SurfaceFitResult) -> sp.Expr:
        """Build F(x,y,z) = 0 implicit surface equation in global coordinates."""
        x, y, z = self._x, self._y, self._z
        cx, cy, cz = [float(v) for v in fit.center_global]
        axes = fit.local_axes
        _c = self._clean_coeff

        cx, cy, cz = _c(cx), _c(cy), _c(cz)

        # Transform global to local: [u, v, w] = axes @ (pos - center)
        dx, dy, dz = x - cx, y - cy, z - cz
        u_expr = _c(axes[0, 0]) * dx + _c(axes[0, 1]) * dy + _c(axes[0, 2]) * dz
        v_expr = _c(axes[1, 0]) * dx + _c(axes[1, 1]) * dy + _c(axes[1, 2]) * dz
        w_expr = _c(axes[2, 0]) * dx + _c(axes[2, 1]) * dy + _c(axes[2, 2]) * dz

        # Surface: w - f(u, v) = 0
        f_uv = self._eval_fit_symbolic(fit, u_expr, v_expr)
        expr = sp.expand(w_expr - f_uv)

        # Clean near-zero coefficients from floating point noise
        replacements = {}
        for atom in expr.atoms(sp.Float):
            val = float(atom)
            if abs(val) < 1e-12:
                replacements[atom] = sp.S.Zero
            elif abs(val - round(val)) < 1e-12:
                replacements[atom] = sp.Integer(round(val))
        if replacements:
            expr = expr.xreplace(replacements)

        return expr

    def _eval_fit_symbolic(self, fit: SurfaceFitResult, u, v) -> sp.Expr:
        """Evaluate the fitted polynomial symbolically."""
        c = fit.coefficients
        if fit.fit_type == FitType.PLANE:
            return c[0] + c[1] * u + c[2] * v
        elif fit.fit_type == FitType.QUADRATIC:
            return (c[0] + c[1] * u + c[2] * v
                    + c[3] * u**2 + c[4] * u * v + c[5] * v**2)
        else:
            expr = (c[0] + c[1] * u + c[2] * v
                    + c[3] * u**2 + c[4] * u * v + c[5] * v**2)
            expr += c[6] * u**3 + c[7] * u**2 * v + c[8] * u * v**2 + c[9] * v**3
            expr += (c[10] * u**4 + c[11] * u**3 * v + c[12] * u**2 * v**2
                     + c[13] * u * v**3 + c[14] * v**4)
            return expr

    def _derive_energy_integrals(
        self,
        fit: SurfaceFitResult,
        contact_angle: float,
        tension: float,
        solder_density: float,
        gravity: float,
    ) -> tuple:
        """Derive energy line integrals for contact angle on this surface.

        The contact line integral enforces the contact angle θ via:
            E_contact = σ·cos(θ) × (wetted pad area)

        Using Green's theorem, for a surface with local normal n = (n_x, n_y, n_z):
            wetted_area = (1/n_z) × projected_area = (1/n_z) × ∮ x dy
        So:
            e2 = -σ·cos(θ)·x / n_z

        For a curved surface z = f(u,v) in the pad's local frame, the surface
        normal z-component at a point (u,v) is:
            n_z(u,v) = 1 / sqrt(1 + (∂f/∂u · |∂u/∂x|)² + (∂f/∂v · |∂v/∂y|)²)

        We express 1/n_z = |∇F| / |∂F/∂z| symbolically via the implicit
        surface F(x,y,z) = 0, where |∇F| / |∂F/∂z| = 1/nz_component.

        For the gravity term: E_grav = G·ρ ∮ x·z²/2 dy
        This is correct for all surface orientations when expressed in global
        coordinates (the SE body volume integral reduces to this boundary form).
        """
        x, y, z = self._x, self._y, self._z
        theta_rad = contact_angle * sp.pi / 180
        sigma_cos = tension * sp.cos(theta_rad)
        G = gravity
        rho = solder_density

        # Build the area-scaling factor 1/n_z from the surface geometry.
        # For surface F(x,y,z)=0: n_z_component = |∂F/∂z| / |∇F|
        # So 1/n_z = |∇F| / |∂F/∂z|
        #
        # We use the local frame: F = w - f(u,v) = 0 in local coordinates.
        # In local coordinates, ∂F/∂w = 1, ∂F/∂u = -∂f/∂u, ∂F/∂v = -∂f/∂v
        # |∇F|_local = sqrt(1 + (∂f/∂u)² + (∂f/∂v)²)
        # In global coords, n_z_global = (axes[2]) · n_local_normalized
        #
        # For the energy line integral, we evaluate 1/n_z at the local
        # polynomial (u=0, v=0) center as a constant-coefficient approximation
        # valid across the contact loop. For flat pads this is exact; for
        # curved pads this is accurate when pad curvature radius >> solder radius.
        #
        # Exact approach: substitute symbolic u(x,y), v(x,y) into ∂f/∂u, ∂f/∂v.
        # We use the exact approach via sympy for all surface types.

        axes = fit.local_axes  # shape (3,3): rows are u, v, n axes
        _c = self._clean_coeff
        cx, cy, cz = [float(v) for v in fit.center_global]

        # Local coordinate expressions: u = axes[0] · (r - center)
        dx = x - _c(cx)
        dy = y - _c(cy)
        dz = z - _c(cz)
        u_expr = _c(axes[0, 0]) * dx + _c(axes[0, 1]) * dy + _c(axes[0, 2]) * dz
        v_expr = _c(axes[1, 0]) * dx + _c(axes[1, 1]) * dy + _c(axes[1, 2]) * dz

        # Surface: w - f(u,v) = 0  →  F = w - f(u,v)
        # On the surface, z satisfies F = 0 → z is constrained.
        # The local normal vector: N_local = (-∂f/∂u, -∂f/∂v, 1) (unnormalized)
        # Global normal: N_global = axes.T @ N_local
        # n_z_global = axes[2,2]*1 + axes[0,2]*(-∂f/∂u) + axes[1,2]*(-∂f/∂v)
        # (only z-component of global normal from normal axis contribution + tangent leakage)

        f_expr = self._eval_fit_symbolic(fit, u_expr, v_expr)
        df_du = sp.diff(f_expr, x) * _c(axes[0, 0]) + sp.diff(f_expr, y) * _c(axes[0, 1]) + sp.diff(f_expr, z) * _c(axes[0, 2])
        df_dv = sp.diff(f_expr, x) * _c(axes[1, 0]) + sp.diff(f_expr, y) * _c(axes[1, 1]) + sp.diff(f_expr, z) * _c(axes[1, 2])

        # This is circular for implicit; use the chain rule correctly:
        # f(u,v) where u,v are linear in (x,y,z) → ∂f/∂x = (∂f/∂u)(∂u/∂x) + (∂f/∂v)(∂v/∂x)
        # Already computed above by differentiating f_expr wrt x directly (since u,v are linear in x)
        df_dx = sp.diff(f_expr, x)
        df_dy = sp.diff(f_expr, y)
        df_dz = sp.diff(f_expr, z)

        # F = w - f(u,v), ∂F/∂z = axes[2,2] - df_dz (since w = axes[2]·(r-c))
        # ∂F/∂x = axes[2,0] - df_dx,  ∂F/∂y = axes[2,1] - df_dy
        dF_dx = _c(axes[2, 0]) - df_dx
        dF_dy = _c(axes[2, 1]) - df_dy
        dF_dz = _c(axes[2, 2]) - df_dz

        # For the line integral e2 = -σcos(θ)·x·(|∂F/∂z| / |∇F|)^{-1}
        # = -σcos(θ)·x · |∇F| / |∂F/∂z|
        # However, this is x-y-z dependent and complex.
        # Practical simplification: evaluate at the contact loop center (u=0, v=0):
        # For polynomial f, ∂f/∂u|_{center} = c1 (linear coefficient)
        #                    ∂f/∂v|_{center} = c2 (linear coefficient)
        # This gives the correct leading-order correction for both tilted planes
        # and weakly curved surfaces.

        c = fit.coefficients
        if fit.fit_type.value == "plane":
            # z_local = c0 + c1*u + c2*v  →  ∂f/∂u = c1, ∂f/∂v = c2 (constants)
            # Substitute into dF expressions at center (df_dx, etc. are constants for plane)
            dF_dx_val = float(dF_dx)
            dF_dy_val = float(dF_dy)
            dF_dz_val = float(dF_dz)
        else:
            # Evaluate gradient at the center of the contact loop (u=0, v=0)
            # by substituting center coordinates
            subs_center = {x: sp.Float(cx), y: sp.Float(cy), z: sp.Float(cz)}
            dF_dx_val = float(dF_dx.subs(subs_center))
            dF_dy_val = float(dF_dy.subs(subs_center))
            dF_dz_val = float(dF_dz.subs(subs_center))

        import math
        grad_norm = math.sqrt(dF_dx_val**2 + dF_dy_val**2 + dF_dz_val**2)

        if abs(dF_dz_val) < 1e-10:
            # Vertical surface (e.g. wall): contact energy goes into e3 instead of e2
            # n_x = dF_dx/|∇F|, contact along x-direction
            inv_nz = None
        else:
            # 1/n_z = |∇F| / |∂F/∂z|
            inv_nz = grad_norm / abs(dF_dz_val)

        # Contact angle energy: E = -σcos(θ) × ∮ x·(area_scale) dy
        # For vertical surfaces (wall), use e3 or e1 component
        if inv_nz is None:
            # Wall: normal is horizontal, contact along vertical direction
            # E = -σcos(θ) × ∮ x dz (integrate along z)
            e1 = "0"
            e2 = "0"
            e3_expr = -sigma_cos * x
            e3 = _sympy_to_se(e3_expr)
        else:
            e1 = "0"
            scale = sp.Float(inv_nz)
            e2_contact = -sigma_cos * scale * x
            e2_gravity = sp.Rational(1, 2) * G * rho * x * z**2
            e2_expr = e2_contact + e2_gravity
            e2 = _sympy_to_se(sp.nsimplify(e2_expr, rational=False))
            e3 = "0"

        return (e1, e2, e3)

    def generate_wall_constraint(
        self,
        fit: SurfaceFitResult,
        constraint_id: int,
        contact_angle_wall: float = 90.0,
        tension: float = 480.0,
        strategy: str = "pinned",
    ) -> SEConstraint:
        """Generate a SE constraint for a vertical wall surface.

        For Strategy A (pinned): only the formula is generated.
            Wall vertices are fixed in place by MeshToSEConverter, so
            no energy/content integrals are needed.

        For Strategy B (full): formula + energy + content integrals are
            generated so SE enforces the contact angle on the wall.

        Wall surface formula: derived from the fitted plane normal.
        For a vertical wall (no z-tilt) with plane n·r = d:
            formula: n_x*(x - cx) + n_y*(y - cy)  [= 0 on wall]

        Wall energy integrals (for vertical wall with outward normal n=(nx,ny,0)):
            The wetted wall area A = (1/2) ∮ (t₁ dz - z dt₁)
            where t₁ is the tangential coordinate along the wall surface.
            For a wall at x = xw (n = (1,0,0)):
                e2 =  σ·cos(θ_wall)·z/2   (dy coefficient)
                e3 = -σ·cos(θ_wall)·y/2   (dz coefficient)

        Wall content integrals (volume contribution from wall arc):
            For a wall at x = xw (n = (1,0,0)):
                c2 = -x·z/2   (dy coefficient)
                c3 =  x·y/2   (dz coefficient)
            These give V_wall = xw × A_yz (slab volume from x=0 to xw).

        Args:
            fit: SurfaceFitResult for the wall (should be FitType.PLANE).
            constraint_id: SE constraint number to assign.
            contact_angle_wall: Contact angle of solder on wall (degrees).
            tension: Surface tension σ (erg/cm² or mN/m).
            strategy: "pinned" – formula only; "full" – formula + integrals.

        Returns:
            SEConstraint with appropriate fields populated.
        """
        # Build formula (same for both strategies)
        F_expr = self._build_implicit_formula(fit)
        formula_str = _sympy_to_se(F_expr)

        if strategy == "pinned":
            # No integrals: wall vertices are fixed externally
            return SEConstraint(
                constraint_id=constraint_id,
                formula=formula_str,
                energy=("0", "0", "0"),
                content=("0", "0", "0"),
                is_boundary=False,
            )

        # Strategy B: derive energy and content integrals
        # General formulas for arbitrary vertical wall normal n̂ = (nx, ny, 0).
        #
        # Define rotated coordinates on the wall plane:
        #   p = nx*x + ny*y   (perpendicular distance from origin to wall)
        #   q = -ny*x + nx*y  (tangential coordinate along wall)
        #
        # Content integral (volume):
        #   c1 = ny*p*z/2,  c2 = -nx*p*z/2,  c3 = p*q/2
        #   ∮ = d_wall · π·R²  where d_wall = nx*xc + ny*yc  (wall position)
        #   Derived from Stokes' theorem in (q, z) coordinates on the wall:
        #   ∮(p*z/2 dq - p*q/2 dz) = d_wall · ∫∫ dq dz = d_wall · A
        #
        # Energy integral (wetted area):
        #   e1 = -ny*σcos(θ)*z/2,  e2 = nx*σcos(θ)*z/2,  e3 = σcos(θ)*(ny*x-nx*y)/2
        #   ∮ = -σcos(θ) · A  (correct sign for wetting energy reduction)
        #   Derived from ∮(z/2 dq - q/2 dz) = -A in (q, z) frame.
        #
        # These reduce to old axis-aligned formulas for (1,0,0) and (0,1,0).
        x, y, z = self._x, self._y, self._z
        import math
        theta_rad = contact_angle_wall * math.pi / 180.0
        sigma_cos = tension * math.cos(theta_rad)

        n_global = fit.local_axes[2]  # (nx, ny, nz) global surface normal
        nx_val = self._clean_coeff(float(n_global[0]))
        ny_val = self._clean_coeff(float(n_global[1]))

        # Rotated wall coordinates
        p = sp.Float(nx_val) * x + sp.Float(ny_val) * y  # wall distance
        q = sp.Float(-ny_val) * x + sp.Float(nx_val) * y  # wall tangent

        # Content: c1 = ny*p*z/2,  c2 = -nx*p*z/2,  c3 = p*q/2
        c1_expr = sp.Float(ny_val) * p * z / 2
        c2_expr = sp.Float(-nx_val) * p * z / 2
        c3_expr = p * q / 2
        c1 = _sympy_to_se(sp.expand(c1_expr))
        c2 = _sympy_to_se(sp.expand(c2_expr))
        c3 = _sympy_to_se(sp.expand(c3_expr))

        # Energy: e1 = -ny*σcos(θ)*z/2, e2 = nx*σcos(θ)*z/2,
        #         e3 = σcos(θ)*(ny*x - nx*y)/2
        e1_expr = sp.Float(-ny_val * sigma_cos / 2) * z
        e2_expr = sp.Float(nx_val * sigma_cos / 2) * z
        e3_expr = sp.Float(sigma_cos / 2) * (sp.Float(ny_val) * x - sp.Float(nx_val) * y)
        e1 = _sympy_to_se(e1_expr)
        e2 = _sympy_to_se(e2_expr)
        e3 = _sympy_to_se(e3_expr)

        return SEConstraint(
            constraint_id=constraint_id,
            formula=formula_str,
            energy=(e1, e2, e3),
            content=(c1, c2, c3),
            is_boundary=False,
        )

    def _derive_content_integrals(self, fit: SurfaceFitResult) -> tuple:
        """Derive content line integrals for volume accounting.

        The content integral compensates for omitted pad facets in volume
        calculation.  By Green's theorem, ∮ c2(x,y) dy = ∫∫ ∂c2/∂x dA.
        Setting c2 = G(x,y) = ∫ z_surface(x,y) dx makes ∂G/∂x = z_surface,
        yielding the exact cap volume for any polynomial surface.

        Algorithm:
          1. Build implicit surface F(x,y,z) = 0.
          2. Solve for z = z_surface(x,y) as a polynomial in (x, y).
          3. Compute G(x,y) = ∫ z_surface dx  (x-antiderivative).
          4. Return c2 = G(x,y).

        This is exact for PLANE, QUADRATIC, and QUARTIC fits with any
        orientation (tilted or rotated axes).
        """
        x, y, z = self._x, self._y, self._z

        # Build implicit surface F(x,y,z) = 0
        F_expr = self._build_implicit_formula(fit)

        # Check that the surface is non-vertical (has z-dependence)
        dF_dz = sp.diff(F_expr, z)
        if dF_dz.is_zero or (dF_dz.is_Number and abs(float(dF_dz)) < 1e-10):
            # Vertical/near-vertical surface: fallback to x*z
            return ("0", _sympy_to_se(x * z), "0")

        # Solve F(x,y,z) = 0 for z → z_surface(x,y)
        z_solutions = sp.solve(F_expr, z)
        if not z_solutions:
            return ("0", _sympy_to_se(x * z), "0")

        z_surface = z_solutions[0]  # linear in z → unique solution

        # G(x,y) = ∫ z_surface dx  (antiderivative w.r.t. x)
        G = sp.integrate(z_surface, x)

        # Clean near-zero coefficients
        G = sp.expand(G)
        replacements = {}
        for atom in G.atoms(sp.Float):
            val = float(atom)
            if abs(val) < 1e-12:
                replacements[atom] = sp.S.Zero
        if replacements:
            G = G.xreplace(replacements)

        return ("0", _sympy_to_se(G), "0")


def _sympy_to_se(expr: sp.Expr) -> str:
    """Convert a sympy expression to Surface Evolver syntax string.

    Handles:
    - Power operator: ** → ^ (SE syntax)
    - Rational fractions: 3/25 → 0.12 (decimal form)
    - Near-zero cleanup: 1e-17 → 0
    """
    import re

    if isinstance(expr, (int, float)):
        expr = sp.sympify(expr)

    if expr.is_zero or (expr.is_Number and abs(float(expr)) < 1e-15):
        return "0"

    # Replace Rational numbers with Float to avoid fractions like 16106127/134217728
    replacements = {}
    for atom in expr.atoms(sp.Number):
        # Keep pi as symbolic
        if isinstance(atom, sp.core.numbers.Pi):
            continue
        if isinstance(atom, sp.Rational) and atom.q != 1:
            # It's a fraction — convert to float
            replacements[atom] = sp.Float(float(atom), 15)
        elif isinstance(atom, sp.Float):
            # Clean near-zero floats
            if abs(float(atom)) < 1e-15:
                replacements[atom] = sp.S.Zero
    if replacements:
        expr = expr.xreplace(replacements)

    s = str(expr)

    # SE uses ^ for power, not **
    s = s.replace("**", "^")

    # Clean up float formatting
    def _fmt_float(m):
        val = float(m.group())
        if abs(val) < 1e-15:
            return "0"
        if val == int(val) and abs(val) < 1e8:
            return str(int(val))
        return f"{val:.10g}"

    s = re.sub(r"-?\d+\.\d+(?:e[+-]?\d+)?", _fmt_float, s)

    # Clean up spacing
    s = s.replace("  ", " ").strip()

    return s if s else "0"
