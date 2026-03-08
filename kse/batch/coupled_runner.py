"""Coupled multi-solder simulation in a single SE instance."""

from pathlib import Path
from typing import Optional

import numpy as np

from ..core.stl_reader import STLReader
from ..core.surface_fitter import SurfaceFitter
from ..core.constraint_gen import ConstraintGenerator
from ..core.geometry_builder import GeometryBuilder
from ..core.fe_writer import FEWriter, SolderJointConfig
from ..solver.evolver_runner import EvolverRunner, EvolverResult
from ..solver.evolution_scripts import EvolutionStrategy, generate_runtime_commands
from .parallel_runner import JointDefinition


class CoupledRunner:
    """Run multiple solder joints in a single SE instance with interactions."""

    def __init__(
        self,
        evolver_path: Optional[str | Path] = None,
        config: Optional[SolderJointConfig] = None,
    ):
        self.evolver_path = evolver_path
        self.config = config or SolderJointConfig()
        self.fitter = SurfaceFitter()
        self.cgen = ConstraintGenerator()
        self.builder = GeometryBuilder()
        self.writer = FEWriter()

    def run_coupled(
        self,
        stl_A: str | Path,
        stl_B: str | Path,
        joints: list,
        output_dir: str | Path,
        group_distance: float = 0.0,
        timeout: int = 600,
    ) -> EvolverResult:
        """Run coupled simulation.

        If group_distance > 0, auto-group nearby joints.
        Otherwise, all joints run in one .fe file.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        reader_A = STLReader(stl_A)
        reader_B = STLReader(stl_B)

        if group_distance > 0:
            groups = self._group_joints(joints, group_distance)
        else:
            groups = [joints]

        results = []
        for gi, group in enumerate(groups):
            result = self._run_group(
                reader_A, reader_B, group, output_dir, gi, timeout
            )
            results.append(result)

        # Return combined result
        if len(results) == 1:
            return results[0]

        success = all(r.success for r in results)
        return EvolverResult(
            success=success,
            dump_file=results[0].dump_file if results else None,
            stdout="\n".join(r.stdout for r in results),
            stderr="\n".join(r.stderr for r in results),
            elapsed_seconds=sum(r.elapsed_seconds for r in results),
        )

    def _run_group(
        self,
        reader_A: STLReader,
        reader_B: STLReader,
        joints: list,
        output_dir: Path,
        group_id: int,
        timeout: int,
    ) -> EvolverResult:
        """Run a group of joints in a single .fe file."""
        geometries = []
        all_constraints = []
        all_boundaries = []

        # Each joint gets unique constraint/boundary IDs
        c_offset = 0
        b_offset = 0

        for ji, joint in enumerate(joints):
            patch_A = reader_A.extract_patch(joint.center_A, joint.radius)
            patch_B = reader_B.extract_patch(joint.center_B, joint.radius)

            fit_A = self.fitter.fit(patch_A)
            fit_B = self.fitter.fit(patch_B)

            c_a_id = c_offset + 1
            c_b_id = c_offset + 2
            rim_id = c_offset + 3
            bdry_id = b_offset + 1

            c_A = self.cgen.generate_surface_constraint(
                fit_A, c_a_id, joint.contact_angle_A, self.config.tension,
            )
            c_B = self.cgen.generate_surface_constraint(
                fit_B, c_b_id, joint.contact_angle_B, self.config.tension,
            )
            rim = self.cgen.generate_rim_constraint(fit_A, rim_id, joint.radius)
            bdry = self.cgen.generate_parametric_boundary(
                fit_B, bdry_id, joint.radius,
            )

            geom = self.builder.build(
                fit_A, fit_B, joint.radius, joint.volume,
                self.config.density, self.config.tension,
                constraint_A_id=c_a_id,
                constraint_B_id=c_b_id,
                rim_A_id=rim_id,
                boundary_B_id=bdry_id,
            )

            geometries.append(geom)
            all_constraints.extend([c_A, c_B, rim])
            all_boundaries.append(bdry)

            c_offset += 3
            b_offset += 1

        # Write coupled .fe file
        fe_path = output_dir / f"coupled_group_{group_id:04d}.fe"
        self.writer.write_coupled(
            fe_path, geometries, all_constraints, all_boundaries, self.config,
        )

        # Run SE
        runner = EvolverRunner(self.evolver_path)
        dump_path = fe_path.with_suffix(".dmp")
        strategy = self.config.strategy if self.config.strategy else EvolutionStrategy(preset="basic")
        commands = generate_runtime_commands(strategy, dump_path.name)
        return runner.run(fe_path, commands, dump_path, timeout)

    @staticmethod
    def _group_joints(
        joints: list, distance: float
    ) -> list:
        """Group joints by proximity."""
        n = len(joints)
        centers = np.array([
            (j.center_A + j.center_B) / 2.0 for j in joints
        ])

        visited = [False] * n
        groups = []

        for i in range(n):
            if visited[i]:
                continue
            group = [joints[i]]
            visited[i] = True

            # BFS for nearby joints
            queue = [i]
            while queue:
                ci = queue.pop(0)
                for j in range(n):
                    if visited[j]:
                        continue
                    d = np.linalg.norm(centers[ci] - centers[j])
                    if d <= distance:
                        visited[j] = True
                        group.append(joints[j])
                        queue.append(j)

            groups.append(group)

        return groups
