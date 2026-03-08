"""Unit tests for evolution_scripts module."""

import pytest
from kse.solver.evolution_scripts import (
    EvolutionStrategy,
    generate_evolution_script,
    generate_runtime_commands,
    generate_dump_commands,
    generate_fine_dump_commands,
    _apply_preset,
)


class TestEvolutionStrategy:
    """Test EvolutionStrategy dataclass defaults."""

    def test_default_preset(self):
        s = EvolutionStrategy()
        assert s.preset == "standard"
        assert s.n_refine == 3
        assert s.n_gradient == 10
        assert s.use_hessian is True
        assert s.use_volume_correction is True
        assert s.use_equiangulate is True

    def test_basic_preset_unchanged(self):
        s = EvolutionStrategy(preset="basic")
        s = _apply_preset(s)
        # basic doesn't override anything
        assert s.use_gofine is False

    def test_standard_preset(self):
        s = EvolutionStrategy(preset="standard")
        s = _apply_preset(s)
        assert s.use_volume_correction is True
        assert s.use_equiangulate is True
        assert s.use_gofine is True

    def test_advanced_preset(self):
        s = EvolutionStrategy(preset="advanced")
        s = _apply_preset(s)
        assert s.autopop is True
        assert s.use_pop is True
        assert s.use_skinny_refine is True
        assert s.eigenprobe is True
        assert s.report_pressure is True
        assert s.report_volumes is True
        assert s.use_gofine is True

    def test_custom_preset(self):
        s = EvolutionStrategy(preset="custom", custom_commands="my_cmd := { g 5; }")
        script = generate_evolution_script(s)
        assert script == "my_cmd := { g 5; }"


class TestGenerateEvolutionScript:
    """Test SE macro generation for .fe files."""

    def test_basic_has_gogo_gomore(self):
        s = EvolutionStrategy(preset="basic")
        script = generate_evolution_script(s)
        assert "gogo := {" in script
        assert "gomore := {" in script
        assert "gofine := {" not in script

    def test_standard_has_gofine(self):
        s = EvolutionStrategy(preset="standard")
        s = _apply_preset(s)
        script = generate_evolution_script(s)
        assert "gogo := {" in script
        assert "gomore := {" in script
        assert "gofine := {" in script

    def test_gogo_contains_refine(self):
        s = EvolutionStrategy(preset="basic", n_refine=2, n_gradient=5)
        script = generate_evolution_script(s)
        assert "r;" in script
        assert "g 5;" in script

    def test_hessian_in_gogo(self):
        s = EvolutionStrategy(preset="basic", use_hessian=True, n_hessian=3)
        script = generate_evolution_script(s)
        assert "hessian;" in script

    def test_no_hessian_when_disabled(self):
        s = EvolutionStrategy(preset="basic", use_hessian=False)
        script = generate_evolution_script(s)
        assert "hessian;" not in script
        assert "hessian_seek;" not in script

    def test_hessian_seek(self):
        s = EvolutionStrategy(
            preset="basic",
            use_hessian_seek=True,
            use_hessian=False,
            n_hessian=2,
        )
        script = generate_evolution_script(s)
        assert "hessian_seek;" in script
        # Should have 2 hessian_seek lines in gogo
        gogo_section = script.split("gomore")[0]
        assert gogo_section.count("hessian_seek;") == 2

    def test_volume_correction(self):
        s = EvolutionStrategy(preset="basic", use_volume_correction=True)
        script = generate_evolution_script(s)
        assert "V;" in script

    def test_no_volume_correction(self):
        s = EvolutionStrategy(
            preset="basic",
            use_volume_correction=False,
            use_equiangulate=False,
        )
        script = generate_evolution_script(s)
        # V should not appear (only in gogo/gomore)
        for line in script.splitlines():
            stripped = line.strip()
            if stripped == "V;":
                pytest.fail("V; should not be present when volume correction is off")

    def test_equiangulate(self):
        s = EvolutionStrategy(preset="basic", use_equiangulate=True)
        script = generate_evolution_script(s)
        assert "u;" in script

    def test_saddle(self):
        s = EvolutionStrategy(preset="basic", use_saddle=True)
        script = generate_evolution_script(s)
        assert "saddle;" in script


class TestSetupToggles:
    """Test Phase 1 setup toggle generation."""

    def test_hessian_normal(self):
        s = EvolutionStrategy(preset="basic", hessian_normal=True)
        script = generate_evolution_script(s)
        assert "hessian_normal" in script

    def test_conj_grad(self):
        s = EvolutionStrategy(preset="basic", conj_grad=True)
        script = generate_evolution_script(s)
        assert "U" in script  # SE toggle for conj_grad

    def test_check_increase(self):
        s = EvolutionStrategy(preset="basic", check_increase=True)
        script = generate_evolution_script(s)
        assert "check_increase ON" in script

    def test_autopop(self):
        s = EvolutionStrategy(preset="basic", autopop=True)
        script = generate_evolution_script(s)
        assert "autopop ON" in script

    def test_autochop(self):
        s = EvolutionStrategy(preset="basic", autochop=True)
        script = generate_evolution_script(s)
        assert "autochop ON" in script

    def test_normal_motion(self):
        s = EvolutionStrategy(preset="basic", normal_motion=True)
        script = generate_evolution_script(s)
        assert "normal_motion ON" in script

    def test_area_normalization(self):
        s = EvolutionStrategy(preset="basic", area_normalization=True)
        script = generate_evolution_script(s)
        # 'a' toggle
        assert "\na\n" in script or script.startswith("a\n") or "\na" in script

    def test_runge_kutta(self):
        s = EvolutionStrategy(preset="basic", runge_kutta=True)
        script = generate_evolution_script(s)
        assert "runge_kutta ON" in script

    def test_gravity_on(self):
        s = EvolutionStrategy(preset="basic", gravity_on=True)
        script = generate_evolution_script(s)
        assert "G ON" in script

    def test_gravity_off(self):
        s = EvolutionStrategy(preset="basic", gravity_on=False)
        script = generate_evolution_script(s)
        assert "G OFF" in script

    def test_gravity_default(self):
        s = EvolutionStrategy(preset="basic", gravity_on=None)
        script = generate_evolution_script(s)
        assert "G ON" not in script
        assert "G OFF" not in script

    def test_scale_factor(self):
        s = EvolutionStrategy(preset="basic", scale_factor=0.5)
        script = generate_evolution_script(s)
        assert "m 0.5" in script

    def test_diffusion(self):
        s = EvolutionStrategy(preset="basic", diffusion=True)
        script = generate_evolution_script(s)
        assert "diffusion ON" in script

    def test_approximate_curvature(self):
        s = EvolutionStrategy(preset="basic", approximate_curvature=True)
        script = generate_evolution_script(s)
        assert "approximate_curvature ON" in script


class TestMeshQuality:
    """Test mesh quality command generation."""

    def test_tiny_edge(self):
        s = EvolutionStrategy(preset="basic", tiny_edge_threshold=0.001)
        script = generate_evolution_script(s)
        assert "t 0.001;" in script

    def test_long_edge(self):
        s = EvolutionStrategy(preset="basic", long_edge_threshold=0.05)
        script = generate_evolution_script(s)
        assert "l 0.05;" in script

    def test_weed(self):
        s = EvolutionStrategy(preset="basic", weed_threshold=1e-5)
        script = generate_evolution_script(s)
        assert "w 1e-05;" in script

    def test_skinny_refine(self):
        s = EvolutionStrategy(preset="basic", use_skinny_refine=True, skinny_angle=20.0)
        script = generate_evolution_script(s)
        assert "K 20;" in script

    def test_pop(self):
        s = EvolutionStrategy(preset="basic", use_pop=True)
        script = generate_evolution_script(s)
        assert "o;" in script

    def test_pop_edge(self):
        s = EvolutionStrategy(preset="basic", use_pop_edge=True)
        script = generate_evolution_script(s)
        assert "O;" in script

    def test_notch(self):
        s = EvolutionStrategy(preset="basic", use_notch=True, notch_angle=1.0)
        script = generate_evolution_script(s)
        assert "n 1;" in script

    def test_jiggle(self):
        s = EvolutionStrategy(preset="basic", use_jiggle=True, jiggle_temperature=0.001)
        script = generate_evolution_script(s)
        assert "j 0.001;" in script

    def test_edgeswap(self):
        s = EvolutionStrategy(preset="basic", use_edgeswap=True)
        script = generate_evolution_script(s)
        assert "edgeswap edge where 1;" in script

    def test_target_edge_length(self):
        s = EvolutionStrategy(
            preset="basic",
            target_edge_length=0.01,
            n_refine=2,
        )
        script = generate_evolution_script(s)
        assert "refine edge where length > 0.01" in script

    def test_no_mesh_cleanup_by_default(self):
        s = EvolutionStrategy(preset="basic")
        script = generate_evolution_script(s)
        assert "  K " not in script
        assert "  o;" not in script
        assert "  O;" not in script
        assert "  n " not in script
        assert "  j " not in script


class TestGofine:
    """Test gofine macro generation."""

    def test_gofine_generated(self):
        s = EvolutionStrategy(preset="basic", use_gofine=True)
        script = generate_evolution_script(s)
        assert "gofine := {" in script

    def test_gofine_extra_refine(self):
        s = EvolutionStrategy(
            preset="basic",
            use_gofine=True,
            gofine_extra_refine=3,
        )
        script = generate_evolution_script(s)
        gofine_section = script.split("gofine := {")[1].split("}")[0]
        assert gofine_section.count("r;") == 3

    def test_gofine_gradient_mult(self):
        s = EvolutionStrategy(
            preset="basic",
            use_gofine=True,
            n_gradient=10,
            gofine_gradient_mult=3,
        )
        script = generate_evolution_script(s)
        assert "g 30;" in script  # 10 * 3 = 30

    def test_no_gofine_by_default_basic(self):
        s = EvolutionStrategy(preset="basic")
        script = generate_evolution_script(s)
        assert "gofine" not in script


class TestAnalysis:
    """Test analysis procedure generation."""

    def test_eigenprobe(self):
        s = EvolutionStrategy(preset="basic", eigenprobe=True, eigenprobe_value=0.5)
        script = generate_evolution_script(s)
        assert "analyze := {" in script
        assert "eigenprobe 0.5;" in script

    def test_ritz(self):
        s = EvolutionStrategy(
            preset="basic",
            ritz_count=5,
            ritz_value=0.1,
        )
        script = generate_evolution_script(s)
        assert "ritz(0.1, 5);" in script

    def test_report_volumes(self):
        s = EvolutionStrategy(preset="basic", report_volumes=True)
        script = generate_evolution_script(s)
        assert "analyze := {" in script

    def test_report_pressure(self):
        s = EvolutionStrategy(preset="basic", report_pressure=True)
        script = generate_evolution_script(s)
        assert "BODY_" in script or "pressure" in script

    def test_report_energy(self):
        s = EvolutionStrategy(preset="basic", report_energy=True)
        script = generate_evolution_script(s)
        assert "TOTAL_ENERGY" in script

    def test_no_analysis_by_default(self):
        s = EvolutionStrategy(preset="basic")
        script = generate_evolution_script(s)
        assert "analyze := {" not in script


class TestRuntimeCommands:
    """Test runtime command generation (piped to SE stdin)."""

    def test_basic_runtime(self):
        s = EvolutionStrategy(preset="basic")
        cmds = generate_runtime_commands(s, "out.dmp")
        assert "gogo;" in cmds
        assert "gomore;" in cmds
        assert 'dump "out.dmp";' in cmds
        assert cmds.strip().endswith("q")

    def test_gofine_in_runtime(self):
        s = EvolutionStrategy(preset="basic", use_gofine=True)
        cmds = generate_runtime_commands(s, "out.dmp")
        assert "gofine;" in cmds

    def test_no_gofine_in_runtime(self):
        s = EvolutionStrategy(preset="basic", use_gofine=False)
        cmds = generate_runtime_commands(s, "out.dmp")
        assert "gofine;" not in cmds

    def test_eigenprobe_in_runtime(self):
        s = EvolutionStrategy(preset="basic", eigenprobe=True, eigenprobe_value=0.0)
        cmds = generate_runtime_commands(s, "out.dmp")
        assert "eigenprobe 0.0;" in cmds

    def test_ritz_in_runtime(self):
        s = EvolutionStrategy(preset="basic", ritz_count=5, ritz_value=0.0)
        cmds = generate_runtime_commands(s, "out.dmp")
        assert "ritz(0.0, 5);" in cmds

    def test_report_volumes_in_runtime(self):
        s = EvolutionStrategy(preset="basic", report_volumes=True)
        cmds = generate_runtime_commands(s, "out.dmp")
        assert "v;" in cmds

    def test_report_quantities_in_runtime(self):
        s = EvolutionStrategy(preset="basic", report_quantities=True)
        cmds = generate_runtime_commands(s, "out.dmp")
        assert "Q;" in cmds

    def test_report_pressure_in_runtime(self):
        s = EvolutionStrategy(preset="basic", report_pressure=True)
        cmds = generate_runtime_commands(s, "out.dmp")
        assert "print body[1].pressure;" in cmds

    def test_report_energy_in_runtime(self):
        s = EvolutionStrategy(preset="basic", report_energy=True)
        cmds = generate_runtime_commands(s, "out.dmp")
        assert "print total_energy;" in cmds


class TestLegacyAPI:
    """Test backward-compatible legacy functions."""

    def test_generate_dump_commands(self):
        cmds = generate_dump_commands("result.dmp")
        assert "gogo;" in cmds
        assert "gomore;" in cmds
        assert 'dump "result.dmp";' in cmds
        assert "q" in cmds

    def test_generate_fine_dump_commands(self):
        cmds = generate_fine_dump_commands("result.dmp")
        assert "gogo;" in cmds
        assert "gomore;" in cmds
        assert "gofine;" in cmds
        assert 'dump "result.dmp";' in cmds
        assert "q" in cmds


class TestScriptStructure:
    """Test overall script structure and formatting."""

    def test_no_empty_macros(self):
        """Macros should always have content between braces."""
        s = EvolutionStrategy(preset="basic")
        script = generate_evolution_script(s)
        # Should not have empty braces
        assert "{ }" not in script.replace("\n", " ")

    def test_all_macros_closed(self):
        """Every { should have a matching }."""
        s = EvolutionStrategy(preset="advanced")
        s = _apply_preset(s)
        script = generate_evolution_script(s)
        assert script.count("{") == script.count("}")

    def test_advanced_full_script(self):
        """Advanced preset should produce a substantial script."""
        s = EvolutionStrategy(preset="advanced")
        s = _apply_preset(s)
        script = generate_evolution_script(s)
        # Should have gogo, gomore, gofine, analyze
        assert "gogo := {" in script
        assert "gomore := {" in script
        assert "gofine := {" in script
        assert "analyze := {" in script

    def test_custom_ignores_all_options(self):
        """Custom preset should only use custom_commands."""
        s = EvolutionStrategy(
            preset="custom",
            custom_commands="my_gogo := { g 5; r; g 5; }",
            use_hessian=True,
            eigenprobe=True,
            use_gofine=True,
        )
        script = generate_evolution_script(s)
        assert script == "my_gogo := { g 5; r; g 5; }"
        assert "hessian" not in script
        assert "eigenprobe" not in script
