"""Generate synthetic STEP assembly files for testing the STEP pipeline.

Uses CadQuery to create solder + pad assemblies as STEP files.
Each generator creates a 3-solid assembly (bottom_pad, solder, top_pad)
or separate files per solid.
"""

from pathlib import Path
from typing import Optional

import numpy as np

try:
    import cadquery as cq
    HAS_CADQUERY = True
except ImportError:
    HAS_CADQUERY = False


def _require_cadquery():
    if not HAS_CADQUERY:
        raise ImportError("STEP generators require CadQuery.")


def generate_cylinder_assembly_step(
    bottom_center: np.ndarray,
    top_center: np.ndarray,
    solder_radius: float,
    pad_radius: float,
    pad_thickness: float = 0.002,
    output_path: Optional[Path] = None,
) -> Path:
    """Generate a cylindrical solder + two flat circular pad assembly as STEP.

    Three solids stacked along Z: bottom_pad, solder cylinder, top_pad.

    Returns:
        Path to the written STEP file.
    """
    _require_cadquery()
    bottom = np.asarray(bottom_center, dtype=float)
    top = np.asarray(top_center, dtype=float)
    height = float(top[2] - bottom[2])

    # Bottom pad: cylinder below solder
    bot_pad = (
        cq.Workplane("XY")
        .center(float(bottom[0]), float(bottom[1]))
        .circle(pad_radius)
        .extrude(pad_thickness)
        .translate((0, 0, float(bottom[2]) - pad_thickness))
    )

    # Solder cylinder
    solder = (
        cq.Workplane("XY")
        .center(float(bottom[0]), float(bottom[1]))
        .circle(solder_radius)
        .extrude(height)
        .translate((0, 0, float(bottom[2])))
    )

    # Top pad: cylinder above solder
    top_pad = (
        cq.Workplane("XY")
        .center(float(top[0]), float(top[1]))
        .circle(pad_radius)
        .extrude(pad_thickness)
        .translate((0, 0, float(top[2])))
    )

    # Combine into assembly compound
    assembly = bot_pad.add(solder).add(top_pad)

    if output_path is None:
        output_path = Path("cylinder_assembly.step")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(assembly, str(output_path))
    return output_path


def generate_barrel_assembly_step(
    bottom_center: np.ndarray,
    top_center: np.ndarray,
    radius_end: float,
    radius_mid: float,
    pad_radius: float,
    pad_thickness: float = 0.002,
    n_sections: int = 8,
    output_path: Optional[Path] = None,
) -> Path:
    """Generate a barrel-shaped solder + two flat pads as STEP.

    The solder profile is a parabolic arc rotated around Z:
    r(z) = r_end + (r_mid - r_end) * 4*t*(1-t), t = (z - z_bot) / height.
    Built via loft between circular cross-sections at different Z levels.

    Returns:
        Path to the written STEP file.
    """
    _require_cadquery()
    bottom = np.asarray(bottom_center, dtype=float)
    top = np.asarray(top_center, dtype=float)
    height = float(top[2] - bottom[2])
    cx, cy = float(bottom[0]), float(bottom[1])

    # Build barrel via loft between circular sections at different Z levels
    dz = height / n_sections
    wp = cq.Workplane("XY").workplane(offset=float(bottom[2])).circle(radius_end)
    for i in range(1, n_sections + 1):
        t = i / n_sections
        r = radius_end + (radius_mid - radius_end) * 4 * t * (1 - t)
        wp = wp.workplane(offset=dz).circle(r)
    solder = wp.loft()
    if cx != 0 or cy != 0:
        solder = solder.translate((cx, cy, 0))

    # Pads
    bot_pad = (
        cq.Workplane("XY")
        .center(cx, cy)
        .circle(pad_radius)
        .extrude(pad_thickness)
        .translate((0, 0, float(bottom[2]) - pad_thickness))
    )
    top_pad = (
        cq.Workplane("XY")
        .center(cx, cy)
        .circle(pad_radius)
        .extrude(pad_thickness)
        .translate((0, 0, float(top[2])))
    )

    assembly = bot_pad.add(solder).add(top_pad)

    if output_path is None:
        output_path = Path("barrel_assembly.step")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(assembly, str(output_path))
    return output_path


def generate_box_assembly_step(
    bottom_center: np.ndarray,
    top_center: np.ndarray,
    solder_side: float,
    pad_side: float,
    pad_thickness: float = 0.002,
    output_path: Optional[Path] = None,
) -> Path:
    """Generate a box solder + two square pads as STEP.

    Returns:
        Path to the written STEP file.
    """
    _require_cadquery()
    bottom = np.asarray(bottom_center, dtype=float)
    top = np.asarray(top_center, dtype=float)
    height = float(top[2] - bottom[2])
    cx, cy = float(bottom[0]), float(bottom[1])

    bot_pad = (
        cq.Workplane("XY")
        .center(cx, cy)
        .rect(pad_side, pad_side)
        .extrude(pad_thickness)
        .translate((0, 0, float(bottom[2]) - pad_thickness))
    )

    solder = (
        cq.Workplane("XY")
        .center(cx, cy)
        .rect(solder_side, solder_side)
        .extrude(height)
        .translate((0, 0, float(bottom[2])))
    )

    top_pad = (
        cq.Workplane("XY")
        .center(cx, cy)
        .rect(pad_side, pad_side)
        .extrude(pad_thickness)
        .translate((0, 0, float(top[2])))
    )

    assembly = bot_pad.add(solder).add(top_pad)

    if output_path is None:
        output_path = Path("box_assembly.step")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(assembly, str(output_path))
    return output_path


def generate_separate_step_files(
    bottom_center: np.ndarray,
    top_center: np.ndarray,
    solder_radius: float,
    pad_radius: float,
    pad_thickness: float = 0.002,
    output_dir: Optional[Path] = None,
) -> tuple:
    """Generate 3 separate STEP files: solder, bottom_pad, top_pad.

    Returns:
        (solder_path, bottom_pad_path, top_pad_path)
    """
    _require_cadquery()
    bottom = np.asarray(bottom_center, dtype=float)
    top = np.asarray(top_center, dtype=float)
    height = float(top[2] - bottom[2])
    cx, cy = float(bottom[0]), float(bottom[1])

    if output_dir is None:
        output_dir = Path(".")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Solder
    solder = (
        cq.Workplane("XY")
        .center(cx, cy)
        .circle(solder_radius)
        .extrude(height)
        .translate((0, 0, float(bottom[2])))
    )
    solder_path = output_dir / "solder.step"
    cq.exporters.export(solder, str(solder_path))

    # Bottom pad
    bot_pad = (
        cq.Workplane("XY")
        .center(cx, cy)
        .circle(pad_radius)
        .extrude(pad_thickness)
        .translate((0, 0, float(bottom[2]) - pad_thickness))
    )
    bot_path = output_dir / "bottom_pad.step"
    cq.exporters.export(bot_pad, str(bot_path))

    # Top pad
    top_pad = (
        cq.Workplane("XY")
        .center(cx, cy)
        .circle(pad_radius)
        .extrude(pad_thickness)
        .translate((0, 0, float(top[2])))
    )
    top_path = output_dir / "top_pad.step"
    cq.exporters.export(top_pad, str(top_path))

    return solder_path, bot_path, top_path


def generate_bridge_assembly_step(
    solder_length: float,
    solder_width: float,
    solder_height: float,
    pad_positions: list,
    pad_radius: float,
    pad_thickness: float = 0.002,
    output_path: Optional[Path] = None,
) -> Path:
    """Generate a bridge pad assembly: 1 large solder + N circular pads.

    The solder is a box spanning all pad positions.
    Each pad is a small cylinder at the given XY position, at Z=0.

    Args:
        solder_length: Solder extent in X direction.
        solder_width: Solder extent in Y direction.
        solder_height: Solder height (Z).
        pad_positions: List of (x, y) tuples for pad centers.
        pad_radius: Radius of each pad.
        pad_thickness: Thickness of each pad cylinder.

    Returns:
        Path to STEP file.
    """
    _require_cadquery()

    # Solder: box centered at origin, sitting on Z=0
    solder = (
        cq.Workplane("XY")
        .rect(solder_length, solder_width)
        .extrude(solder_height)
    )

    # Pads: cylinders at Z = -pad_thickness to Z = 0
    assembly = solder
    for px, py in pad_positions:
        pad = (
            cq.Workplane("XY")
            .center(px, py)
            .circle(pad_radius)
            .extrude(pad_thickness)
            .translate((0, 0, -pad_thickness))
        )
        assembly = assembly.add(pad)

    if output_path is None:
        output_path = Path("bridge_assembly.step")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(assembly, str(output_path))
    return output_path


def generate_fillet_assembly_step(
    bottom_center: np.ndarray,
    solder_radius: float,
    solder_height: float,
    pad_radius: float,
    pad_thickness: float = 0.002,
    wall_width: float = None,
    wall_height: float = None,
    wall_thickness: float = None,
    output_path: Optional[Path] = None,
    wall_output_path: Optional[Path] = None,
) -> tuple:
    """Generate a fillet assembly: solder + bottom pad + wall.

    The wall is a vertical rectangular solid adjacent to the solder,
    simulating a component lead that the solder wets.

    Returns:
        (assembly_step_path, wall_step_path)
    """
    _require_cadquery()
    bc = np.asarray(bottom_center, dtype=float)
    cx, cy, cz = float(bc[0]), float(bc[1]), float(bc[2])

    if wall_width is None:
        wall_width = solder_radius * 2
    if wall_height is None:
        wall_height = solder_height * 2
    if wall_thickness is None:
        wall_thickness = solder_radius * 0.5

    # Bottom pad
    bot_pad = (
        cq.Workplane("XY")
        .center(cx, cy)
        .circle(pad_radius)
        .extrude(pad_thickness)
        .translate((0, 0, cz - pad_thickness))
    )

    # Solder (half-cylinder profile for fillet shape)
    solder = (
        cq.Workplane("XY")
        .center(cx, cy)
        .circle(solder_radius)
        .extrude(solder_height)
        .translate((0, 0, cz))
    )

    assembly = bot_pad.add(solder)

    if output_path is None:
        output_path = Path("fillet_assembly.step")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(assembly, str(output_path))

    # Wall: vertical block next to solder
    wall_x = cx + solder_radius + wall_thickness / 2
    wall = (
        cq.Workplane("XY")
        .center(wall_x, cy)
        .rect(wall_thickness, wall_width)
        .extrude(wall_height)
        .translate((0, 0, cz))
    )

    if wall_output_path is None:
        wall_output_path = output_path.parent / "wall.step"
    wall_output_path = Path(wall_output_path)
    cq.exporters.export(wall, str(wall_output_path))

    return output_path, wall_output_path


def generate_array_assembly_step(
    n_joints: int,
    pitch: float,
    solder_radius: float,
    solder_height: float,
    pad_radius: float,
    pad_thickness: float = 0.002,
    output_path: Optional[Path] = None,
) -> Path:
    """Generate a multi-joint BGA array: 2 pads + N solder cylinders.

    Solders are arranged in a row along X with given pitch.
    Two large pads (bottom and top) span all joints.

    Returns:
        Path to STEP file.
    """
    _require_cadquery()

    # Pad extent: covers all joints with margin
    total_x = pitch * (n_joints - 1) + 4 * pad_radius
    pad_y = 4 * pad_radius
    x_start = -pitch * (n_joints - 1) / 2

    # Bottom pad: large rectangle
    bot_pad = (
        cq.Workplane("XY")
        .rect(total_x, pad_y)
        .extrude(pad_thickness)
        .translate((0, 0, -pad_thickness))
    )

    # Top pad
    top_pad = (
        cq.Workplane("XY")
        .rect(total_x, pad_y)
        .extrude(pad_thickness)
        .translate((0, 0, solder_height))
    )

    assembly = bot_pad.add(top_pad)

    # Solder cylinders
    for i in range(n_joints):
        x = x_start + i * pitch
        s = (
            cq.Workplane("XY")
            .center(x, 0)
            .circle(solder_radius)
            .extrude(solder_height)
        )
        assembly = assembly.add(s)

    if output_path is None:
        output_path = Path("array_assembly.step")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(assembly, str(output_path))
    return output_path


def generate_qfn_assembly_step(
    bottom_center: np.ndarray,
    solder_radius: float,
    solder_height: float,
    pad_radius: float,
    pad_thickness: float = 0.002,
    lead_width: float = None,
    lead_height: float = None,
    lead_thickness: float = None,
    output_path: Optional[Path] = None,
    lead_output_path: Optional[Path] = None,
) -> tuple:
    """Generate a QFN fillet assembly: solder + bottom pad + vertical lead wall.

    Models a solder fillet that wets both a PCB pad (horizontal, at z=0)
    and a component lead side (vertical wall adjacent to the solder).

    Geometry:
        - Bottom pad: circular, at z = -pad_thickness to z = 0
        - Solder: cylinder, at z = 0 to z = solder_height
        - Lead wall: rectangular solid, adjacent to solder at +X side

    Returns:
        (assembly_step_path, lead_step_path)
    """
    _require_cadquery()
    bc = np.asarray(bottom_center, dtype=float)
    cx, cy, cz = float(bc[0]), float(bc[1]), float(bc[2])

    if lead_width is None:
        lead_width = solder_radius * 2.5
    if lead_height is None:
        lead_height = solder_height * 1.5
    if lead_thickness is None:
        lead_thickness = solder_radius * 0.6

    # Bottom pad (circular)
    bot_pad = (
        cq.Workplane("XY")
        .center(cx, cy)
        .circle(pad_radius)
        .extrude(pad_thickness)
        .translate((0, 0, cz - pad_thickness))
    )

    # Solder cylinder
    solder = (
        cq.Workplane("XY")
        .center(cx, cy)
        .circle(solder_radius)
        .extrude(solder_height)
        .translate((0, 0, cz))
    )

    assembly = bot_pad.add(solder)

    if output_path is None:
        output_path = Path("qfn_assembly.step")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(assembly, str(output_path))

    # Lead wall: vertical rectangular block adjacent to solder on +X side
    lead_x = cx + solder_radius + lead_thickness / 2
    lead = (
        cq.Workplane("XY")
        .center(lead_x, cy)
        .rect(lead_thickness, lead_width)
        .extrude(lead_height)
        .translate((0, 0, cz))
    )

    if lead_output_path is None:
        lead_output_path = output_path.parent / "lead.step"
    lead_output_path = Path(lead_output_path)
    cq.exporters.export(lead, str(lead_output_path))

    return output_path, lead_output_path


def generate_mlcc_assembly_step(
    bottom_center: np.ndarray,
    solder_radius: float,
    solder_height: float,
    pad_radius: float,
    pad_thickness: float = 0.002,
    cap_width: float = None,
    cap_height: float = None,
    cap_thickness: float = None,
    output_path: Optional[Path] = None,
    left_wall_path: Optional[Path] = None,
    right_wall_path: Optional[Path] = None,
) -> tuple:
    """Generate an MLCC fillet assembly: solder + bottom pad + two end-cap walls.

    Models an MLCC solder fillet where the solder wets the PCB pad (horizontal)
    and one vertical end-cap of the MLCC body.

    Geometry:
        - Bottom pad: circular at z = 0
        - Solder: cylinder between z = 0 and solder_height
        - Left wall: rectangular solid at -X side (left end-cap face)
        - Right wall: rectangular solid at +X side (right end-cap face)

    Returns:
        (assembly_step_path, left_wall_step_path, right_wall_step_path)
    """
    _require_cadquery()
    bc = np.asarray(bottom_center, dtype=float)
    cx, cy, cz = float(bc[0]), float(bc[1]), float(bc[2])

    if cap_width is None:
        cap_width = solder_radius * 2.5
    if cap_height is None:
        cap_height = solder_height * 1.5
    if cap_thickness is None:
        cap_thickness = solder_radius * 0.5

    # Bottom pad
    bot_pad = (
        cq.Workplane("XY")
        .center(cx, cy)
        .circle(pad_radius)
        .extrude(pad_thickness)
        .translate((0, 0, cz - pad_thickness))
    )

    # Solder cylinder
    solder = (
        cq.Workplane("XY")
        .center(cx, cy)
        .circle(solder_radius)
        .extrude(solder_height)
        .translate((0, 0, cz))
    )

    assembly = bot_pad.add(solder)

    if output_path is None:
        output_path = Path("mlcc_assembly.step")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(assembly, str(output_path))

    # Left end-cap wall (at -X)
    left_x = cx - solder_radius - cap_thickness / 2
    left_wall = (
        cq.Workplane("XY")
        .center(left_x, cy)
        .rect(cap_thickness, cap_width)
        .extrude(cap_height)
        .translate((0, 0, cz))
    )
    if left_wall_path is None:
        left_wall_path = output_path.parent / "mlcc_left_wall.step"
    left_wall_path = Path(left_wall_path)
    cq.exporters.export(left_wall, str(left_wall_path))

    # Right end-cap wall (at +X)
    right_x = cx + solder_radius + cap_thickness / 2
    right_wall = (
        cq.Workplane("XY")
        .center(right_x, cy)
        .rect(cap_thickness, cap_width)
        .extrude(cap_height)
        .translate((0, 0, cz))
    )
    if right_wall_path is None:
        right_wall_path = output_path.parent / "mlcc_right_wall.step"
    right_wall_path = Path(right_wall_path)
    cq.exporters.export(right_wall, str(right_wall_path))

    return output_path, left_wall_path, right_wall_path
