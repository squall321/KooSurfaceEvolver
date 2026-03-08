"""Parallel batch execution of independent solder joint simulations."""

import json
import multiprocessing
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from ..core.stl_reader import STLReader
from ..core.surface_fitter import SurfaceFitter
from ..core.constraint_gen import ConstraintGenerator
from ..core.geometry_builder import GeometryBuilder
from ..core.fe_writer import FEWriter, SolderJointConfig
from ..solver.evolver_runner import EvolverRunner, EvolverResult
from ..solver.dump_parser import DumpParser
from ..solver.evolution_scripts import EvolutionStrategy, generate_runtime_commands


@dataclass
class JointDefinition:
    """Definition of a single solder joint."""

    center_A: np.ndarray    # (3,) center on surface A
    center_B: np.ndarray    # (3,) center on surface B
    radius: float           # pad radius
    volume: float           # solder volume
    contact_angle_A: float = 30.0
    contact_angle_B: float = 30.0
    name: str = ""


@dataclass
class BatchResult:
    """Result from a batch of solder joint simulations."""

    n_total: int
    n_success: int
    n_failed: int
    results: list             # list of (JointDefinition, EvolverResult) tuples
    total_elapsed: float
    output_dir: Path


class ParallelRunner:
    """Run multiple independent solder joints in parallel."""

    def __init__(
        self,
        evolver_path: Optional[str | Path] = None,
        max_workers: int = 0,
        config: Optional[SolderJointConfig] = None,
    ):
        self.evolver_path = evolver_path
        self.max_workers = max_workers or max(1, multiprocessing.cpu_count() - 1)
        self.config = config or SolderJointConfig()
        self.fitter = SurfaceFitter()
        self.cgen = ConstraintGenerator()
        self.builder = GeometryBuilder()
        self.writer = FEWriter()

    def run_batch(
        self,
        stl_A: str | Path,
        stl_B: str | Path,
        joints: list,
        output_dir: str | Path,
        timeout_per_joint: int = 300,
    ) -> BatchResult:
        """Run batch of solder joint simulations.

        Args:
            stl_A: Path to bottom surface STL.
            stl_B: Path to top surface STL.
            joints: List of JointDefinition objects.
            output_dir: Directory for output files.
            timeout_per_joint: Max seconds per joint.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        start = time.time()

        # Prepare all jobs
        reader_A = STLReader(stl_A)
        reader_B = STLReader(stl_B)

        jobs = []
        for i, joint in enumerate(joints):
            name = joint.name or f"joint_{i:04d}"
            joint_dir = output_dir / name
            joint_dir.mkdir(parents=True, exist_ok=True)

            try:
                fe_path = self._prepare_job(
                    reader_A, reader_B, joint, joint_dir, name
                )
                jobs.append((i, joint, fe_path, joint_dir, timeout_per_joint))
            except Exception as e:
                print(f"Failed to prepare joint {name}: {e}")
                jobs.append((i, joint, None, joint_dir, timeout_per_joint))

        # Run in parallel
        results = []
        if self.max_workers == 1:
            for job in jobs:
                results.append(self._run_single_job(job))
        else:
            with multiprocessing.Pool(self.max_workers) as pool:
                results = pool.map(self._run_single_job_wrapper, jobs)

        # Collect results
        n_success = sum(1 for _, r in results if r and r.success)
        elapsed = time.time() - start

        return BatchResult(
            n_total=len(joints),
            n_success=n_success,
            n_failed=len(joints) - n_success,
            results=results,
            total_elapsed=elapsed,
            output_dir=output_dir,
        )

    def _prepare_job(
        self,
        reader_A: STLReader,
        reader_B: STLReader,
        joint: JointDefinition,
        job_dir: Path,
        name: str,
    ) -> Path:
        """Prepare a single job: extract patches, fit, build geometry, write .fe."""
        # Extract patches
        patch_A = reader_A.extract_patch(joint.center_A, joint.radius)
        patch_B = reader_B.extract_patch(joint.center_B, joint.radius)

        # Fit surfaces
        fit_A = self.fitter.fit(patch_A)
        fit_B = self.fitter.fit(patch_B)

        # Generate constraints
        c_A = self.cgen.generate_surface_constraint(
            fit_A, 1, joint.contact_angle_A, self.config.tension,
        )
        c_B = self.cgen.generate_surface_constraint(
            fit_B, 2, joint.contact_angle_B, self.config.tension,
        )
        rim_A = self.cgen.generate_rim_constraint(fit_A, 3, joint.radius)
        bdry_B = self.cgen.generate_parametric_boundary(
            fit_B, 1, joint.radius,
        )

        # Build geometry
        geom = self.builder.build(
            fit_A, fit_B, joint.radius, joint.volume,
            self.config.density, self.config.tension,
        )

        # Write .fe
        config = SolderJointConfig(
            joint_name=name,
            tension=self.config.tension,
            density=self.config.density,
            gravity=self.config.gravity,
            radius=joint.radius,
            volume=joint.volume,
            contact_angle_A=joint.contact_angle_A,
            contact_angle_B=joint.contact_angle_B,
        )

        fe_path = job_dir / f"{name}.fe"
        self.writer.write_single(
            fe_path, geom,
            constraints=[c_A, c_B, rim_A],
            boundaries=[bdry_B],
            config=config,
        )

        return fe_path

    def _run_single_job(self, job_args):
        """Run a single SE job."""
        idx, joint, fe_path, job_dir, timeout = job_args

        if fe_path is None:
            return (joint, EvolverResult(
                success=False, dump_file=None,
                stdout="", stderr="Job preparation failed",
                elapsed_seconds=0,
            ))

        try:
            runner = EvolverRunner(self.evolver_path)
            dump_path = job_dir / f"{fe_path.stem}.dmp"
            strategy = self.config.strategy if self.config.strategy else EvolutionStrategy(preset="basic")
            commands = generate_runtime_commands(strategy, dump_path.name)
            result = runner.run(fe_path, commands, dump_path, timeout)
            return (joint, result)
        except Exception as e:
            return (joint, EvolverResult(
                success=False, dump_file=None,
                stdout="", stderr=str(e),
                elapsed_seconds=0,
            ))

    @staticmethod
    def _run_single_job_wrapper(args):
        """Wrapper for multiprocessing (needs to be picklable)."""
        # Can't use instance method directly in Pool.map
        idx, joint, fe_path, job_dir, timeout = args
        if fe_path is None:
            return (joint, EvolverResult(
                success=False, dump_file=None,
                stdout="", stderr="Job preparation failed",
                elapsed_seconds=0,
            ))
        try:
            runner = EvolverRunner()
            dump_path = job_dir / f"{fe_path.stem}.dmp"
            strategy = EvolutionStrategy(preset="basic")
            commands = generate_runtime_commands(strategy, dump_path.name)
            result = runner.run(fe_path, commands, dump_path, timeout)
            return (joint, result)
        except Exception as e:
            return (joint, EvolverResult(
                success=False, dump_file=None,
                stdout="", stderr=str(e),
                elapsed_seconds=0,
            ))


def load_joints_csv(csv_path: str | Path) -> list:
    """Load joint definitions from CSV file.

    Expected columns:
        center_ax, center_ay, center_az,
        center_bx, center_by, center_bz,
        radius, volume[, contact_angle_a, contact_angle_b, name]
    """
    import csv

    joints = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            jd = JointDefinition(
                center_A=np.array([
                    float(row["center_ax"]),
                    float(row["center_ay"]),
                    float(row["center_az"]),
                ]),
                center_B=np.array([
                    float(row["center_bx"]),
                    float(row["center_by"]),
                    float(row["center_bz"]),
                ]),
                radius=float(row["radius"]),
                volume=float(row["volume"]),
                contact_angle_A=float(row.get("contact_angle_a", 30.0)),
                contact_angle_B=float(row.get("contact_angle_b", 30.0)),
                name=row.get("name", f"joint_{i:04d}"),
            )
            joints.append(jd)

    return joints
