"""YAML-based configuration for KSE pipelines.

Loads and validates a YAML configuration file that specifies input mode,
physical parameters, solver options, output formats, and optional features
like void modeling, fillet prediction, and parameter sweeps.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from ..core.units import UnitSystem, get_unit_system, CGS


@dataclass
class PhysicsConfig:
    """Physical parameters for solder simulation."""

    tension: float = 480.0
    density: float = 9.0
    gravity: float = 980.0
    contact_angle_bottom: float = 30.0
    contact_angle_top: float = 30.0


@dataclass
class InputConfig:
    """Input file specification."""

    mode: str = "step_assembly"  # step_assembly | step_separate | step_bridge | step_array | stl_complex | parametric
    # step_assembly
    step_file: Optional[str] = None
    # step_separate
    step_solder: Optional[str] = None
    step_bottom: Optional[str] = None
    step_top: Optional[str] = None
    # stl_complex
    stl_solder: Optional[str] = None
    stl_bottom: Optional[str] = None
    stl_top: Optional[str] = None
    # parametric (centers/radius specified in geometry)
    stl_a: Optional[str] = None
    stl_b: Optional[str] = None
    center_a: Optional[list] = None
    center_b: Optional[list] = None


@dataclass
class GeometryConfig:
    """Geometric parameters (parametric mode only)."""

    pad_shape: str = "circular"  # circular | rectangular
    radius: Optional[float] = None
    side_x: Optional[float] = None
    side_y: Optional[float] = None
    volume: Optional[float] = None
    target_volume: Optional[float] = None


@dataclass
class OptionsConfig:
    """Optional features."""

    void: bool = False
    void_radius: float = 0.05
    void_position: Optional[list] = None
    fillet: bool = False
    fillet_walls: list = field(default_factory=list)
    smooth_iterations: int = 0
    max_edge_length: float = 0.0
    tessellation_tolerance: float = 0.001
    angular_tolerance: float = 0.1
    contact_distance_tol: float = 1e-4
    pad_extract_margin: float = 1.5
    on_surface_tol: Optional[float] = None


@dataclass
class StrategyConfig:
    """Evolution strategy configuration for SE scripting."""

    preset: str = "standard"  # basic | standard | advanced | custom

    # Setup toggles
    hessian_normal: bool = True
    conj_grad: bool = False
    check_increase: bool = False
    autopop: bool = False
    autochop: bool = False
    normal_motion: bool = False
    area_normalization: bool = False
    approximate_curvature: bool = False
    runge_kutta: bool = False
    diffusion: bool = False
    gravity_on: Optional[bool] = None

    # Evolution parameters
    n_refine: Optional[int] = None       # None = inherit from solver.refine_steps
    n_gradient: Optional[int] = None     # None = inherit from solver.gradient_steps
    use_hessian: Optional[bool] = None   # None = inherit from solver.use_hessian
    n_hessian: int = 3
    n_hessian_more: int = 2
    use_hessian_seek: bool = False
    use_volume_correction: bool = True
    use_equiangulate: bool = True
    use_saddle: bool = False
    scale_factor: Optional[float] = None

    # Mesh quality
    tiny_edge_threshold: float = 0.0
    long_edge_threshold: float = 0.0
    target_edge_length: float = 0.0
    weed_threshold: float = 0.0
    use_skinny_refine: bool = False
    skinny_angle: float = 20.0
    use_pop: bool = False
    use_pop_edge: bool = False
    use_notch: bool = False
    notch_angle: float = 1.0
    use_jiggle: bool = False
    jiggle_temperature: float = 0.001
    use_edgeswap: bool = False

    # Analysis
    eigenprobe: bool = False
    eigenprobe_value: float = 0.0
    ritz_count: int = 0
    ritz_value: float = 0.0
    report_pressure: bool = False
    report_volumes: bool = False
    report_energy: bool = False
    report_quantities: bool = False

    # gofine
    use_gofine: bool = False
    gofine_extra_refine: int = 2
    gofine_gradient_mult: int = 2

    # Custom
    custom_commands: str = ""


@dataclass
class SolverConfig:
    """SE solver parameters."""

    evolver_path: Optional[str] = None
    timeout: int = 300
    refine_steps: int = 3
    gradient_steps: int = 10
    use_hessian: bool = True
    fe_only: bool = False
    strategy: Optional[StrategyConfig] = None


@dataclass
class OutputConfig:
    """Output settings."""

    directory: str = "output"
    formats: list = field(default_factory=lambda: ["stl", "vtk"])
    joint_name: str = "solder_joint"


@dataclass
class SweepConfig:
    """Parameter sweep configuration."""

    enabled: bool = False
    variable: str = "volume"
    values: Optional[list] = None
    min: Optional[float] = None
    max: Optional[float] = None
    steps: Optional[int] = None


@dataclass
class KSEConfig:
    """Unified configuration from YAML."""

    unit_system: UnitSystem = field(default_factory=lambda: CGS)
    physics: PhysicsConfig = field(default_factory=PhysicsConfig)
    input: InputConfig = field(default_factory=InputConfig)
    geometry: GeometryConfig = field(default_factory=GeometryConfig)
    options: OptionsConfig = field(default_factory=OptionsConfig)
    solver: SolverConfig = field(default_factory=SolverConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    sweep: SweepConfig = field(default_factory=SweepConfig)


def load_config(yaml_path: str | Path) -> KSEConfig:
    """Load configuration from a YAML file.

    Args:
        yaml_path: Path to the YAML configuration file.

    Returns:
        Parsed and validated KSEConfig.
    """
    yaml_path = Path(yaml_path)
    with open(yaml_path) as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raw = {}

    config = KSEConfig()

    # Unit system
    if "units" in raw:
        config.unit_system = get_unit_system(raw["units"])

    # Physics
    if "physics" in raw:
        p = raw["physics"]
        config.physics = PhysicsConfig(
            tension=p.get("tension", config.unit_system.default_tension),
            density=p.get("density", config.unit_system.default_density),
            gravity=p.get("gravity", config.unit_system.gravity),
            contact_angle_bottom=p.get("contact_angle_bottom", 30.0),
            contact_angle_top=p.get("contact_angle_top", 30.0),
        )
    else:
        # Apply unit system defaults
        config.physics = PhysicsConfig(
            tension=config.unit_system.default_tension,
            density=config.unit_system.default_density,
            gravity=config.unit_system.gravity,
        )

    # Input
    if "input" in raw:
        inp = raw["input"]
        config.input = InputConfig(
            mode=inp.get("mode", "step_assembly"),
            step_file=inp.get("step_file"),
            step_solder=inp.get("step_solder"),
            step_bottom=inp.get("step_bottom"),
            step_top=inp.get("step_top"),
            stl_solder=inp.get("stl_solder"),
            stl_bottom=inp.get("stl_bottom"),
            stl_top=inp.get("stl_top"),
            stl_a=inp.get("stl_a"),
            stl_b=inp.get("stl_b"),
            center_a=inp.get("center_a"),
            center_b=inp.get("center_b"),
        )

    # Geometry
    if "geometry" in raw:
        g = raw["geometry"]
        config.geometry = GeometryConfig(
            pad_shape=g.get("pad_shape", "circular"),
            radius=g.get("radius"),
            side_x=g.get("side_x"),
            side_y=g.get("side_y"),
            volume=g.get("volume"),
            target_volume=g.get("target_volume"),
        )

    # Options
    if "options" in raw:
        o = raw["options"]
        config.options = OptionsConfig(
            void=o.get("void", False),
            void_radius=o.get("void_radius", 0.05),
            void_position=o.get("void_position"),
            fillet=o.get("fillet", False),
            fillet_walls=o.get("fillet_walls", []),
            smooth_iterations=o.get("smooth_iterations", 0),
            max_edge_length=o.get("max_edge_length", 0.0),
            tessellation_tolerance=o.get("tessellation_tolerance", 0.001),
            angular_tolerance=o.get("angular_tolerance", 0.1),
            contact_distance_tol=o.get("contact_distance_tol", 1e-4),
            pad_extract_margin=o.get("pad_extract_margin", 1.5),
            on_surface_tol=o.get("on_surface_tol"),
        )

    # Solver
    if "solver" in raw:
        s = raw["solver"]
        strat = None
        if "strategy" in s:
            st = s["strategy"]
            strat = StrategyConfig(
                preset=st.get("preset", "standard"),
                hessian_normal=st.get("hessian_normal", True),
                conj_grad=st.get("conj_grad", False),
                check_increase=st.get("check_increase", False),
                autopop=st.get("autopop", False),
                autochop=st.get("autochop", False),
                normal_motion=st.get("normal_motion", False),
                area_normalization=st.get("area_normalization", False),
                approximate_curvature=st.get("approximate_curvature", False),
                runge_kutta=st.get("runge_kutta", False),
                diffusion=st.get("diffusion", False),
                gravity_on=st.get("gravity_on"),
                n_refine=st.get("n_refine"),
                n_gradient=st.get("n_gradient"),
                use_hessian=st.get("use_hessian"),
                n_hessian=st.get("n_hessian", 3),
                n_hessian_more=st.get("n_hessian_more", 2),
                use_hessian_seek=st.get("use_hessian_seek", False),
                use_volume_correction=st.get("use_volume_correction", True),
                use_equiangulate=st.get("use_equiangulate", True),
                use_saddle=st.get("use_saddle", False),
                scale_factor=st.get("scale_factor"),
                tiny_edge_threshold=st.get("tiny_edge_threshold", 0.0),
                long_edge_threshold=st.get("long_edge_threshold", 0.0),
                target_edge_length=st.get("target_edge_length", 0.0),
                weed_threshold=st.get("weed_threshold", 0.0),
                use_skinny_refine=st.get("use_skinny_refine", False),
                skinny_angle=st.get("skinny_angle", 20.0),
                use_pop=st.get("use_pop", False),
                use_pop_edge=st.get("use_pop_edge", False),
                use_notch=st.get("use_notch", False),
                notch_angle=st.get("notch_angle", 1.0),
                use_jiggle=st.get("use_jiggle", False),
                jiggle_temperature=st.get("jiggle_temperature", 0.001),
                use_edgeswap=st.get("use_edgeswap", False),
                eigenprobe=st.get("eigenprobe", False),
                eigenprobe_value=st.get("eigenprobe_value", 0.0),
                ritz_count=st.get("ritz_count", 0),
                ritz_value=st.get("ritz_value", 0.0),
                report_pressure=st.get("report_pressure", False),
                report_volumes=st.get("report_volumes", False),
                report_energy=st.get("report_energy", False),
                report_quantities=st.get("report_quantities", False),
                use_gofine=st.get("use_gofine", False),
                gofine_extra_refine=st.get("gofine_extra_refine", 2),
                gofine_gradient_mult=st.get("gofine_gradient_mult", 2),
                custom_commands=st.get("custom_commands", ""),
            )
        config.solver = SolverConfig(
            evolver_path=s.get("evolver_path"),
            timeout=s.get("timeout", 300),
            refine_steps=s.get("refine_steps", 3),
            gradient_steps=s.get("gradient_steps", 10),
            use_hessian=s.get("use_hessian", True),
            fe_only=s.get("fe_only", False),
            strategy=strat,
        )

    # Output
    if "output" in raw:
        out = raw["output"]
        config.output = OutputConfig(
            directory=out.get("directory", "output"),
            formats=out.get("formats", ["stl", "vtk"]),
            joint_name=out.get("joint_name", "solder_joint"),
        )

    # Sweep
    if "sweep" in raw:
        sw = raw["sweep"]
        config.sweep = SweepConfig(
            enabled=sw.get("enabled", False),
            variable=sw.get("variable", "volume"),
            values=sw.get("values"),
            min=sw.get("min"),
            max=sw.get("max"),
            steps=sw.get("steps"),
        )

    # Resolve relative paths against YAML file directory
    _resolve_paths(config, yaml_path.parent)

    return config


def _resolve_paths(config: KSEConfig, base_dir: Path) -> None:
    """Resolve relative file paths against the YAML file directory."""
    inp = config.input
    for attr in (
        "step_file", "step_solder", "step_bottom", "step_top",
        "stl_solder", "stl_bottom", "stl_top", "stl_a", "stl_b",
    ):
        val = getattr(inp, attr)
        if val is not None:
            p = Path(val)
            if not p.is_absolute():
                setattr(inp, attr, str(base_dir / p))

    # Fillet walls
    resolved_walls = []
    for w in config.options.fillet_walls:
        p = Path(w)
        if not p.is_absolute():
            resolved_walls.append(str(base_dir / p))
        else:
            resolved_walls.append(w)
    config.options.fillet_walls = resolved_walls

    # Output directory
    out_dir = Path(config.output.directory)
    if not out_dir.is_absolute():
        config.output.directory = str(base_dir / out_dir)


def validate_config(config: KSEConfig) -> list:
    """Validate configuration and return list of warnings/errors.

    Returns:
        List of warning/error strings. Empty list means valid.
    """
    warnings = []
    inp = config.input
    mode = inp.mode

    if mode == "step_assembly":
        if not inp.step_file:
            warnings.append("ERROR: step_assembly mode requires input.step_file")
    elif mode == "step_separate":
        if not all([inp.step_solder, inp.step_bottom, inp.step_top]):
            warnings.append(
                "ERROR: step_separate mode requires "
                "input.step_solder, step_bottom, step_top"
            )
    elif mode == "step_bridge":
        if not inp.step_file:
            warnings.append("ERROR: step_bridge mode requires input.step_file")
    elif mode == "step_array":
        if not inp.step_file:
            warnings.append("ERROR: step_array mode requires input.step_file")
    elif mode == "stl_complex":
        if not all([inp.stl_solder, inp.stl_bottom, inp.stl_top]):
            warnings.append(
                "ERROR: stl_complex mode requires "
                "input.stl_solder, stl_bottom, stl_top"
            )
    elif mode == "parametric":
        if not inp.stl_a or not inp.stl_b:
            warnings.append("ERROR: parametric mode requires input.stl_a, stl_b")
        if not inp.center_a or not inp.center_b:
            warnings.append(
                "ERROR: parametric mode requires input.center_a, center_b"
            )
        g = config.geometry
        if g.radius is None and g.side_x is None:
            warnings.append("ERROR: parametric mode requires geometry.radius or side_x/side_y")
        if g.volume is None:
            warnings.append("ERROR: parametric mode requires geometry.volume")
    else:
        warnings.append(f"ERROR: Unknown input mode '{mode}'")

    # Physics validation
    if config.physics.tension <= 0:
        warnings.append("WARNING: tension should be positive")
    if config.physics.density <= 0:
        warnings.append("WARNING: density should be positive")

    # Sweep validation
    if config.sweep.enabled:
        if config.sweep.values is None and config.sweep.min is None:
            warnings.append(
                "ERROR: sweep enabled but no values or min/max/steps specified"
            )

    # Void validation
    if config.options.void:
        if config.options.void_radius <= 0:
            warnings.append("WARNING: void_radius should be positive")

    return warnings


def generate_sweep_values(sweep: SweepConfig) -> list:
    """Generate the list of sweep parameter values.

    Returns:
        List of float values for the sweep variable.
    """
    if sweep.values is not None:
        return [float(v) for v in sweep.values]

    if sweep.min is not None and sweep.max is not None and sweep.steps is not None:
        import numpy as np
        return list(np.linspace(sweep.min, sweep.max, sweep.steps))

    return []
