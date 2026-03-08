"""Phase 8: STEP (.stp) file pipeline validation.

Tests the STEP-based pipeline: STEP loading, B-rep face classification,
part identification, and end-to-end .fe generation.

Test classes:
- TestSTEPLoading: STEP file loading, solid/face enumeration, tessellation
- TestPartIdentification: Z-position based part role assignment
- TestFaceClassification: B-rep contact vs free face classification
- TestSTEPPipelineLevel1: Level 1 integration (STEP -> trimesh -> STL pipeline)
- TestSTEPPipelineLevel2: Level 2 integration (B-rep labels -> SE)
- TestSTEPPipelineSE: SE convergence for STEP-derived .fe files
- TestSeparateFiles: 3 separate STEP file mode
"""

import numpy as np
import pytest
import trimesh

from kse.core.step_reader import (
    STEPReader, STEPAssembly, STEPSolid, STEPFace,
    ClassifiedSolderMesh, FaceRole, PartRole,
)

from .helpers.step_generators import (
    generate_cylinder_assembly_step,
    generate_barrel_assembly_step,
    generate_box_assembly_step,
    generate_separate_step_files,
)

# Skip entire module if CadQuery is not available
pytest.importorskip("cadquery")

# ---------------------------------------------------------------------------
# Shared geometry constants (CGS units)
# ---------------------------------------------------------------------------
RADIUS = 0.010        # solder radius, cm
PAD_RADIUS = 0.015    # pad radius, cm
HEIGHT = 0.005        # standoff height, cm
PAD_THICK = 0.002     # pad thickness, cm
BOTTOM_CENTER = np.array([0.0, 0.0, 0.0])
TOP_CENTER = np.array([0.0, 0.0, HEIGHT])
TENSION = 480.0
DENSITY = 9.0
GRAVITY = 980.0


# ===========================================================================
# TestSTEPLoading
# ===========================================================================
class TestSTEPLoading:
    """Verify STEP file loading, solid enumeration, and tessellation."""

    def test_cylinder_assembly_loads(self, tmp_path):
        """Cylinder assembly STEP loads and contains 3 solids."""
        step_file = generate_cylinder_assembly_step(
            BOTTOM_CENTER, TOP_CENTER, RADIUS, PAD_RADIUS,
            pad_thickness=PAD_THICK, output_path=tmp_path / "cyl.step",
        )
        reader = STEPReader()
        assembly = reader.load_assembly(step_file)

        assert len(assembly.solids) == 3, (
            f"Expected 3 solids, got {len(assembly.solids)}"
        )
        print(f"Loaded {len(assembly.solids)} solids from cylinder assembly")

    def test_barrel_assembly_loads(self, tmp_path):
        """Barrel assembly STEP loads and contains 3 solids."""
        step_file = generate_barrel_assembly_step(
            BOTTOM_CENTER, TOP_CENTER,
            radius_end=RADIUS * 0.8, radius_mid=RADIUS,
            pad_radius=PAD_RADIUS, pad_thickness=PAD_THICK,
            output_path=tmp_path / "barrel.step",
        )
        reader = STEPReader()
        assembly = reader.load_assembly(step_file)

        assert len(assembly.solids) == 3
        print(f"Barrel assembly: {len(assembly.solids)} solids")

    def test_box_assembly_loads(self, tmp_path):
        """Box assembly STEP loads and contains 3 solids."""
        step_file = generate_box_assembly_step(
            BOTTOM_CENTER, TOP_CENTER,
            solder_side=RADIUS * 1.5, pad_side=PAD_RADIUS * 2,
            pad_thickness=PAD_THICK, output_path=tmp_path / "box.step",
        )
        reader = STEPReader()
        assembly = reader.load_assembly(step_file)

        assert len(assembly.solids) == 3
        print(f"Box assembly: {len(assembly.solids)} solids")

    def test_each_solid_has_faces(self, tmp_path):
        """Each solid should have at least 1 face."""
        step_file = generate_cylinder_assembly_step(
            BOTTOM_CENTER, TOP_CENTER, RADIUS, PAD_RADIUS,
            pad_thickness=PAD_THICK, output_path=tmp_path / "cyl.step",
        )
        reader = STEPReader()
        assembly = reader.load_assembly(step_file)

        for solid in assembly.solids:
            assert len(solid.faces) > 0, (
                f"Solid '{solid.name}' has no faces"
            )
            print(f"  {solid.name}: {len(solid.faces)} faces, "
                  f"vol={solid.volume:.6e}")

    def test_faces_have_valid_meshes(self, tmp_path):
        """Each face should have a valid tessellation."""
        step_file = generate_cylinder_assembly_step(
            BOTTOM_CENTER, TOP_CENTER, RADIUS, PAD_RADIUS,
            pad_thickness=PAD_THICK, output_path=tmp_path / "cyl.step",
        )
        reader = STEPReader()
        assembly = reader.load_assembly(step_file)

        for solid in assembly.solids:
            for face in solid.faces:
                assert len(face.mesh.vertices) > 0, (
                    f"Face {face.face_id} in {solid.name} has no vertices"
                )
                assert len(face.mesh.faces) > 0, (
                    f"Face {face.face_id} in {solid.name} has no triangles"
                )
                assert face.area > 0, (
                    f"Face {face.face_id} in {solid.name} has zero area"
                )

        total_faces = sum(len(s.faces) for s in assembly.solids)
        print(f"All {total_faces} faces have valid tessellations")

    def test_combined_mesh_exists(self, tmp_path):
        """Each solid should have a combined_mesh."""
        step_file = generate_cylinder_assembly_step(
            BOTTOM_CENTER, TOP_CENTER, RADIUS, PAD_RADIUS,
            pad_thickness=PAD_THICK, output_path=tmp_path / "cyl.step",
        )
        reader = STEPReader()
        assembly = reader.load_assembly(step_file)

        for solid in assembly.solids:
            assert solid.combined_mesh is not None, (
                f"Solid '{solid.name}' has no combined mesh"
            )
            assert len(solid.combined_mesh.vertices) > 0
            assert len(solid.combined_mesh.faces) > 0
        print("All solids have combined meshes")


# ===========================================================================
# TestPartIdentification
# ===========================================================================
class TestPartIdentification:
    """Verify automatic part role identification."""

    def test_three_solids_identified(self, tmp_path):
        """3-solid assembly: Z-position identifies bottom_pad, solder, top_pad."""
        step_file = generate_cylinder_assembly_step(
            BOTTOM_CENTER, TOP_CENTER, RADIUS, PAD_RADIUS,
            pad_thickness=PAD_THICK, output_path=tmp_path / "cyl.step",
        )
        reader = STEPReader()
        assembly = reader.load_assembly(step_file)
        assembly = reader.identify_parts(assembly)

        assert assembly.bottom_pad is not None
        assert assembly.solder is not None
        assert assembly.top_pad is not None
        assert assembly.bottom_pad.role == PartRole.BOTTOM_PAD
        assert assembly.solder.role == PartRole.SOLDER
        assert assembly.top_pad.role == PartRole.TOP_PAD
        print(f"Identified: bottom_pad={assembly.bottom_pad.name}, "
              f"solder={assembly.solder.name}, top_pad={assembly.top_pad.name}")

    def test_solder_is_middle_z(self, tmp_path):
        """Solder Z-centroid should be between the two pads."""
        step_file = generate_cylinder_assembly_step(
            BOTTOM_CENTER, TOP_CENTER, RADIUS, PAD_RADIUS,
            pad_thickness=PAD_THICK, output_path=tmp_path / "cyl.step",
        )
        reader = STEPReader()
        assembly = reader.load_assembly(step_file)
        assembly = reader.identify_parts(assembly)

        def z_center(s):
            return (s.bounds[0][2] + s.bounds[1][2]) / 2

        z_bot = z_center(assembly.bottom_pad)
        z_sol = z_center(assembly.solder)
        z_top = z_center(assembly.top_pad)

        assert z_bot < z_sol < z_top, (
            f"Z order wrong: bot={z_bot:.4f}, sol={z_sol:.4f}, top={z_top:.4f}"
        )
        print(f"Z-centroids: bot={z_bot:.5f}, sol={z_sol:.5f}, top={z_top:.5f}")

    def test_barrel_parts_identified(self, tmp_path):
        """Barrel assembly parts correctly identified."""
        step_file = generate_barrel_assembly_step(
            BOTTOM_CENTER, TOP_CENTER,
            radius_end=RADIUS * 0.8, radius_mid=RADIUS,
            pad_radius=PAD_RADIUS, pad_thickness=PAD_THICK,
            output_path=tmp_path / "barrel.step",
        )
        reader = STEPReader()
        assembly = reader.load_assembly(step_file)
        assembly = reader.identify_parts(assembly)

        assert assembly.solder is not None
        assert assembly.bottom_pad is not None
        assert assembly.top_pad is not None
        print(f"Barrel solder volume: {assembly.solder.volume:.6e}")

    def test_box_parts_identified(self, tmp_path):
        """Box assembly parts correctly identified."""
        step_file = generate_box_assembly_step(
            BOTTOM_CENTER, TOP_CENTER,
            solder_side=RADIUS * 1.5, pad_side=PAD_RADIUS * 2,
            pad_thickness=PAD_THICK, output_path=tmp_path / "box.step",
        )
        reader = STEPReader()
        assembly = reader.load_assembly(step_file)
        assembly = reader.identify_parts(assembly)

        assert assembly.solder.role == PartRole.SOLDER
        assert assembly.bottom_pad.role == PartRole.BOTTOM_PAD
        assert assembly.top_pad.role == PartRole.TOP_PAD
        print("Box parts identified correctly")


# ===========================================================================
# TestFaceClassification
# ===========================================================================
class TestFaceClassification:
    """Verify B-rep contact face classification."""

    def test_cylinder_contact_faces_detected(self, tmp_path):
        """Cylinder: should have both contact_bottom and contact_top faces."""
        step_file = generate_cylinder_assembly_step(
            BOTTOM_CENTER, TOP_CENTER, RADIUS, PAD_RADIUS,
            pad_thickness=PAD_THICK, output_path=tmp_path / "cyl.step",
        )
        reader = STEPReader()
        assembly = reader.load_assembly(step_file)
        assembly = reader.identify_parts(assembly)
        classified = reader.classify_faces(assembly)

        has_bottom = np.any(classified.contact_bottom_mask)
        has_top = np.any(classified.contact_top_mask)

        assert has_bottom, "Should detect bottom contact faces"
        assert has_top, "Should detect top contact faces"

        n_bot = int(np.sum(classified.contact_bottom_mask))
        n_top = int(np.sum(classified.contact_top_mask))
        n_lat = int(np.sum(classified.face_roles == 2))
        print(f"Cylinder faces: bottom_contact={n_bot}, "
              f"top_contact={n_top}, lateral={n_lat}")

    def test_lateral_faces_exist(self, tmp_path):
        """Cylinder should have lateral (free) faces."""
        step_file = generate_cylinder_assembly_step(
            BOTTOM_CENTER, TOP_CENTER, RADIUS, PAD_RADIUS,
            pad_thickness=PAD_THICK, output_path=tmp_path / "cyl.step",
        )
        reader = STEPReader()
        assembly = reader.load_assembly(step_file)
        assembly = reader.identify_parts(assembly)
        classified = reader.classify_faces(assembly)

        n_lateral = int(np.sum(classified.face_roles == 2))
        assert n_lateral > 0, "Should have lateral faces"
        assert len(classified.lateral_mesh.vertices) > 0
        assert len(classified.lateral_mesh.faces) > 0
        print(f"Lateral mesh: {len(classified.lateral_mesh.vertices)} verts, "
              f"{len(classified.lateral_mesh.faces)} faces")

    def test_box_contact_faces(self, tmp_path):
        """Box: flat top and bottom faces should be classified as contact."""
        step_file = generate_box_assembly_step(
            BOTTOM_CENTER, TOP_CENTER,
            solder_side=RADIUS * 1.5, pad_side=PAD_RADIUS * 2,
            pad_thickness=PAD_THICK, output_path=tmp_path / "box.step",
        )
        reader = STEPReader()
        assembly = reader.load_assembly(step_file)
        assembly = reader.identify_parts(assembly)
        classified = reader.classify_faces(assembly)

        assert np.any(classified.contact_bottom_mask)
        assert np.any(classified.contact_top_mask)
        n_lat = int(np.sum(classified.face_roles == 2))
        assert n_lat > 0, "Box should have 4 lateral faces"
        print(f"Box: lateral triangles={n_lat}")

    def test_classified_mesh_has_all_triangles(self, tmp_path):
        """Combined classified mesh should have all solder triangles."""
        step_file = generate_cylinder_assembly_step(
            BOTTOM_CENTER, TOP_CENTER, RADIUS, PAD_RADIUS,
            pad_thickness=PAD_THICK, output_path=tmp_path / "cyl.step",
        )
        reader = STEPReader()
        assembly = reader.load_assembly(step_file)
        assembly = reader.identify_parts(assembly)
        classified = reader.classify_faces(assembly)

        assert len(classified.face_roles) == len(classified.mesh.faces), (
            f"face_roles len ({len(classified.face_roles)}) != "
            f"mesh faces ({len(classified.mesh.faces)})"
        )
        print(f"Total solder triangles: {len(classified.mesh.faces)}")

    def test_barrel_contact_faces(self, tmp_path):
        """Barrel: contact faces should be at top and bottom."""
        step_file = generate_barrel_assembly_step(
            BOTTOM_CENTER, TOP_CENTER,
            radius_end=RADIUS * 0.8, radius_mid=RADIUS,
            pad_radius=PAD_RADIUS, pad_thickness=PAD_THICK,
            output_path=tmp_path / "barrel.step",
        )
        reader = STEPReader()
        assembly = reader.load_assembly(step_file)
        assembly = reader.identify_parts(assembly)
        classified = reader.classify_faces(assembly)

        assert np.any(classified.contact_bottom_mask)
        assert np.any(classified.contact_top_mask)

        n_bot = int(np.sum(classified.contact_bottom_mask))
        n_top = int(np.sum(classified.contact_top_mask))
        n_lat = int(np.sum(classified.face_roles == 2))
        print(f"Barrel: contact_bot={n_bot}, contact_top={n_top}, lat={n_lat}")

    def test_solder_volume_positive(self, tmp_path):
        """Classified mesh should report positive solder volume."""
        step_file = generate_cylinder_assembly_step(
            BOTTOM_CENTER, TOP_CENTER, RADIUS, PAD_RADIUS,
            pad_thickness=PAD_THICK, output_path=tmp_path / "cyl.step",
        )
        reader = STEPReader()
        assembly = reader.load_assembly(step_file)
        assembly = reader.identify_parts(assembly)
        classified = reader.classify_faces(assembly)

        assert classified.solder_volume > 0
        expected = np.pi * RADIUS**2 * HEIGHT
        ratio = classified.solder_volume / expected
        assert 0.8 < ratio < 1.2, (
            f"Volume ratio {ratio:.3f} out of expected range (B-rep vs analytic)"
        )
        print(f"Solder volume: {classified.solder_volume:.6e} "
              f"(expected ~{expected:.6e}, ratio={ratio:.3f})")

    def test_pad_meshes_present(self, tmp_path):
        """Classified result should include pad meshes."""
        step_file = generate_cylinder_assembly_step(
            BOTTOM_CENTER, TOP_CENTER, RADIUS, PAD_RADIUS,
            pad_thickness=PAD_THICK, output_path=tmp_path / "cyl.step",
        )
        reader = STEPReader()
        assembly = reader.load_assembly(step_file)
        assembly = reader.identify_parts(assembly)
        classified = reader.classify_faces(assembly)

        assert classified.pad_bottom_mesh is not None
        assert classified.pad_top_mesh is not None
        assert len(classified.pad_bottom_mesh.vertices) > 0
        assert len(classified.pad_top_mesh.vertices) > 0
        print("Pad meshes present in classified result")


# ===========================================================================
# TestSTEPPipelineLevel1
# ===========================================================================
class TestSTEPPipelineLevel1:
    """Level 1: STEP -> trimesh -> existing ComplexSTLPipeline."""

    def test_cylinder_level1_generates_fe(self, tmp_path):
        """Cylinder STEP -> Level 1 pipeline -> valid .fe file."""
        from kse.core.step_pipeline import STEPPipeline, STEPPipelineConfig

        step_file = generate_cylinder_assembly_step(
            BOTTOM_CENTER, TOP_CENTER, RADIUS, PAD_RADIUS,
            pad_thickness=PAD_THICK, output_path=tmp_path / "cyl.step",
        )

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            joint_name="step_cylinder_l1",
            integration_level=1,
        )
        pipeline = STEPPipeline(config)
        fe_path = tmp_path / "output" / "cyl_l1.fe"
        result = pipeline.run_assembly(step_file, fe_path)

        assert result.exists()
        text = result.read_text()
        assert "constraint 1" in text
        assert "constraint 2" in text
        assert "vertices" in text
        assert "edges" in text
        assert "faces" in text
        assert "bodies" in text
        print(f"Level 1 .fe: {len(text)} chars")

    def test_box_level1_generates_fe(self, tmp_path):
        """Box STEP -> Level 1 pipeline -> valid .fe file."""
        from kse.core.step_pipeline import STEPPipeline, STEPPipelineConfig

        step_file = generate_box_assembly_step(
            BOTTOM_CENTER, TOP_CENTER,
            solder_side=RADIUS * 1.5, pad_side=PAD_RADIUS * 2,
            pad_thickness=PAD_THICK, output_path=tmp_path / "box.step",
        )

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            joint_name="step_box_l1",
            integration_level=1,
        )
        pipeline = STEPPipeline(config)
        fe_path = tmp_path / "output" / "box_l1.fe"
        result = pipeline.run_assembly(step_file, fe_path)

        assert result.exists()
        text = result.read_text()
        assert "constraint" in text
        print(f"Box Level 1 .fe: {len(text)} chars")


# ===========================================================================
# TestSTEPPipelineLevel2
# ===========================================================================
class TestSTEPPipelineLevel2:
    """Level 2: B-rep face classification -> direct SE conversion."""

    def test_cylinder_level2_generates_fe(self, tmp_path):
        """Cylinder STEP -> Level 2 pipeline -> valid .fe file."""
        from kse.core.step_pipeline import STEPPipeline, STEPPipelineConfig

        step_file = generate_cylinder_assembly_step(
            BOTTOM_CENTER, TOP_CENTER, RADIUS, PAD_RADIUS,
            pad_thickness=PAD_THICK, output_path=tmp_path / "cyl.step",
        )

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            joint_name="step_cylinder_l2",
            integration_level=2,
        )
        pipeline = STEPPipeline(config)
        fe_path = tmp_path / "output" / "cyl_l2.fe"
        result = pipeline.run_assembly(step_file, fe_path)

        assert result.exists()
        text = result.read_text()
        assert "constraint 1" in text
        assert "constraint 2" in text
        assert "vertices" in text
        assert "bodies" in text
        print(f"Level 2 .fe: {len(text)} chars")

    def test_barrel_level2_generates_fe(self, tmp_path):
        """Barrel STEP -> Level 2 -> .fe file."""
        from kse.core.step_pipeline import STEPPipeline, STEPPipelineConfig

        step_file = generate_barrel_assembly_step(
            BOTTOM_CENTER, TOP_CENTER,
            radius_end=RADIUS * 0.8, radius_mid=RADIUS,
            pad_radius=PAD_RADIUS, pad_thickness=PAD_THICK,
            output_path=tmp_path / "barrel.step",
        )

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            joint_name="step_barrel_l2",
            integration_level=2,
        )
        pipeline = STEPPipeline(config)
        fe_path = tmp_path / "output" / "barrel_l2.fe"
        result = pipeline.run_assembly(step_file, fe_path)

        assert result.exists()
        print(f"Barrel Level 2 .fe generated")

    def test_box_level2_generates_fe(self, tmp_path):
        """Box STEP -> Level 2 -> .fe file."""
        from kse.core.step_pipeline import STEPPipeline, STEPPipelineConfig

        step_file = generate_box_assembly_step(
            BOTTOM_CENTER, TOP_CENTER,
            solder_side=RADIUS * 1.5, pad_side=PAD_RADIUS * 2,
            pad_thickness=PAD_THICK, output_path=tmp_path / "box.step",
        )

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            joint_name="step_box_l2",
            integration_level=2,
        )
        pipeline = STEPPipeline(config)
        fe_path = tmp_path / "output" / "box_l2.fe"
        result = pipeline.run_assembly(step_file, fe_path)

        assert result.exists()
        print("Box Level 2 .fe generated")


# ===========================================================================
# TestSTEPPipelineSE
# ===========================================================================
class TestSTEPPipelineSE:
    """Verify SE convergence for STEP-derived .fe files."""

    @pytest.mark.parametrize(
        "shape,gen_func,gen_kwargs",
        [
            ("cylinder", generate_cylinder_assembly_step, dict(
                solder_radius=RADIUS, pad_radius=PAD_RADIUS,
                pad_thickness=PAD_THICK,
            )),
            ("box", generate_box_assembly_step, dict(
                solder_side=RADIUS * 1.5, pad_side=PAD_RADIUS * 2,
                pad_thickness=PAD_THICK,
            )),
        ],
        ids=["cylinder", "box"],
    )
    def test_se_converges(self, shape, gen_func, gen_kwargs, evolver_path, tmp_path):
        """SE evolves the STEP-derived .fe to convergence."""
        from kse.core.step_pipeline import STEPPipeline, STEPPipelineConfig
        from tests.validation.helpers.se_runner import run_kse_fe

        step_file = gen_func(
            BOTTOM_CENTER, TOP_CENTER,
            output_path=tmp_path / f"{shape}.step",
            **gen_kwargs,
        )

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            contact_angle_bottom=30.0, contact_angle_top=30.0,
            joint_name=f"step_{shape}_se",
            integration_level=2,
        )
        pipeline = STEPPipeline(config)
        fe_path = tmp_path / "build" / f"{shape}.fe"
        pipeline.run_assembly(step_file, fe_path)

        work_dir = tmp_path / "run"
        work_dir.mkdir(exist_ok=True)
        result = run_kse_fe(fe_path, evolver_path, work_dir, timeout=120)

        assert result.success, f"SE failed for {shape}: {result.stderr[:500]}"
        assert result.energy is not None and result.energy > 0
        print(f"STEP {shape}: energy={result.energy:.6e}, volume={result.volume}")


# ===========================================================================
# TestSeparateFiles
# ===========================================================================
class TestSeparateFiles:
    """Test loading 3 separate STEP files with explicit roles."""

    def test_separate_files_load(self, tmp_path):
        """3 separate STEP files load with correct roles."""
        solder_stp, bot_stp, top_stp = generate_separate_step_files(
            BOTTOM_CENTER, TOP_CENTER, RADIUS, PAD_RADIUS,
            pad_thickness=PAD_THICK, output_dir=tmp_path / "separate",
        )

        reader = STEPReader()
        assembly = reader.load_separate(solder_stp, bot_stp, top_stp)

        assert assembly.solder is not None
        assert assembly.solder.role == PartRole.SOLDER
        assert assembly.bottom_pad is not None
        assert assembly.bottom_pad.role == PartRole.BOTTOM_PAD
        assert assembly.top_pad is not None
        assert assembly.top_pad.role == PartRole.TOP_PAD
        print("Separate STEP files loaded with correct roles")

    def test_separate_files_classify(self, tmp_path):
        """3 separate STEP files: face classification works."""
        solder_stp, bot_stp, top_stp = generate_separate_step_files(
            BOTTOM_CENTER, TOP_CENTER, RADIUS, PAD_RADIUS,
            pad_thickness=PAD_THICK, output_dir=tmp_path / "separate",
        )

        reader = STEPReader()
        assembly = reader.load_separate(solder_stp, bot_stp, top_stp)
        classified = reader.classify_faces(assembly)

        assert np.any(classified.contact_bottom_mask)
        assert np.any(classified.contact_top_mask)
        n_lat = int(np.sum(classified.face_roles == 2))
        assert n_lat > 0
        print(f"Separate files classified: lateral={n_lat} triangles")

    def test_separate_files_pipeline(self, tmp_path):
        """3 separate STEP files -> pipeline -> .fe file."""
        from kse.core.step_pipeline import STEPPipeline, STEPPipelineConfig

        solder_stp, bot_stp, top_stp = generate_separate_step_files(
            BOTTOM_CENTER, TOP_CENTER, RADIUS, PAD_RADIUS,
            pad_thickness=PAD_THICK, output_dir=tmp_path / "separate",
        )

        config = STEPPipelineConfig(
            tension=TENSION, density=DENSITY, gravity=GRAVITY,
            joint_name="separate_files",
            integration_level=2,
        )
        pipeline = STEPPipeline(config)
        fe_path = tmp_path / "output" / "separate.fe"
        result = pipeline.run_separate(solder_stp, bot_stp, top_stp, fe_path)

        assert result.exists()
        text = result.read_text()
        assert "constraint" in text
        assert "vertices" in text
        print(f"Separate files pipeline: {len(text)} chars")
