"""High-level pipeline for complex CAD-derived STL inputs.

Orchestrates: pad STL fitting, solder mesh preprocessing,
boundary extraction, SE topology conversion, and .fe generation.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import trimesh

from .stl_reader import STLReader
from .surface_fitter import SurfaceFitter, SurfaceFitResult
from .constraint_gen import ConstraintGenerator
from .geometry_builder import InitialGeometry
from .fe_writer import FEWriter, SolderJointConfig
from .mesh_preprocessor import MeshPreprocessor
from .boundary_extractor import BoundaryExtractor
from .mesh_to_se import MeshToSEConverter


@dataclass
class ComplexPipelineConfig:
    """Configuration for complex STL pipeline."""

    # Physical parameters (CGS)
    tension: float = 480.0
    density: float = 9.0
    gravity: float = 980.0
    contact_angle_bottom: float = 30.0
    contact_angle_top: float = 30.0

    # Mesh preprocessing
    smooth_iterations: int = 0
    max_edge_length: float = 0.0
    on_surface_tol: Optional[float] = None

    # Pad fitting
    pad_extract_margin: float = 1.5

    # Volume
    target_volume: Optional[float] = None

    # Output
    joint_name: str = "complex_joint"


class ComplexSTLPipeline:
    """Complete pipeline from 3 CAD STLs to .fe file."""

    def __init__(self, config: Optional[ComplexPipelineConfig] = None):
        self.config = config or ComplexPipelineConfig()

    def run(
        self,
        bottom_pad_stl: str | Path,
        top_pad_stl: str | Path,
        solder_stl: str | Path,
        output_path: str | Path,
        center_bottom: Optional[np.ndarray] = None,
        center_top: Optional[np.ndarray] = None,
    ) -> Path:
        """Complete pipeline: 3 STL files → .fe file.

        Args:
            bottom_pad_stl: Path to bottom pad surface STL.
            top_pad_stl: Path to top pad surface STL.
            solder_stl: Path to initial solder shape STL.
            output_path: Output .fe file path.
            center_bottom: Approximate center on bottom pad.
                If None, uses solder mesh centroid projected down.
            center_top: Approximate center on top pad.
                If None, uses solder mesh centroid projected up.

        Returns:
            Path to generated .fe file.
        """
        cfg = self.config
        output_path = Path(output_path)

        # 1. Load solder mesh
        solder_mesh = trimesh.load(str(solder_stl), force="mesh")

        # 2. Preprocess solder mesh
        preprocessor = MeshPreprocessor(
            smooth_iterations=cfg.smooth_iterations,
            max_edge_length=cfg.max_edge_length,
        )
        prep = preprocessor.preprocess(solder_mesh)
        solder_mesh = prep.mesh

        # 3. Auto-detect pad centers if not provided
        if center_bottom is None or center_top is None:
            bounds = solder_mesh.bounds
            mid_xy = (bounds[0][:2] + bounds[1][:2]) / 2
            if center_bottom is None:
                center_bottom = np.array([mid_xy[0], mid_xy[1], bounds[0][2]])
            if center_top is None:
                center_top = np.array([mid_xy[0], mid_xy[1], bounds[1][2]])

        center_bottom = np.asarray(center_bottom, dtype=float)
        center_top = np.asarray(center_top, dtype=float)

        # 4. Estimate pad extraction radius from solder mesh extent
        pad_radius = self._estimate_pad_radius(solder_mesh, center_bottom)

        # 5. Fit pad surfaces
        reader_bottom = STLReader(bottom_pad_stl)
        reader_top = STLReader(top_pad_stl)

        patch_bottom = reader_bottom.extract_patch(
            center_bottom, pad_radius * cfg.pad_extract_margin,
        )
        patch_top = reader_top.extract_patch(
            center_top, pad_radius * cfg.pad_extract_margin,
        )

        fitter = SurfaceFitter()
        fit_bottom = fitter.fit(patch_bottom)
        fit_top = fitter.fit(patch_top)

        # 6. Extract boundaries
        extractor = BoundaryExtractor(
            fit_bottom=fit_bottom,
            fit_top=fit_top,
            on_surface_tol=cfg.on_surface_tol,
        )
        extraction = extractor.extract(solder_mesh)

        # 7. Convert to SE topology
        converter = MeshToSEConverter(
            tension=cfg.tension,
            density=cfg.density,
        )
        se_result = converter.convert(
            extraction.lateral_mesh,
            extraction.boundary_loops,
            target_volume=cfg.target_volume,
        )

        # 8. Generate constraints with energy/content integrals
        cgen = ConstraintGenerator()
        c_bottom = cgen.generate_surface_constraint(
            fit_bottom, 1,
            contact_angle=cfg.contact_angle_bottom,
            tension=cfg.tension,
            solder_density=cfg.density,
            gravity=cfg.gravity,
            use_boundary_integrals=True,
        )
        c_top = cgen.generate_surface_constraint(
            fit_top, 2,
            contact_angle=cfg.contact_angle_top,
            tension=cfg.tension,
            solder_density=cfg.density,
            gravity=cfg.gravity,
            use_boundary_integrals=True,
        )

        # 9. Write .fe file
        fe_config = SolderJointConfig(
            joint_name=cfg.joint_name,
            tension=cfg.tension,
            density=cfg.density,
            gravity=cfg.gravity,
            radius=pad_radius,
            volume=se_result.computed_volume,
            contact_angle_A=cfg.contact_angle_bottom,
            contact_angle_B=cfg.contact_angle_top,
        )

        writer = FEWriter()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        writer.write_single(
            output_path,
            se_result.geometry,
            [c_bottom, c_top],  # constraints with integrals
            [],  # no parametric boundaries
            fe_config,
        )

        return output_path

    def run_from_meshes(
        self,
        bottom_pad_mesh: trimesh.Trimesh,
        top_pad_mesh: trimesh.Trimesh,
        solder_mesh: trimesh.Trimesh,
        output_path: str | Path,
        center_bottom: Optional[np.ndarray] = None,
        center_top: Optional[np.ndarray] = None,
    ) -> Path:
        """Pipeline from 3 trimesh objects -> .fe file.

        Same as run() but accepts trimesh objects directly
        instead of file paths. Used by STEP pipeline (Level 1).
        """
        cfg = self.config
        output_path = Path(output_path)

        # 1. Preprocess solder mesh
        preprocessor = MeshPreprocessor(
            smooth_iterations=cfg.smooth_iterations,
            max_edge_length=cfg.max_edge_length,
        )
        prep = preprocessor.preprocess(solder_mesh)
        solder_mesh = prep.mesh

        # 2. Auto-detect pad centers
        if center_bottom is None or center_top is None:
            bounds = solder_mesh.bounds
            mid_xy = (bounds[0][:2] + bounds[1][:2]) / 2
            if center_bottom is None:
                center_bottom = np.array([mid_xy[0], mid_xy[1], bounds[0][2]])
            if center_top is None:
                center_top = np.array([mid_xy[0], mid_xy[1], bounds[1][2]])

        center_bottom = np.asarray(center_bottom, dtype=float)
        center_top = np.asarray(center_top, dtype=float)

        # 3. Estimate pad extraction radius
        pad_radius = self._estimate_pad_radius(solder_mesh, center_bottom)

        # 4. Fit pad surfaces from trimesh objects
        reader_bottom = STLReader.from_mesh(bottom_pad_mesh)
        reader_top = STLReader.from_mesh(top_pad_mesh)

        patch_bottom = reader_bottom.extract_patch(
            center_bottom, pad_radius * cfg.pad_extract_margin,
        )
        patch_top = reader_top.extract_patch(
            center_top, pad_radius * cfg.pad_extract_margin,
        )

        fitter = SurfaceFitter()
        fit_bottom = fitter.fit(patch_bottom)
        fit_top = fitter.fit(patch_top)

        # 5. Extract boundaries
        extractor = BoundaryExtractor(
            fit_bottom=fit_bottom,
            fit_top=fit_top,
            on_surface_tol=cfg.on_surface_tol,
        )
        extraction = extractor.extract(solder_mesh)

        # 6. Convert to SE topology
        converter = MeshToSEConverter(
            tension=cfg.tension,
            density=cfg.density,
        )
        se_result = converter.convert(
            extraction.lateral_mesh,
            extraction.boundary_loops,
            target_volume=cfg.target_volume,
        )

        # 7. Generate constraints
        cgen = ConstraintGenerator()
        c_bottom = cgen.generate_surface_constraint(
            fit_bottom, 1,
            contact_angle=cfg.contact_angle_bottom,
            tension=cfg.tension,
            solder_density=cfg.density,
            gravity=cfg.gravity,
            use_boundary_integrals=True,
        )
        c_top = cgen.generate_surface_constraint(
            fit_top, 2,
            contact_angle=cfg.contact_angle_top,
            tension=cfg.tension,
            solder_density=cfg.density,
            gravity=cfg.gravity,
            use_boundary_integrals=True,
        )

        # 8. Write .fe file
        fe_config = SolderJointConfig(
            joint_name=cfg.joint_name,
            tension=cfg.tension,
            density=cfg.density,
            gravity=cfg.gravity,
            radius=pad_radius,
            volume=se_result.computed_volume,
            contact_angle_A=cfg.contact_angle_bottom,
            contact_angle_B=cfg.contact_angle_top,
        )

        writer = FEWriter()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        writer.write_single(
            output_path,
            se_result.geometry,
            [c_bottom, c_top],
            [],
            fe_config,
        )

        return output_path

    def _estimate_pad_radius(
        self, mesh: trimesh.Trimesh, center: np.ndarray
    ) -> float:
        """Estimate pad radius from solder mesh lateral extent."""
        verts = mesh.vertices
        # Distance from center in XY plane
        dx = verts[:, 0] - center[0]
        dy = verts[:, 1] - center[1]
        dists = np.sqrt(dx**2 + dy**2)
        return float(np.max(dists)) * 1.1  # 10% margin
