#!/usr/bin/env python3
"""KooSolderEvolver CLI - STL-based automatic solder joint simulation."""

import argparse
import sys
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(
        prog="kse",
        description="KooSolderEvolver: STL-based automatic solder joint simulation",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- run: single solder joint ---
    p_run = subparsers.add_parser("run", help="Run single solder joint simulation")
    p_run.add_argument("--stl-a", required=True, help="Bottom surface STL file")
    p_run.add_argument("--stl-b", required=True, help="Top surface STL file")
    p_run.add_argument("--center-a", required=True, help="Center on A: 'x,y,z'")
    p_run.add_argument("--center-b", required=True, help="Center on B: 'x,y,z'")
    p_run.add_argument("--radius", type=float, required=True, help="Pad radius (cm)")
    p_run.add_argument("--volume", type=float, required=True, help="Solder volume (cm^3)")
    p_run.add_argument("--output", default="output", help="Output directory")
    p_run.add_argument("--format", default="stl,vtk", help="Export formats (comma-separated)")
    p_run.add_argument("--tension", type=float, default=480.0, help="Surface tension (erg/cm^2)")
    p_run.add_argument("--density", type=float, default=9.0, help="Solder density (g/cm^3)")
    p_run.add_argument("--gravity", type=float, default=980.0, help="Gravity (cm/s^2)")
    p_run.add_argument("--contact-angle", type=float, default=30.0, help="Contact angle (deg)")
    p_run.add_argument("--evolver-path", default=None, help="Path to SE executable")
    p_run.add_argument("--fe-only", action="store_true", help="Generate .fe file only, don't run SE")
    p_run.add_argument("--timeout", type=int, default=300, help="Timeout in seconds")
    p_run.add_argument("--refine-steps", type=int, default=3,
                       help="SE mesh refinement steps (default 3 → ~8k tris; 2 → ~2k tris)")

    # --- batch: parallel independent joints ---
    p_batch = subparsers.add_parser("batch", help="Run batch of independent solder joints")
    p_batch.add_argument("--stl-a", required=True, help="Bottom surface STL")
    p_batch.add_argument("--stl-b", required=True, help="Top surface STL")
    p_batch.add_argument("--joints", required=True, help="CSV file with joint definitions")
    p_batch.add_argument("--output", default="output", help="Output directory")
    p_batch.add_argument("--format", default="stl,vtk", help="Export formats")
    p_batch.add_argument("--workers", type=int, default=0, help="Max parallel workers (0=auto)")
    p_batch.add_argument("--evolver-path", default=None, help="Path to SE executable")
    p_batch.add_argument("--timeout", type=int, default=300, help="Timeout per joint")

    # --- coupled: interacting joints ---
    p_coupled = subparsers.add_parser("coupled", help="Run coupled solder joints")
    p_coupled.add_argument("--stl-a", required=True, help="Bottom surface STL")
    p_coupled.add_argument("--stl-b", required=True, help="Top surface STL")
    p_coupled.add_argument("--joints", required=True, help="CSV file with joint definitions")
    p_coupled.add_argument("--output", default="output", help="Output directory")
    p_coupled.add_argument("--format", default="stl,vtk", help="Export formats")
    p_coupled.add_argument("--group-distance", type=float, default=0.0, help="Grouping distance")
    p_coupled.add_argument("--evolver-path", default=None, help="Path to SE executable")
    p_coupled.add_argument("--timeout", type=int, default=600, help="Timeout per group")

    # --- validate: test against known examples ---
    p_val = subparsers.add_parser("validate", help="Validate against known examples")
    p_val.add_argument("--example", default=None, help="Specific example to validate")
    p_val.add_argument("--all", action="store_true", help="Validate all examples")
    p_val.add_argument("--evolver-path", default=None, help="Path to SE executable")

    # --- yaml: YAML-configured pipeline ---
    p_yaml = subparsers.add_parser("yaml", help="Run from YAML configuration file")
    p_yaml.add_argument("config", help="Path to YAML configuration file")
    p_yaml.add_argument("--dry-run", action="store_true", help="Generate .fe only, skip SE")
    p_yaml.add_argument("--sweep", action="store_true", help="Run parameter sweep")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "run":
        return cmd_run(args)
    elif args.command == "batch":
        return cmd_batch(args)
    elif args.command == "coupled":
        return cmd_coupled(args)
    elif args.command == "validate":
        return cmd_validate(args)
    elif args.command == "yaml":
        return cmd_yaml(args)

    return 0


def _parse_point(s: str) -> np.ndarray:
    """Parse 'x,y,z' string to numpy array."""
    return np.array([float(x.strip()) for x in s.split(",")])


def cmd_run(args) -> int:
    """Execute single solder joint simulation."""
    from kse.core.stl_reader import STLReader
    from kse.core.surface_fitter import SurfaceFitter
    from kse.core.constraint_gen import ConstraintGenerator
    from kse.core.geometry_builder import GeometryBuilder
    from kse.core.fe_writer import FEWriter, SolderJointConfig
    from kse.solver.evolver_runner import EvolverRunner
    from kse.solver.dump_parser import DumpParser
    from kse.solver.evolution_scripts import EvolutionStrategy, generate_runtime_commands
    from kse.mesh.quality import assess_quality, assess_tet_quality
    from kse.batch.job_manager import SURFACE_EXPORT_FUNCS, SOLID_EXPORT_FUNCS

    center_a = _parse_point(args.center_a)
    center_b = _parse_point(args.center_b)
    formats = [f.strip() for f in args.format.split(",")]
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading STL files...")
    reader_a = STLReader(args.stl_a)
    reader_b = STLReader(args.stl_b)

    print(f"Extracting patches (radius={args.radius})...")
    patch_a = reader_a.extract_patch(center_a, args.radius)
    patch_b = reader_b.extract_patch(center_b, args.radius)

    print(f"Fitting surfaces...")
    fitter = SurfaceFitter()
    fit_a = fitter.fit(patch_a)
    fit_b = fitter.fit(patch_b)
    print(f"  Surface A: {fit_a.fit_type.value} (RMS={fit_a.residual_rms:.2e})")
    print(f"  Surface B: {fit_b.fit_type.value} (RMS={fit_b.residual_rms:.2e})")

    print(f"Generating constraints and initial geometry...")
    cgen = ConstraintGenerator()
    c_a = cgen.generate_surface_constraint(fit_a, 1, args.contact_angle, args.tension)
    c_b = cgen.generate_surface_constraint(fit_b, 2, args.contact_angle, args.tension)
    rim_a = cgen.generate_rim_constraint(fit_a, 3, args.radius)
    bdry_b = cgen.generate_parametric_boundary(fit_b, 1, args.radius)

    builder = GeometryBuilder()
    geom = builder.build(fit_a, fit_b, args.radius, args.volume, args.density, args.tension)

    config = SolderJointConfig(
        joint_name="solder_joint",
        tension=args.tension,
        density=args.density,
        gravity=args.gravity,
        radius=args.radius,
        volume=args.volume,
        contact_angle_A=args.contact_angle,
        contact_angle_B=args.contact_angle,
    )

    writer = FEWriter()
    fe_path = output_dir / "solder_joint.fe"
    writer.write_single(fe_path, geom, [c_a, c_b, rim_a], [bdry_b], config)
    print(f"Generated: {fe_path}")

    if args.fe_only:
        print("--fe-only: skipping SE execution.")
        return 0

    print(f"Running Surface Evolver...")
    runner = EvolverRunner(args.evolver_path)
    dump_path = fe_path.with_suffix(".dmp")
    strategy = EvolutionStrategy(preset="basic", n_refine=args.refine_steps)
    commands = generate_runtime_commands(strategy, dump_path.name)
    result = runner.run(fe_path, commands, dump_path, args.timeout)

    if not result.success:
        print(f"SE failed: {result.stderr[:200]}")
        return 1

    print(f"SE completed in {result.elapsed_seconds:.1f}s")

    # Parse and export
    parser = DumpParser()
    mesh = parser.parse(dump_path)
    vertices = mesh.vertex_array
    triangles = mesh.face_triangles

    quality = assess_quality(vertices, triangles)
    print(quality.summary())

    out_base = output_dir / "solder_joint"
    for fmt in formats:
        fmt_lower = fmt.lower().replace("-", "_")
        if fmt_lower in SURFACE_EXPORT_FUNCS:
            out = SURFACE_EXPORT_FUNCS[fmt_lower](vertices, triangles, out_base)
            print(f"Exported: {out}")

    solid_fmts = [f.lower().replace("-", "_") for f in formats
                  if f.lower().replace("-", "_") in SOLID_EXPORT_FUNCS]
    if solid_fmts:
        try:
            from kse.mesh.volume_mesher import generate_volume_mesh
            vol = generate_volume_mesh(vertices, triangles)
            tet_q = assess_tet_quality(vol.vertices, vol.tetrahedra)
            print(tet_q.summary())
            for fmt in solid_fmts:
                out = SOLID_EXPORT_FUNCS[fmt](vol.vertices, vol.tetrahedra, out_base)
                print(f"Exported: {out}")
        except ImportError as e:
            print(f"Solid export skipped: {e}")
        except Exception as e:
            print(f"Solid export failed: {e}")

    return 0


def cmd_batch(args) -> int:
    """Execute batch parallel simulations."""
    from kse.batch.parallel_runner import ParallelRunner, load_joints_csv
    from kse.batch.job_manager import JobManager
    from kse.core.fe_writer import SolderJointConfig

    joints = load_joints_csv(args.joints)
    formats = [f.strip() for f in args.format.split(",")]

    print(f"Loaded {len(joints)} joint definitions from {args.joints}")

    config = SolderJointConfig()
    manager = JobManager(args.evolver_path, config)

    results = manager.run_and_export(
        args.stl_a, args.stl_b, joints, args.output,
        formats=formats, mode="parallel",
        max_workers=args.workers, timeout=args.timeout,
    )

    n_ok = sum(1 for v in results.values() if v["fem_suitable"])
    print(f"Completed: {len(results)}/{len(joints)} joints")
    print(f"FEM suitable: {n_ok}/{len(results)}")

    return 0


def cmd_coupled(args) -> int:
    """Execute coupled simulation."""
    from kse.batch.parallel_runner import load_joints_csv
    from kse.batch.job_manager import JobManager
    from kse.core.fe_writer import SolderJointConfig

    joints = load_joints_csv(args.joints)
    formats = [f.strip() for f in args.format.split(",")]

    print(f"Loaded {len(joints)} joint definitions (coupled mode)")

    config = SolderJointConfig()
    manager = JobManager(args.evolver_path, config)

    results = manager.run_and_export(
        args.stl_a, args.stl_b, joints, args.output,
        formats=formats, mode="coupled",
        group_distance=args.group_distance, timeout=args.timeout,
    )

    print(f"Completed: {len(results)} result groups")
    return 0


def cmd_validate(args) -> int:
    """Validate against known examples by running A/B comparison."""
    import math
    import tempfile

    from kse.core.stl_reader import STLReader
    from kse.core.surface_fitter import SurfaceFitter
    from kse.core.constraint_gen import ConstraintGenerator
    from kse.core.geometry_builder import GeometryBuilder
    from kse.core.fe_writer import FEWriter, SolderJointConfig

    from tests.validation.conftest import EXAMPLE_REGISTRY, PROJECT_ROOT
    from tests.validation.helpers.stl_from_constraints import generate_flat_pad_stl
    from tests.validation.helpers.se_runner import run_original_fe, run_kse_fe
    from tests.validation.helpers.comparison import compare_results, THRESHOLDS

    evolver_path = Path(args.evolver_path) if args.evolver_path else PROJECT_ROOT / "src" / "evolver"
    if not evolver_path.exists():
        print(f"ERROR: SE binary not found at {evolver_path}")
        return 1

    # Supported examples for CLI validation
    available = ["bga-1", "bga-3", "bga-7"]

    if args.example:
        if args.example not in available:
            print(f"Unknown example: {args.example}")
            print(f"Available: {', '.join(available)}")
            return 1
        names = [args.example]
    elif args.all:
        names = available
    else:
        print(f"Available examples: {', '.join(available)}")
        print("Use --example <name> or --all")
        return 0

    def _build_kse_fe(tmp_dir, params):
        """Run full KSE pipeline: generate STL pads → .fe."""
        r = params["radius"]
        h = params["height"]
        x_off = params.get("x_offset", 0.0)
        y_off = params.get("y_offset", 0.0)
        n_seg = params.get("n_segments", 6)

        stl_dir = tmp_dir / "stls"
        stl_dir.mkdir(parents=True, exist_ok=True)

        center_a = np.array([0.0, 0.0, 0.0])
        center_b = np.array([x_off, y_off, h])

        generate_flat_pad_stl(center_a, r, output_path=stl_dir / "bottom.stl")
        generate_flat_pad_stl(center_b, r, output_path=stl_dir / "top.stl")

        reader_a = STLReader(stl_dir / "bottom.stl")
        reader_b = STLReader(stl_dir / "top.stl")
        patch_a = reader_a.extract_patch(center_a, r)
        patch_b = reader_b.extract_patch(center_b, r)

        fitter = SurfaceFitter()
        fit_a = fitter.fit(patch_a)
        fit_b = fitter.fit(patch_b)

        cgen = ConstraintGenerator()
        c_a = cgen.generate_surface_constraint(
            fit_a, 1, contact_angle=params["contact_angle"],
            tension=params["tension"], solder_density=params["density"],
            gravity=params["gravity"], use_boundary_integrals=False,
        )
        c_b = cgen.generate_surface_constraint(
            fit_b, 2, contact_angle=params["contact_angle"],
            tension=params["tension"], solder_density=params["density"],
            gravity=params["gravity"], use_boundary_integrals=False,
        )
        rim = cgen.generate_rim_constraint(fit_a, 3, r)
        bdry = cgen.generate_parametric_boundary(
            fit_b, 1, r,
            solder_density=params["density"],
            gravity=params["gravity"],
        )

        builder = GeometryBuilder(n_segments=n_seg)
        geom = builder.build(fit_a, fit_b, r, params["volume"])

        config = SolderJointConfig(
            tension=params["tension"], density=params["density"],
            gravity=params["gravity"], radius=r, volume=params["volume"],
            contact_angle_A=params["contact_angle"],
            contact_angle_B=params["contact_angle"],
        )

        writer = FEWriter()
        fe_path = tmp_dir / "kse_output.fe"
        writer.write_single(fe_path, geom, [c_a, c_b, rim], [bdry], config)
        return fe_path

    all_pass = True
    for name in names:
        info = EXAMPLE_REGISTRY[name]
        params = info["params"]
        tier = info["tier"]

        print(f"\n{'='*50}")
        print(f"  {name} (Tier {tier})")
        print(f"{'='*50}")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            # Run original .fe
            print("  Running original .fe ... ", end="", flush=True)
            ref = run_original_fe(
                info["fe_path"], evolver_path, tmp / "ref",
                gogo_cmd=info["gogo_cmd"], timeout=300,
            )
            if not ref.success:
                print(f"FAILED ({ref.stderr})")
                all_pass = False
                continue
            print("OK")

            # Build and run KSE .fe
            print("  Building KSE .fe ... ", end="", flush=True)
            kse_fe = _build_kse_fe(tmp / "kse_build", params)
            print("OK")

            print("  Running KSE .fe ... ", end="", flush=True)
            kse = run_kse_fe(kse_fe, evolver_path, tmp / "kse_run", timeout=300)
            if not kse.success:
                print(f"FAILED ({kse.stderr})")
                all_pass = False
                continue
            print("OK")

            # Adjust ref energy for pad tension
            r = params["radius"]
            pad_tension = params.get("pad_tension", 0.0)
            pad_energy = 2 * math.pi * r**2 * pad_tension

            ref_data = {
                "energy": ref.energy - pad_energy,
                "volume": ref.volume,
                "vertex_positions": ref.vertex_positions,
                "face_triangles": ref.face_triangles,
                "free_face_triangles": ref.free_face_triangles,
            }
            kse_data = {
                "energy": kse.energy,
                "volume": kse.volume,
                "vertex_positions": kse.vertex_positions,
                "face_triangles": kse.face_triangles,
                "free_face_triangles": kse.free_face_triangles,
            }

            result = compare_results(ref_data, kse_data, tier, characteristic_length=r)
            print(result.summary())

            if not result.pass_all:
                all_pass = False

    print(f"\n{'='*50}")
    if all_pass:
        print("  ALL PASSED")
    else:
        print("  SOME FAILED")
    print(f"{'='*50}")

    return 0 if all_pass else 1


def cmd_yaml(args) -> int:
    """Execute pipeline from YAML configuration."""
    from kse.config.yaml_config import load_config, validate_config
    from kse.core.fe_writer import SolderJointConfig
    from kse.core.units import CGS

    config = load_config(args.config)
    warnings = validate_config(config)

    for w in warnings:
        print(w)
    if any(w.startswith("ERROR") for w in warnings):
        return 1

    if args.dry_run:
        config.solver.fe_only = True

    output_dir = Path(config.output.directory)
    output_dir.mkdir(parents=True, exist_ok=True)

    mode = config.input.mode
    print(f"Mode: {mode} | Units: {config.unit_system.name}")
    print(f"Physics: sigma={config.physics.tension}, rho={config.physics.density}, G={config.physics.gravity}")

    # Parameter sweep mode
    if args.sweep:
        if not config.sweep or not config.sweep.enabled:
            print("ERROR: --sweep requires sweep.enabled=true in YAML config")
            return 1
        from kse.batch.sweep_runner import SweepRunner
        runner = SweepRunner()
        result = runner.run_sweep(config)
        report_path = runner.generate_report(result, output_dir)
        n_ok = sum(1 for p in result.points if p.success)
        print(f"Sweep complete: {n_ok}/{len(result.points)} succeeded")
        print(f"Report: {report_path}")
        return 0

    if mode == "step_assembly":
        return _yaml_step_assembly(config)
    elif mode == "step_separate":
        return _yaml_step_separate(config)
    elif mode == "step_bridge":
        return _yaml_step_bridge(config)
    elif mode == "step_array":
        return _yaml_step_array(config)
    elif mode == "stl_complex":
        return _yaml_stl_complex(config)
    elif mode == "parametric":
        return _yaml_parametric(config)
    else:
        print(f"Unknown mode: {mode}")
        return 1


def _build_step_config(config):
    """Build STEPPipelineConfig from YAML config."""
    from kse.core.step_pipeline import STEPPipelineConfig
    return STEPPipelineConfig(
        tension=config.physics.tension,
        density=config.physics.density,
        gravity=config.physics.gravity,
        contact_angle_bottom=config.physics.contact_angle_bottom,
        contact_angle_top=config.physics.contact_angle_top,
        tessellation_tolerance=config.options.tessellation_tolerance,
        angular_tolerance=config.options.angular_tolerance,
        contact_distance_tol=config.options.contact_distance_tol,
        pad_extract_margin=config.options.pad_extract_margin,
        on_surface_tol=config.options.on_surface_tol,
        target_volume=config.geometry.target_volume,
        joint_name=config.output.joint_name,
        void_enabled=config.options.void,
        void_radius=config.options.void_radius,
        void_position=config.options.void_position,
    )


def _yaml_step_assembly(config) -> int:
    """Run STEP assembly pipeline from YAML config."""
    from kse.core.step_pipeline import STEPPipeline

    cfg = _build_step_config(config)

    output_path = Path(config.output.directory) / f"{config.output.joint_name}.fe"
    pipeline = STEPPipeline(cfg)
    result = pipeline.run_assembly(config.input.step_file, output_path)
    print(f"Generated: {result}")

    if not config.solver.fe_only:
        return _run_se_and_export(result, config)
    return 0


def _yaml_step_separate(config) -> int:
    """Run STEP separate files pipeline from YAML config."""
    from kse.core.step_pipeline import STEPPipeline

    cfg = _build_step_config(config)

    output_path = Path(config.output.directory) / f"{config.output.joint_name}.fe"
    pipeline = STEPPipeline(cfg)
    result = pipeline.run_separate(
        config.input.step_solder,
        config.input.step_bottom,
        config.input.step_top,
        output_path,
    )
    print(f"Generated: {result}")

    if not config.solver.fe_only:
        return _run_se_and_export(result, config)
    return 0


def _yaml_step_bridge(config) -> int:
    """Run STEP bridge pad pipeline from YAML config."""
    from kse.core.step_pipeline import STEPPipeline

    cfg = _build_step_config(config)

    output_path = Path(config.output.directory) / f"{config.output.joint_name}.fe"
    pipeline = STEPPipeline(cfg)
    result = pipeline.run_bridge(config.input.step_file, output_path)
    print(f"Generated: {result}")

    if not config.solver.fe_only:
        return _run_se_and_export(result, config)
    return 0


def _yaml_step_array(config) -> int:
    """Run STEP multi-joint array pipeline from YAML config."""
    from kse.core.step_pipeline import STEPPipeline

    cfg = _build_step_config(config)

    pipeline = STEPPipeline(cfg)
    results = pipeline.run_array(
        config.input.step_file, config.output.directory,
    )
    print(f"Generated {len(results)} .fe files:")
    for r in results:
        print(f"  {r}")

    if not config.solver.fe_only:
        for fe_path in results:
            _run_se_and_export(fe_path, config)
    return 0


def _yaml_stl_complex(config) -> int:
    """Run complex STL pipeline from YAML config."""
    from kse.core.complex_pipeline import ComplexSTLPipeline, ComplexPipelineConfig

    cfg = ComplexPipelineConfig(
        tension=config.physics.tension,
        density=config.physics.density,
        gravity=config.physics.gravity,
        contact_angle_bottom=config.physics.contact_angle_bottom,
        contact_angle_top=config.physics.contact_angle_top,
        smooth_iterations=config.options.smooth_iterations,
        max_edge_length=config.options.max_edge_length,
        pad_extract_margin=config.options.pad_extract_margin,
        on_surface_tol=config.options.on_surface_tol,
        target_volume=config.geometry.target_volume,
        joint_name=config.output.joint_name,
    )

    output_path = Path(config.output.directory) / f"{config.output.joint_name}.fe"
    pipeline = ComplexSTLPipeline(cfg)
    result = pipeline.run(
        config.input.stl_bottom,
        config.input.stl_top,
        config.input.stl_solder,
        output_path,
    )
    print(f"Generated: {result}")

    if not config.solver.fe_only:
        return _run_se_and_export(result, config)
    return 0


def _yaml_parametric(config) -> int:
    """Run parametric (standard) pipeline from YAML config."""
    from kse.core.stl_reader import STLReader
    from kse.core.surface_fitter import SurfaceFitter
    from kse.core.constraint_gen import ConstraintGenerator
    from kse.core.geometry_builder import GeometryBuilder
    from kse.core.fe_writer import FEWriter, SolderJointConfig

    center_a = np.array(config.input.center_a, dtype=float)
    center_b = np.array(config.input.center_b, dtype=float)
    radius = config.geometry.radius
    volume = config.geometry.volume

    reader_a = STLReader(config.input.stl_a)
    reader_b = STLReader(config.input.stl_b)

    patch_a = reader_a.extract_patch(center_a, radius)
    patch_b = reader_b.extract_patch(center_b, radius)

    fitter = SurfaceFitter()
    fit_a = fitter.fit(patch_a)
    fit_b = fitter.fit(patch_b)

    cgen = ConstraintGenerator()
    c_a = cgen.generate_surface_constraint(
        fit_a, 1, config.physics.contact_angle_bottom, config.physics.tension,
    )
    c_b = cgen.generate_surface_constraint(
        fit_b, 2, config.physics.contact_angle_top, config.physics.tension,
    )
    rim_a = cgen.generate_rim_constraint(fit_a, 3, radius)
    bdry_b = cgen.generate_parametric_boundary(fit_b, 1, radius)

    builder = GeometryBuilder()
    geom = builder.build(
        fit_a, fit_b, radius, volume,
        config.physics.density, config.physics.tension,
    )

    fe_config = SolderJointConfig(
        joint_name=config.output.joint_name,
        tension=config.physics.tension,
        density=config.physics.density,
        gravity=config.physics.gravity,
        radius=radius,
        volume=volume,
        contact_angle_A=config.physics.contact_angle_bottom,
        contact_angle_B=config.physics.contact_angle_top,
        unit_system=config.unit_system,
    )

    output_path = Path(config.output.directory) / f"{config.output.joint_name}.fe"
    writer = FEWriter()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer.write_single(output_path, geom, [c_a, c_b, rim_a], [bdry_b], fe_config)
    print(f"Generated: {output_path}")

    if not config.solver.fe_only:
        return _run_se_and_export(output_path, config)
    return 0


def _run_se_and_export(fe_path, config) -> int:
    """Run SE and export results."""
    from kse.solver.evolver_runner import EvolverRunner
    from kse.solver.dump_parser import DumpParser
    from kse.solver.evolution_scripts import EvolutionStrategy, generate_runtime_commands, _apply_preset
    from kse.mesh.quality import assess_quality, assess_tet_quality
    from kse.batch.job_manager import SURFACE_EXPORT_FUNCS, SOLID_EXPORT_FUNCS

    fe_path = Path(fe_path)
    print(f"Running Surface Evolver...")
    runner = EvolverRunner(config.solver.evolver_path)
    dump_path = fe_path.with_suffix(".dmp")

    # Use strategy-based commands if available
    strategy = getattr(config.solver, 'strategy', None)
    if strategy:
        # Fill inherited values
        if strategy.n_refine is None:
            strategy.n_refine = config.solver.refine_steps
        if strategy.n_gradient is None:
            strategy.n_gradient = config.solver.gradient_steps
        if strategy.use_hessian is None:
            strategy.use_hessian = config.solver.use_hessian
        strategy = _apply_preset(strategy)
    else:
        strategy = EvolutionStrategy(preset="basic")
    commands = generate_runtime_commands(strategy, dump_path.name)

    result = runner.run(fe_path, commands, dump_path, config.solver.timeout)

    if not result.success:
        print(f"SE failed: {result.stderr[:200]}")
        return 1

    print(f"SE completed in {result.elapsed_seconds:.1f}s")

    parser = DumpParser()
    mesh = parser.parse(dump_path)
    vertices = mesh.vertex_array
    triangles = mesh.face_triangles

    quality = assess_quality(vertices, triangles)
    print(quality.summary())

    # Analyze results
    try:
        from kse.solver.result_analyzer import ResultAnalyzer
        analyzer = ResultAnalyzer()
        jr = analyzer.analyze_mesh(vertices, triangles)
        print(f"Standoff height: {jr.standoff_height:.6f} {config.unit_system.length}")
        print(f"Max radius: {jr.max_radius:.6f} {config.unit_system.length}")
    except ImportError:
        pass

    out_base = fe_path.parent / fe_path.stem

    # Surface exports
    for fmt in config.output.formats:
        fmt_lower = fmt.lower().replace("-", "_")
        if fmt_lower in SURFACE_EXPORT_FUNCS:
            out = SURFACE_EXPORT_FUNCS[fmt_lower](vertices, triangles, out_base)
            print(f"Exported: {out}")

    # Solid exports (volume mesh)
    solid_fmts = [f.lower().replace("-", "_") for f in config.output.formats
                  if f.lower().replace("-", "_") in SOLID_EXPORT_FUNCS]
    if solid_fmts:
        try:
            from kse.mesh.volume_mesher import generate_volume_mesh
            vol = generate_volume_mesh(vertices, triangles)
            tet_q = assess_tet_quality(vol.vertices, vol.tetrahedra)
            print(tet_q.summary())
            for fmt in solid_fmts:
                out = SOLID_EXPORT_FUNCS[fmt](vol.vertices, vol.tetrahedra, out_base)
                print(f"Exported: {out}")
        except ImportError as e:
            print(f"Solid export skipped: {e}")
        except Exception as e:
            print(f"Solid export failed: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
