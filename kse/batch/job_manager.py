"""Job queue manager for batch solder simulations."""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from .parallel_runner import ParallelRunner, JointDefinition, BatchResult, load_joints_csv
from .coupled_runner import CoupledRunner
from ..core.fe_writer import SolderJointConfig
from ..solver.dump_parser import DumpParser
from ..mesh.quality import assess_quality, assess_tet_quality
from ..mesh.volume_mesher import generate_volume_mesh
from ..mesh.exporters.stl_export import export_stl_ascii, export_stl_binary
from ..mesh.exporters.vtk_export import export_vtk, export_vtk_solid
from ..mesh.exporters.gmsh_export import export_gmsh, export_gmsh_solid
from ..mesh.exporters.ansys_export import export_ansys_cdb, export_ansys_cdb_solid
from ..mesh.exporters.lsdyna_export import export_lsdyna_k, export_lsdyna_k_solid


# Surface mesh exporters (triangles)
SURFACE_EXPORT_FUNCS = {
    "stl":     lambda v, t, p, **kw: export_stl_ascii(v, t, p.with_suffix(".stl"), **kw),
    "stl_bin": lambda v, t, p, **kw: export_stl_binary(v, t, p.with_suffix(".stl"), **kw),
    "vtk":     lambda v, t, p, **kw: export_vtk(v, t, p.with_suffix(".vtk"), **kw),
}

# Solid mesh exporters (tetrahedra) — require volume meshing step
SOLID_EXPORT_FUNCS = {
    "gmsh":    lambda v, tet, p, **kw: export_gmsh_solid(v, tet, p.with_suffix(".msh"), **kw),
    "ansys":   lambda v, tet, p, **kw: export_ansys_cdb_solid(v, tet, p.with_suffix(".cdb"), **kw),
    "lsdyna":  lambda v, tet, p, **kw: export_lsdyna_k_solid(v, tet, p.with_suffix(".k"), **kw),
    "vtk_solid": lambda v, tet, p, **kw: export_vtk_solid(v, tet, p.with_suffix(".vtk"), **kw),
}

# Unified lookup (for backward-compatible callers)
EXPORT_FUNCS = {**SURFACE_EXPORT_FUNCS, **SOLID_EXPORT_FUNCS}


class JobManager:
    """High-level manager for batch solder simulation jobs."""

    def __init__(
        self,
        evolver_path: Optional[str | Path] = None,
        config: Optional[SolderJointConfig] = None,
    ):
        self.evolver_path = evolver_path
        self.config = config or SolderJointConfig()
        self.parser = DumpParser()

    def run_and_export(
        self,
        stl_A: str | Path,
        stl_B: str | Path,
        joints: list,
        output_dir: str | Path,
        formats: list = None,
        mode: str = "parallel",
        max_workers: int = 0,
        group_distance: float = 0.0,
        timeout: int = 300,
    ) -> dict:
        """Run simulations and export results in requested formats.

        Args:
            stl_A: Path to bottom surface STL.
            stl_B: Path to top surface STL.
            joints: List of JointDefinition objects.
            output_dir: Output directory.
            formats: List of export formats (stl, vtk, gmsh, ansys, lsdyna).
            mode: "parallel" or "coupled".
            max_workers: Number of parallel workers.
            group_distance: Distance for joint grouping (coupled mode).
            timeout: Timeout per job in seconds.
        """
        if formats is None:
            formats = ["stl", "vtk"]

        output_dir = Path(output_dir)

        # Run simulations
        if mode == "coupled":
            runner = CoupledRunner(self.evolver_path, self.config)
            result = runner.run_coupled(
                stl_A, stl_B, joints, output_dir, group_distance, timeout
            )
            dump_files = [result.dump_file] if result.dump_file else []
        else:
            runner = ParallelRunner(self.evolver_path, max_workers, self.config)
            batch_result = runner.run_batch(
                stl_A, stl_B, joints, output_dir, timeout
            )
            dump_files = [
                r.dump_file for _, r in batch_result.results
                if r and r.dump_file
            ]

        # Process and export each result
        export_results = {}
        for dump_file in dump_files:
            if dump_file is None or not dump_file.exists():
                continue

            mesh = self.parser.parse(dump_file)
            vertices = mesh.vertex_array
            triangles = mesh.face_triangles

            if len(triangles) == 0:
                continue

            # Quality assessment
            quality = assess_quality(vertices, triangles)
            name = dump_file.stem
            export_dir = dump_file.parent
            out_path = export_dir / name
            exported = {}

            # Surface exports
            surf_fmts = [f.lower().replace("-", "_") for f in formats
                         if f.lower().replace("-", "_") in SURFACE_EXPORT_FUNCS]
            for fmt in surf_fmts:
                try:
                    path = SURFACE_EXPORT_FUNCS[fmt](vertices, triangles, out_path)
                    exported[fmt] = str(path)
                except Exception as e:
                    exported[fmt] = f"ERROR: {e}"

            # Solid exports — generate volume mesh once if any solid format requested
            solid_fmts = [f.lower().replace("-", "_") for f in formats
                          if f.lower().replace("-", "_") in SOLID_EXPORT_FUNCS]
            if solid_fmts:
                try:
                    vol = generate_volume_mesh(vertices, triangles)
                    tet_quality = assess_tet_quality(vol.vertices, vol.tetrahedra)
                    for fmt in solid_fmts:
                        try:
                            path = SOLID_EXPORT_FUNCS[fmt](vol.vertices, vol.tetrahedra, out_path)
                            exported[fmt] = str(path)
                        except Exception as e:
                            exported[fmt] = f"ERROR: {e}"
                except ImportError as e:
                    for fmt in solid_fmts:
                        exported[fmt] = f"ERROR: {e}"
                    tet_quality = None
                except Exception as e:
                    for fmt in solid_fmts:
                        exported[fmt] = f"ERROR: {e}"
                    tet_quality = None
            else:
                tet_quality = None

            export_results[name] = {
                "quality": quality.summary(),
                "fem_suitable": quality.fem_suitable,
                "tet_quality": tet_quality.summary() if tet_quality else None,
                "tet_fem_suitable": tet_quality.fem_suitable if tet_quality else None,
                "files": exported,
            }

        # Save summary
        summary_path = output_dir / "summary.json"
        summary = {
            "n_joints": len(joints),
            "n_exported": len(export_results),
            "formats": formats,
            "results": {
                k: {"fem_suitable": v["fem_suitable"], "files": v["files"]}
                for k, v in export_results.items()
            },
        }
        summary_path.write_text(json.dumps(summary, indent=2))

        return export_results
