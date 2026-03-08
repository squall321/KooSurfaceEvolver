"""Parameter sweep runner for KSE.

Runs multiple simulations varying a single parameter (volume, contact angle,
tension, etc.) and collects results into a summary report.
"""

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class SweepPoint:
    """Result of a single sweep point."""

    value: float
    fe_path: Optional[Path] = None
    success: bool = False
    standoff_height: Optional[float] = None
    max_radius: Optional[float] = None
    volume: Optional[float] = None
    surface_area: Optional[float] = None
    error: Optional[str] = None


@dataclass
class SweepResult:
    """Complete sweep results."""

    variable: str
    values: list
    points: list
    unit_system: str = "CGS"


class SweepRunner:
    """Run parameter sweeps from a KSEConfig."""

    def run_sweep(self, base_config, sweep_values: Optional[list] = None) -> SweepResult:
        """Execute parameter sweep.

        Args:
            base_config: KSEConfig with sweep configuration.
            sweep_values: Override sweep values (if None, uses config.sweep).

        Returns:
            SweepResult with all sweep points.
        """
        from ..config.yaml_config import generate_sweep_values

        sweep = base_config.sweep
        variable = sweep.variable

        if sweep_values is None:
            sweep_values = generate_sweep_values(sweep)

        if not sweep_values:
            raise ValueError("No sweep values specified")

        points = []
        for i, val in enumerate(sweep_values):
            print(f"Sweep [{i+1}/{len(sweep_values)}] {variable}={val}")
            cfg = self._make_variant(base_config, variable, val, i)
            point = self._run_single(cfg, val)
            points.append(point)

        return SweepResult(
            variable=variable,
            values=sweep_values,
            points=points,
            unit_system=base_config.unit_system.name,
        )

    def generate_report(
        self, result: SweepResult, output_dir: str | Path,
    ) -> Path:
        """Generate CSV and JSON sweep report.

        Args:
            result: Completed SweepResult.
            output_dir: Directory for report files.

        Returns:
            Path to the JSON report.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # JSON report
        report = {
            "variable": result.variable,
            "unit_system": result.unit_system,
            "n_points": len(result.points),
            "n_success": sum(1 for p in result.points if p.success),
            "points": [],
        }
        for p in result.points:
            report["points"].append({
                "value": p.value,
                "success": p.success,
                "standoff_height": p.standoff_height,
                "max_radius": p.max_radius,
                "volume": p.volume,
                "surface_area": p.surface_area,
                "error": p.error,
            })

        json_path = output_dir / "sweep_report.json"
        json_path.write_text(json.dumps(report, indent=2))

        # CSV report
        csv_path = output_dir / "sweep_report.csv"
        with open(csv_path, "w") as f:
            f.write(f"{result.variable},success,standoff_height,max_radius,volume,surface_area\n")
            for p in result.points:
                f.write(
                    f"{p.value},{p.success},"
                    f"{p.standoff_height or ''},"
                    f"{p.max_radius or ''},"
                    f"{p.volume or ''},"
                    f"{p.surface_area or ''}\n"
                )

        print(f"Reports: {json_path}, {csv_path}")
        return json_path

    def _make_variant(self, base_config, variable: str, value: float, index: int):
        """Create a config variant with the sweep variable modified."""
        cfg = copy.deepcopy(base_config)

        # Map variable name to config field
        if variable == "volume":
            if cfg.geometry:
                cfg.geometry.volume = value
                cfg.geometry.target_volume = value
        elif variable == "contact_angle_bottom":
            cfg.physics.contact_angle_bottom = value
        elif variable == "contact_angle_top":
            cfg.physics.contact_angle_top = value
        elif variable == "contact_angle":
            cfg.physics.contact_angle_bottom = value
            cfg.physics.contact_angle_top = value
        elif variable == "tension":
            cfg.physics.tension = value
        elif variable == "density":
            cfg.physics.density = value
        elif variable == "radius":
            if cfg.geometry:
                cfg.geometry.radius = value
        else:
            raise ValueError(f"Unknown sweep variable: {variable}")

        # Unique output subdirectory per point
        base_dir = Path(cfg.output.directory)
        cfg.output.directory = str(base_dir / f"sweep_{index:03d}")
        cfg.output.joint_name = f"{cfg.output.joint_name}_sweep_{index:03d}"

        return cfg

    def _run_single(self, config, value: float) -> SweepPoint:
        """Run a single sweep point."""
        point = SweepPoint(value=value)

        try:
            output_dir = Path(config.output.directory)
            output_dir.mkdir(parents=True, exist_ok=True)

            fe_path = self._generate_fe(config)
            point.fe_path = fe_path

            if config.solver.fe_only:
                point.success = True
                return point

            # Run SE
            from ..solver.evolver_runner import EvolverRunner
            from ..solver.dump_parser import DumpParser
            from ..solver.evolution_scripts import EvolutionStrategy, generate_runtime_commands
            from ..solver.result_analyzer import ResultAnalyzer

            runner = EvolverRunner(config.solver.evolver_path)
            dump_path = fe_path.with_suffix(".dmp")
            strategy = EvolutionStrategy(preset="basic")
            commands = generate_runtime_commands(strategy, dump_path.name)
            result = runner.run(fe_path, commands, dump_path, config.solver.timeout)

            if not result.success:
                point.error = result.stderr[:200] if result.stderr else "SE failed"
                return point

            # Analyze
            parser = DumpParser()
            mesh = parser.parse(dump_path)
            analyzer = ResultAnalyzer()
            jr = analyzer.analyze_mesh(mesh.vertex_array, mesh.face_triangles)

            point.success = True
            point.standoff_height = jr.standoff_height
            point.max_radius = jr.max_radius
            point.volume = jr.volume
            point.surface_area = jr.surface_area

        except Exception as e:
            point.error = str(e)

        return point

    def _generate_fe(self, config) -> Path:
        """Generate .fe file for a single config."""
        mode = config.input.mode

        if mode in ("step_assembly", "step_bridge", "step_separate", "step_array"):
            from ..core.step_pipeline import STEPPipeline, STEPPipelineConfig
            cfg = STEPPipelineConfig(
                tension=config.physics.tension,
                density=config.physics.density,
                gravity=config.physics.gravity,
                contact_angle_bottom=config.physics.contact_angle_bottom,
                contact_angle_top=config.physics.contact_angle_top,
                target_volume=config.geometry.target_volume if config.geometry else None,
                joint_name=config.output.joint_name,
                void_enabled=getattr(config.options, 'void', False),
                void_radius=getattr(config.options, 'void_radius', 0.05),
                void_position=getattr(config.options, 'void_position', None),
            )
            output_path = Path(config.output.directory) / f"{config.output.joint_name}.fe"
            pipeline = STEPPipeline(cfg)

            if mode == "step_assembly":
                return pipeline.run_assembly(config.input.step_file, output_path)
            elif mode == "step_bridge":
                return pipeline.run_bridge(config.input.step_file, output_path)
            elif mode == "step_array":
                results = pipeline.run_array(
                    config.input.step_file, config.output.directory,
                )
                return results[0] if results else output_path
            else:
                return pipeline.run_separate(
                    config.input.step_solder,
                    config.input.step_bottom,
                    config.input.step_top,
                    output_path,
                )

        elif mode == "stl_complex":
            from ..core.complex_pipeline import ComplexSTLPipeline, ComplexPipelineConfig
            cfg = ComplexPipelineConfig(
                tension=config.physics.tension,
                density=config.physics.density,
                gravity=config.physics.gravity,
                contact_angle_bottom=config.physics.contact_angle_bottom,
                contact_angle_top=config.physics.contact_angle_top,
                target_volume=config.geometry.target_volume if config.geometry else None,
                joint_name=config.output.joint_name,
            )
            output_path = Path(config.output.directory) / f"{config.output.joint_name}.fe"
            pipeline = ComplexSTLPipeline(cfg)
            return pipeline.run(
                config.input.stl_bottom,
                config.input.stl_top,
                config.input.stl_solder,
                output_path,
            )

        else:
            raise ValueError(f"Sweep not supported for mode: {mode}")
