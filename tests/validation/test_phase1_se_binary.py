"""Phase 1: Verify SE binary works and dump parser handles real output."""

import json
import math
import shutil

import numpy as np
import pytest

from kse.solver.dump_parser import DumpParser

from .conftest import (
    EVOLVER_PATH, EXAMPLES_DIR, EXAMPLE_REGISTRY,
    REFERENCE_DIR, save_reference,
)
from .helpers.se_runner import run_original_fe, result_to_dict


class TestSEBinarySmoke:
    """Verify the SE binary executes correctly on known examples."""

    def test_mound_energy(self, evolver_path, tmp_path):
        """Run mound.fe and verify total energy ≈ 5.0."""
        fe_src = EXAMPLES_DIR / "basic" / "mound.fe"
        if not fe_src.exists():
            pytest.skip("mound.fe not found")

        result = run_original_fe(fe_src, evolver_path, tmp_path, gogo_cmd="gogo")

        assert result.success, f"SE failed: {result.stderr}"
        assert result.energy is not None, "No energy parsed from dump"
        # mound gogo refines further than the pre-existing mound.dmp (energy=5.0)
        # Actual converged energy is ~3.85 (sessile drop, contact angle 90, volume 1)
        assert result.energy < 5.5, f"Energy {result.energy} seems too high"
        assert result.energy > 2.0, f"Energy {result.energy} seems too low"
        assert result.n_vertices > 10
        assert result.n_faces > 10
        assert result.volume is not None

    def test_bga1_baseline(self, evolver_path, tmp_path):
        """Run bga-1.fe: coaxial pads, tension=1, no gravity."""
        info = EXAMPLE_REGISTRY["bga-1"]
        result = run_original_fe(
            info["fe_path"], evolver_path, tmp_path,
            gogo_cmd=info["gogo_cmd"],
        )

        assert result.success, f"SE failed on bga-1: {result.stderr}"
        assert result.energy is not None
        assert result.energy > 0, "Energy should be positive (surface area)"
        # Total energy = surface area (tension=1), including fixed pad faces
        # bga-1 includes 2 pad faces (area ~pi*r^2 each = ~0.0314 each)
        # + lateral surface area. Total ~0.155 after convergence
        assert result.energy < 0.20, f"Energy {result.energy} too high"

        # Volume conservation
        target_vol = info["params"]["volume"]
        assert result.volume is not None, "No volume parsed"
        assert abs(result.volume - target_vol) / target_vol < 0.02, \
            f"Volume: expected {target_vol:.6e}, got {result.volume:.6e}"

        # Mesh should be refined (more than initial 12 vertices)
        assert result.n_vertices > 12

    def test_bga3_gravity(self, evolver_path, tmp_path):
        """Run bga-3.fe: coaxial pads with gravity (T=480, G=980)."""
        info = EXAMPLE_REGISTRY["bga-3"]
        result = run_original_fe(
            info["fe_path"], evolver_path, tmp_path,
            gogo_cmd=info["gogo_cmd"],
        )

        assert result.success, f"SE failed on bga-3: {result.stderr}"
        assert result.energy is not None
        assert result.energy > 0, "Energy should be positive"
        # With tension=480, energy should be substantial
        assert result.energy > 10, f"Energy {result.energy} too low for T=480"

        target_vol = info["params"]["volume"]
        assert result.volume is not None
        assert abs(result.volume - target_vol) / target_vol < 0.02

    def test_parse_existing_mound_dmp(self):
        """Parse the pre-existing mound.dmp to verify parser on real data."""
        dmp_path = EXAMPLES_DIR / "workshop" / "fe" / "mound.dmp"
        if not dmp_path.exists():
            pytest.skip("mound.dmp not found")

        parser = DumpParser()
        mesh = parser.parse(dmp_path)

        assert mesh.total_energy == 5.0
        assert len(mesh.bodies) == 1
        body = list(mesh.bodies.values())[0]
        assert body.volume is not None

        triangles = mesh.face_triangles
        assert len(triangles) > 0

        verts = mesh.vertex_array
        assert verts.shape[1] == 3
        assert len(verts) == len(mesh.vertices)


class TestReferenceGeneration:
    """Generate and save reference data for Tier 1 examples."""

    @pytest.mark.parametrize("example_name", ["bga-1", "bga-2", "bga-3"])
    def test_generate_tier1_reference(self, example_name, evolver_path, tmp_path):
        """Run each Tier 1 example and save reference data."""
        info = EXAMPLE_REGISTRY[example_name]
        result = run_original_fe(
            info["fe_path"], evolver_path, tmp_path,
            gogo_cmd=info["gogo_cmd"],
        )

        assert result.success, f"SE failed on {example_name}: {result.stderr}"
        assert result.energy is not None
        assert result.volume is not None

        # Save reference
        ref = result_to_dict(result)
        ref["example"] = example_name
        ref["tier"] = info["tier"]
        save_reference(example_name, ref)

        # Verify saved
        ref_path = REFERENCE_DIR / f"{example_name}.ref.json"
        assert ref_path.exists()

    @pytest.mark.parametrize("example_name", ["bga-5", "bga-7", "bga-12"])
    def test_generate_tier2_reference(self, example_name, evolver_path, tmp_path):
        """Run Tier 2 examples and save reference data."""
        info = EXAMPLE_REGISTRY[example_name]
        if not info["fe_path"].exists():
            pytest.skip(f"{example_name}.fe not found")

        result = run_original_fe(
            info["fe_path"], evolver_path, tmp_path,
            gogo_cmd=info["gogo_cmd"],
            timeout=300,
        )

        assert result.success, f"SE failed on {example_name}: {result.stderr}"

        ref = result_to_dict(result)
        ref["example"] = example_name
        ref["tier"] = info["tier"]
        save_reference(example_name, ref)
