"""Phase 13: STEP E2E tests for fillet, bridge, and array pipelines.

Tests:
- Bridge assembly: 1 solder + 3 pads → .fe with N constraints
- Fillet assembly: solder + pad + wall → .fe with wall constraint
- Array assembly: 2 pads + 3 solders → multiple .fe files
- SE convergence for bridge and fillet .fe files
"""

import numpy as np
import pytest

from kse.core.step_pipeline import STEPPipeline, STEPPipelineConfig

from .helpers.step_generators import (
    generate_bridge_assembly_step,
    generate_fillet_assembly_step,
    generate_array_assembly_step,
)

# Skip if CadQuery is not available
pytest.importorskip("cadquery")

# Geometry constants (CGS units)
RADIUS = 0.010
PAD_RADIUS = 0.015
HEIGHT = 0.005
PAD_THICK = 0.002
TENSION = 480.0
DENSITY = 9.0
GRAVITY = 980.0


# ===========================================================================
# Bridge E2E
# ===========================================================================
class TestBridgeE2E:
    """End-to-end tests for bridge pad pipeline."""

    def _make_bridge_step(self, tmp_path):
        """Create a bridge STEP: box solder + 3 pads."""
        pad_positions = [(-0.01, 0.0), (0.0, 0.0), (0.01, 0.0)]
        return generate_bridge_assembly_step(
            solder_length=0.03,
            solder_width=0.01,
            solder_height=HEIGHT,
            pad_positions=pad_positions,
            pad_radius=PAD_RADIUS * 0.5,
            pad_thickness=PAD_THICK,
            output_path=tmp_path / "bridge.step",
        )

    def test_bridge_step_generates(self, tmp_path):
        """Bridge STEP file is generated successfully."""
        step_file = self._make_bridge_step(tmp_path)
        assert step_file.exists()
        assert step_file.stat().st_size > 100

    def test_bridge_pipeline_generates_fe(self, tmp_path):
        """Bridge pipeline generates a valid .fe file."""
        step_file = self._make_bridge_step(tmp_path)

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            joint_name="bridge_test",
            integration_level=2,
        )
        pipeline = STEPPipeline(config)
        fe_path = tmp_path / "output" / "bridge.fe"
        result = pipeline.run_bridge(step_file, fe_path)

        assert result.exists()
        text = result.read_text()
        assert "constraint 1" in text
        assert "vertices" in text
        assert "edges" in text
        assert "faces" in text
        assert "bodies" in text
        print(f"Bridge .fe: {len(text)} chars")

    def test_bridge_fe_has_multiple_constraints(self, tmp_path):
        """Bridge .fe should have constraints for each pad."""
        step_file = self._make_bridge_step(tmp_path)

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            joint_name="bridge_multi",
            integration_level=2,
        )
        pipeline = STEPPipeline(config)
        fe_path = tmp_path / "output" / "bridge.fe"
        pipeline.run_bridge(step_file, fe_path)

        text = fe_path.read_text()
        # Should have at least 2 constraints (one per pad that contacts solder)
        assert "constraint 1" in text
        assert "constraint 2" in text
        print(f"Bridge constraints found in .fe")

    def test_bridge_se_converges(self, tmp_path, evolver_path):
        """Bridge .fe converges in Surface Evolver."""
        from tests.validation.helpers.se_runner import run_kse_fe

        step_file = self._make_bridge_step(tmp_path)

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            contact_angle_bottom=30.0, contact_angle_top=30.0,
            joint_name="bridge_se",
            integration_level=2,
        )
        pipeline = STEPPipeline(config)
        fe_path = tmp_path / "build" / "bridge.fe"
        pipeline.run_bridge(step_file, fe_path)

        result = run_kse_fe(fe_path, evolver_path, tmp_path / "run", timeout=120)
        assert result.success, f"SE failed: {result.stderr[:500]}"
        assert result.energy is not None and result.energy > 0
        print(f"Bridge SE: energy={result.energy:.6e}, volume={result.volume}")


# ===========================================================================
# Fillet E2E
# ===========================================================================
class TestFilletE2E:
    """End-to-end tests for fillet pipeline."""

    def _make_fillet_step(self, tmp_path):
        """Create a fillet STEP: solder + pad + wall."""
        return generate_fillet_assembly_step(
            bottom_center=np.array([0.0, 0.0, 0.0]),
            solder_radius=RADIUS,
            solder_height=HEIGHT,
            pad_radius=PAD_RADIUS,
            pad_thickness=PAD_THICK,
            output_path=tmp_path / "fillet.step",
            wall_output_path=tmp_path / "wall.step",
        )

    def test_fillet_steps_generate(self, tmp_path):
        """Fillet STEP files generated: main assembly + wall."""
        assy_path, wall_path = self._make_fillet_step(tmp_path)
        assert assy_path.exists()
        assert wall_path.exists()

    def test_fillet_pipeline_generates_fe(self, tmp_path):
        """Fillet pipeline generates a valid .fe file with wall constraint."""
        assy_path, wall_path = self._make_fillet_step(tmp_path)

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            joint_name="fillet_test",
            integration_level=2,
            wall_step_paths=[str(wall_path)],
        )
        pipeline = STEPPipeline(config)
        fe_path = tmp_path / "output" / "fillet.fe"
        result = pipeline.run_fillet(assy_path, [wall_path], fe_path)

        assert result.exists()
        text = result.read_text()
        assert "constraint 1" in text
        assert "vertices" in text
        assert "bodies" in text
        print(f"Fillet .fe: {len(text)} chars")

    def test_fillet_se_converges(self, tmp_path, evolver_path):
        """Fillet .fe converges in SE."""
        from tests.validation.helpers.se_runner import run_kse_fe

        assy_path, wall_path = self._make_fillet_step(tmp_path)

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            contact_angle_bottom=30.0, contact_angle_top=30.0,
            joint_name="fillet_se",
            integration_level=2,
            wall_step_paths=[str(wall_path)],
        )
        pipeline = STEPPipeline(config)
        fe_path = tmp_path / "build" / "fillet.fe"
        pipeline.run_fillet(assy_path, [wall_path], fe_path)

        result = run_kse_fe(fe_path, evolver_path, tmp_path / "run", timeout=120)
        assert result.success, f"SE failed: {result.stderr[:500]}"
        assert result.energy is not None and result.energy > 0
        print(f"Fillet SE: energy={result.energy:.6e}, volume={result.volume}")


# ===========================================================================
# Array E2E
# ===========================================================================
class TestArrayE2E:
    """End-to-end tests for multi-joint array pipeline."""

    def _make_array_step(self, tmp_path, n_joints=3):
        """Create an array STEP: 2 pads + N solder cylinders."""
        return generate_array_assembly_step(
            n_joints=n_joints,
            pitch=0.04,
            solder_radius=RADIUS,
            solder_height=HEIGHT,
            pad_radius=PAD_RADIUS,
            pad_thickness=PAD_THICK,
            output_path=tmp_path / "array.step",
        )

    def test_array_step_generates(self, tmp_path):
        """Array STEP file generated successfully."""
        step_file = self._make_array_step(tmp_path)
        assert step_file.exists()
        assert step_file.stat().st_size > 100

    def test_array_pipeline_generates_multiple_fe(self, tmp_path):
        """Array pipeline produces one .fe per joint."""
        step_file = self._make_array_step(tmp_path, n_joints=3)

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            joint_name="array_test",
            integration_level=2,
        )
        pipeline = STEPPipeline(config)
        output_dir = tmp_path / "output"
        results = pipeline.run_array(step_file, output_dir)

        assert len(results) >= 2, f"Expected at least 2 .fe files, got {len(results)}"
        for fe_path in results:
            assert fe_path.exists()
            text = fe_path.read_text()
            assert "constraint" in text
            assert "vertices" in text
        print(f"Array: {len(results)} .fe files generated")

    def test_array_fe_converges(self, tmp_path, evolver_path):
        """At least one array .fe converges in SE."""
        from tests.validation.helpers.se_runner import run_kse_fe

        step_file = self._make_array_step(tmp_path, n_joints=2)

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            contact_angle_bottom=30.0, contact_angle_top=30.0,
            joint_name="array_se",
            integration_level=2,
        )
        pipeline = STEPPipeline(config)
        output_dir = tmp_path / "build"
        results = pipeline.run_array(step_file, output_dir)

        assert len(results) > 0, "No .fe files generated"

        # Test first joint
        fe_path = results[0]
        result = run_kse_fe(fe_path, evolver_path, tmp_path / "run", timeout=120)
        assert result.success, f"SE failed: {result.stderr[:500]}"
        assert result.energy is not None and result.energy > 0
        print(f"Array SE: energy={result.energy:.6e}, volume={result.volume}")


# ===========================================================================
# Coupled Array E2E
# ===========================================================================
class TestCoupledArrayE2E:
    """End-to-end tests for coupled multi-joint array pipeline."""

    def _make_array_step(self, tmp_path, n_joints=3, pitch=0.04):
        """Create an array STEP with given joint count and pitch."""
        return generate_array_assembly_step(
            n_joints=n_joints,
            pitch=pitch,
            solder_radius=RADIUS,
            solder_height=HEIGHT,
            pad_radius=PAD_RADIUS,
            pad_thickness=PAD_THICK,
            output_path=tmp_path / "array_coupled.step",
        )

    def test_coupled_all_in_one_group(self, tmp_path):
        """With large group_distance, all joints go in one .fe."""
        step_file = self._make_array_step(tmp_path, n_joints=2, pitch=0.03)

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            joint_name="coupled_all",
            integration_level=2,
        )
        pipeline = STEPPipeline(config)
        output_dir = tmp_path / "output"
        results = pipeline.run_array_coupled(step_file, output_dir, group_distance=1.0)

        assert len(results) == 1, f"Expected 1 coupled .fe, got {len(results)}"
        text = results[0].read_text()
        assert "constraint 1" in text
        assert "constraint 3" in text  # second joint's first constraint
        print(f"Coupled .fe: {len(text)} chars")

    def test_independent_with_zero_distance(self, tmp_path):
        """With group_distance=0, each joint is independent."""
        step_file = self._make_array_step(tmp_path, n_joints=2, pitch=0.04)

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            joint_name="indep",
            integration_level=2,
        )
        pipeline = STEPPipeline(config)
        output_dir = tmp_path / "output"
        results = pipeline.run_array_coupled(step_file, output_dir, group_distance=0.0)

        assert len(results) >= 2, f"Expected >=2 independent .fe, got {len(results)}"
        for fe in results:
            assert fe.exists()
        print(f"Independent: {len(results)} .fe files")

    def test_coupled_se_converges(self, tmp_path, evolver_path):
        """Coupled .fe converges in SE."""
        from tests.validation.helpers.se_runner import run_kse_fe

        step_file = self._make_array_step(tmp_path, n_joints=2, pitch=0.03)

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            contact_angle_bottom=30.0, contact_angle_top=30.0,
            joint_name="coupled_se",
            integration_level=2,
        )
        pipeline = STEPPipeline(config)
        output_dir = tmp_path / "build"
        results = pipeline.run_array_coupled(step_file, output_dir, group_distance=1.0)

        assert len(results) > 0, "No .fe files generated"
        result = run_kse_fe(results[0], evolver_path, tmp_path / "run", timeout=300)
        assert result.success, f"SE failed: {result.stderr[:500]}"
        assert result.energy is not None and result.energy > 0
        print(f"Coupled SE: energy={result.energy:.6e}")
