"""Generate Surface Evolver .fe datafiles from geometry and constraint data."""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import jinja2

from .geometry_builder import InitialGeometry, Vertex, Edge, Face, Body
from .constraint_gen import SEConstraint, SERimConstraint
from .units import UnitSystem, CGS


@dataclass
class ConstraintDef:
    """Constraint definition for template rendering."""
    id: int
    formula: str
    comment: str = ""
    energy: Optional[tuple] = None
    content: Optional[tuple] = None


@dataclass
class BoundaryDef:
    """Boundary definition for template rendering."""
    id: int
    params: str
    definition: str
    comment: str = ""
    energy: Optional[tuple] = None
    content: Optional[tuple] = None


@dataclass
class ParamDef:
    """Extra parameter definition."""
    name: str
    value: str
    comment: str = ""


@dataclass
class SolderJointConfig:
    """Complete configuration for a solder joint simulation."""

    joint_name: str = "solder_joint"
    tension: float = 480.0           # erg/cm^2
    density: float = 9.0             # g/cm^3
    gravity: float = 980.0           # cm/s^2
    radius: float = 0.1             # cm
    volume: float = 0.0             # cm^3
    contact_angle_A: float = 30.0    # degrees
    contact_angle_B: float = 30.0    # degrees
    unit_system: UnitSystem = field(default_factory=lambda: CGS)
    evolver_version: str = "2.70"
    n_refine_steps: int = 3
    n_gradient_steps: int = 10
    use_hessian: bool = True
    extra_params: list = field(default_factory=list)
    strategy: Optional[object] = None  # EvolutionStrategy (optional)


class FEWriter:
    """Generate .fe datafiles using Jinja2 templates."""

    def __init__(self, template_dir: Optional[str | Path] = None):
        if template_dir is None:
            meipass = getattr(sys, '_MEIPASS', None)
            if meipass:
                template_dir = Path(meipass) / "templates"
            else:
                template_dir = Path(__file__).parent.parent.parent / "templates"
        self.template_dir = Path(template_dir)
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def write_single(
        self,
        output_path: str | Path,
        geometry: InitialGeometry,
        constraints: list,
        boundaries: list,
        config: SolderJointConfig,
    ) -> Path:
        """Write a single solder joint .fe file.

        Args:
            output_path: Path for the output .fe file.
            geometry: Initial geometry from GeometryBuilder.
            constraints: List of SEConstraint/SERimConstraint objects.
            boundaries: List of SEConstraint objects with is_boundary=True.
            config: Physical and simulation parameters.
        """
        output_path = Path(output_path)

        # Prepare template data
        constraint_defs = []
        for c in constraints:
            if isinstance(c, SERimConstraint):
                constraint_defs.append(ConstraintDef(
                    id=c.constraint_id,
                    formula=c.formula,
                    comment=f"Rim constraint {c.constraint_id}",
                ))
            elif isinstance(c, SEConstraint) and not c.is_boundary:
                constraint_defs.append(ConstraintDef(
                    id=c.constraint_id,
                    formula=c.formula,
                    comment=f"Surface constraint {c.constraint_id}",
                    energy=c.energy if any(e != "0" for e in c.energy) else None,
                    content=c.content if any(e != "0" for e in c.content) else None,
                ))

        boundary_defs = []
        for b in boundaries:
            if isinstance(b, SEConstraint) and b.is_boundary:
                boundary_defs.append(BoundaryDef(
                    id=b.constraint_id,
                    params=b.boundary_params or "parameters 1",
                    definition=b.formula,
                    comment=f"Parametric boundary {b.constraint_id}",
                    energy=b.energy if any(e != "0" for e in b.energy) else None,
                    content=b.content if any(e != "0" for e in b.content) else None,
                ))

        # Prepare vertex data for template
        vert_data = []
        for v in geometry.vertices:
            vd = {
                "id": v.id,
                "x": _fmt(v.x),
                "y": _fmt(v.y),
                "z": _fmt(v.z),
                "constraints": v.constraints if v.constraints else None,
                "boundary": v.boundary,
                "fixed": v.fixed,
                "extras": v.extras,
            }
            # For boundary vertices, use parameter value instead of coordinates
            if v.boundary is not None and v.boundary_param is not None:
                vd["x"] = _fmt(v.boundary_param)
                vd["y"] = ""
                vd["z"] = ""
                vd["constraints"] = None
            vert_data.append(vd)

        # Prepare edge data
        edge_data = []
        for e in geometry.edges:
            edge_data.append({
                "id": e.id,
                "v1": e.v1,
                "v2": e.v2,
                "constraints": e.constraints if e.constraints else None,
                "boundary": e.boundary,
                "fixed": e.fixed,
            })

        # Prepare face data
        face_data = []
        for f in geometry.faces:
            face_data.append({
                "id": f.id,
                "edges": [str(e) for e in f.edges],
                "tension": f.tension,
                "fixed": f.fixed,
                "color": f.color,
                "no_refine": f.no_refine,
            })

        # Prepare body data
        body_data = []
        for b in geometry.bodies:
            body_data.append({
                "id": b.id,
                "faces": [str(f) for f in b.faces],
                "volume": b.volume,
                "density": b.density,
            })

        # Generate evolution script
        evo_script = self._generate_evolution_script(config)

        # Render template
        template = self.env.get_template("solder_basic.fe.j2")
        us = config.unit_system
        content = template.render(
            version="0.1.0",
            joint_name=config.joint_name,
            evolver_version=config.evolver_version,
            tension=config.tension,
            density=config.density,
            gravity=config.gravity,
            radius=config.radius,
            unit_system_name=us.name,
            tension_unit=us.tension_unit,
            density_unit=us.density_unit,
            length_unit=us.length,
            extra_params=config.extra_params,
            constraints=constraint_defs,
            boundaries=boundary_defs,
            vertices=vert_data,
            edges=edge_data,
            faces=face_data,
            bodies=body_data,
            evolution_script=evo_script,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content)
        return output_path

    def write_coupled(
        self,
        output_path: str | Path,
        geometries: list,
        all_constraints: list,
        all_boundaries: list,
        config: SolderJointConfig,
    ) -> Path:
        """Write a coupled multi-joint .fe file."""
        output_path = Path(output_path)

        # Merge all geometries with offset IDs
        merged_verts = []
        merged_edges = []
        merged_faces = []
        merged_bodies = []

        v_offset = 0
        e_offset = 0
        f_offset = 0

        for i, geom in enumerate(geometries):
            for v in geom.vertices:
                mv = dict(
                    id=v.id + v_offset,
                    x=_fmt(v.x), y=_fmt(v.y), z=_fmt(v.z),
                    constraints=v.constraints if v.constraints else None,
                    boundary=v.boundary,
                    fixed=v.fixed,
                    extras=v.extras,
                )
                if v.boundary is not None and v.boundary_param is not None:
                    mv["x"] = _fmt(v.boundary_param)
                    mv["y"] = ""
                    mv["z"] = ""
                    mv["constraints"] = None
                merged_verts.append(mv)

            for e in geom.edges:
                merged_edges.append({
                    "id": e.id + e_offset,
                    "v1": e.v1 + v_offset,
                    "v2": e.v2 + v_offset,
                    "constraints": e.constraints if e.constraints else None,
                    "boundary": e.boundary,
                    "fixed": e.fixed,
                })

            for f in geom.faces:
                offset_edges = []
                for eid in f.edges:
                    sign = 1 if eid > 0 else -1
                    offset_edges.append(str(sign * (abs(eid) + e_offset)))
                merged_faces.append({
                    "id": f.id + f_offset,
                    "edges": offset_edges,
                    "tension": f.tension,
                    "fixed": f.fixed,
                    "color": f.color,
                    "no_refine": f.no_refine,
                })

            for b in geom.bodies:
                offset_faces = [str(abs(fid) + f_offset) for fid in b.faces]
                merged_bodies.append({
                    "id": b.id + i,  # unique body ID per joint
                    "faces": offset_faces,
                    "volume": b.volume,
                    "density": b.density,
                })

            v_offset += geom.n_vertices
            e_offset += geom.n_edges
            f_offset += geom.n_faces

        # Flatten constraints and boundaries
        c_defs = []
        for c in all_constraints:
            if isinstance(c, SERimConstraint):
                c_defs.append(ConstraintDef(
                    id=c.constraint_id, formula=c.formula,
                    comment=f"Rim {c.constraint_id}",
                ))
            elif isinstance(c, SEConstraint) and not c.is_boundary:
                c_defs.append(ConstraintDef(
                    id=c.constraint_id, formula=c.formula,
                    comment=f"Surface {c.constraint_id}",
                    energy=c.energy if any(e != "0" for e in c.energy) else None,
                    content=c.content if any(e != "0" for e in c.content) else None,
                ))

        b_defs = []
        for b in all_boundaries:
            if isinstance(b, SEConstraint) and b.is_boundary:
                b_defs.append(BoundaryDef(
                    id=b.constraint_id,
                    params=b.boundary_params or "parameters 1",
                    definition=b.formula,
                    comment=f"Boundary {b.constraint_id}",
                    energy=b.energy if any(e != "0" for e in b.energy) else None,
                    content=b.content if any(e != "0" for e in b.content) else None,
                ))

        evo_script = self._generate_evolution_script(config)

        template = self.env.get_template("solder_coupled.fe.j2")
        us = config.unit_system
        content = template.render(
            version="0.1.0",
            n_joints=len(geometries),
            evolver_version=config.evolver_version,
            tension=config.tension,
            density=config.density,
            gravity=config.gravity,
            unit_system_name=us.name,
            tension_unit=us.tension_unit,
            density_unit=us.density_unit,
            length_unit=us.length,
            constraints=c_defs,
            boundaries=b_defs,
            vertices=merged_verts,
            edges=merged_edges,
            faces=merged_faces,
            bodies=merged_bodies,
            evolution_script=evo_script,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content)
        return output_path

    def _generate_evolution_script(self, config: SolderJointConfig) -> str:
        """Generate the evolution command script.

        Uses EvolutionStrategy if available on config, otherwise
        falls back to legacy parameters for backward compatibility.
        """
        from kse.solver.evolution_scripts import (
            generate_evolution_script, EvolutionStrategy, _apply_preset,
        )

        if hasattr(config, 'strategy') and config.strategy is not None:
            strategy = config.strategy
            # Fill in inherited values from solver config
            if strategy.n_refine is None:
                strategy.n_refine = config.n_refine_steps
            if strategy.n_gradient is None:
                strategy.n_gradient = config.n_gradient_steps
            if strategy.use_hessian is None:
                strategy.use_hessian = config.use_hessian
            strategy = _apply_preset(strategy)
            return generate_evolution_script(strategy)

        # Legacy fallback: build strategy from old parameters
        strategy = EvolutionStrategy(
            preset="basic",
            n_refine=config.n_refine_steps,
            n_gradient=config.n_gradient_steps,
            use_hessian=config.use_hessian,
            use_volume_correction=True,
            use_equiangulate=True,
        )
        return generate_evolution_script(strategy)


def _fmt(val) -> str:
    """Format a numeric value for .fe output."""
    if isinstance(val, str):
        return val
    if val is None:
        return ""
    f = float(val)
    if abs(f) < 1e-15:
        return "0"
    if f == int(f) and abs(f) < 1e8:
        return str(int(f))
    return f"{f:.10g}"
