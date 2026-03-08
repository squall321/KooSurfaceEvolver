"""Phase 9: Infrastructure tests (unit system, YAML config, CLI).

Tests:
- Unit system definitions and conversions
- YAML config loading and validation
- Sweep value generation
"""

import tempfile
from pathlib import Path

import numpy as np
import pytest
import yaml

from kse.core.units import UnitSystem, CGS, MM, get_unit_system
from kse.config.yaml_config import (
    KSEConfig,
    load_config,
    validate_config,
    generate_sweep_values,
    SweepConfig,
    PhysicsConfig,
    InputConfig,
    GeometryConfig,
    OptionsConfig,
    SolverConfig,
    OutputConfig,
)


# ---------------------------------------------------------------------------
# Phase 9A: Unit system
# ---------------------------------------------------------------------------

class TestUnitSystem:
    """Test unit system definitions."""

    def test_cgs_defaults(self):
        assert CGS.name == "CGS"
        assert CGS.gravity == 980.0
        assert CGS.default_tension == 480.0
        assert CGS.default_density == 9.0
        assert CGS.length == "cm"

    def test_mm_defaults(self):
        assert MM.name == "mm"
        assert MM.gravity == 9800.0
        assert MM.default_tension == 480.0
        assert MM.default_density == 0.009
        assert MM.length == "mm"

    def test_get_unit_system(self):
        assert get_unit_system("CGS") is CGS
        assert get_unit_system("cgs") is CGS
        assert get_unit_system("mm") is MM

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown"):
            get_unit_system("inches")

    def test_frozen(self):
        with pytest.raises(AttributeError):
            CGS.gravity = 100.0

    def test_bond_number_preserved(self):
        """Bond number ρGL²/σ should be equivalent between unit systems."""
        L_cm = 0.01
        L_mm = L_cm * 10
        Bo_cgs = CGS.default_density * CGS.gravity * L_cm**2 / CGS.default_tension
        Bo_mm = MM.default_density * MM.gravity * L_mm**2 / MM.default_tension
        np.testing.assert_allclose(Bo_cgs, Bo_mm, rtol=1e-10)


# ---------------------------------------------------------------------------
# Phase 9B: YAML config loading
# ---------------------------------------------------------------------------

class TestYAMLConfig:
    """Test YAML config loading and validation."""

    def _write_yaml(self, data: dict) -> Path:
        """Write a YAML dict to a temp file and return its path."""
        tmp = tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False)
        yaml.dump(data, tmp)
        tmp.close()
        return Path(tmp.name)

    def test_load_minimal(self):
        path = self._write_yaml({})
        config = load_config(path)
        assert config.unit_system is CGS
        assert config.physics.tension == 480.0
        assert config.physics.gravity == 980.0

    def test_load_mm_units(self):
        path = self._write_yaml({"units": "mm"})
        config = load_config(path)
        assert config.unit_system is MM
        assert config.physics.gravity == 9800.0
        assert config.physics.density == 0.009

    def test_load_physics(self):
        path = self._write_yaml({
            "physics": {
                "tension": 500.0,
                "density": 10.0,
                "contact_angle_bottom": 45.0,
            },
        })
        config = load_config(path)
        assert config.physics.tension == 500.0
        assert config.physics.density == 10.0
        assert config.physics.contact_angle_bottom == 45.0

    def test_load_step_assembly(self):
        path = self._write_yaml({
            "input": {
                "mode": "step_assembly",
                "step_file": "test.stp",
            },
        })
        config = load_config(path)
        assert config.input.mode == "step_assembly"
        assert config.input.step_file.endswith("test.stp")

    def test_load_void_options(self):
        path = self._write_yaml({
            "options": {
                "void": True,
                "void_radius": 0.1,
                "void_position": [0, 0, 0.5],
            },
        })
        config = load_config(path)
        assert config.options.void is True
        assert config.options.void_radius == 0.1
        assert config.options.void_position == [0, 0, 0.5]

    def test_load_sweep(self):
        path = self._write_yaml({
            "sweep": {
                "enabled": True,
                "variable": "volume",
                "values": [0.001, 0.002, 0.003],
            },
        })
        config = load_config(path)
        assert config.sweep.enabled is True
        assert config.sweep.values == [0.001, 0.002, 0.003]

    def test_validate_step_assembly_ok(self):
        path = self._write_yaml({
            "input": {"mode": "step_assembly", "step_file": "test.stp"},
        })
        config = load_config(path)
        warnings = validate_config(config)
        assert not any(w.startswith("ERROR") for w in warnings)

    def test_validate_step_assembly_missing(self):
        path = self._write_yaml({
            "input": {"mode": "step_assembly"},
        })
        config = load_config(path)
        warnings = validate_config(config)
        assert any("step_file" in w for w in warnings)

    def test_validate_step_bridge(self):
        path = self._write_yaml({
            "input": {"mode": "step_bridge", "step_file": "bridge.stp"},
        })
        config = load_config(path)
        warnings = validate_config(config)
        assert not any(w.startswith("ERROR") for w in warnings)

    def test_validate_step_array(self):
        path = self._write_yaml({
            "input": {"mode": "step_array", "step_file": "array.stp"},
        })
        config = load_config(path)
        warnings = validate_config(config)
        assert not any(w.startswith("ERROR") for w in warnings)

    def test_validate_negative_tension(self):
        path = self._write_yaml({
            "input": {"mode": "step_assembly", "step_file": "t.stp"},
            "physics": {"tension": -1.0},
        })
        config = load_config(path)
        warnings = validate_config(config)
        assert any("tension" in w for w in warnings)

    def test_validate_sweep_missing_values(self):
        path = self._write_yaml({
            "input": {"mode": "step_assembly", "step_file": "t.stp"},
            "sweep": {"enabled": True},
        })
        config = load_config(path)
        warnings = validate_config(config)
        assert any("sweep" in w.lower() for w in warnings)


class TestSweepValues:
    """Test sweep value generation."""

    def test_from_list(self):
        sweep = SweepConfig(enabled=True, values=[1.0, 2.0, 3.0])
        vals = generate_sweep_values(sweep)
        assert vals == [1.0, 2.0, 3.0]

    def test_from_range(self):
        sweep = SweepConfig(enabled=True, min=0.0, max=1.0, steps=5)
        vals = generate_sweep_values(sweep)
        assert len(vals) == 5
        np.testing.assert_allclose(vals[0], 0.0)
        np.testing.assert_allclose(vals[-1], 1.0)

    def test_empty(self):
        sweep = SweepConfig(enabled=True)
        vals = generate_sweep_values(sweep)
        assert vals == []
