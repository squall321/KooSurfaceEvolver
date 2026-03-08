"""Surface Evolver evolution script generation with full command support.

Generates SE command scripts from an EvolutionStrategy dataclass.
Supports 4 presets (basic/standard/advanced/custom) and per-command
control over all SE iteration, mesh quality, and analysis commands.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EvolutionStrategy:
    """Complete Surface Evolver evolution strategy configuration.

    Controls all 4 phases: Setup → Evolution → Analysis → Output.
    Use preset="basic"|"standard"|"advanced" for predefined strategies,
    or preset="custom" with custom_commands for full control.
    """

    preset: str = "standard"  # basic | standard | advanced | custom

    # ── Phase 1: Setup toggles ─────────────────────────────────────
    hessian_normal: bool = True       # hessian_normal ON — normal motion for Hessian
    conj_grad: bool = False           # conjugate gradient acceleration
    check_increase: bool = False      # reject moves that increase energy
    autopop: bool = False             # auto-delete degenerate edges/vertices
    autochop: bool = False            # auto-subdivide long edges
    normal_motion: bool = False       # project motion to surface normal
    area_normalization: bool = False  # force/area normalization (mean curvature motion)
    approximate_curvature: bool = False  # polyhedral curvature discretization
    runge_kutta: bool = False         # 4th-order Runge-Kutta (vs Euler)
    diffusion: bool = False           # gas diffusion between bodies
    gravity_on: Optional[bool] = None  # explicit gravity toggle (None = leave default)

    # ── Phase 2: Evolution parameters ──────────────────────────────
    n_refine: int = 3                 # number of refinement stages
    n_gradient: int = 10              # gradient descent iterations per stage
    use_hessian: bool = True          # Newton's method (hessian command)
    n_hessian: int = 3                # number of hessian iterations in gogo
    n_hessian_more: int = 2           # number of hessian iterations in gomore
    use_hessian_seek: bool = False    # hessian_seek (with line search)
    use_volume_correction: bool = True  # V command (volume correction)
    use_equiangulate: bool = True     # u command (equiangulation)
    use_saddle: bool = False          # saddle point detection
    scale_factor: Optional[float] = None  # fixed scale factor (None = optimizing)

    # ── Mesh quality commands ──────────────────────────────────────
    tiny_edge_threshold: float = 0.0  # t command: eliminate edges shorter than this (0=skip)
    long_edge_threshold: float = 0.0  # l command: subdivide edges longer than this (0=skip)
    target_edge_length: float = 0.0   # selective refine: refine edge where length > this
    weed_threshold: float = 0.0       # w command: remove small triangles (0=skip)
    use_skinny_refine: bool = False   # K command: subdivide long edges of skinny triangles
    skinny_angle: float = 20.0        # K command: cutoff angle in degrees (triangles with smallest angle < this)
    use_pop: bool = False             # o command: pop non-minimal vertices
    use_pop_edge: bool = False        # O command: pop non-minimal edges
    use_notch: bool = False           # n command: notch ridges/valleys
    notch_angle: float = 1.0          # n command: cutoff angle in radians (~57 degrees)
    use_jiggle: bool = False          # j command: random vertex perturbation
    jiggle_temperature: float = 0.001 # j command: perturbation temperature
    use_edgeswap: bool = False        # edgeswap for mesh quality

    # ── Phase 3: Analysis / Post-processing ────────────────────────
    eigenprobe: bool = False          # eigenprobe command (stability check)
    eigenprobe_value: float = 0.0     # probe value for eigenprobe
    ritz_count: int = 0               # ritz(value, count): 0 = skip
    ritz_value: float = 0.0           # ritz probe value
    report_pressure: bool = False     # print body pressures (force data)
    report_volumes: bool = False      # v command: volume/pressure report
    report_energy: bool = False       # print total_energy
    report_quantities: bool = False   # Q command: named quantity report

    # ── Custom (preset="custom" only) ──────────────────────────────
    custom_commands: str = ""         # raw SE commands for custom preset

    # ── gofine: high-quality final pass ────────────────────────────
    use_gofine: bool = False          # generate and run gofine macro
    gofine_extra_refine: int = 2      # extra refinement steps in gofine
    gofine_gradient_mult: int = 2     # gradient multiplier in gofine


def _apply_preset(strategy: EvolutionStrategy) -> EvolutionStrategy:
    """Apply preset defaults. Returns a copy with preset values filled in."""
    if strategy.preset == "basic":
        # Minimal: u, g, r, hessian — current KSE behavior
        pass  # all defaults are fine for basic
    elif strategy.preset == "standard":
        # Standard: + V, equiangulate, mesh cleanup, gomore, gofine
        strategy.use_volume_correction = True
        strategy.use_equiangulate = True
        strategy.use_gofine = True
    elif strategy.preset == "advanced":
        # Advanced: + eigenprobe, autopop, adaptive edges, full analysis
        strategy.use_volume_correction = True
        strategy.use_equiangulate = True
        strategy.use_gofine = True
        strategy.check_increase = True
        strategy.autopop = True
        strategy.use_pop = True
        strategy.use_skinny_refine = True
        strategy.eigenprobe = True
        strategy.report_pressure = True
        strategy.report_volumes = True
    # "custom" uses custom_commands directly
    return strategy


def generate_evolution_script(strategy: EvolutionStrategy) -> str:
    """Generate the evolution script to embed in the .fe file.

    This creates the procedure definitions (gogo, gomore, gofine)
    that get embedded in the .fe datafile. These are SE macros,
    not runtime commands.

    Args:
        strategy: Evolution strategy configuration.

    Returns:
        Multi-line string of SE procedure definitions.
    """
    if strategy.preset == "custom" and strategy.custom_commands:
        return strategy.custom_commands.rstrip()

    lines = []

    # ── Phase 1: Setup toggles (executed once at file load) ────────
    setup = _generate_setup(strategy)
    if setup:
        lines.append("// Setup toggles")
        lines.extend(setup)
        lines.append("")

    # ── Phase 2: gogo macro ────────────────────────────────────────
    lines.append("// Main evolution sequence")
    lines.extend(_generate_gogo(strategy))
    lines.append("")

    # ── gomore macro ───────────────────────────────────────────────
    lines.append("// Extended evolution with volume correction and mesh cleanup")
    lines.extend(_generate_gomore(strategy))

    # ── gofine macro (optional) ────────────────────────────────────
    if strategy.use_gofine:
        lines.append("")
        lines.append("// Final high-quality refinement")
        lines.extend(_generate_gofine(strategy))

    # ── Analysis procedures (optional) ─────────────────────────────
    analysis = _generate_analysis_proc(strategy)
    if analysis:
        lines.append("")
        lines.append("// Post-processing analysis")
        lines.extend(analysis)

    return "\n".join(lines)


def generate_runtime_commands(
    strategy: EvolutionStrategy,
    dump_filename: str,
) -> str:
    """Generate the runtime commands piped to SE stdin.

    These are the commands sent to SE after the .fe file is loaded:
    execute macros, run analysis, dump results, quit.

    Args:
        strategy: Evolution strategy configuration.
        dump_filename: Name of the dump output file.

    Returns:
        Multi-line string of SE commands.
    """
    cmds = []
    cmds.append("gogo;")
    cmds.append("gomore;")

    if strategy.use_gofine:
        cmds.append("gofine;")

    # Analysis commands (run after evolution)
    if strategy.eigenprobe:
        cmds.append(f"eigenprobe {strategy.eigenprobe_value};")
    if strategy.ritz_count > 0:
        cmds.append(f"ritz({strategy.ritz_value}, {strategy.ritz_count});")
    if strategy.report_volumes:
        cmds.append("v;")
    if strategy.report_quantities:
        cmds.append("Q;")
    if strategy.report_pressure:
        cmds.append("print body[1].pressure;")
    if strategy.report_energy:
        cmds.append("print total_energy;")

    # Dump and quit
    cmds.append(f'dump "{dump_filename}";')
    cmds.append("q")

    return "\n".join(cmds)


# ── Legacy API (backward compatibility) ────────────────────────────

def generate_dump_commands(dump_filename: str) -> str:
    """Generate commands to dump results and quit (legacy API)."""
    return (
        f"gogo;\n"
        f"gomore;\n"
        f"dump \"{dump_filename}\";\n"
        f"q\n"
    )


def generate_fine_dump_commands(dump_filename: str) -> str:
    """Generate commands for high-quality output (legacy API)."""
    return (
        f"gogo;\n"
        f"gomore;\n"
        f"gofine;\n"
        f"dump \"{dump_filename}\";\n"
        f"q\n"
    )


# ── Internal generators ───────────────────────────────────────────

def _generate_setup(strategy: EvolutionStrategy) -> list[str]:
    """Generate toggle/mode setup commands."""
    lines = []

    if strategy.hessian_normal:
        lines.append("hessian_normal")
    if strategy.conj_grad:
        lines.append("U")  # toggle conjugate gradient ON
    if strategy.check_increase:
        lines.append("check_increase ON")
    if strategy.autopop:
        lines.append("autopop ON")
    if strategy.autochop:
        lines.append("autochop ON")
    if strategy.normal_motion:
        lines.append("normal_motion ON")
    if strategy.area_normalization:
        lines.append("a")  # toggle area normalization
    if strategy.approximate_curvature:
        lines.append("approximate_curvature ON")
    if strategy.runge_kutta:
        lines.append("runge_kutta ON")
    if strategy.diffusion:
        lines.append("diffusion ON")
    if strategy.gravity_on is True:
        lines.append("G ON")
    elif strategy.gravity_on is False:
        lines.append("G OFF")
    if strategy.scale_factor is not None:
        lines.append(f"m {strategy.scale_factor}")

    return lines


def _generate_gogo(strategy: EvolutionStrategy) -> list[str]:
    """Generate the gogo macro definition."""
    lines = ["gogo := {"]
    n_g = strategy.n_gradient

    # Initial smoothing
    if strategy.use_equiangulate:
        lines.append(f"  u;")
    if strategy.use_volume_correction:
        lines.append(f"  V;")
    lines.append(f"  g {n_g};")

    # Refinement stages
    for i in range(strategy.n_refine):
        # Mesh quality cleanup before refine (standard+)
        _append_mesh_cleanup(lines, strategy)

        # Refine
        if strategy.target_edge_length > 0 and i > 0:
            lines.append(
                f"  refine edge where length > {strategy.target_edge_length:.6g}"
                f" and not no_refine and not fixed;"
            )
        else:
            lines.append("  r;")

        # Post-refine smoothing
        if strategy.use_equiangulate:
            lines.append("  u;")
        if strategy.use_volume_correction:
            lines.append("  V;")
        lines.append(f"  g {n_g};")

    # Final convergence
    if strategy.use_hessian_seek:
        for _ in range(strategy.n_hessian):
            lines.append("  hessian_seek;")
    elif strategy.use_hessian:
        lines.append("  " + " ".join(["hessian;"] * strategy.n_hessian))

    if strategy.use_saddle:
        lines.append("  saddle;")

    lines.append("}")
    return lines


def _generate_gomore(strategy: EvolutionStrategy) -> list[str]:
    """Generate the gomore macro definition."""
    lines = ["gomore := {"]
    n_g = strategy.n_gradient

    # Volume correction + gradient
    if strategy.use_volume_correction:
        lines.append(f"  V;")
    if strategy.use_equiangulate:
        lines.append("  u;")
    lines.append(f"  g {n_g};")

    # One more refine + converge cycle
    _append_mesh_cleanup(lines, strategy)
    lines.append("  r;")
    if strategy.use_volume_correction:
        lines.append("  V;")
    if strategy.use_equiangulate:
        lines.append("  u;")
    lines.append(f"  g {n_g};")

    # Hessian convergence
    if strategy.use_hessian_seek:
        for _ in range(strategy.n_hessian_more):
            lines.append("  hessian_seek;")
    elif strategy.use_hessian:
        lines.append("  " + " ".join(["hessian;"] * strategy.n_hessian_more))

    lines.append("}")
    return lines


def _generate_gofine(strategy: EvolutionStrategy) -> list[str]:
    """Generate the gofine macro for high-quality final pass."""
    lines = ["gofine := {"]
    n_g = strategy.n_gradient * strategy.gofine_gradient_mult

    # Extra refinement
    for _ in range(strategy.gofine_extra_refine):
        lines.append("  r;")

    # Full mesh cleanup
    _append_mesh_cleanup(lines, strategy)

    # Convergence
    if strategy.use_volume_correction:
        lines.append("  V;")
    if strategy.use_equiangulate:
        lines.append("  u;")
    lines.append(f"  g {n_g};")

    if strategy.use_hessian_seek:
        lines.append("  hessian_seek; hessian_seek; hessian_seek;")
    elif strategy.use_hessian:
        lines.append("  hessian; hessian; hessian;")

    lines.append("}")
    return lines


def _generate_analysis_proc(strategy: EvolutionStrategy) -> list[str]:
    """Generate the analyze procedure if any analysis is requested."""
    has_analysis = (
        strategy.eigenprobe
        or strategy.ritz_count > 0
        or strategy.report_pressure
        or strategy.report_volumes
        or strategy.report_energy
        or strategy.report_quantities
    )
    if not has_analysis:
        return []

    lines = ["analyze := {"]

    if strategy.report_volumes:
        lines.append("  v;")
    if strategy.report_quantities:
        lines.append("  Q;")
    if strategy.report_energy:
        lines.append('  printf "TOTAL_ENERGY: %20.15g\\n", total_energy;')
    if strategy.report_pressure:
        lines.append(
            '  foreach body bb do'
            ' printf "BODY_%d_PRESSURE: %20.15g\\n", bb.id, bb.pressure;'
        )
    if strategy.eigenprobe:
        lines.append(f"  eigenprobe {strategy.eigenprobe_value};")
    if strategy.ritz_count > 0:
        lines.append(f"  ritz({strategy.ritz_value}, {strategy.ritz_count});")

    lines.append("}")
    return lines


def _append_mesh_cleanup(lines: list[str], strategy: EvolutionStrategy) -> None:
    """Append mesh quality commands to a macro."""
    if strategy.tiny_edge_threshold > 0:
        lines.append(f"  t {strategy.tiny_edge_threshold:.6g};")
    if strategy.long_edge_threshold > 0:
        lines.append(f"  l {strategy.long_edge_threshold:.6g};")
    if strategy.weed_threshold > 0:
        lines.append(f"  w {strategy.weed_threshold:.6g};")
    if strategy.use_skinny_refine:
        lines.append(f"  K {strategy.skinny_angle:.6g};")
    if strategy.use_pop:
        lines.append("  o;")
    if strategy.use_pop_edge:
        lines.append("  O;")
    if strategy.use_notch:
        lines.append(f"  n {strategy.notch_angle:.6g};")
    if strategy.use_edgeswap:
        lines.append("  edgeswap edge where 1;")
    if strategy.use_jiggle:
        lines.append(f"  j {strategy.jiggle_temperature:.6g};")
