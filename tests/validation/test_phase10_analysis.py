"""Phase 10: Result analysis and parameter sweep tests.

Tests:
- ResultAnalyzer: standoff height, max radius, volume, area from mesh
- SweepRunner: config variant generation
"""

import tempfile
from pathlib import Path

import numpy as np
import pytest
import trimesh

from kse.solver.result_analyzer import ResultAnalyzer, JointResult
from kse.batch.sweep_runner import SweepRunner, SweepPoint, SweepResult


# ---------------------------------------------------------------------------
# Phase 10A: Result analyzer
# ---------------------------------------------------------------------------

class TestResultAnalyzer:
    """Test physical quantity extraction from mesh data."""

    def test_cube_mesh(self):
        """Cube 1x1x1 centered at origin."""
        box = trimesh.creation.box(extents=[1, 1, 1])
        analyzer = ResultAnalyzer()
        jr = analyzer.analyze_mesh(box.vertices, box.faces)

        assert jr.standoff_height == pytest.approx(1.0, abs=1e-6)
        assert jr.z_min == pytest.approx(-0.5, abs=1e-6)
        assert jr.z_max == pytest.approx(0.5, abs=1e-6)
        assert jr.max_radius == pytest.approx(np.sqrt(0.5), abs=1e-3)
        assert jr.surface_area == pytest.approx(6.0, abs=1e-3)
        assert jr.volume == pytest.approx(1.0, abs=0.05)

    def test_cylinder_mesh(self):
        """Cylinder with known dimensions."""
        cyl = trimesh.creation.cylinder(radius=0.5, height=2.0, sections=32)
        analyzer = ResultAnalyzer()
        jr = analyzer.analyze_mesh(cyl.vertices, cyl.faces)

        assert jr.standoff_height == pytest.approx(2.0, abs=0.01)
        assert jr.max_radius == pytest.approx(0.5, abs=0.02)
        assert jr.volume == pytest.approx(np.pi * 0.25 * 2.0, abs=0.1)

    def test_sphere_mesh(self):
        """Sphere with known radius."""
        sphere = trimesh.creation.icosphere(subdivisions=3, radius=1.0)
        analyzer = ResultAnalyzer()
        jr = analyzer.analyze_mesh(sphere.vertices, sphere.faces)

        assert jr.standoff_height == pytest.approx(2.0, abs=0.05)
        assert jr.max_radius == pytest.approx(1.0, abs=0.05)
        assert jr.surface_area == pytest.approx(4 * np.pi, abs=0.5)
        assert jr.volume == pytest.approx(4/3 * np.pi, abs=0.2)

    def test_centroid(self):
        """Centroid of a translated box."""
        box = trimesh.creation.box(extents=[1, 1, 1])
        box.apply_translation([5, 3, 1])
        analyzer = ResultAnalyzer()
        jr = analyzer.analyze_mesh(box.vertices, box.faces)

        np.testing.assert_allclose(jr.centroid, [5, 3, 1], atol=1e-6)


# ---------------------------------------------------------------------------
# Phase 10B: Sweep runner
# ---------------------------------------------------------------------------

class TestSweepRunner:
    """Test parameter sweep infrastructure."""

    def _make_config(self):
        """Create a minimal KSEConfig for testing."""
        from kse.config.yaml_config import (
            KSEConfig, PhysicsConfig, InputConfig, GeometryConfig,
            OptionsConfig, SolverConfig, OutputConfig, SweepConfig,
        )
        from kse.core.units import CGS

        return KSEConfig(
            unit_system=CGS,
            physics=PhysicsConfig(),
            input=InputConfig(mode="parametric"),
            geometry=GeometryConfig(radius=0.01, volume=0.001),
            options=OptionsConfig(),
            solver=SolverConfig(fe_only=True),
            output=OutputConfig(
                directory=tempfile.mkdtemp(),
                joint_name="test",
            ),
            sweep=SweepConfig(
                enabled=True,
                variable="volume",
                values=[0.001, 0.002],
            ),
        )

    def test_make_variant_volume(self):
        config = self._make_config()
        runner = SweepRunner()
        variant = runner._make_variant(config, "volume", 0.005, 0)
        assert variant.geometry.volume == 0.005
        assert variant.geometry.target_volume == 0.005
        assert "sweep_000" in variant.output.directory

    def test_make_variant_contact_angle(self):
        config = self._make_config()
        runner = SweepRunner()
        variant = runner._make_variant(config, "contact_angle", 45.0, 1)
        assert variant.physics.contact_angle_bottom == 45.0
        assert variant.physics.contact_angle_top == 45.0

    def test_make_variant_tension(self):
        config = self._make_config()
        runner = SweepRunner()
        variant = runner._make_variant(config, "tension", 500.0, 2)
        assert variant.physics.tension == 500.0

    def test_make_variant_unknown_raises(self):
        config = self._make_config()
        runner = SweepRunner()
        with pytest.raises(ValueError, match="Unknown"):
            runner._make_variant(config, "unknown_var", 1.0, 0)

    def test_sweep_point_defaults(self):
        pt = SweepPoint(value=0.5)
        assert pt.success is False
        assert pt.standoff_height is None
        assert pt.error is None

    def test_generate_report(self):
        runner = SweepRunner()
        result = SweepResult(
            variable="volume",
            values=[0.001, 0.002],
            points=[
                SweepPoint(value=0.001, success=True, standoff_height=0.01),
                SweepPoint(value=0.002, success=True, standoff_height=0.02),
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = runner.generate_report(result, tmpdir)
            assert json_path.exists()
            csv_path = json_path.parent / "sweep_report.csv"
            assert csv_path.exists()

            import json
            report = json.loads(json_path.read_text())
            assert report["n_points"] == 2
            assert report["n_success"] == 2
