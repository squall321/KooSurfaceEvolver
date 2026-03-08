"""Generate LS-DYNA .k files for all representative solder joint examples.

Usage:
    python examples/gen_lsdyna_k.py

Output:
    examples/lsdyna_k/
        ── 원형 패드 (BGA / WLCSP) ──
        bga_standard/        - BGA 표준 (r=1.0mm, h=1.2mm)
        bga_barrel/          - 바렐 형상 (과잉 솔더)
        bga_hourglass/       - 모래시계 형상 (부족 솔더)
        bga_low_standoff/    - 낮은 스탠드오프
        bga_high_standoff/   - 높은 스탠드오프
        wlcsp_small/         - WLCSP 소형 (r=0.4mm)
        bga_tilted/          - 패드 오프셋 (X 방향 시프트)
        bga_high_angle/      - 고접촉각 60°
        bga_low_angle/       - 저접촉각 10°
        ── 사각형 패드 (LGA / QFN) ──
        lga_rect/            - LGA 직사각형 (2.0mm × 1.5mm)
        square_bga/          - 정사각 BGA (1.0mm × 1.0mm)
        qfn_rect/            - QFN 직사각형 패드 (0.5mm × 0.3mm)
        lga_high_angle/      - LGA 고접촉각 (θ=50°)

Surface mesh fineness:
    REFINE_STEPS (default 3) → ~8 k surface triangles → ~27 k TET4 요소
    REFINE_STEPS = 2         → ~2 k surface triangles → ~7 k TET4 요소 (품질 ↑)
    YAML 모드: solver.refine_steps 파라미터로 동일 제어 가능
    CLI 모드:  kse run --refine-steps N
"""

import sys
import subprocess
import tempfile
import numpy as np
from pathlib import Path

# KSE 루트를 sys.path에 추가
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from tests.validation.helpers.stl_from_constraints import generate_flat_pad_stl

OUT_DIR = ROOT / "examples" / "lsdyna_k"
EVOLVER = ROOT / "src" / "evolver"
PI = np.pi

# ────────────────────────────────────────────────────────────────
# 표면 밀도 제어
# ────────────────────────────────────────────────────────────────
# SE 세분화 단계: 3 → ~8192 삼각형, 2 → ~2048 삼각형
# 줄이면 TetGen 품질 개선 (슬리버 감소), SE 정밀도는 소폭 저하
REFINE_STEPS = 3

# ────────────────────────────────────────────────────────────────
# 공통 물성 (CGS)
# ────────────────────────────────────────────────────────────────
PHYSICS = {
    "tension": 480.0,    # erg/cm²  SAC305 @ 250°C
    "density": 8.5,      # g/cm³
    "gravity": 980.0,    # cm/s²
}

# ────────────────────────────────────────────────────────────────
# 원형 패드 케이스
# ────────────────────────────────────────────────────────────────
_r = 0.10   # 기준 반경 [cm]  = 1.0 mm
_h = 0.12   # 기준 높이 [cm]  = 1.2 mm
_V0 = 1.3 * PI * _r**2 * _h   # 기준 체적 ≈ 4.9e-3 cm³

CASES_CIRC = [
    {
        "name": "bga_standard",
        "desc": "BGA 표준 (r=1.0mm, h=1.2mm, V=V0, θ=30°)",
        "radius": _r, "height": _h, "volume": _V0,
        "x_offset": 0.0, "contact_angle": 30.0,
    },
    {
        "name": "bga_barrel",
        "desc": "바렐형 — 과잉 솔더 (V=1.6×V0)",
        "radius": _r, "height": _h, "volume": 1.6 * _V0,
        "x_offset": 0.0, "contact_angle": 30.0,
    },
    {
        "name": "bga_hourglass",
        "desc": "모래시계형 — 부족 솔더 (V=0.6×V0)",
        "radius": _r, "height": _h, "volume": 0.6 * _V0,
        "x_offset": 0.0, "contact_angle": 30.0,
    },
    {
        "name": "bga_low_standoff",
        "desc": "낮은 스탠드오프 (h=0.06 cm, V=1.3×π×r²×h)",
        "radius": _r, "height": 0.06,
        "volume": 1.3 * PI * _r**2 * 0.06,
        "x_offset": 0.0, "contact_angle": 30.0,
    },
    {
        "name": "bga_high_standoff",
        "desc": "높은 스탠드오프 (h=0.20 cm)",
        "radius": _r, "height": 0.20, "volume": _V0,
        "x_offset": 0.0, "contact_angle": 30.0,
    },
    {
        "name": "wlcsp_small",
        "desc": "WLCSP 소형 — r=0.4mm, h=0.2mm",
        "radius": 0.04, "height": 0.02, "volume": 1e-4,
        "x_offset": 0.0, "contact_angle": 25.0,
    },
    {
        "name": "bga_tilted",
        "desc": "패드 오프셋 — X 방향 0.05 cm 시프트",
        "radius": _r, "height": _h, "volume": _V0,
        "x_offset": 0.05, "contact_angle": 30.0,
    },
    {
        "name": "bga_high_angle",
        "desc": "고접촉각 θ=60° (강한 젖음)",
        "radius": _r, "height": _h, "volume": _V0,
        "x_offset": 0.0, "contact_angle": 60.0,
    },
    {
        "name": "bga_low_angle",
        "desc": "저접촉각 θ=10° (약한 젖음)",
        "radius": _r, "height": _h, "volume": _V0,
        "x_offset": 0.0, "contact_angle": 10.0,
    },
]

# ────────────────────────────────────────────────────────────────
# 사각형 패드 케이스  (LGA / QFN)
# ────────────────────────────────────────────────────────────────
CASES_RECT = [
    {
        "name": "lga_rect",
        "desc": "LGA 직사각형 (2.0mm × 1.5mm, h=0.8mm, θ=30°)",
        "side_x": 0.20, "side_y": 0.15, "height": 0.08,
        "volume": 1.3 * 0.20 * 0.15 * 0.08,   # 3.12e-3 cm³
        "contact_angle": 30.0,
    },
    {
        "name": "square_bga",
        "desc": "정사각 BGA (1.0mm × 1.0mm, h=1.2mm, θ=30°)",
        "side_x": 0.10, "side_y": 0.10, "height": 0.12,
        "volume": 1.3 * 0.10 * 0.10 * 0.12,   # 1.56e-3 cm³
        "contact_angle": 30.0,
    },
    {
        "name": "qfn_rect",
        "desc": "QFN 직사각형 패드 (0.5mm × 0.3mm, h=0.6mm, θ=30°)",
        "side_x": 0.05, "side_y": 0.03, "height": 0.06,
        "volume": 1.3 * 0.05 * 0.03 * 0.06,   # 1.17e-4 cm³
        "contact_angle": 30.0,
    },
    {
        "name": "lga_high_angle",
        "desc": "LGA 고접촉각 (2.0mm × 1.5mm, θ=50°, 강한 젖음)",
        "side_x": 0.20, "side_y": 0.15, "height": 0.08,
        "volume": 1.3 * 0.20 * 0.15 * 0.08,   # 3.12e-3 cm³
        "contact_angle": 50.0,
    },
]


# ────────────────────────────────────────────────────────────────
# 원형 패드: CLI subprocess 방식
# ────────────────────────────────────────────────────────────────

def run_case_circ(case: dict, tmp_root: Path) -> bool:
    name = case["name"]
    r = case["radius"]
    h = case["height"]
    V = case["volume"]
    x_off = case["x_offset"]
    angle = case["contact_angle"]

    print(f"\n{'='*60}")
    print(f"  {name}  [원형]")
    print(f"  {case['desc']}")
    print(f"  r={r:.4f} cm  h={h:.4f} cm  V={V:.4e} cm³  θ={angle}°")
    print(f"{'='*60}")

    work = tmp_root / name
    work.mkdir(parents=True, exist_ok=True)

    center_a = np.array([0.0, 0.0, 0.0])
    center_b = np.array([x_off, 0.0, h])
    pad_a = work / "pad_bottom.stl"
    pad_b = work / "pad_top.stl"
    generate_flat_pad_stl(center_a, r, output_path=pad_a)
    generate_flat_pad_stl(center_b, r, output_path=pad_b)

    out = OUT_DIR / name
    out.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, str(ROOT / "cli.py"), "run",
        "--stl-a", str(pad_a),
        "--stl-b", str(pad_b),
        "--center-a", "0.0,0.0,0.0",
        "--center-b", f"{x_off},0.0,{h}",
        "--radius", str(r),
        "--volume", str(V),
        "--output", str(out),
        "--format", "lsdyna",
        "--tension", str(PHYSICS["tension"]),
        "--density", str(PHYSICS["density"]),
        "--gravity", str(PHYSICS["gravity"]),
        "--contact-angle", str(angle),
        "--refine-steps", str(REFINE_STEPS),
        "--timeout", "300",
    ]
    if EVOLVER.exists():
        cmd += ["--evolver-path", str(EVOLVER)]

    result = subprocess.run(cmd, capture_output=False, text=True)
    if result.returncode != 0:
        print(f"  [FAIL] returncode={result.returncode}")
        return False

    k_files = list(out.glob("*.k"))
    if k_files:
        size_kb = k_files[0].stat().st_size / 1024
        print(f"  [OK]  {k_files[0].name}  ({size_kb:.1f} KB)")
    else:
        print(f"  [WARN] .k 파일 없음 — 출력 목록: {list(out.iterdir())}")

    return True


# ────────────────────────────────────────────────────────────────
# 사각형 패드: Python API 직접 호출
# ────────────────────────────────────────────────────────────────

def run_case_rect(case: dict, tmp_root: Path) -> bool:
    from kse.core.stl_reader import STLReader
    from kse.core.surface_fitter import SurfaceFitter
    from kse.core.constraint_gen import ConstraintGenerator
    from kse.core.geometry_builder import GeometryBuilder
    from kse.core.fe_writer import FEWriter, SolderJointConfig
    from kse.solver.evolver_runner import EvolverRunner
    from kse.solver.dump_parser import DumpParser
    from kse.solver.evolution_scripts import EvolutionStrategy, generate_runtime_commands
    from kse.mesh.quality import assess_tet_quality
    from kse.batch.job_manager import SOLID_EXPORT_FUNCS
    from kse.mesh.volume_mesher import generate_volume_mesh

    name = case["name"]
    sx = case["side_x"]
    sy = case["side_y"]
    h = case["height"]
    V = case["volume"]
    angle = case["contact_angle"]

    # 사각형 반대각선 반경 (패드 코너를 포함하는 최소 원)
    half_diag = np.sqrt((sx / 2) ** 2 + (sy / 2) ** 2) * 1.1

    print(f"\n{'='*60}")
    print(f"  {name}  [사각형]")
    print(f"  {case['desc']}")
    print(f"  {sx*10:.1f}mm × {sy*10:.1f}mm  h={h*10:.2f}mm  "
          f"V={V:.4e} cm³  θ={angle}°")
    print(f"{'='*60}")

    work = tmp_root / name
    work.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / name
    out.mkdir(parents=True, exist_ok=True)

    # 평면 STL 생성 (사각형 코너를 덮는 원형 그리드)
    center_a = np.array([0.0, 0.0, 0.0])
    center_b = np.array([0.0, 0.0, h])
    pad_a = work / "pad_bottom.stl"
    pad_b = work / "pad_top.stl"
    generate_flat_pad_stl(center_a, half_diag, output_path=pad_a)
    generate_flat_pad_stl(center_b, half_diag, output_path=pad_b)

    # 패치 추출 → 표면 피팅 (평면 z=const)
    reader_a = STLReader(pad_a)
    reader_b = STLReader(pad_b)
    patch_a = reader_a.extract_patch(center_a, half_diag)
    patch_b = reader_b.extract_patch(center_b, half_diag)

    fitter = SurfaceFitter()
    fit_a = fitter.fit(patch_a)
    fit_b = fitter.fit(patch_b)

    # 구속 조건 생성 (사각형: 두 면 모두 boundary integral 방식)
    cgen = ConstraintGenerator()
    c_a = cgen.generate_surface_constraint(
        fit_a, 1, angle, PHYSICS["tension"],
        solder_density=PHYSICS["density"],
        gravity=PHYSICS["gravity"],
        use_boundary_integrals=True,
    )
    c_b = cgen.generate_surface_constraint(
        fit_b, 2, angle, PHYSICS["tension"],
        solder_density=PHYSICS["density"],
        gravity=PHYSICS["gravity"],
        use_boundary_integrals=True,
    )

    # 직사각형 초기 형상 생성
    builder = GeometryBuilder(n_segments=8)
    geom = builder.build_rectangular(fit_a, fit_b, sx, sy, V)

    # .fe 파일 작성
    fe_config = SolderJointConfig(
        joint_name=name,
        tension=PHYSICS["tension"],
        density=PHYSICS["density"],
        gravity=PHYSICS["gravity"],
        radius=half_diag,
        volume=V,
        contact_angle_A=angle,
        contact_angle_B=angle,
    )
    fe_path = out / f"{name}.fe"
    writer = FEWriter()
    writer.write_single(fe_path, geom, [c_a, c_b], [], fe_config)
    print(f"  Generated .fe: {fe_path.name}")

    # Surface Evolver 실행
    evolver_path = str(EVOLVER) if EVOLVER.exists() else None
    runner = EvolverRunner(evolver_path)
    dump_path = fe_path.with_suffix(".dmp")
    strategy = EvolutionStrategy(preset="basic", n_refine=REFINE_STEPS)
    commands = generate_runtime_commands(strategy, dump_path.name)
    se_result = runner.run(fe_path, commands, dump_path, timeout=300)

    if not se_result.success:
        print(f"  [FAIL] SE failed: {se_result.stderr[:200]}")
        return False

    print(f"  SE completed in {se_result.elapsed_seconds:.1f}s")

    # 덤프 파싱 → 체적 메시 → .k 내보내기
    parser = DumpParser()
    mesh = parser.parse(dump_path)
    vertices = mesh.vertex_array
    triangles = mesh.face_triangles

    out_base = out / name
    try:
        vol = generate_volume_mesh(vertices, triangles)
        q = assess_tet_quality(vol.vertices, vol.tetrahedra)
        lines = q.summary().splitlines()
        print(f"  TET4: {len(vol.tetrahedra)} elems  {lines[1].strip() if len(lines) > 1 else ''}")
        k_path = SOLID_EXPORT_FUNCS["lsdyna"](vol.vertices, vol.tetrahedra, out_base)
        size_kb = Path(k_path).stat().st_size / 1024
        print(f"  [OK]  {Path(k_path).name}  ({size_kb:.1f} KB)")
    except ImportError as e:
        print(f"  [SKIP] {e}")
        return False
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"  [FAIL] {e}")
        return False

    return True


# ────────────────────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────────────────────

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []

    with tempfile.TemporaryDirectory(prefix="kse_lsdyna_") as tmp_str:
        tmp_root = Path(tmp_str)

        print(f"\n{'#'*60}")
        print(f"  원형 패드 케이스 ({len(CASES_CIRC)}개)")
        print(f"  REFINE_STEPS = {REFINE_STEPS}")
        print(f"{'#'*60}")
        for case in CASES_CIRC:
            ok = run_case_circ(case, tmp_root)
            results.append((case["name"], "원형", ok))

        print(f"\n{'#'*60}")
        print(f"  사각형 패드 케이스 ({len(CASES_RECT)}개)")
        print(f"  REFINE_STEPS = {REFINE_STEPS}")
        print(f"{'#'*60}")
        for case in CASES_RECT:
            ok = run_case_rect(case, tmp_root)
            results.append((case["name"], "사각형", ok))

    # 결과 요약
    print(f"\n{'='*60}")
    print("  결과 요약")
    print(f"{'='*60}")
    pass_count = 0
    for name, shape, ok in results:
        status = "OK  " if ok else "FAIL"
        print(f"  [{status}]  {name}  ({shape})")
        if ok:
            pass_count += 1
    print(f"\n  {pass_count}/{len(results)} 성공")
    print(f"  출력 위치: {OUT_DIR}")

    # .k 파일 목록
    k_files = sorted(OUT_DIR.rglob("*.k"))
    if k_files:
        print(f"\n  생성된 .k 파일:")
        for k in k_files:
            size_kb = k.stat().st_size / 1024
            rel = k.relative_to(ROOT)
            print(f"    {rel}  ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
