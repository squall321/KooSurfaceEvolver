# KSE (KooSurfaceEvolver)

솔더 조인트 평형 형상 시뮬레이션 및 FEA 메시 자동 생성 도구.

패드 형상(STL/STEP)과 솔더 물성을 입력하면, Surface Evolver 엔진을 사용하여 표면장력·중력·접촉각 조건 하에서 솔더 조인트의 **최소 에너지 평형 형상**을 계산하고, FEA 해석용 체적 메시(TET4)로 자동 변환합니다.

---

## 목차

1. [주요 기능](#1-주요-기능)
2. [설치](#2-설치)
3. [빠른 시작 (Quick Start)](#3-빠른-시작-quick-start)
4. [CLI 명령어 상세](#4-cli-명령어-상세)
5. [YAML 설정 가이드](#5-yaml-설정-가이드)
6. [입력 모드 상세](#6-입력-모드-상세)
7. [출력 형식](#7-출력-형식)
8. [파라미터 스윕](#8-파라미터-스윕)
9. [Evolution Strategy (고급)](#9-evolution-strategy-고급)
10. [솔더 물성 참고표](#10-솔더-물성-참고표)
11. [외부 프로그램 연동 (Integration)](#11-외부-프로그램-연동-integration)
12. [프로젝트 구조](#12-프로젝트-구조)
13. [빌드 (독립 실행파일)](#13-빌드-독립-실행파일)
14. [트러블슈팅](#14-트러블슈팅)

---

## 1. 주요 기능

| 기능 | 설명 |
|------|------|
| **자동 파이프라인** | STL/STEP 패드 → SE .fe 생성 → 시뮬레이션 → 메시 출력 (원클릭) |
| **다양한 패드 형상** | BGA(원형), LGA(직사각형), QFN, WLCSP, MLCC 필렛, 브릿지 |
| **FEA 체적 메시** | TET4 사면체 출력: LS-DYNA(.k), ANSYS(.cdb), Gmsh(.msh), VTK |
| **표면 메시** | STL(ASCII/Binary), VTK |
| **STEP 지원** | 단일 어셈블리, 개별 파일, 브릿지, 배열 자동 인식 |
| **배치/병렬** | 다수 조인트 병렬 시뮬레이션, 커플 조인트 |
| **파라미터 스윕** | 체적·표면장력·접촉각 등 자동 변화 시뮬레이션 |
| **YAML 설정** | 모든 옵션을 YAML 파일로 관리, 재현 가능 |
| **2단위계** | CGS(cm, g, erg) 또는 mm(mm, mg, mJ) |

---

## 2. 설치

### 요구사항

- **Python 3.12+**
- **OS**: Windows 10/11, Linux (Ubuntu 20.04+)

### Windows 자동 설치 (권장)

```cmd
git clone https://github.com/squall321/KooSurfaceEvolver.git
cd KooSurfaceEvolver
install_windows.bat
```

`install_windows.bat`이 자동으로 수행하는 작업:
- `.venv` 가상환경 생성
- 기본 의존성 설치 (numpy, scipy, trimesh, jinja2, sympy, pyyaml 등)
- KSE 패키지 설치 (editable mode)
- FEA 의존성 설치 여부 질문 (tetgen, pymeshfix — 체적 메시 필요 시)
- STEP/CAD 의존성 설치 여부 질문 (cadquery — STEP 파일 사용 시)

### Windows 수동 설치

```cmd
git clone https://github.com/squall321/KooSurfaceEvolver.git
cd KooSurfaceEvolver

python -m venv .venv
.venv\Scripts\activate.bat

pip install -r requirements.txt
pip install -e .

REM (선택) FEA 체적 메시 지원
pip install -r requirements-fea.txt

REM (선택) STEP/CAD 파일 지원
pip install cadquery>=2.3
```

### Linux 설치

```bash
git clone https://github.com/squall321/KooSurfaceEvolver.git
cd KooSurfaceEvolver

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
pip install -e .
```

### 설치 확인

```cmd
.venv\Scripts\activate.bat      (Windows)
source .venv/bin/activate       (Linux)

kse --help
```

---

## 3. 빠른 시작 (Quick Start)

### 3.1 가장 간단한 실행 (CLI)

```cmd
kse run ^
  --stl-a bottom_pad.stl ^
  --stl-b top_pad.stl ^
  --center-a 0,0,0 ^
  --center-b 0,0,0.03 ^
  --radius 0.025 ^
  --volume 3.27e-6 ^
  --format stl,vtk ^
  --output results
```

> Linux에서는 `^` 대신 `\` 사용

### 3.2 YAML 파일로 실행 (권장)

**`my_config.yaml`** 작성:

```yaml
units: cgs

physics:
  tension: 480.0
  density: 8.5
  gravity: 980.0
  contact_angle_bottom: 30.0
  contact_angle_top: 30.0

input:
  mode: parametric
  stl_a: bottom_pad.stl
  stl_b: top_pad.stl
  center_a: [0.0, 0.0, 0.0]
  center_b: [0.0, 0.0, 0.03]

geometry:
  pad_shape: circular
  radius: 0.025
  volume: 3.27e-6

solver:
  timeout: 300
  refine_steps: 3
  use_hessian: true

output:
  directory: output
  formats: [stl, vtk]
  joint_name: solder_joint
```

실행:
```cmd
kse yaml my_config.yaml
```

.fe 파일만 생성 (SE 실행 안함):
```cmd
kse yaml my_config.yaml --dry-run
```

### 3.3 LS-DYNA 체적 메시 출력

`output.formats`에 `lsdyna` 추가:

```yaml
output:
  formats: [stl, vtk, lsdyna]
```

> `requirements-fea.txt` 의존성 설치 필요 (tetgen, pymeshfix)

### 3.4 실행 결과

```
Mode: parametric | Units: cgs
Physics: sigma=480.0, rho=8.5, G=980.0
Generated: output/solder_joint.fe
Running Surface Evolver...
SE completed in 8.3s
[Mesh Quality]
  Vertices: 4098, Faces: 8192
  Area: 0.001234 cm^2
  Aspect ratio (avg): 1.12, (max): 2.34
Standoff height: 0.028500 cm
Max radius: 0.032100 cm
Exported: output/solder_joint.stl
Exported: output/solder_joint.vtk
[Tet Quality]
  Tetrahedra: 27010, Vertices: 5432
  Min dihedral: 2.1°, Max: 174.2°
Exported: output/solder_joint.k
```

생성 파일:
```
output/
├── solder_joint.fe     # Surface Evolver 입력 파일
├── solder_joint.dmp    # SE dump (파싱된 결과)
├── solder_joint.stl    # 표면 삼각형 메시
├── solder_joint.vtk    # VTK 표면 메시
└── solder_joint.k      # LS-DYNA TET4 체적 메시
```

---

## 4. CLI 명령어 상세

```
kse <command> [options]

Commands:
  run        단일 솔더 조인트 시뮬레이션
  yaml       YAML 설정 파일로 실행 (권장)
  batch      병렬 독립 조인트 시뮬레이션
  coupled    상호작용 조인트 시뮬레이션
  validate   기준 예제 대비 검증
```

### 4.1 `kse run` — 단일 조인트

모든 파라미터를 명령줄 인자로 직접 지정합니다.

```cmd
kse run ^
  --stl-a bottom.stl ^
  --stl-b top.stl ^
  --center-a "0,0,0" ^
  --center-b "0,0,0.03" ^
  --radius 0.025 ^
  --volume 3.27e-6 ^
  --tension 480.0 ^
  --density 8.5 ^
  --gravity 980.0 ^
  --contact-angle 30.0 ^
  --format "stl,vtk,lsdyna" ^
  --refine-steps 3 ^
  --output output ^
  --timeout 300
```

| 인자 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `--stl-a` | O | — | 하부 패드 STL 파일 |
| `--stl-b` | O | — | 상부 패드 STL 파일 |
| `--center-a` | O | — | 하부 패드 중심 "x,y,z" |
| `--center-b` | O | — | 상부 패드 중심 "x,y,z" |
| `--radius` | O | — | 패드 반경 [cm] |
| `--volume` | O | — | 솔더 체적 [cm³] |
| `--tension` | X | 480.0 | 표면장력 [erg/cm²] |
| `--density` | X | 9.0 | 솔더 밀도 [g/cm³] |
| `--gravity` | X | 980.0 | 중력가속도 [cm/s²] |
| `--contact-angle` | X | 30.0 | 접촉각 [deg] |
| `--format` | X | "stl,vtk" | 출력 포맷 (쉼표 구분) |
| `--refine-steps` | X | 3 | SE 세분화 단계 (높을수록 정밀) |
| `--output` | X | "output" | 출력 디렉토리 |
| `--evolver-path` | X | 자동 탐지 | SE 바이너리 경로 |
| `--fe-only` | X | false | .fe 파일만 생성 |
| `--timeout` | X | 300 | 타임아웃 [초] |

**`--refine-steps`에 따른 메시 밀도:**

| refine-steps | 표면 삼각형 수 | TET4 수 | 용도 |
|:---:|:---:|:---:|:---:|
| 2 | ~2,000 | ~7,000 | 빠른 테스트 |
| 3 | ~8,000 | ~27,000 | 표준 (기본값) |
| 4 | ~32,000 | ~100,000+ | 고정밀 |
| 5 | ~130,000 | ~400,000+ | 초고정밀 (느림) |

### 4.2 `kse yaml` — YAML 설정 실행

```cmd
kse yaml <config.yaml> [--dry-run] [--sweep]
```

| 플래그 | 설명 |
|--------|------|
| `config` (위치인자) | YAML 설정 파일 경로 |
| `--dry-run` | .fe 파일만 생성, SE 실행 안함 |
| `--sweep` | 파라미터 스윕 실행 |

### 4.3 `kse batch` — 병렬 배치

```cmd
kse batch ^
  --stl-a bottom.stl ^
  --stl-b top.stl ^
  --joints joints.csv ^
  --workers 4 ^
  --format "stl,vtk" ^
  --output output_batch
```

**`joints.csv` 형식:**
```csv
name,center_ax,center_ay,center_az,center_bx,center_by,center_bz,radius,volume
joint1,0.0,0.0,0.0,0.0,0.0,0.03,0.025,3.27e-6
joint2,0.1,0.0,0.0,0.1,0.0,0.03,0.025,3.27e-6
joint3,0.2,0.0,0.0,0.2,0.0,0.03,0.020,2.00e-6
```

| 인자 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `--joints` | O | — | 조인트 정의 CSV 파일 |
| `--workers` | X | 0 | 병렬 워커 수 (0 = CPU 코어 수) |

### 4.4 `kse coupled` — 상호작용 조인트

인접 조인트가 서로 영향을 주는 경우 (예: 솔더 브릿지).

```cmd
kse coupled ^
  --stl-a bottom.stl ^
  --stl-b top.stl ^
  --joints joints.csv ^
  --group-distance 0.1 ^
  --timeout 600
```

| 인자 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `--group-distance` | X | 0.0 | 조인트 그룹핑 거리 |

### 4.5 `kse validate` — 검증

내장 예제(bga-1, bga-3, bga-7)로 에너지/체적/형상 정확도를 검증합니다.

```cmd
kse validate --all
kse validate --example bga-1
```

---

## 5. YAML 설정 가이드

YAML은 KSE의 권장 인터페이스입니다. 모든 옵션을 한 파일에 정리하여 재현 가능한 시뮬레이션을 구성합니다.

### 5.1 전체 스키마

```yaml
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 단위계: "cgs" 또는 "mm"
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# cgs: cm, g, s, erg/cm² (Surface Evolver 기본 단위)
# mm:  mm, mg, s, mJ/mm²
units: cgs

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 물리 속성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
physics:
  tension: 480.0              # 표면장력
  density: 8.5                # 솔더 밀도
  gravity: 980.0              # 중력가속도
  contact_angle_bottom: 30.0  # 하부 패드 접촉각 [deg] (0~180)
  contact_angle_top: 30.0     # 상부 패드 접촉각 [deg] (0~180)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 입력 (6가지 모드 중 하나 선택)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
input:
  mode: parametric            # parametric | stl_complex | step_assembly
                              # step_separate | step_bridge | step_array
  # 모드별 필드는 §6 참조

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 형상 파라미터
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
geometry:
  pad_shape: circular         # circular | rectangular (parametric 모드)
  radius: 0.025               # 원형 패드 반경
  # side_x: 0.05              # 사각 패드 X 방향 길이
  # side_y: 0.03              # 사각 패드 Y 방향 길이
  volume: 3.27e-6             # 솔더 체적
  # target_volume: 3.27e-6    # 명시적 체적 강제 지정 (STEP/STL 모드)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 옵션
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
options:
  void: false                 # 보이드(기포) 모델링
  # void_radius: 0.005        # 보이드 반경
  # void_position: [0, 0, 0.015]  # 보이드 위치 (null = 자동)
  fillet: false               # 필렛 예측
  # fillet_walls: []           # 벽면 STEP 파일 리스트
  smooth_iterations: 0        # 메시 스무딩 반복
  max_edge_length: 0.0        # 최대 엣지 길이 (0 = 무제한)
  tessellation_tolerance: 0.001  # STEP → 메시 변환 공차
  angular_tolerance: 0.1      # 각도 공차 [rad]
  contact_distance_tol: 1e-4  # 접촉면 판별 거리
  pad_extract_margin: 1.5     # 패드 추출 마진 (반경 대비 배율)
  # on_surface_tol: null      # 면 위 판정 허용 오차 (null = 자동)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 솔버 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
solver:
  # evolver_path: null        # SE 바이너리 경로 (null = 자동 탐지)
  timeout: 300                # 타임아웃 [초]
  refine_steps: 3             # 메시 세분화 단계
  gradient_steps: 10          # 단계당 gradient descent 반복
  use_hessian: true           # Hessian 최적화 사용
  fe_only: false              # .fe 파일만 생성
  # strategy: ...             # 고급 SE 스크립팅 (§9 참조)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 출력
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
output:
  directory: output           # 출력 디렉토리
  joint_name: solder_joint    # 출력 파일 기본 이름
  formats:                    # 내보내기 포맷 리스트
    - stl                     # 표면 메시 (ASCII STL)
    - vtk                     # 표면 메시 (ParaView)
    # - stl_bin               # 표면 메시 (Binary STL)
    # - lsdyna                # TET4 체적 메시 (LS-DYNA .k)
    # - ansys                 # TET4 체적 메시 (ANSYS .cdb)
    # - gmsh                  # TET4 체적 메시 (Gmsh .msh)
    # - vtk_solid             # TET4 체적 메시 (VTK)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 파라미터 스윕 (선택)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# sweep:
#   enabled: true
#   variable: volume          # 변화시킬 변수
#   values: [1e-6, 2e-6, 3e-6, 5e-6]  # 방법 1: 값 직접 지정
#   # min: 1e-6               # 방법 2: 범위 지정
#   # max: 1e-5
#   # steps: 10
```

### 5.2 단위계

KSE는 두 가지 단위계를 지원합니다. `units` 필드로 전환합니다.

| 항목 | CGS (`units: cgs`) | mm (`units: mm`) |
|------|:---:|:---:|
| 길이 | cm | mm |
| 질량 | g | mg |
| 시간 | s | s |
| 표면장력 | erg/cm² | mJ/mm² |
| 밀도 | g/cm³ | mg/mm³ |
| 중력 | cm/s² | mm/s² |

**변환 예시 (SAC305):**

| 물성 | CGS | mm |
|------|:---:|:---:|
| tension | 480.0 | 0.48 |
| density | 8.5 | 8.5e-3 |
| gravity | 980.0 | 9800.0 |

### 5.3 주의사항

- 모든 파일 경로는 YAML 파일 위치 기준 **상대 경로** 또는 **절대 경로**
- `evolver_path`가 null이면 `src/evolver` (Linux) 또는 `src/evolver.exe` (Windows)를 자동 탐지
- `formats` 리스트에서 `lsdyna`, `ansys`, `gmsh`, `vtk_solid`는 FEA 의존성 필요

---

## 6. 입력 모드 상세

### 6.1 `parametric` — 파라미터 직접 지정

가장 기본적인 모드. 패드 형상과 치수를 직접 입력합니다.

```yaml
input:
  mode: parametric
  stl_a: bottom_pad.stl       # 하부 패드 STL
  stl_b: top_pad.stl          # 상부 패드 STL
  center_a: [0.0, 0.0, 0.0]   # 하부 패드 중심 좌표
  center_b: [0.0, 0.0, 0.03]  # 상부 패드 중심 좌표

geometry:
  pad_shape: circular          # circular | rectangular
  radius: 0.025                # circular일 때 필수
  # side_x: 0.05              # rectangular일 때 필수
  # side_y: 0.03              # rectangular일 때 필수
  volume: 3.27e-6              # 솔더 체적
```

**필요한 STL 파일**: 패드 영역을 포함하는 평면(또는 곡면) STL. KSE가 자동으로 패드 영역을 추출하고 해석면(PLANE/QUADRATIC/QUARTIC)을 피팅합니다.

**용도**: BGA, LGA, QFN 등 단순 패드 형상

### 6.2 `stl_complex` — 임의 형상 STL

CAD에서 내보낸 복잡한 패드 형상을 STL 메시로 직접 입력합니다.

```yaml
input:
  mode: stl_complex
  stl_solder: solder_initial.stl   # 솔더 초기 형상
  stl_bottom: bottom_pad.stl       # 하부 패드 표면
  stl_top: top_pad.stl             # 상부 패드 표면

options:
  smooth_iterations: 3             # STL 메시 스무딩
  max_edge_length: 0.01            # 리메싱 엣지 길이
```

**용도**: 비표준 패드 형상, 곡면 패드, CAD 직접 입력

### 6.3 `step_assembly` — STEP 어셈블리

단일 STEP 파일 안에 솔더, 패드, 기판이 멀티바디로 포함된 경우. KSE가 자동으로 면을 분류합니다.

```yaml
input:
  mode: step_assembly
  step_file: assembly.step

geometry:
  target_volume: 0.05              # 목표 솔더 체적 (STEP에서 자동 계산 가능)

options:
  tessellation_tolerance: 0.001    # STEP → 메시 변환 정밀도
  contact_distance_tol: 1.0e-4     # 접촉면 판별 거리
```

**STEP 파일 요구사항**:
- 최소 2개 바디 (솔더 + 패드/기판)
- 솔더 바디는 접촉 분석으로 자동 식별
- `cadquery` 설치 필요

### 6.4 `step_separate` — STEP 개별 파일

솔더, 하부 패드, 상부 패드를 각각 별도 STEP 파일로 입력합니다.

```yaml
input:
  mode: step_separate
  step_solder: solder_body.step
  step_bottom: bottom_pad.step
  step_top: top_pad.step

geometry:
  target_volume: 0.03
```

### 6.5 `step_bridge` — 브릿지 조인트

두 패드를 수평으로 연결하는 브릿지형 솔더 조인트.

```yaml
input:
  mode: step_bridge
  step_file: bridge_assembly.step

options:
  fillet: true                     # 필렛 예측 활성화
```

### 6.6 `step_array` — 멀티 조인트 배열

BGA 등 하나의 STEP 파일에 다수의 조인트가 포함된 경우. KSE가 자동으로 각 조인트를 인식하고 개별 시뮬레이션합니다.

```yaml
input:
  mode: step_array
  step_file: bga_array.step

options:
  void: true                       # 보이드 모델링
  void_radius: 0.02
```

**출력**: 조인트 수만큼 개별 .fe, .dmp, .stl 파일 생성

---

## 7. 출력 형식

### 7.1 포맷 목록

| 포맷 이름 | 파일 | 타입 | 설명 | 뷰어 |
|-----------|------|------|------|------|
| `stl` | `.stl` | 표면 | ASCII STL 삼각형 메시 | LS-PrePost, ParaView |
| `stl_bin` | `.stl` | 표면 | Binary STL (대용량에 유리) | LS-PrePost, ParaView |
| `vtk` | `.vtk` | 표면 | VTK Unstructured Grid | ParaView, VisIt |
| `lsdyna` | `.k` | 체적 | LS-DYNA 키워드 (TET4) | LS-PrePost |
| `ansys` | `.cdb` | 체적 | ANSYS CDB (SOLID285) | ANSYS Mechanical |
| `gmsh` | `.msh` | 체적 | Gmsh MSH v4.1 | Gmsh, ParaView |
| `vtk_solid` | `.vtk` | 체적 | VTK Tetrahedra | ParaView, VisIt |

### 7.2 표면 메시 vs 체적 메시

**표면 메시** (`stl`, `stl_bin`, `vtk`):
- 솔더 조인트 외형만 삼각형으로 표현
- 시각화, 형상 비교에 적합
- 추가 의존성 불필요

**체적 메시** (`lsdyna`, `ansys`, `gmsh`, `vtk_solid`):
- 내부까지 TET4 사면체로 채움
- FEA 구조/열 해석에 직접 사용 가능
- `requirements-fea.txt` 설치 필요 (tetgen, pymeshfix)

### 7.3 LS-DYNA .k 파일 구조

```
*KEYWORD
*TITLE
KSE solder_joint
*NODE
       1  1.23456e-01  2.34567e-01  3.45678e-01
       2  ...
*ELEMENT_SOLID
       1       1       1       2       3       4       0       0       0       0
       2  ...
*SECTION_SOLID
         1
        13
*MAT_ELASTIC
         1  8.500e+00  3.000e+04  3.500e-01
*PART
solder
         1         1         1
*END
```

- `ELEMENT_SOLID`: elform=13 (1-point TET4)
- Node 5~8 = 0 (4-node tetrahedron)
- 좌표는 입력 단위계 그대로

### 7.4 ANSYS .cdb 파일 구조

- `ET,1,SOLID285` (4-node tetrahedral solid)
- NBLOCK + EBLOCK 형식
- ANSYS Mechanical에서 `/INPUT` 명령으로 읽기

### 7.5 출력 좌표계

출력 좌표는 입력 단위계(CGS 또는 mm)를 그대로 따릅니다. 단위 변환이 필요하면 YAML의 `units` 필드를 변경하세요.

---

## 8. 파라미터 스윕

하나의 변수를 여러 값으로 변화시키며 자동으로 다수의 시뮬레이션을 실행합니다.

### 8.1 설정

```yaml
sweep:
  enabled: true
  variable: volume             # 변화시킬 변수

  # 방법 1: 값 목록 직접 지정
  values: [1.0e-6, 2.0e-6, 3.27e-6, 5.0e-6, 8.0e-6]

  # 방법 2: 범위 지정 (values와 동시 사용 불가)
  # min: 1.0e-6
  # max: 1.0e-5
  # steps: 10
```

### 8.2 실행

```cmd
kse yaml sweep_config.yaml --sweep
```

### 8.3 스윕 가능 변수

| 변수명 | 설명 |
|--------|------|
| `volume` | 솔더 체적 |
| `tension` | 표면장력 |
| `density` | 솔더 밀도 |
| `gravity` | 중력가속도 |
| `contact_angle_bottom` | 하부 접촉각 |
| `contact_angle_top` | 상부 접촉각 |
| `radius` | 패드 반경 |

### 8.4 출력

```
output_sweep/
├── sweep_report.txt          # 전체 결과 요약
├── sweep_v1.0e-06/
│   ├── sweep_result.fe
│   ├── sweep_result.dmp
│   ├── sweep_result.stl
│   └── sweep_result.vtk
├── sweep_v2.0e-06/
│   └── ...
└── sweep_v3.27e-06/
    └── ...
```

---

## 9. Evolution Strategy (고급)

Surface Evolver의 진화 스크립트를 세밀하게 제어합니다. `solver.strategy` 섹션에서 설정합니다.

### 9.1 프리셋

| 프리셋 | 설명 | 속도 | 정밀도 |
|--------|------|:---:|:---:|
| `basic` | 최소: u, g, r, hessian | 빠름 | 보통 |
| `standard` | + 체적 보정, 등각화, gofine | 보통 | 높음 |
| `advanced` | + autopop, skinny refine, eigenprobe | 느림 | 매우 높음 |
| `custom` | 사용자 직접 SE 명령 작성 | — | — |

### 9.2 사용 예시

**기본 (프리셋 사용):**
```yaml
solver:
  strategy:
    preset: standard
```

**고급 (개별 파라미터 조정):**
```yaml
solver:
  strategy:
    preset: advanced
    n_refine: 4
    n_gradient: 15
    n_hessian: 5
    use_skinny_refine: true
    skinny_angle: 15.0
    autopop: true
    use_gofine: true
    gofine_extra_refine: 3
    eigenprobe: true
```

**커스텀 (SE 명령 직접 작성):**
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
        r; u; V; g 30;
        hessian; hessian; hessian; hessian; hessian;
      }
      gomore := {
        V; u; g 30;
        hessian; hessian; hessian;
      }
```

### 9.3 전체 Strategy 파라미터

**Setup (SE 모드 토글):**

| 파라미터 | 기본값 | SE 명령 | 설명 |
|----------|--------|---------|------|
| `hessian_normal` | true | `hessian_normal` | Hessian 법선 방향 모드 |
| `conj_grad` | false | `U` | 켤레 기울기 가속 |
| `check_increase` | true | `check_increase ON` | 에너지 증가 거부 |
| `autopop` | false | `autopop ON` | 퇴화 요소 자동 제거 |
| `autochop` | false | `autochop ON` | 긴 엣지 자동 분할 |
| `normal_motion` | false | `normal_motion ON` | 법선 방향 투영 |
| `area_normalization` | false | `a` | 평균 곡률 운동 |
| `approximate_curvature` | false | `approximate_curvature ON` | 다면체 곡률 근사 |
| `runge_kutta` | false | `runge_kutta ON` | 4차 Runge-Kutta |
| `diffusion` | false | `diffusion ON` | 기체 확산 |
| `gravity_on` | null | `G ON/OFF` | 중력 명시 토글 |
| `scale_factor` | null | `m F` | 고정 스케일 팩터 |

**Evolution (진화 시퀀스):**

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `n_refine` | 3 | 리파인 단계 수 |
| `n_gradient` | 10 | 단계당 gradient descent 횟수 |
| `use_hessian` | true | Newton법 (hessian) 사용 |
| `n_hessian` | 3 | gogo에서 hessian 반복 |
| `n_hessian_more` | 2 | gomore에서 hessian 반복 |
| `use_hessian_seek` | false | hessian + line search |
| `use_volume_correction` | true | V 명령 (체적 보정) |
| `use_equiangulate` | true | u 명령 (등각화) |
| `use_saddle` | false | 안장점 탐색 |

**Mesh Quality (메시 품질):**

| 파라미터 | 기본값 | SE 명령 | 설명 |
|----------|--------|---------|------|
| `tiny_edge_threshold` | 0.0 | `t T` | 짧은 엣지 제거 (0=건너뜀) |
| `long_edge_threshold` | 0.0 | `l L` | 긴 엣지 분할 (0=건너뜀) |
| `weed_threshold` | 0.0 | `w W` | 작은 삼각형 제거 |
| `use_skinny_refine` | false | `K A` | 얇은 삼각형 분할 |
| `skinny_angle` | 20.0 | | 각도 임계값 [deg] |
| `use_pop` | false | `o` | 비최소 꼭짓점 팝 |
| `use_pop_edge` | false | `O` | 비최소 엣지 팝 |
| `use_notch` | false | `n A` | 리지/밸리 노치 |
| `use_edgeswap` | false | `edgeswap` | 엣지 교환 |
| `use_jiggle` | false | `j T` | 랜덤 꼭짓점 섭동 |

**gofine (고품질 최종 패스):**

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `use_gofine` | false | gofine 매크로 활성화 |
| `gofine_extra_refine` | 2 | 추가 리파인 횟수 |
| `gofine_gradient_mult` | 2 | gradient 배수 |

**Analysis (후처리):**

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `eigenprobe` | false | 안정성 고유치 탐색 |
| `ritz_count` | 0 | Ritz 고유치 개수 (0=건너뜀) |
| `report_pressure` | false | 바디 압력 출력 |
| `report_volumes` | false | 체적/압력 리포트 |
| `report_energy` | false | 총 에너지 출력 |

---

## 10. 솔더 물성 참고표

### 합금별 물성

| 합금 | 표면장력 | 표면장력 | 밀도 | 융점 |
|------|:---:|:---:|:---:|:---:|
| | [erg/cm²] | [mJ/mm²] | [g/cm³] | [°C] |
| SAC305 (Sn96.5Ag3Cu0.5) | 480 | 0.48 | 8.5 | 217-220 |
| SAC405 (Sn95.5Ag4Cu0.5) | 490 | 0.49 | 8.5 | 217-220 |
| SnPb (Sn63Pb37) | 460 | 0.46 | 8.4 | 183 |
| SnBi (Sn42Bi58) | 350 | 0.35 | 8.7 | 138 |
| Pure Sn | 520 | 0.52 | 7.3 | 232 |

### 표면별 접촉각

| 표면 | 접촉각 [deg] | 비고 |
|------|:---:|------|
| Cu 패드 (flux 활성) | 20-35 | PCB 일반 패드 |
| Cu 패드 (flux 없음) | 40-60 | 산화 표면 |
| Ni/Au 패드 (ENIG) | 25-40 | ENIG 마감 |
| 솔더 마스크 | 90-130 | 비젖음 |
| FR-4 기판 | 110-140 | 비젖음 |

---

## 11. 외부 프로그램 연동 (Integration)

### 11.1 Python subprocess 연동

다른 Python 프로그램에서 KSE를 호출하는 가장 간단한 방법입니다.

```python
import subprocess
import yaml
from pathlib import Path

def run_kse_simulation(
    stl_bottom: str,
    stl_top: str,
    center_a: list,
    center_b: list,
    radius: float,
    volume: float,
    output_dir: str = "output",
    formats: list = None,
    tension: float = 480.0,
    density: float = 8.5,
    contact_angle: float = 30.0,
    refine_steps: int = 3,
    timeout: int = 300,
) -> dict:
    """KSE 시뮬레이션 실행 후 결과 반환."""
    if formats is None:
        formats = ["stl", "vtk"]

    config = {
        "units": "cgs",
        "physics": {
            "tension": tension,
            "density": density,
            "gravity": 980.0,
            "contact_angle_bottom": contact_angle,
            "contact_angle_top": contact_angle,
        },
        "input": {
            "mode": "parametric",
            "stl_a": stl_bottom,
            "stl_b": stl_top,
            "center_a": center_a,
            "center_b": center_b,
        },
        "geometry": {
            "pad_shape": "circular",
            "radius": radius,
            "volume": volume,
        },
        "solver": {
            "timeout": timeout,
            "refine_steps": refine_steps,
            "use_hessian": True,
        },
        "output": {
            "directory": output_dir,
            "formats": formats,
            "joint_name": "solder_joint",
        },
    }

    # YAML 설정 파일 생성
    config_path = Path(output_dir) / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    # KSE 실행
    result = subprocess.run(
        ["kse", "yaml", str(config_path)],
        capture_output=True, text=True, timeout=timeout + 60
    )

    # 결과 파싱
    output = {
        "success": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "files": {},
    }

    if result.returncode == 0:
        base = Path(output_dir) / "solder_joint"
        for fmt in formats:
            ext_map = {
                "stl": ".stl", "stl_bin": ".stl", "vtk": ".vtk",
                "lsdyna": ".k", "ansys": ".cdb", "gmsh": ".msh",
                "vtk_solid": ".vtk",
            }
            ext = ext_map.get(fmt, "")
            fpath = base.with_suffix(ext)
            if fpath.exists():
                output["files"][fmt] = str(fpath)

        # stdout에서 standoff height 파싱
        for line in result.stdout.splitlines():
            if "Standoff height:" in line:
                output["standoff_height"] = float(
                    line.split(":")[1].strip().split()[0]
                )
            if "Max radius:" in line:
                output["max_radius"] = float(
                    line.split(":")[1].strip().split()[0]
                )

    return output


# 사용 예시
result = run_kse_simulation(
    stl_bottom="bottom_pad.stl",
    stl_top="top_pad.stl",
    center_a=[0, 0, 0],
    center_b=[0, 0, 0.03],
    radius=0.025,
    volume=3.27e-6,
    formats=["stl", "lsdyna"],
)

if result["success"]:
    print(f"Standoff height: {result['standoff_height']} cm")
    print(f"LS-DYNA file: {result['files']['lsdyna']}")
```

### 11.2 KSE 모듈 직접 import

Python 프로그램에서 KSE 내부 모듈을 직접 사용할 수도 있습니다.

```python
import numpy as np
from pathlib import Path

from kse.core.stl_reader import STLReader
from kse.core.surface_fitter import SurfaceFitter
from kse.core.constraint_gen import ConstraintGenerator
from kse.core.geometry_builder import GeometryBuilder
from kse.core.fe_writer import FEWriter, SolderJointConfig
from kse.solver.evolver_runner import EvolverRunner
from kse.solver.dump_parser import DumpParser
from kse.solver.evolution_scripts import EvolutionStrategy, generate_runtime_commands
from kse.mesh.volume_mesher import generate_volume_mesh
from kse.mesh.exporters.lsdyna_export import export_lsdyna_k_solid

# 1. 패드 STL 읽기 + 패치 추출
reader_a = STLReader("bottom_pad.stl")
reader_b = STLReader("top_pad.stl")
patch_a = reader_a.extract_patch(np.array([0, 0, 0]), radius=0.025)
patch_b = reader_b.extract_patch(np.array([0, 0, 0.03]), radius=0.025)

# 2. 해석면 피팅
fitter = SurfaceFitter()
fit_a = fitter.fit(patch_a)
fit_b = fitter.fit(patch_b)

# 3. SE 제약 조건 생성
cgen = ConstraintGenerator()
c_a = cgen.generate_surface_constraint(fit_a, 1, contact_angle=30.0, tension=480.0)
c_b = cgen.generate_surface_constraint(fit_b, 2, contact_angle=30.0, tension=480.0)
rim_a = cgen.generate_rim_constraint(fit_a, 3, radius=0.025)
bdry_b = cgen.generate_parametric_boundary(fit_b, 1, radius=0.025)

# 4. 초기 메시 + .fe 파일 생성
builder = GeometryBuilder()
geom = builder.build(fit_a, fit_b, radius=0.025, volume=3.27e-6)

config = SolderJointConfig(
    tension=480.0, density=8.5, gravity=980.0,
    radius=0.025, volume=3.27e-6,
    contact_angle_A=30.0, contact_angle_B=30.0,
)

writer = FEWriter()
fe_path = Path("output/solder_joint.fe")
fe_path.parent.mkdir(exist_ok=True)
writer.write_single(fe_path, geom, [c_a, c_b, rim_a], [bdry_b], config)

# 5. Surface Evolver 실행
runner = EvolverRunner()  # 자동으로 src/evolver 또는 src/evolver.exe 탐지
dump_path = fe_path.with_suffix(".dmp")
strategy = EvolutionStrategy(preset="basic", n_refine=3)
commands = generate_runtime_commands(strategy, dump_path.name)
result = runner.run(fe_path, commands, dump_path, timeout=300)

assert result.success, f"SE failed: {result.stderr}"

# 6. 결과 파싱
parser = DumpParser()
mesh = parser.parse(dump_path)
vertices = mesh.vertex_array     # (N, 3) numpy array
triangles = mesh.face_triangles  # (M, 3) numpy array

# 7. 체적 메시 생성 + LS-DYNA 출력
vol = generate_volume_mesh(vertices, triangles)
export_lsdyna_k_solid(vol.vertices, vol.tetrahedra, Path("output/solder_joint"))
# → output/solder_joint.k 생성
```

### 11.3 Batch 스크립트 연동 (Windows)

```batch
@echo off
REM 여러 케이스를 순차적으로 실행

call .venv\Scripts\activate.bat

for %%c in (configs\case_01.yaml configs\case_02.yaml configs\case_03.yaml) do (
    echo Running %%c ...
    kse yaml %%c
    if errorlevel 1 (
        echo FAILED: %%c
    ) else (
        echo OK: %%c
    )
)

echo All done.
```

### 11.4 Batch 스크립트 연동 (Linux/bash)

```bash
#!/bin/bash
source .venv/bin/activate

for config in configs/case_*.yaml; do
    echo "Running $config ..."
    if kse yaml "$config"; then
        echo "OK: $config"
    else
        echo "FAILED: $config"
    fi
done
```

### 11.5 LS-DYNA 워크플로우 예시

```
1. KSE로 솔더 조인트 형상 시뮬레이션
   kse yaml solder_config.yaml
   → output/solder_joint.k (TET4 메시)

2. LS-PrePost에서 .k 파일 로드
   - File → Import → LS-DYNA Keyword
   - 솔더 메시 확인 (Part 1)

3. 물성/경계조건 추가
   - 솔더 물성 수정 (MAT_ELASTIC → MAT_PIECEWISE_LINEAR_PLASTICITY 등)
   - PCB/부품 메시와 접합
   - 하중/경계조건 부여

4. LS-DYNA 해석 실행
```

### 11.6 ANSYS 워크플로우 예시

```
1. KSE로 솔더 형상 생성 (ANSYS 포맷)
   formats: [ansys] → output/solder_joint.cdb (SOLID285 TET4)

2. ANSYS Mechanical에서 읽기
   /INPUT, solder_joint, cdb

3. 물성/경계조건 추가 및 해석
```

### 11.7 YAML 동적 생성 (자동화용)

```python
import yaml

def generate_config(case_name, radius_mm, height_mm, volume_mm3, angle_deg):
    """케이스별 YAML 설정을 자동 생성."""
    # mm 단위계 사용
    return {
        "units": "mm",
        "physics": {
            "tension": 0.48,
            "density": 8.5e-3,
            "gravity": 9800.0,
            "contact_angle_bottom": angle_deg,
            "contact_angle_top": angle_deg,
        },
        "input": {
            "mode": "parametric",
            "stl_a": "common/bottom_pad.stl",
            "stl_b": "common/top_pad.stl",
            "center_a": [0, 0, 0],
            "center_b": [0, 0, height_mm],
        },
        "geometry": {
            "pad_shape": "circular",
            "radius": radius_mm,
            "volume": volume_mm3,
        },
        "solver": {
            "timeout": 300,
            "refine_steps": 3,
            "use_hessian": True,
        },
        "output": {
            "directory": f"output/{case_name}",
            "formats": ["stl", "lsdyna"],
            "joint_name": case_name,
        },
    }


# DOE (Design of Experiments) 자동 생성
import itertools

radii = [0.15, 0.20, 0.25]      # mm
heights = [0.20, 0.30]           # mm
angles = [20, 30, 45]            # deg

for r, h, a in itertools.product(radii, heights, angles):
    vol = 1.3 * 3.14159 * r**2 * h  # mm³ (원기둥 × 1.3)
    name = f"r{r:.2f}_h{h:.2f}_a{a}"
    config = generate_config(name, r, h, vol, a)

    path = f"configs/{name}.yaml"
    with open(path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    print(f"Generated: {path}")
```

### 11.8 Exit Codes

| 코드 | 의미 |
|:---:|------|
| 0 | 성공 |
| 1 | 오류 (설정 오류, SE 실패, 타임아웃 등) |

### 11.9 stdout 파싱 키워드

프로그램 연동 시 stdout에서 다음 키워드를 파싱하여 결과를 추출할 수 있습니다:

| 키워드 | 형식 | 설명 |
|--------|------|------|
| `Standoff height:` | `Standoff height: 0.028500 cm` | 솔더 높이 |
| `Max radius:` | `Max radius: 0.032100 cm` | 최대 반경 |
| `SE completed in` | `SE completed in 8.3s` | SE 실행 시간 |
| `Exported:` | `Exported: output/solder_joint.k` | 생성된 파일 경로 |
| `SE failed:` | `SE failed: ...` | 오류 메시지 |

---

## 12. 프로젝트 구조

```
KooSurfaceEvolver/
├── cli.py                  # CLI 진입점 (5개 서브커맨드)
├── setup.py                # 패키지 설정 + C 확장
├── kse.spec                # PyInstaller 빌드 스펙
├── install_windows.bat     # Windows 자동 설치
├── build.bat               # Windows 독립 빌드
├── build.sh                # Linux 독립 빌드
├── requirements.txt        # 기본 의존성
├── requirements-fea.txt    # FEA 선택 의존성
│
├── kse/                    # 메인 패키지
│   ├── core/               # 파이프라인 코어
│   │   ├── stl_reader.py          # STL 로딩 + 패치 추출
│   │   ├── surface_fitter.py      # 해석면 피팅 (PLANE/QUAD/QUARTIC)
│   │   ├── constraint_gen.py      # SE 제약조건 생성 (SymPy)
│   │   ├── geometry_builder.py    # 초기 메시 생성
│   │   ├── fe_writer.py           # Jinja2 .fe 파일 렌더링
│   │   ├── step_pipeline.py       # STEP 파이프라인
│   │   ├── complex_pipeline.py    # 복합 STL 파이프라인
│   │   ├── step_reader.py         # STEP 파일 읽기 (CadQuery)
│   │   └── units.py               # 단위계 (CGS/mm)
│   │
│   ├── solver/             # SE 실행 + 결과 분석
│   │   ├── evolver_runner.py      # SE subprocess 실행
│   │   ├── dump_parser.py         # SE .dmp 파싱
│   │   ├── evolution_scripts.py   # 진화 스크립트 생성
│   │   └── result_analyzer.py     # standoff height 분석
│   │
│   ├── batch/              # 배치 + 스윕
│   │   ├── parallel_runner.py     # 병렬 실행
│   │   ├── coupled_runner.py      # 커플 조인트
│   │   ├── job_manager.py         # 작업 관리 + export
│   │   └── sweep_runner.py        # 파라미터 스윕
│   │
│   ├── mesh/               # 메시 처리 + 내보내기
│   │   ├── volume_mesher.py       # 표면→체적 메시 (TetGen)
│   │   ├── quality.py             # 메시 품질 평가
│   │   └── exporters/
│   │       ├── stl_export.py      # STL 내보내기
│   │       ├── vtk_export.py      # VTK 내보내기
│   │       ├── lsdyna_export.py   # LS-DYNA .k 내보내기
│   │       ├── ansys_export.py    # ANSYS .cdb 내보내기
│   │       └── gmsh_export.py     # Gmsh .msh 내보내기
│   │
│   └── config/
│       └── yaml_config.py         # YAML 설정 로더
│
├── src/
│   ├── evolver             # SE 바이너리 (Linux, 포함됨)
│   └── evolver.exe         # SE 바이너리 (Windows, 포함됨)
│
├── templates/              # Jinja2 .fe 템플릿
├── examples/
│   ├── configs/            # YAML 설정 예제 (8개)
│   ├── lsdyna_k/           # LS-DYNA 출력 예제
│   └── *.fe                # SE 예제 파일들
│
└── tests/
    ├── test_core.py        # 단위 테스트 (17개)
    └── validation/         # 검증 테스트 (274개)
```

### 파이프라인 흐름

```
입력 (STL/STEP)
   │
   ├─→ STLReader / STEPReader       패드 형상 읽기
   │
   ├─→ SurfaceFitter                해석면 피팅 (PLANE/QUADRATIC/QUARTIC)
   │
   ├─→ ConstraintGenerator          SE 제약조건 + 적분식 생성
   │
   ├─→ GeometryBuilder              초기 메시 (vertices/edges/faces)
   │
   ├─→ FEWriter (Jinja2)            .fe 데이터파일 렌더링
   │
   ├─→ EvolverRunner                Surface Evolver 실행 (subprocess)
   │
   ├─→ DumpParser                   .dmp 결과 파싱 → 표면 메시
   │
   ├─→ [표면 출력]                   STL / VTK
   │
   └─→ [체적 출력]
       ├─→ volume_mesher             경계 감지 → cap 생성 → TetGen
       └─→ exporters                 LS-DYNA / ANSYS / Gmsh / VTK
```

---

## 13. 빌드 (독립 실행파일)

Python 설치 없이 다른 PC에서 사용 가능한 독립 실행파일을 빌드합니다.

### Windows

```cmd
build.bat
```

결과: `dist\kse\kse.exe` + 필요한 모든 라이브러리

### Linux

```bash
bash build.sh
```

결과: `dist/kse/kse` + 필요한 모든 라이브러리

### 빌드 요구사항

- PyInstaller (빌드 스크립트가 자동 설치)
- (선택) Visual C++ Build Tools — C 확장 컴파일용. 없으면 순수 Python fallback

### 배포

`dist/kse/` 폴더 전체를 복사하면 됩니다. Surface Evolver 바이너리가 포함되어 있으므로 별도 설치 불필요.

---

## 14. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `SE binary not found` | evolver 경로 문제 | YAML에 `solver.evolver_path` 지정 |
| `SE failed: timeout` | 시뮬레이션 너무 느림 | `solver.timeout` 증가 또는 `refine_steps` 감소 |
| `SE failed: singular matrix` | 기하학적 문제 | 패드 형상, 체적, 접촉각 확인 |
| `No module named 'cadquery'` | CadQuery 미설치 | `pip install cadquery` (STEP 모드용) |
| `No module named 'tetgen'` | tetgen 미설치 | `pip install -r requirements-fea.txt` (체적 메시용) |
| `Python not found` | PATH 미등록 | Python 설치 시 "Add to PATH" 체크 |
| C 확장 빌드 실패 | Visual C++ 없음 | 무시 가능 (순수 Python fallback 사용) |
| `.k` 파일 미생성 | FEA 의존성 없음 | `pip install -r requirements-fea.txt` |
| `formats`에 `lsdyna` 지정했는데 무시됨 | tetgen import 실패 | stdout에 `Solid export skipped:` 확인 |

---

## 예제 YAML 설정 (examples/configs/)

| 파일 | 모드 | 설명 |
|------|------|------|
| `01_parametric.yaml` | parametric | 기본: 원형 패드, 치수 직접 지정 |
| `02_stl_complex.yaml` | stl_complex | CAD 임의 형상 STL 입력 |
| `03_step_assembly.yaml` | step_assembly | STEP 멀티바디 어셈블리 |
| `04_step_separate.yaml` | step_separate | STEP 개별 파일 3개 |
| `05_step_bridge.yaml` | step_bridge | 브릿지 솔더 조인트 |
| `06_step_array.yaml` | step_array | BGA 배열 (다수 조인트) |
| `07_sweep.yaml` | parametric + sweep | 체적 파라미터 스윕 |
| `08_advanced_strategy.yaml` | parametric + strategy | 고급 SE 스크립팅 |

---

Surface Evolver v2.70a by Ken Brakke.
KSE wrapper by squall321.
