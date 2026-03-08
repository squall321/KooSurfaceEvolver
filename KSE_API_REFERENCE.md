# KSE (KooSurfaceEvolver) API Reference

**For programmatic use by AI agents and automated systems.**

KSE is a standalone CLI tool that simulates solder joint equilibrium shapes using the Surface Evolver engine. Given pad geometry (STL or STEP) and solder material properties, it computes the minimum-energy meniscus shape under surface tension, gravity, and contact angle constraints.

---

## 1. Installation & Execution

### Standalone Binary (recommended)

```bash
# Linux
./dist/kse/kse --help

# Windows
dist\kse\kse.exe --help
```

No Python or dependencies required. The binary includes all necessary libraries (NumPy, SciPy, CadQuery, Surface Evolver).

### From Source

```bash
pip install -e ".[step]"
python cli.py --help
# or after install:
kse --help
```

---

## 2. CLI Commands Overview

```
kse <command> [options]

Commands:
  run        Single solder joint simulation (CLI args)
  batch      Parallel independent joint simulations
  coupled    Interacting joint simulations
  validate   Test against known reference examples
  yaml       Run from YAML configuration file (recommended)
```

---

## 3. `kse yaml` — YAML-Based Pipeline (Recommended)

The most flexible and feature-complete interface. All 6 input modes are available.

```bash
kse yaml <config.yaml> [--dry-run] [--sweep]
```

| Flag | Description |
|------|-------------|
| `config` | Path to YAML configuration file (required, positional) |
| `--dry-run` | Generate .fe file only, skip Surface Evolver execution |
| `--sweep` | Run parameter sweep (requires `sweep.enabled: true` in YAML) |

### Exit codes
- `0` — Success
- `1` — Error (invalid config, SE failure, etc.)

### stdout format
```
Mode: step_assembly | Units: cgs
Physics: sigma=480.0, rho=8.5, G=980.0
Generated: output/solder_joint.fe
Running Surface Evolver...
SE completed in 12.3s
[Mesh Quality Summary]
Standoff height: 0.028500 cm
Max radius: 0.032100 cm
Exported: output/solder_joint.stl
Exported: output/solder_joint.vtk
```

---

## 4. YAML Configuration Schema

### Complete Schema

```yaml
# Unit system: "cgs" or "mm"
# cgs: cm, g, s, erg (default)
# mm:  mm, mg, s, mJ
units: cgs

physics:
  tension: 480.0              # Surface tension [erg/cm^2 for cgs, mJ/mm^2 for mm]
  density: 8.5                # Solder density [g/cm^3 for cgs, mg/mm^3 for mm]
  gravity: 980.0              # Gravitational acceleration [cm/s^2 for cgs, mm/s^2 for mm]
  contact_angle_bottom: 30.0  # Bottom pad contact angle [degrees, 0-180]
  contact_angle_top: 30.0     # Top pad contact angle [degrees, 0-180]

input:
  mode: <string>              # REQUIRED. One of the 6 modes below.
  # Mode-specific fields — see Section 5

geometry:
  pad_shape: circular         # "circular" or "rectangular" (parametric mode only)
  radius: <float>             # Pad radius (circular pads)
  side_x: <float>             # Pad X dimension (rectangular pads)
  side_y: <float>             # Pad Y dimension (rectangular pads)
  volume: <float>             # Solder volume
  target_volume: <float>      # Override volume (STEP/STL modes)

options:
  void: false                 # Enable void (bubble) modeling
  void_radius: 0.05           # Void radius
  void_position: [x, y, z]   # Void center position (null = auto)
  fillet: false               # Enable fillet prediction
  fillet_walls: []            # List of wall STEP file paths
  smooth_iterations: 0        # Mesh smoothing iterations
  max_edge_length: 0.0        # Max edge length for remeshing (0 = unlimited)
  tessellation_tolerance: 0.001  # STEP to mesh conversion tolerance
  angular_tolerance: 0.1      # Angular tolerance [radians]
  contact_distance_tol: 1e-4  # Contact surface detection tolerance
  pad_extract_margin: 1.5     # Pad extraction margin (multiplier of radius)
  on_surface_tol: null        # On-surface tolerance (null = auto)

solver:
  evolver_path: null          # Path to SE binary (null = auto-detect)
  timeout: 300                # Execution timeout [seconds]
  refine_steps: 3             # Mesh refinement iterations
  gradient_steps: 10          # Gradient descent iterations per refinement
  use_hessian: true           # Use Hessian-based optimization
  fe_only: false              # Generate .fe only, skip SE execution

  # ── Evolution Strategy (optional, advanced SE scripting) ──
  strategy:
    preset: standard          # basic | standard | advanced | custom
    # Setup toggles
    hessian_normal: true      # Hessian normal motion mode
    conj_grad: false          # Conjugate gradient acceleration
    check_increase: true      # Reject moves that increase energy
    autopop: false            # Auto-delete degenerate elements
    autochop: false           # Auto-subdivide long edges
    normal_motion: false      # Project motion to surface normal
    area_normalization: false # Force/area normalization (mean curvature motion)
    approximate_curvature: false  # Polyhedral curvature discretization
    runge_kutta: false        # 4th-order Runge-Kutta (vs Euler)
    diffusion: false          # Gas diffusion between bodies
    gravity_on: null          # Explicit gravity toggle (null=default)
    scale_factor: null        # Fixed scale factor (null=optimizing)
    # Evolution
    n_refine: 3               # Refinement stages
    n_gradient: 10            # Gradient iterations per stage
    use_hessian: true         # Newton's method (hessian command)
    n_hessian: 3              # Hessian iterations in gogo
    n_hessian_more: 2         # Hessian iterations in gomore
    use_hessian_seek: false   # Hessian with line search
    use_volume_correction: true  # V command (volume correction)
    use_equiangulate: true    # u command (equiangulation)
    use_saddle: false         # Saddle point detection
    # Mesh quality
    tiny_edge_threshold: 0.0  # t: eliminate short edges (0=skip)
    long_edge_threshold: 0.0  # l: subdivide long edges (0=skip)
    target_edge_length: 0.0   # Selective refine threshold (0=global)
    weed_threshold: 0.0       # w: remove small triangles (0=skip)
    use_skinny_refine: false  # K: subdivide skinny triangles
    skinny_angle: 20.0        # K: cutoff angle in degrees
    use_pop: false            # o: pop non-minimal vertices
    use_pop_edge: false       # O: pop non-minimal edges
    use_notch: false          # n: notch ridges/valleys
    notch_angle: 1.0          # n: cutoff angle in radians (~57 deg)
    use_jiggle: false         # j: random vertex perturbation
    jiggle_temperature: 0.001 # j: perturbation temperature
    use_edgeswap: false       # edgeswap for mesh quality
    # High-quality final pass
    use_gofine: false         # Enable gofine macro
    gofine_extra_refine: 2    # Extra refinement steps in gofine
    gofine_gradient_mult: 2   # Gradient multiplier in gofine
    # Analysis/post-processing
    eigenprobe: false         # Stability eigenvalue analysis
    eigenprobe_value: 0.0     # Eigenprobe search value
    ritz_count: 0             # Ritz eigenvalue count (0=skip)
    ritz_value: 0.0           # Ritz search value
    report_pressure: false    # Print body pressures
    report_volumes: false     # Volume/pressure report
    report_energy: false      # Print total energy
    report_quantities: false  # Named quantity report
    # Custom (preset=custom only)
    custom_commands: ""       # Raw SE commands

output:
  directory: output           # Output directory path
  formats:                    # Export format list
    - stl                     # STL mesh
    - vtk                     # VTK (ParaView)
    # - gmsh                  # GMSH .msh
    # - ansys                 # ANSYS CDB
    # - ls-dyna               # LS-DYNA .k
  joint_name: solder_joint    # Base filename for output files

sweep:
  enabled: false              # Enable parameter sweep
  variable: volume            # Variable to sweep (any physics/geometry field)
  values: [v1, v2, ...]       # Explicit value list (method 1)
  min: <float>                # Range minimum (method 2)
  max: <float>                # Range maximum (method 2)
  steps: <int>                # Number of points in range (method 2)
```

---

## 5. Input Modes

### 5.1 `parametric`

Direct specification of pad geometry via centers, radius, and volume. Requires STL surface files for pad shapes.

```yaml
input:
  mode: parametric
  stl_a: bottom_pad.stl       # REQUIRED: Bottom pad surface STL
  stl_b: top_pad.stl           # REQUIRED: Top pad surface STL
  center_a: [x, y, z]         # REQUIRED: Bottom pad center coordinates
  center_b: [x, y, z]         # REQUIRED: Top pad center coordinates
geometry:
  pad_shape: circular          # REQUIRED: "circular" or "rectangular"
  radius: 0.025                # REQUIRED for circular
  # side_x, side_y             # REQUIRED for rectangular
  volume: 3.27e-6              # REQUIRED: Solder volume
```

### 5.2 `stl_complex`

Arbitrary STL meshes for complex pad geometries exported from CAD. KSE automatically fits analytical surfaces and generates constraints.

```yaml
input:
  mode: stl_complex
  stl_solder: solder.stl       # REQUIRED: Initial solder shape STL
  stl_bottom: bottom.stl       # REQUIRED: Bottom pad surface STL
  stl_top: top.stl             # REQUIRED: Top pad surface STL
```

### 5.3 `step_assembly`

Single STEP file containing multi-body assembly (solder + pads + substrate). KSE auto-classifies faces.

```yaml
input:
  mode: step_assembly
  step_file: assembly.step     # REQUIRED: STEP assembly file
```

**STEP file requirements:**
- Must contain at least 2 bodies (solder body + pad/substrate bodies)
- Solder body is identified by contact analysis
- Pad faces are detected via contact distance tolerance

### 5.4 `step_separate`

Three separate STEP files for solder, bottom pad, and top pad.

```yaml
input:
  mode: step_separate
  step_solder: solder.step     # REQUIRED: Solder body STEP
  step_bottom: bottom.step     # REQUIRED: Bottom pad STEP
  step_top: top.step           # REQUIRED: Top pad STEP
```

### 5.5 `step_bridge`

Bridge-type solder joint connecting two pads horizontally.

```yaml
input:
  mode: step_bridge
  step_file: bridge.step       # REQUIRED: Bridge assembly STEP
```

### 5.6 `step_array`

Multi-joint array (e.g., BGA). KSE detects and simulates each joint individually.

```yaml
input:
  mode: step_array
  step_file: array.step        # REQUIRED: Array assembly STEP
```

**Output:** Multiple .fe files, one per detected joint, in the output directory.

---

## 6. `kse run` — Single Joint (CLI Arguments)

For quick single-joint simulations without YAML.

```bash
kse run \
  --stl-a bottom.stl \
  --stl-b top.stl \
  --center-a "0,0,0" \
  --center-b "0,0,0.03" \
  --radius 0.025 \
  --volume 3.27e-6 \
  [--tension 480.0] \
  [--density 9.0] \
  [--gravity 980.0] \
  [--contact-angle 30.0] \
  [--output output] \
  [--format "stl,vtk"] \
  [--evolver-path /path/to/evolver] \
  [--fe-only] \
  [--timeout 300]
```

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--stl-a` | Yes | — | Bottom surface STL file path |
| `--stl-b` | Yes | — | Top surface STL file path |
| `--center-a` | Yes | — | Center on A surface: "x,y,z" |
| `--center-b` | Yes | — | Center on B surface: "x,y,z" |
| `--radius` | Yes | — | Pad radius [cm] |
| `--volume` | Yes | — | Solder volume [cm^3] |
| `--tension` | No | 480.0 | Surface tension [erg/cm^2] |
| `--density` | No | 9.0 | Solder density [g/cm^3] |
| `--gravity` | No | 980.0 | Gravity [cm/s^2] |
| `--contact-angle` | No | 30.0 | Contact angle [degrees] |
| `--output` | No | "output" | Output directory |
| `--format` | No | "stl,vtk" | Export formats (comma-separated) |
| `--evolver-path` | No | auto | Path to SE executable |
| `--fe-only` | No | false | Generate .fe only |
| `--timeout` | No | 300 | Timeout in seconds |

---

## 7. `kse batch` — Parallel Independent Joints

```bash
kse batch \
  --stl-a bottom.stl \
  --stl-b top.stl \
  --joints joints.csv \
  [--output output] \
  [--format "stl,vtk"] \
  [--workers 0] \
  [--evolver-path /path/to/evolver] \
  [--timeout 300]
```

### CSV Format (`joints.csv`)

```csv
name,center_ax,center_ay,center_az,center_bx,center_by,center_bz,radius,volume
joint1,0.0,0.0,0.0,0.0,0.0,0.03,0.025,3.27e-6
joint2,0.1,0.0,0.0,0.1,0.0,0.03,0.025,3.27e-6
```

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--joints` | Yes | — | CSV file path |
| `--workers` | No | 0 | Max parallel workers (0 = auto, uses CPU count) |

---

## 8. `kse coupled` — Interacting Joints

For joints that share solder (e.g., bridging).

```bash
kse coupled \
  --stl-a bottom.stl \
  --stl-b top.stl \
  --joints joints.csv \
  [--group-distance 0.0] \
  [--timeout 600]
```

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--group-distance` | No | 0.0 | Distance threshold for grouping joints |

---

## 9. `kse validate` — Reference Validation

Test KSE against known Surface Evolver reference examples.

```bash
kse validate [--example bga-1] [--all] [--evolver-path /path/to/evolver]
```

Available examples: `bga-1`, `bga-3`, `bga-7`

Output includes energy error (%), volume error (%), and Hausdorff distance comparisons.

---

## 10. Output Files

For a job named `solder_joint`, outputs are:

| File | Format | Description |
|------|--------|-------------|
| `solder_joint.fe` | SE datafile | Surface Evolver input (human-readable text) |
| `solder_joint.dmp` | SE dump | Raw SE output (vertex/face data) |
| `solder_joint.stl` | STL mesh | Triangulated equilibrium surface |
| `solder_joint.vtk` | VTK | ParaView-compatible visualization |
| `solder_joint.msh` | GMSH | GMSH mesh format |
| `solder_joint.cdb` | ANSYS CDB | ANSYS Mechanical import |
| `solder_joint.k` | LS-DYNA | LS-DYNA keyword format |

### STL Output Details
- ASCII STL format
- Triangle mesh of the equilibrium solder meniscus surface
- Vertex coordinates in the input unit system (cgs or mm)

### VTK Output Details
- Unstructured grid format
- Compatible with ParaView, VisIt, and other VTK readers

---

## 11. Parameter Sweep

Run multiple simulations varying a single parameter.

```bash
kse yaml sweep_config.yaml --sweep
```

Sweep output:
- Individual .fe and export files per sweep point
- Summary report (`sweep_report.txt`) with all results

Sweepable variables: `volume`, `tension`, `density`, `gravity`, `contact_angle_bottom`, `contact_angle_top`, `radius`

---

## 12. Programmatic Usage Examples

### Python (subprocess)

```python
import subprocess
import json

# Generate .fe file only (dry run)
result = subprocess.run(
    ["./dist/kse/kse", "yaml", "config.yaml", "--dry-run"],
    capture_output=True, text=True
)
print(result.stdout)
assert result.returncode == 0

# Full simulation
result = subprocess.run(
    ["./dist/kse/kse", "yaml", "config.yaml"],
    capture_output=True, text=True, timeout=600
)
if result.returncode == 0:
    # Parse standoff height from stdout
    for line in result.stdout.splitlines():
        if "Standoff height:" in line:
            height = float(line.split(":")[1].strip().split()[0])
            print(f"Standoff height = {height}")
```

### Bash Script

```bash
#!/bin/bash
# Run simulation and check result
KSE="./dist/kse/kse"

$KSE yaml config.yaml
if [ $? -eq 0 ]; then
    echo "Simulation succeeded"
    # Output files are in the configured output directory
    ls -la output/solder_joint.*
else
    echo "Simulation failed"
fi
```

### YAML Config Generation (Python)

```python
import yaml

config = {
    "units": "cgs",
    "physics": {
        "tension": 480.0,
        "density": 8.5,
        "gravity": 980.0,
        "contact_angle_bottom": 30.0,
        "contact_angle_top": 30.0,
    },
    "input": {
        "mode": "step_assembly",
        "step_file": "my_assembly.step",
    },
    "geometry": {
        "target_volume": 3.27e-6,
    },
    "solver": {
        "timeout": 300,
        "refine_steps": 3,
        "use_hessian": True,
    },
    "output": {
        "directory": "output",
        "formats": ["stl", "vtk"],
        "joint_name": "my_joint",
    },
}

with open("generated_config.yaml", "w") as f:
    yaml.dump(config, f, default_flow_style=False)
```

---

## 13. Common Solder Material Properties

| Alloy | Tension [erg/cm^2] | Tension [mJ/mm^2] | Density [g/cm^3] | Melting [C] |
|-------|-------------------|--------------------|-------------------|-------------|
| SAC305 (Sn96.5Ag3Cu0.5) | 480 | 0.48 | 8.5 | 217-220 |
| SAC405 (Sn95.5Ag4Cu0.5) | 490 | 0.49 | 8.5 | 217-220 |
| SnPb (Sn63Pb37) | 460 | 0.46 | 8.4 | 183 |
| SnBi (Sn42Bi58) | 350 | 0.35 | 8.7 | 138 |
| Pure Sn | 520 | 0.52 | 7.3 | 232 |

### Typical Contact Angles

| Surface | Angle [deg] | Notes |
|---------|------------|-------|
| Cu pad (flux-activated) | 20-35 | Most common PCB pad |
| Cu pad (no flux) | 40-60 | Oxidized surface |
| Ni/Au pad | 25-40 | ENIG finish |
| Solder mask (PCB) | 90-130 | Non-wetting |
| FR-4 substrate | 110-140 | Non-wetting |

---

## 14. Evolution Strategy (Advanced SE Scripting)

The `solver.strategy` section gives full control over Surface Evolver's scripting engine.
When omitted, KSE uses a legacy "basic" strategy (equivalent to `preset: basic`).

### 14.1 Presets

| Preset | Description | Macros Generated |
|--------|-------------|-----------------|
| `basic` | Minimal: u, g, r, hessian — fastest | gogo, gomore |
| `standard` | + volume correction, equiangulate, gofine | gogo, gomore, gofine |
| `advanced` | + autopop, skinny refine, eigenprobe, pressure reporting | gogo, gomore, gofine, analyze |
| `custom` | User-provided raw SE commands (ignores all other options) | user-defined |

### 14.2 Generated SE Macros

KSE generates these SE macros in the .fe datafile:

**gogo** — Main evolution sequence:
```
gogo := {
  u;                    // equiangulation
  V;                    // volume correction
  g N;                  // gradient descent N iterations
  [mesh cleanup]        // t, l, w, K, o, O, n, edgeswap, j
  r;                    // global refine (repeated n_refine times)
  hessian; hessian; ... // Newton convergence
}
```

**gomore** — Extended evolution:
```
gomore := {
  V; u; g N;            // volume + equiangulate + gradient
  [mesh cleanup]
  r; V; u; g N;         // one more refine cycle
  hessian; hessian;     // Hessian convergence
}
```

**gofine** (when `use_gofine: true`) — High-quality final pass:
```
gofine := {
  r; r;                 // extra refinement (gofine_extra_refine times)
  [mesh cleanup]
  V; u; g N*M;          // gradient with multiplier
  hessian; hessian; hessian;  // thorough convergence
}
```

**analyze** (when analysis options enabled) — Post-processing:
```
analyze := {
  v;                    // volume/pressure report
  Q;                    // named quantity report
  printf "TOTAL_ENERGY: %20.15g\n", total_energy;
  foreach body bb do printf "BODY_%d_PRESSURE: %20.15g\n", bb.id, bb.pressure;
  eigenprobe 0;         // stability analysis
  ritz(0, 5);          // lowest eigenvalues
}
```

### 14.3 SE Command Reference

| Command | Strategy Field | Description |
|---------|---------------|-------------|
| `g N` | `n_gradient` | Gradient descent iterations |
| `r` | `n_refine` | Global mesh refinement |
| `u` | `use_equiangulate` | Equiangulation (improve triangle quality) |
| `V` | `use_volume_correction` | Volume correction after moves |
| `hessian` | `use_hessian`, `n_hessian` | Newton's method convergence |
| `hessian_seek` | `use_hessian_seek` | Hessian with line search |
| `saddle` | `use_saddle` | Saddle point detection |
| `t T` | `tiny_edge_threshold` | Eliminate edges shorter than T |
| `l L` | `long_edge_threshold` | Subdivide edges longer than L |
| `w W` | `weed_threshold` | Remove triangles smaller than W |
| `K A` | `use_skinny_refine`, `skinny_angle` | Subdivide skinny triangles (angle < A degrees) |
| `o` | `use_pop` | Pop non-minimal vertices |
| `O` | `use_pop_edge` | Pop non-minimal edges |
| `n A` | `use_notch`, `notch_angle` | Notch ridges/valleys (angle > A radians) |
| `j T` | `use_jiggle`, `jiggle_temperature` | Random perturbation (temperature T) |
| `edgeswap` | `use_edgeswap` | Edge swap for mesh quality |
| `eigenprobe V` | `eigenprobe`, `eigenprobe_value` | Stability eigenvalue search |
| `ritz(V,N)` | `ritz_value`, `ritz_count` | Compute N lowest eigenvalues |

### 14.4 Setup Toggles

| Toggle | Strategy Field | SE Command | Description |
|--------|---------------|------------|-------------|
| Hessian normal | `hessian_normal` | `hessian_normal` | Normal motion for Hessian |
| Conjugate gradient | `conj_grad` | `U` | CG acceleration |
| Check increase | `check_increase` | `check_increase ON` | Reject energy-increasing moves |
| Autopop | `autopop` | `autopop ON` | Auto-delete degenerate elements |
| Autochop | `autochop` | `autochop ON` | Auto-subdivide long edges |
| Normal motion | `normal_motion` | `normal_motion ON` | Project to surface normal |
| Area normalization | `area_normalization` | `a` | Mean curvature motion |
| Approx curvature | `approximate_curvature` | `approximate_curvature ON` | Polyhedral curvature |
| Runge-Kutta | `runge_kutta` | `runge_kutta ON` | 4th-order RK integration |
| Diffusion | `diffusion` | `diffusion ON` | Gas diffusion between bodies |
| Gravity | `gravity_on` | `G ON`/`G OFF` | Explicit gravity toggle |
| Scale factor | `scale_factor` | `m F` | Fixed motion scale factor |

### 14.5 Example: Custom Strategy

```yaml
solver:
  strategy:
    preset: custom
    custom_commands: |
      gogo := {
        u; V;
        g 20;
        r; u; V; g 20;
        r; u; V; g 20;
        hessian; hessian; hessian;
      }
      gomore := {
        V; u; g 30;
        hessian; hessian;
      }
```

### 14.6 Backward Compatibility

When `solver.strategy` is omitted, KSE automatically builds a basic strategy from legacy fields:
- `solver.refine_steps` → `strategy.n_refine`
- `solver.gradient_steps` → `strategy.n_gradient`
- `solver.use_hessian` → `strategy.use_hessian`

This ensures all existing YAML configs continue to work without modification.

---

## 15. Troubleshooting

| Error | Cause | Solution |
|-------|-------|----------|
| `SE binary not found` | evolver not in expected path | Set `solver.evolver_path` in YAML |
| `SE failed: timeout` | Simulation too slow | Increase `solver.timeout` or reduce `refine_steps` |
| `ERROR: step_assembly mode requires input.step_file` | Missing required field | Check YAML `input` section |
| `WARNING: tension should be positive` | Negative/zero tension | Fix `physics.tension` value |
| `SE failed: ...singular matrix...` | Degenerate geometry | Check pad geometry, volume, and contact angles |
| `No module named 'cadquery'` | CadQuery not available | Use standalone build or `pip install cadquery` |

---

## 16. Architecture (for developers)

```
kse/
├── core/                       # Core pipeline
│   ├── stl_reader.py           # STL loading + patch extraction
│   ├── surface_fitter.py       # Analytical surface fitting (PLANE/QUADRATIC/QUARTIC)
│   ├── constraint_gen.py       # SymPy-based SE constraint generation
│   ├── geometry_builder.py     # Initial mesh geometry generation
│   ├── fe_writer.py            # Jinja2 template-based .fe file generation
│   ├── step_reader.py          # CadQuery-based STEP file reading
│   ├── step_pipeline.py        # STEP pipeline (assembly/separate/bridge/array)
│   ├── complex_pipeline.py     # Complex STL pipeline orchestration
│   ├── boundary_extractor.py   # Boundary loop extraction
│   ├── mesh_preprocessor.py    # STL mesh preprocessing
│   ├── mesh_to_se.py           # trimesh → SE topology conversion
│   └── units.py                # Unit system (CGS/mm)
├── solver/
│   ├── evolver_runner.py       # SE subprocess execution (-p1 mode)
│   ├── dump_parser.py          # SE .dmp output parsing
│   ├── evolution_scripts.py    # Evolution command generation
│   └── result_analyzer.py      # Standoff height, max radius analysis
├── batch/
│   ├── parallel_runner.py      # Parallel execution
│   ├── coupled_runner.py       # Coupled joint simulation
│   ├── job_manager.py          # Job orchestration + export
│   └── sweep_runner.py         # Parameter sweep
├── mesh/
│   ├── quality.py              # Mesh quality assessment
│   ├── refiner.py              # Smoothing + refinement
│   └── exporters/              # STL/VTK/GMSH/ANSYS/LS-DYNA exporters
└── config/
    └── yaml_config.py          # YAML config loader (8 dataclasses)
```

### Pipeline Flow

```
Input (STEP/STL) ──→ SurfaceFitter ──→ ConstraintGenerator ──→ GeometryBuilder
                        │                    │                      │
                   fit surfaces          generate SE           build initial
                   (PLANE/QUAD/          constraints            mesh
                    QUARTIC)             (content/energy        (vertices/
                                         integrals)             edges/faces)
                                              │                    │
                                              └─────── FEWriter ───┘
                                                          │
                                                     .fe datafile
                                                          │
                                                   EvolverRunner (SE -p1)
                                                          │
                                                     .dmp dump file
                                                          │
                                                    DumpParser + Exporters
                                                          │
                                               STL/VTK/GMSH/ANSYS/LS-DYNA
```
