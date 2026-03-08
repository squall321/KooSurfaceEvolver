"""Shared fixtures and example registry for validation tests."""

import json
import math
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
EVOLVER_PATH = PROJECT_ROOT / "src" / "evolver"
EXAMPLES_DIR = PROJECT_ROOT / "examples"
VALIDATION_DIR = Path(__file__).parent
REFERENCE_DIR = VALIDATION_DIR / "reference_data"
STL_FIXTURES_DIR = VALIDATION_DIR / "stl_fixtures"

_PI = math.pi

# Example registry: parameters extracted from each original .fe file
EXAMPLE_REGISTRY = {
    "bga-1": {
        "fe_path": EXAMPLES_DIR / "bga" / "bga-1.fe",
        "tier": 1,
        "params": {
            "tension": 1.0,
            "density": 0.0,
            "gravity": 0.0,
            "radius": 0.10,
            "height": 0.12,
            "volume": 1.3 * _PI * 0.01 * 0.12,
            "contact_angle": 90.0,
            "x_offset": 0.0,
            "y_offset": 0.0,
            "tilt": 0.0,
            "n_segments": 6,
            "pad_tension": 1.0,  # pads use default tension (=S_TENSION=1)
        },
        "gogo_cmd": "gogo",
        "notes": "Default tension=1, no gravity. Pure area minimization.",
    },
    "bga-2": {
        "fe_path": EXAMPLES_DIR / "bga" / "bga-2.fe",
        "tier": 1,
        "params": {
            "tension": 1.0,
            "density": 0.0,
            "gravity": 0.0,
            "radius": 0.10,
            "height": 0.12,
            "volume": 1.3 * _PI * 0.01 * 0.12,
            "contact_angle": 90.0,
            "x_offset": 0.0,
            "y_offset": 0.0,
            "tilt": 0.0,
            "n_segments": 6,
            "pad_tension": 1.0,
        },
        "gogo_cmd": "gogo",
        "notes": "Same as bga-1 with no_refine on pad faces.",
    },
    "bga-3": {
        "fe_path": EXAMPLES_DIR / "bga" / "bga-3.fe",
        "tier": 1,
        "params": {
            "tension": 480.0,
            "density": 9.0,
            "gravity": 980.0,
            "radius": 0.10,
            "height": 0.12,
            "volume": 1.3 * _PI * 0.01 * 0.12,
            "contact_angle": 90.0,
            "x_offset": 0.0,
            "y_offset": 0.0,
            "tilt": 0.0,
            "n_segments": 6,
            "pad_tension": 0.0,  # pad faces have tension 0
        },
        "gogo_cmd": "gogo",
        "notes": "Coaxial + gravity. S_TENSION=480, SOLDER_DENSITY=9.",
    },
    "bga-5": {
        "fe_path": EXAMPLES_DIR / "bga" / "bga-5.fe",
        "tier": 2,
        "params": {
            "tension": 480.0,
            "density": 9.0,
            "gravity": 980.0,
            "radius": 0.10,
            "height": 0.12,
            "volume": 1.3 * _PI * 0.01 * 0.12,
            "contact_angle": 90.0,
            "x_offset": 0.0,
            "y_offset": 0.0,
            "tilt": 0.0,
            "n_segments": 6,
            "pad_tension": 0.0,
        },
        "gogo_cmd": "gogo",
        "notes": "Coaxial + gravity + optimizing height (fixed at 0.12 for KSE).",
    },
    "bga-7": {
        "fe_path": EXAMPLES_DIR / "bga" / "bga-7.fe",
        "tier": 2,
        "params": {
            "tension": 480.0,
            "density": 9.0,
            "gravity": 980.0,
            "radius": 0.10,
            "height": 0.12,
            "volume": 1.3 * _PI * 0.01 * 0.12,
            "contact_angle": 90.0,
            "x_offset": 0.03,
            "y_offset": 0.0,
            "tilt": 0.0,
            "n_segments": 6,
            "pad_tension": 0.0,
        },
        # Inline gogo because bga-7.fe requires xzforce.cmd which is missing
        "gogo_cmd": "u; g 3; r; g 5; r; g 5; hessian; hessian",
        "notes": "Non-coaxial with x_offset=0.03 (parameter offset in original .fe).",
    },
    "bga-12": {
        "fe_path": EXAMPLES_DIR / "bga" / "bga-12.fe",
        "tier": 2,
        "params": {
            "tension": 480.0,
            "density": 9.0,
            "gravity": 980.0,
            "radius": 0.10,
            "height": 0.12,
            "volume": 1.3 * _PI * 0.01 * 0.12,
            "contact_angle": 90.0,
            "x_offset": 0.0,
            "y_offset": 0.0,
            "tilt": 0.0,
            "n_segments": 6,
        },
        "gogo_cmd": "gogo",
        "notes": "KSE template reference. Boundary integrals, tilt=0 default.",
    },
    "cbga1": {
        "fe_path": EXAMPLES_DIR / "basic" / "cbga1.fe",
        "tier": 3,
        "params": {
            "tension": 430.0,
            "density": 8.6,
            "gravity": 980.0,
            "radius": 0.04,
            "height": 0.02,
            "volume": 1e-4,
            "contact_angle": 90.0,
            "x_offset": 0.0,
            "y_offset": 0.0,
            "tilt": 0.0,
            "n_segments": 6,
            "r_sphere": 0.04,
        },
        "gogo_cmd": "gogo",
        "notes": "Spherical contact surface. Requires curved surface fitting.",
    },
}

# Acceptance thresholds per tier
THRESHOLDS = {
    1: {"energy_rel": 0.01, "volume_rel": 0.001, "hausdorff_norm": 0.005},
    2: {"energy_rel": 0.05, "volume_rel": 0.005, "hausdorff_norm": 0.01},
    3: {"energy_rel": 0.10, "volume_rel": 0.01, "hausdorff_norm": 0.02},
}


@pytest.fixture
def evolver_path():
    """Path to the Surface Evolver binary."""
    if not EVOLVER_PATH.exists():
        pytest.skip("SE binary not found at src/evolver")
    return EVOLVER_PATH


@pytest.fixture
def examples_dir():
    return EXAMPLES_DIR


@pytest.fixture
def reference_dir():
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    return REFERENCE_DIR


@pytest.fixture
def stl_fixtures_dir():
    STL_FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    return STL_FIXTURES_DIR


def load_reference(example_name: str) -> dict:
    """Load cached reference data for an example."""
    ref_path = REFERENCE_DIR / f"{example_name}.ref.json"
    if not ref_path.exists():
        return None
    return json.loads(ref_path.read_text())


def save_reference(example_name: str, data: dict):
    """Save reference data for an example."""
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    ref_path = REFERENCE_DIR / f"{example_name}.ref.json"
    ref_path.write_text(json.dumps(data, indent=2))
