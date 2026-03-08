"""STEP file to Surface Evolver .fe pipeline.

Orchestrates STEP loading, B-rep face classification, and .fe generation.
Supports two integration levels:
- Level 1: STEP -> trimesh -> existing ComplexSTLPipeline (run_from_meshes)
- Level 2: STEP -> B-rep face classification -> direct SE conversion (optimal)
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import numpy as np
import trimesh

from .step_reader import STEPReader, ClassifiedSolderMesh, MultiJointAssembly
from .stl_reader import STLReader
from .surface_fitter import SurfaceFitter
from .constraint_gen import ConstraintGenerator
from .fe_writer import FEWriter, SolderJointConfig
from .mesh_preprocessor import MeshPreprocessor
from .boundary_extractor import BoundaryExtractor
from .mesh_to_se import MeshToSEConverter
from .complex_pipeline import ComplexSTLPipeline, ComplexPipelineConfig


@dataclass
class STEPPipelineConfig:
    """Configuration for STEP pipeline."""

    # Physical parameters (CGS)
    tension: float = 480.0
    density: float = 9.0
    gravity: float = 980.0
    contact_angle_bottom: float = 30.0
    contact_angle_top: float = 30.0

    # STEP tessellation
    tessellation_tolerance: float = 0.001
    angular_tolerance: float = 0.1
    contact_distance_tol: float = 1e-4

    # Integration level: 1 = through STL pipeline, 2 = B-rep direct
    integration_level: int = 2

    # Mesh preprocessing (Level 1 only)
    smooth_iterations: int = 0
    max_edge_length: float = 0.0

    # Pad fitting
    pad_extract_margin: float = 1.5
    on_surface_tol: Optional[float] = None

    # Volume
    target_volume: Optional[float] = None

    # Fillet: additional wall STEP files + contact strategy
    wall_step_paths: list = None  # list of Path/str for wall solids
    # Wall contact strategy for fillet/QFN/MLCC:
    #   "pinned" – wall contact vertices are fixed in place (Strategy A).
    #   "full"   – SE enforces contact angle on the wall (Strategy B).
    wall_strategy: str = "pinned"

    # Void modeling
    void_enabled: bool = False
    void_radius: float = 0.05
    void_position: Optional[list] = None  # [x, y, z]; None = auto-center

    # Output
    joint_name: str = "step_joint"

    def __post_init__(self):
        if self.wall_step_paths is None:
            self.wall_step_paths = []


class STEPPipeline:
    """Complete pipeline from STEP files to .fe file."""

    def __init__(self, config: Optional[STEPPipelineConfig] = None):
        self.config = config or STEPPipelineConfig()

    def run_assembly(
        self,
        step_path: Union[str, Path],
        output_path: Union[str, Path],
    ) -> Path:
        """Pipeline from single STEP assembly -> .fe file.

        The STEP file must contain at least 3 solids (bottom_pad, solder, top_pad).
        Parts are auto-identified by Z-position.
        """
        cfg = self.config
        reader = STEPReader(
            tessellation_tolerance=cfg.tessellation_tolerance,
            angular_tolerance=cfg.angular_tolerance,
            contact_tolerance=cfg.contact_distance_tol,
        )

        assembly = reader.load_assembly(step_path)
        assembly = reader.identify_parts(assembly)

        if cfg.integration_level == 1:
            return self._run_level1(assembly, output_path)
        else:
            return self._run_level2(reader, assembly, output_path)

    def run_separate(
        self,
        solder_path: Union[str, Path],
        bottom_pad_path: Union[str, Path],
        top_pad_path: Union[str, Path],
        output_path: Union[str, Path],
    ) -> Path:
        """Pipeline from 3 separate STEP files -> .fe file."""
        cfg = self.config
        reader = STEPReader(
            tessellation_tolerance=cfg.tessellation_tolerance,
            angular_tolerance=cfg.angular_tolerance,
            contact_tolerance=cfg.contact_distance_tol,
        )

        assembly = reader.load_separate(solder_path, bottom_pad_path, top_pad_path)

        if cfg.integration_level == 1:
            return self._run_level1(assembly, output_path)
        else:
            return self._run_level2(reader, assembly, output_path)

    def run_fillet(
        self,
        step_path: Union[str, Path],
        wall_step_paths: list,
        output_path: Union[str, Path],
        wall_strategy: str = "pinned",
    ) -> Path:
        """Pipeline for fillet geometry: solder + pads + wall surfaces.

        Args:
            step_path: STEP assembly with solder + pads.
            wall_step_paths: Additional STEP files for wall/lead surfaces.
            output_path: Output .fe path.
            wall_strategy: How to handle wall contact vertices.
                "pinned" – wall vertices are fixed in place (Strategy A).
                    Faster, suitable when wall contact line position is known.
                "full"   – wall vertices carry a wall constraint and SE
                    enforces the contact angle on the wall (Strategy B).
                    More physically accurate, requires correct wall energy
                    and content integral formulas.
        """
        from .step_reader import PartRole

        cfg = self.config
        reader = STEPReader(
            tessellation_tolerance=cfg.tessellation_tolerance,
            angular_tolerance=cfg.angular_tolerance,
            contact_tolerance=cfg.contact_distance_tol,
        )

        assembly = reader.load_assembly(step_path)
        assembly = reader.identify_parts(assembly)

        # Load wall solids
        for wp in wall_step_paths:
            wall_assy = reader.load_assembly(wp)
            for solid in wall_assy.solids:
                solid.role = PartRole.WALL
                assembly.walls.append(solid)

        return self._run_level2(
            reader, assembly, output_path,
            wall_strategy=wall_strategy or cfg.wall_strategy,
        )

    def run_bridge(
        self,
        step_path: Union[str, Path],
        output_path: Union[str, Path],
    ) -> Path:
        """Pipeline for bridge pad geometry: 1 solder + N pads.

        The STEP file contains 1 solder (largest volume) and N pads.
        Each pad gets its own constraint and boundary loop.

        Args:
            step_path: STEP assembly with solder + N pads.
            output_path: Output .fe path.
        """
        cfg = self.config
        reader = STEPReader(
            tessellation_tolerance=cfg.tessellation_tolerance,
            angular_tolerance=cfg.angular_tolerance,
            contact_tolerance=cfg.contact_distance_tol,
        )

        assembly = reader.load_assembly(step_path)
        assembly = reader.identify_parts_bridge(assembly)

        return self._run_level2_bridge(reader, assembly, output_path)

    def run_array(
        self,
        step_path: Union[str, Path],
        output_dir: Union[str, Path],
    ) -> list:
        """Pipeline for multi-joint BGA/CSP array.

        Identifies N solder joints sharing common pads, generates
        individual .fe files for each joint.

        Args:
            step_path: STEP assembly with 2 pads + N solder bodies.
            output_dir: Directory for output .fe files.

        Returns:
            List of output .fe file paths.
        """
        cfg = self.config
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        reader = STEPReader(
            tessellation_tolerance=cfg.tessellation_tolerance,
            angular_tolerance=cfg.angular_tolerance,
            contact_tolerance=cfg.contact_distance_tol,
        )

        assembly = reader.load_assembly(step_path)
        multi = reader.identify_parts_multi(assembly)

        results = []
        for i, joint_assy in enumerate(multi.joints):
            name = f"{cfg.joint_name}_{i:03d}"
            fe_path = output_dir / f"{name}.fe"
            try:
                self._run_level2(reader, joint_assy, fe_path)
                results.append(fe_path)
            except Exception as e:
                print(f"Joint {i} failed: {e}")

        return results

    def run_array_coupled(
        self,
        step_path: Union[str, Path],
        output_dir: Union[str, Path],
        group_distance: float = 0.0,
    ) -> list:
        """Pipeline for multi-joint array with coupling.

        Nearby joints (within group_distance) are grouped into a single
        coupled .fe file. Joints beyond group_distance are independent.

        Args:
            step_path: STEP assembly with 2 pads + N solder bodies.
            output_dir: Directory for output .fe files.
            group_distance: Max XY distance for grouping. 0 = all independent.

        Returns:
            List of output .fe file paths (one per group).
        """
        cfg = self.config
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        reader = STEPReader(
            tessellation_tolerance=cfg.tessellation_tolerance,
            angular_tolerance=cfg.angular_tolerance,
            contact_tolerance=cfg.contact_distance_tol,
        )

        assembly = reader.load_assembly(step_path)
        multi = reader.identify_parts_multi(assembly)

        if group_distance <= 0 or len(multi.joints) <= 1:
            # Fall back to independent processing
            return self._run_array_independent(reader, multi, output_dir)

        # Group joints by XY proximity
        groups = self._group_joints_by_distance(multi.joints, group_distance)

        results = []
        for gi, group in enumerate(groups):
            if len(group) == 1:
                # Single joint: independent .fe
                name = f"{cfg.joint_name}_{gi:03d}"
                fe_path = output_dir / f"{name}.fe"
                try:
                    self._run_level2(reader, group[0], fe_path)
                    results.append(fe_path)
                except Exception as e:
                    print(f"Joint group {gi} (single) failed: {e}")
            else:
                # Multi-joint: coupled .fe
                name = f"{cfg.joint_name}_coupled_{gi:03d}"
                fe_path = output_dir / f"{name}.fe"
                try:
                    self._run_level2_coupled(reader, group, fe_path)
                    results.append(fe_path)
                except Exception as e:
                    print(f"Joint group {gi} (coupled, {len(group)} joints) failed: {e}")

        return results

    def _run_array_independent(self, reader, multi, output_dir):
        """Process each joint independently."""
        cfg = self.config
        results = []
        for i, joint_assy in enumerate(multi.joints):
            name = f"{cfg.joint_name}_{i:03d}"
            fe_path = output_dir / f"{name}.fe"
            try:
                self._run_level2(reader, joint_assy, fe_path)
                results.append(fe_path)
            except Exception as e:
                print(f"Joint {i} failed: {e}")
        return results

    def _run_level2_coupled(self, reader, assemblies: list, output_path):
        """Run Level 2 pipeline for a group of coupled joints.

        Each joint gets its own constraints (unique IDs), but they share
        a single .fe file.
        """
        cfg = self.config
        output_path = Path(output_path)

        geometries = []
        all_constraints = []
        all_boundaries = []
        c_offset = 0

        for ji, joint_assy in enumerate(assemblies):
            classified = reader.classify_faces(joint_assy)
            lateral_mesh = self._ensure_interior_vertices(classified.lateral_mesh)

            solder_bounds = classified.mesh.bounds
            bot_pad_mesh = classified.pad_bottom_mesh
            top_pad_mesh = classified.pad_top_mesh

            mid_xy = (solder_bounds[0][:2] + solder_bounds[1][:2]) / 2
            center_bottom = np.array([mid_xy[0], mid_xy[1], solder_bounds[0][2]])
            center_top = np.array([mid_xy[0], mid_xy[1], solder_bounds[1][2]])

            pad_radius = self._estimate_pad_radius(classified.mesh, center_bottom)

            reader_b = STLReader.from_mesh(bot_pad_mesh)
            reader_t = STLReader.from_mesh(top_pad_mesh)

            patch_b = reader_b.extract_patch(
                center_bottom, pad_radius * cfg.pad_extract_margin,
            )
            patch_t = reader_t.extract_patch(
                center_top, pad_radius * cfg.pad_extract_margin,
            )

            fitter = SurfaceFitter()
            fit_bottom = fitter.fit(patch_b)
            fit_top = fitter.fit(patch_t)

            # Unique constraint IDs
            c_bot_id = c_offset + 1
            c_top_id = c_offset + 2

            surfaces = [
                ("bottom", c_bot_id, fit_bottom),
                ("top", c_top_id, fit_top),
            ]
            extractor = BoundaryExtractor(
                surfaces=surfaces,
                on_surface_tol=cfg.on_surface_tol,
            )
            extraction = extractor.extract_preclassified(
                lateral_mesh,
                classified.contact_bottom_mask,
                classified.contact_top_mask,
            )

            converter = MeshToSEConverter(
                tension=cfg.tension,
                density=cfg.density,
            )
            target_vol = cfg.target_volume or classified.solder_volume
            se_result = converter.convert(
                extraction.lateral_mesh,
                extraction.boundary_loops,
                target_volume=target_vol,
            )

            cgen = ConstraintGenerator()
            c_bottom = cgen.generate_surface_constraint(
                fit_bottom, c_bot_id,
                contact_angle=cfg.contact_angle_bottom,
                tension=cfg.tension,
                solder_density=cfg.density,
                gravity=cfg.gravity,
                use_boundary_integrals=True,
            )
            c_top = cgen.generate_surface_constraint(
                fit_top, c_top_id,
                contact_angle=cfg.contact_angle_top,
                tension=cfg.tension,
                solder_density=cfg.density,
                gravity=cfg.gravity,
                use_boundary_integrals=True,
            )

            all_constraints.extend([c_bottom, c_top])
            geometries.append(se_result.geometry)
            c_offset += 2

        fe_config = SolderJointConfig(
            joint_name=cfg.joint_name,
            tension=cfg.tension,
            density=cfg.density,
            gravity=cfg.gravity,
            radius=pad_radius,
            volume=0.0,
            contact_angle_A=cfg.contact_angle_bottom,
            contact_angle_B=cfg.contact_angle_top,
        )

        writer = FEWriter()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        writer.write_coupled(
            output_path, geometries, all_constraints, all_boundaries, fe_config,
        )

        return output_path

    @staticmethod
    def _group_joints_by_distance(assemblies: list, distance: float) -> list:
        """Group assemblies by XY centroid proximity using BFS."""
        n = len(assemblies)
        centers = []
        for assy in assemblies:
            solder = assy.solder
            mid = (solder.bounds[0] + solder.bounds[1]) / 2
            centers.append(mid[:2])  # XY only
        centers = np.array(centers)

        visited = [False] * n
        groups = []

        for i in range(n):
            if visited[i]:
                continue
            group = [assemblies[i]]
            visited[i] = True

            queue = [i]
            while queue:
                ci = queue.pop(0)
                for j in range(n):
                    if visited[j]:
                        continue
                    d = np.linalg.norm(centers[ci] - centers[j])
                    if d <= distance:
                        visited[j] = True
                        group.append(assemblies[j])
                        queue.append(j)

            groups.append(group)

        return groups

    def _run_level1(self, assembly, output_path: Union[str, Path]) -> Path:
        """Level 1: Extract trimesh objects, feed to ComplexSTLPipeline."""
        cfg = self.config

        solder_mesh = assembly.solder.combined_mesh
        bot_pad_mesh = assembly.bottom_pad.combined_mesh
        top_pad_mesh = assembly.top_pad.combined_mesh

        complex_config = ComplexPipelineConfig(
            tension=cfg.tension,
            density=cfg.density,
            gravity=cfg.gravity,
            contact_angle_bottom=cfg.contact_angle_bottom,
            contact_angle_top=cfg.contact_angle_top,
            smooth_iterations=cfg.smooth_iterations,
            max_edge_length=cfg.max_edge_length,
            pad_extract_margin=cfg.pad_extract_margin,
            on_surface_tol=cfg.on_surface_tol,
            target_volume=cfg.target_volume,
            joint_name=cfg.joint_name,
        )
        pipeline = ComplexSTLPipeline(complex_config)
        return pipeline.run_from_meshes(
            bot_pad_mesh, top_pad_mesh, solder_mesh, output_path,
        )

    def _run_level2(
        self,
        reader,
        assembly,
        output_path: Union[str, Path],
        wall_strategy: str = "none",
    ) -> Path:
        """Level 2: Use B-rep face classification, skip cap detection.

        Args:
            wall_strategy: "none" | "pinned" | "full".  Passed through to
                MeshToSEConverter and ConstraintGenerator for fillet handling.
        """
        cfg = self.config
        output_path = Path(output_path)

        # 1. Classify faces using B-rep proximity
        classified = reader.classify_faces(assembly)

        # 2. Subdivide lateral mesh if too coarse (ensures interior vertices)
        lateral_mesh = self._ensure_interior_vertices(classified.lateral_mesh)

        # 3. Fit pad surfaces for constraint generation
        bot_pad_mesh = classified.pad_bottom_mesh
        top_pad_mesh = classified.pad_top_mesh

        solder_bounds = classified.mesh.bounds
        mid_xy = (solder_bounds[0][:2] + solder_bounds[1][:2]) / 2
        center_bottom = np.array([mid_xy[0], mid_xy[1], solder_bounds[0][2]])
        center_top = np.array([mid_xy[0], mid_xy[1], solder_bounds[1][2]])

        pad_radius = self._estimate_pad_radius(classified.mesh, center_bottom)

        reader_b = STLReader.from_mesh(bot_pad_mesh)
        reader_t = STLReader.from_mesh(top_pad_mesh)

        patch_b = reader_b.extract_patch(
            center_bottom, pad_radius * cfg.pad_extract_margin,
        )
        patch_t = reader_t.extract_patch(
            center_top, pad_radius * cfg.pad_extract_margin,
        )

        fitter = SurfaceFitter()
        fit_bottom = fitter.fit(patch_b)
        fit_top = fitter.fit(patch_t)

        # 4. Fit wall surfaces (for fillet) if wall contacts exist.
        # has_walls: True when B-rep detects wall contact faces OR when
        # wall meshes were explicitly loaded via run_fillet() (even if the
        # solder surface doesn't physically touch the wall in tessellation).
        wall_fits = []
        has_walls = (
            (classified.contact_wall_mask is not None
             and np.any(classified.contact_wall_mask))
            or bool(classified.wall_meshes)
        )

        if has_walls and classified.wall_meshes:
            for wi, wmesh in enumerate(classified.wall_meshes):
                try:
                    w_reader = STLReader.from_mesh(wmesh)
                    w_center = wmesh.vertices.mean(axis=0)
                    w_radius = np.linalg.norm(
                        wmesh.vertices - w_center, axis=1
                    ).max() * 1.5
                    w_patch = w_reader.extract_patch(w_center, w_radius)
                    fit_wall = fitter.fit(w_patch)
                    wall_fits.append((f"wall_{wi}", 3 + wi, fit_wall))
                except Exception:
                    pass

        # 5. Build N-way surface list for boundary extraction
        surfaces = [
            ("bottom", 1, fit_bottom),
            ("top", 2, fit_top),
        ] + wall_fits

        extractor = BoundaryExtractor(
            surfaces=surfaces,
            on_surface_tol=cfg.on_surface_tol,
        )
        extraction = extractor.extract_preclassified(
            lateral_mesh,
            classified.contact_bottom_mask,
            classified.contact_top_mask,
        )

        # 6a. Per-vertex constraint classification for fillet (when walls exist)
        vertex_multi_constraints = None
        if wall_fits and wall_strategy != "none":
            all_boundary_v_ids = set()
            for loop in extraction.boundary_loops:
                for vid in loop.vertex_ids:
                    all_boundary_v_ids.add(vid)
            vertex_multi_constraints = extractor.classify_boundary_vertices(
                extraction.lateral_mesh.vertices,
                all_boundary_v_ids,
            )

        # 6b. Convert to SE topology
        converter = MeshToSEConverter(
            tension=cfg.tension,
            density=cfg.density,
        )
        target_vol = cfg.target_volume or classified.solder_volume

        if cfg.void_enabled:
            void_mesh = self._create_void_mesh(
                classified.mesh, cfg.void_radius, cfg.void_position,
            )
            se_result = converter.convert_with_void(
                extraction.lateral_mesh,
                extraction.boundary_loops,
                void_mesh,
                target_volume=target_vol,
            )
        else:
            se_result = converter.convert(
                extraction.lateral_mesh,
                extraction.boundary_loops,
                target_volume=target_vol,
                vertex_multi_constraints=vertex_multi_constraints,
                wall_strategy=wall_strategy,
            )

        # 7. Generate constraints
        cgen = ConstraintGenerator()
        all_constraints = []

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
        all_constraints = [c_bottom, c_top]

        # Wall constraints (fillet)
        for pad_id, cid, fit_wall in wall_fits:
            if wall_strategy == "full":
                c_wall = cgen.generate_wall_constraint(
                    fit_wall, cid,
                    contact_angle_wall=cfg.contact_angle_bottom,
                    tension=cfg.tension,
                    strategy="full",
                )
            else:
                # Strategy A (pinned): formula only — wall vertices are fixed
                c_wall = cgen.generate_wall_constraint(
                    fit_wall, cid,
                    strategy="pinned",
                )
            all_constraints.append(c_wall)

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
            all_constraints,
            [],
            fe_config,
        )

        return output_path

    def _run_level2_bridge(
        self, reader, assembly, output_path: Union[str, Path],
    ) -> Path:
        """Level 2 pipeline for bridge: N pads."""
        cfg = self.config
        output_path = Path(output_path)

        # 1. Classify faces against N pads
        classified = reader.classify_faces_bridge(assembly)

        # 2. Subdivide lateral mesh if needed
        lateral_mesh = self._ensure_interior_vertices(classified.lateral_mesh)

        # 3. Fit each pad surface
        fitter = SurfaceFitter()
        surfaces = []

        for pi, pad in enumerate(assembly.pads):
            pad_mesh = pad.combined_mesh
            if pad_mesh is None:
                continue

            pad_center = pad_mesh.vertices.mean(axis=0)
            pad_radius = np.linalg.norm(
                pad_mesh.vertices - pad_center, axis=1,
            ).max() * 1.2

            reader_p = STLReader.from_mesh(pad_mesh)
            patch = reader_p.extract_patch(pad_center, pad_radius)
            fit = fitter.fit(patch)

            pad_id = f"pad_{pi}"
            constraint_id = pi + 1  # 1-based
            surfaces.append((pad_id, constraint_id, fit))

        # 4. Boundary extraction with N surfaces
        extractor = BoundaryExtractor(
            surfaces=surfaces,
            on_surface_tol=cfg.on_surface_tol,
        )
        extraction = extractor.extract_preclassified(
            lateral_mesh,
            contact_bottom_mask=None,
            contact_top_mask=None,
        )

        # 5. Convert to SE topology
        converter = MeshToSEConverter(
            tension=cfg.tension,
            density=cfg.density,
        )
        se_result = converter.convert(
            extraction.lateral_mesh,
            extraction.boundary_loops,
            target_volume=cfg.target_volume or classified.solder_volume,
        )

        # 6. Generate constraints for each pad
        cgen = ConstraintGenerator()
        all_constraints = []

        for pad_id, cid, fit in surfaces:
            c = cgen.generate_surface_constraint(
                fit, cid,
                contact_angle=cfg.contact_angle_bottom,
                tension=cfg.tension,
                solder_density=cfg.density,
                gravity=cfg.gravity,
                use_boundary_integrals=True,
            )
            all_constraints.append(c)

        # 7. Write .fe file
        solder_mesh = classified.mesh
        pad_radius = self._estimate_pad_radius(
            solder_mesh, solder_mesh.vertices.mean(axis=0),
        )

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
            all_constraints,
            [],
            fe_config,
        )

        return output_path

    @staticmethod
    def _create_void_mesh(
        solder_mesh: trimesh.Trimesh,
        radius: float,
        position: Optional[list] = None,
    ) -> trimesh.Trimesh:
        """Create a spherical void mesh inside the solder.

        Args:
            solder_mesh: Full solder mesh (for auto-centering).
            radius: Void sphere radius.
            position: [x, y, z] center. If None, uses solder centroid.
        """
        if position is not None:
            center = np.array(position, dtype=float)
        else:
            bounds = solder_mesh.bounds
            center = (bounds[0] + bounds[1]) / 2

        void_mesh = trimesh.creation.icosphere(subdivisions=2, radius=radius)
        void_mesh.apply_translation(center)
        return void_mesh

    @staticmethod
    def _ensure_interior_vertices(lateral_mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """Subdivide lateral mesh if it lacks interior vertices.

        B-rep tessellation of simple surfaces (e.g., a cylinder) may
        produce triangles where all vertices lie on the boundary.
        SE needs free (interior) vertices for gradient/hessian evolution.
        """
        from collections import defaultdict
        from kse.mesh.refiner import subdivide_long_edges

        # Check if mesh has interior vertices by finding boundary vertices
        edge_face_count = defaultdict(int)
        for face in lateral_mesh.faces:
            for i in range(3):
                v1, v2 = int(face[i]), int(face[(i + 1) % 3])
                key = (min(v1, v2), max(v1, v2))
                edge_face_count[key] += 1

        boundary_verts = set()
        for (v1, v2), count in edge_face_count.items():
            if count == 1:
                boundary_verts.add(v1)
                boundary_verts.add(v2)

        n_interior = len(lateral_mesh.vertices) - len(boundary_verts)

        if n_interior < 10:
            # Not enough interior vertices. Subdivide edges to create them.
            # Use half of the mean edge length as threshold.
            edges_arr = lateral_mesh.edges_unique
            edge_vecs = lateral_mesh.vertices[edges_arr[:, 1]] - lateral_mesh.vertices[edges_arr[:, 0]]
            edge_lens = np.linalg.norm(edge_vecs, axis=1)
            max_edge = edge_lens.mean() * 0.6

            # May need multiple passes for very coarse meshes
            verts = lateral_mesh.vertices
            faces = lateral_mesh.faces
            for _ in range(3):
                new_verts, new_faces = subdivide_long_edges(verts, faces, max_edge)
                if len(new_verts) > len(verts):
                    verts = new_verts
                    faces = new_faces
                else:
                    break

            lateral_mesh = trimesh.Trimesh(
                vertices=verts, faces=faces, process=False,
            )

        return lateral_mesh

    @staticmethod
    def _estimate_pad_radius(mesh: trimesh.Trimesh, center: np.ndarray) -> float:
        """Estimate pad radius from solder mesh lateral extent."""
        verts = mesh.vertices
        dx = verts[:, 0] - center[0]
        dy = verts[:, 1] - center[1]
        dists = np.sqrt(dx**2 + dy**2)
        return float(np.max(dists)) * 1.1
