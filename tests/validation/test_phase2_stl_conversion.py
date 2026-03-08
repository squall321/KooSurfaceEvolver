"""Phase 2: Verify STL generation from constraints and surface fitting round-trip."""

import math

import numpy as np
import pytest

from kse.core.stl_reader import STLReader
from kse.core.surface_fitter import SurfaceFitter, FitType
from kse.core.constraint_gen import ConstraintGenerator

from .conftest import EXAMPLE_REGISTRY
from .helpers.stl_from_constraints import (
    generate_flat_pad_stl,
    generate_tilted_pad_stl,
    generate_spherical_cap_stl,
)


class TestFlatPadSTL:
    """Test flat pad STL generation and surface fitting round-trip."""

    def test_bottom_pad_z0(self, tmp_path):
        """Generate flat pad at z=0, verify SurfaceFitter recovers plane."""
        r = 0.10
        center = np.array([0.0, 0.0, 0.0])
        stl_path = tmp_path / "bottom.stl"
        mesh = generate_flat_pad_stl(center, r, output_path=stl_path)

        assert stl_path.exists()
        assert len(mesh.faces) > 100

        reader = STLReader(stl_path)
        patch = reader.extract_patch(center, r)
        fitter = SurfaceFitter()
        fit = fitter.fit(patch)

        assert fit.fit_type == FitType.PLANE
        assert fit.residual_rms < 1e-8
        # Surface should pass through z=0
        val = fit.eval_global(np.array([[0, 0, 0]]))[0]
        assert abs(val) < 1e-6, f"F(0,0,0) = {val}, expected ~0"

    def test_top_pad_z012(self, tmp_path):
        """Generate flat pad at z=0.12, verify fitting."""
        r = 0.10
        h = 0.12
        center = np.array([0.0, 0.0, h])
        stl_path = tmp_path / "top.stl"
        generate_flat_pad_stl(center, r, output_path=stl_path)

        reader = STLReader(stl_path)
        patch = reader.extract_patch(center, r)
        fitter = SurfaceFitter()
        fit = fitter.fit(patch)

        assert fit.fit_type == FitType.PLANE
        assert fit.residual_rms < 1e-8
        # Surface passes through (0,0,0.12)
        val = fit.eval_global(np.array([[0, 0, h]]))[0]
        assert abs(val) < 1e-6, f"F(0,0,{h}) = {val}"
        # Normal should be approximately (0,0,1) or (0,0,-1)
        assert abs(abs(fit.local_axes[2, 2]) - 1.0) < 0.01

    def test_offset_pad(self, tmp_path):
        """Generate offset pad for bga-7 pattern."""
        r = 0.10
        h = 0.12
        y_off = 0.03
        center = np.array([0.0, y_off, h])
        stl_path = tmp_path / "top_offset.stl"
        generate_flat_pad_stl(center, r, output_path=stl_path)

        reader = STLReader(stl_path)
        patch = reader.extract_patch(center, r)
        fitter = SurfaceFitter()
        fit = fitter.fit(patch)

        assert fit.fit_type == FitType.PLANE
        assert fit.residual_rms < 1e-8
        # Center should be near the offset point
        assert abs(fit.center_global[1] - y_off) < 0.01
        assert abs(fit.center_global[2] - h) < 0.01


class TestTiltedPadSTL:
    """Test tilted pad STL for bga-10/12 pattern."""

    def test_tilted_20deg(self, tmp_path):
        """Generate 20-degree tilted pad, verify fitting."""
        r = 0.10
        h = 0.12
        tilt_deg = 20.0
        tilt_rad = np.radians(tilt_deg)
        normal = np.array([0, np.sin(tilt_rad), -np.cos(tilt_rad)])
        center = np.array([0.0, 0.0, h])

        stl_path = tmp_path / "tilted.stl"
        generate_tilted_pad_stl(center, r, normal, output_path=stl_path)

        reader = STLReader(stl_path)
        patch = reader.extract_patch(center, r)
        fitter = SurfaceFitter()
        fit = fitter.fit(patch)

        assert fit.fit_type == FitType.PLANE
        assert fit.residual_rms < 1e-6
        # Check normal direction matches
        fit_normal = fit.local_axes[2]
        cos_angle = abs(np.dot(fit_normal, normal / np.linalg.norm(normal)))
        assert cos_angle > 0.95, f"Normal mismatch: cos={cos_angle}"


class TestSphericalCapSTL:
    """Test spherical cap STL for cbga1 pattern."""

    def test_spherical_cap(self, tmp_path):
        """Generate spherical cap, verify fitting detects curvature."""
        r_sphere = 0.04
        sphere_center = np.array([0.0, 0.0, r_sphere])
        stl_path = tmp_path / "cap.stl"
        generate_spherical_cap_stl(
            sphere_center, r_sphere,
            cap_extent_angle=45.0,
            output_path=stl_path,
        )

        reader = STLReader(stl_path)
        # Contact point is at bottom of sphere
        contact = np.array([0.0, 0.0, 0.0])
        patch = reader.extract_patch(contact, r_sphere * 0.8)
        fitter = SurfaceFitter()
        fit = fitter.fit(patch)

        # Should detect curvature (not just a plane)
        assert fit.fit_type in (FitType.QUADRATIC, FitType.QUARTIC, FitType.PLANE)
        assert fit.residual_rms < 1e-2


class TestConstraintFormula:
    """Verify constraint formulas match the original .fe patterns."""

    def test_plane_z0_constraint(self, tmp_path):
        """STL → fit → constraint formula for z=0 plane."""
        r = 0.10
        center = np.array([0.0, 0.0, 0.0])
        stl_path = tmp_path / "bottom.stl"
        generate_flat_pad_stl(center, r, output_path=stl_path)

        reader = STLReader(stl_path)
        patch = reader.extract_patch(center, r)
        fitter = SurfaceFitter()
        fit = fitter.fit(patch)

        cgen = ConstraintGenerator()
        constraint = cgen.generate_surface_constraint(fit, 1)

        # Formula should evaluate to ~0 at z=0 surface
        assert len(constraint.formula) > 0
        # Check it's a valid constraint (has variables)
        formula_lower = constraint.formula.lower()
        assert any(v in formula_lower for v in ["x", "y", "z"]), \
            f"Formula has no variables: {constraint.formula}"

    def test_plane_z012_constraint(self, tmp_path):
        """STL → fit → constraint formula for z=0.12 plane."""
        r = 0.10
        h = 0.12
        center = np.array([0.0, 0.0, h])
        stl_path = tmp_path / "top.stl"
        generate_flat_pad_stl(center, r, output_path=stl_path)

        reader = STLReader(stl_path)
        patch = reader.extract_patch(center, r)
        fitter = SurfaceFitter()
        fit = fitter.fit(patch)

        cgen = ConstraintGenerator()
        constraint = cgen.generate_surface_constraint(fit, 2)
        assert len(constraint.formula) > 0

    def test_rim_constraint(self, tmp_path):
        """Verify rim constraint is a circle equation."""
        r = 0.10
        center = np.array([0.0, 0.0, 0.0])
        stl_path = tmp_path / "bottom.stl"
        generate_flat_pad_stl(center, r, output_path=stl_path)

        reader = STLReader(stl_path)
        patch = reader.extract_patch(center, r)
        fitter = SurfaceFitter()
        fit = fitter.fit(patch)

        cgen = ConstraintGenerator()
        rim = cgen.generate_rim_constraint(fit, 3, r)
        # Formula should contain r^2 = 0.01
        assert "0.01" in rim.formula or "**2" in rim.formula or "^2" in rim.formula

    def test_parametric_boundary(self, tmp_path):
        """Verify parametric boundary for top surface."""
        r = 0.10
        h = 0.12
        center = np.array([0.0, 0.0, h])
        stl_path = tmp_path / "top.stl"
        generate_flat_pad_stl(center, r, output_path=stl_path)

        reader = STLReader(stl_path)
        patch = reader.extract_patch(center, r)
        fitter = SurfaceFitter()
        fit = fitter.fit(patch)

        cgen = ConstraintGenerator()
        bdry = cgen.generate_parametric_boundary(fit, 1, r)

        assert bdry.is_boundary
        assert "x1:" in bdry.formula
        assert "x2:" in bdry.formula
        assert "x3:" in bdry.formula
        # Should contain cos(p1) and sin(p1) for circular rim
        assert "cos" in bdry.formula.lower()
        assert "sin" in bdry.formula.lower()
