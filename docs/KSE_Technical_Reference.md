# KooSurfaceEvolver (KSE) 기술 참조 문서

**버전**: 0.1.0
**대상**: CAD STL → Surface Evolver 자동화 파이프라인
**단위계**: CGS (cm, g, s, erg)

---

## 목차

1. [시스템 개요](#1-시스템-개요)
2. [이론적 배경](#2-이론적-배경)
3. [모듈별 상세 설명](#3-모듈별-상세-설명)
4. [파이프라인 흐름도](#4-파이프라인-흐름도)
5. [수학 공식 정리](#5-수학-공식-정리)
6. [활용 가능 범위](#6-활용-가능-범위)
7. [사용 예제](#7-사용-예제)
8. [검증 결과](#8-검증-결과)

---

## 1. 시스템 개요

### 1.1 KSE가 하는 일

KSE는 **솔더 조인트의 평형 형상**을 자동으로 계산합니다.

```
입력: 패드 형상 (STL) + 솔더 물성 + 공정 조건
  ↓
KSE 파이프라인
  ↓
출력: Surface Evolver .fe 파일 → SE 실행 → 평형 메니스커스 형상
```

솔더 조인트의 최종 형상은 **표면 에너지 최소화** 원리로 결정됩니다. 표면장력, 중력, 접촉각, 체적 보존이 동시에 만족되는 형상을 찾습니다.

### 1.2 두 가지 파이프라인

| 파이프라인 | 입력 | 용도 |
|---|---|---|
| **Standard Pipeline** | 패드 형상(원형/사각) + 치수 파라미터 | 설계 단계: 파라미터로 정의 가능한 단순 형상 |
| **Complex STL Pipeline** | bottom_pad.stl + top_pad.stl + solder.stl | 검증 단계: CAD에서 내보낸 임의 형상 |

### 1.3 전체 아키텍처

```
kse/
├── core/                    ← 핵심 파이프라인
│   ├── stl_reader.py        ← STL 로딩 + 패치 추출
│   ├── surface_fitter.py    ← 해석적 곡면 피팅
│   ├── constraint_gen.py    ← SE 제약식 생성 (SymPy)
│   ├── geometry_builder.py  ← 초기 형상 생성 (원형/사각)
│   ├── fe_writer.py         ← .fe 파일 생성 (Jinja2)
│   ├── mesh_preprocessor.py ← STL 메시 전처리
│   ├── boundary_extractor.py← 경계 루프 추출
│   ├── mesh_to_se.py        ← trimesh → SE 토폴로지 변환
│   └── complex_pipeline.py  ← Complex STL 파이프라인 오케스트레이션
├── solver/
│   ├── dump_parser.py       ← SE .dmp 파일 파싱
│   ├── evolver_runner.py    ← SE 프로세스 실행
│   └── evolution_scripts.py ← 진화 명령 스크립트
├── mesh/
│   ├── quality.py           ← 메시 품질 평가
│   ├── refiner.py           ← 스무딩 + 세분화
│   └── exporters/           ← STL/VTK/GMSH/ANSYS/LS-DYNA 내보내기
└── batch/
    ├── parallel_runner.py   ← 병렬 실행
    ├── coupled_runner.py    ← 커플링 실행
    └── job_manager.py       ← 작업 관리
```

---

## 2. 이론적 배경

### 2.1 에너지 최소화 원리

솔더 조인트의 평형 형상은 **총 에너지의 정류점(stationary point)**에서 결정됩니다:

```
E_total = E_surface + E_gravity + E_contact
```

각 에너지 항:

**표면 에너지 (Surface Energy)**
```
E_surface = σ · A_free
```
- σ: 표면장력 (SAC305: 480 erg/cm²)
- A_free: 자유 표면(솔더-공기 경계면) 면적

**중력 에너지 (Gravitational Energy)**
```
E_gravity = ρ · g · ∫∫∫ z dV
```
- ρ: 솔더 밀도 (SAC305: 8.5~9.0 g/cm³)
- g: 중력가속도 (980 cm/s²)
- z: 높이 좌표

**접촉 에너지 (Contact/Wetting Energy)**
```
E_contact = -σ · cos(θ) · A_wetted
```
- θ: 접촉각 (Young's equation)
- A_wetted: 솔더가 패드와 접촉하는 면적

### 2.2 Young's 방정식 (접촉각)

패드-솔더-공기 삼중점에서의 힘 평형:

```
σ_SG = σ_SL + σ_LG · cos(θ)
```
- σ_SG: 고체-기체 표면 에너지
- σ_SL: 고체-액체 표면 에너지
- σ_LG: 액체-기체 표면장력 (= σ)
- θ: 접촉각

KSE에서는 접촉각 θ를 직접 지정합니다. 일반적 범위:
- SAC305 on Cu: θ = 25°~40°
- SAC305 on Ni: θ = 30°~50°
- SAC305 on OSP: θ = 20°~35°

### 2.3 체적 보존 조건

리플로우 과정에서 솔더 체적은 보존됩니다:

```
∫∫∫_Ω dV = V_target
```

이는 Surface Evolver에서 **라그랑주 승수(Lagrange multiplier)**를 통한 제약 조건으로 구현됩니다:

```
E_augmented = E_total + λ · (V - V_target)
```

### 2.4 Surface Evolver의 부호 엣지 토폴로지

SE는 **부호 엣지(signed edge)** 기반 토폴로지를 사용합니다:

```
정규 엣지 정의: edge_id  v_low  v_high
  → 정방향: v_low → v_high (+edge_id)
  → 역방향: v_high → v_low (-edge_id)

면 정의: face_id  ±e1  ±e2  ±e3
  → 3개의 부호 엣지가 닫힌 루프를 형성
  → 법선 방향: 오른손 법칙
```

체적 계산은 **발산 정리(divergence theorem)**를 사용합니다:

```
V = (1/3) ∫∫_∂Ω x⃗ · n̂ dA
```

각 삼각형 면의 체적 기여분은 부호 엣지 순서로 결정되므로, 엣지 부호의 정확한 할당이 필수적입니다.

### 2.5 제약식과 경계 적분

#### 2.5.1 암묵적 표면 제약 (Implicit Surface Constraint)

패드 표면 F(x,y,z) = 0을 SE CONSTRAINT로 표현합니다:

```
constraint N
formula: F(x, y, z)
```

F(x,y,z)의 구성:
1. 전역 좌표 → 로컬 좌표 변환: [u, v, w] = R · (P - C)
2. 로컬에서의 표면: w = f(u, v) (다항식)
3. 암묵적 형태: F = w - f(u, v) = 0

여기서 f(u,v)는 피팅 차수에 따라:

| 타입 | 다항식 | 계수 수 |
|---|---|---|
| PLANE | c₀ + c₁u + c₂v | 3 |
| QUADRATIC | c₀ + c₁u + c₂v + c₃u² + c₄uv + c₅v² | 6 |
| QUARTIC | ... + c₆u³ + ... + c₁₄v⁴ | 15 |

#### 2.5.2 에너지 경계 적분 (Energy Boundary Integral)

캡 면(패드 위의 면)을 제거한 열린 메시에서, 접촉 에너지와 중력 에너지는 **경계선 적분**으로 계산됩니다:

```
constraint N
energy:
e1: 0
e2: -σ·cos(θ)·x + (1/2)·G·ρ·x·z²
e3: 0
```

이 적분의 물리적 의미:

**접촉 에너지 항**: `-σ·cos(θ)·x`
- Green 정리: ∮ -σ·cos(θ)·x dy dz = -σ·cos(θ) · ∫∫ dA
- 즉, 경계 루프를 따른 선적분이 해당 패드 위의 젖음 면적 × (-σ·cos θ)와 같음

**중력 에너지 항**: `(1/2)·G·ρ·x·z²`
- Green 정리: ∮ (1/2)·G·ρ·x·z² dy dz = G·ρ · ∫∫∫ z dV (캡 아래 영역)
- 패드 캡 아래 솔더의 중력 퍼텐셜 에너지

#### 2.5.3 체적 보정 적분 (Content Boundary Integral)

캡 면 제거로 인한 체적 손실을 보정합니다:

```
content:
c1: 0
c2: x·z
c3: 0
```

발산 정리를 적용하면:
```
∮ x·z dy dz = ∫∫ z dA  (패드 위의 캡 면적 × 높이)
```

이 적분이 경계 루프를 따라 계산되어, 제거된 캡 면의 체적 기여분을 자동으로 보정합니다.

#### 2.5.4 파라메트릭 경계 (Parametric Boundary)

원형 패드에서는 경계를 파라미터로 정의할 수 있습니다:

```
boundary 1 parameters 1
x1: cx + r·cos(p1)·u_x + r·sin(p1)·v_x + f(r·cos(p1), r·sin(p1))·n_x
x2: cy + r·cos(p1)·u_y + r·sin(p1)·v_y + f(r·cos(p1), r·sin(p1))·n_y
x3: cz + r·cos(p1)·u_z + r·sin(p1)·v_z + f(r·cos(p1), r·sin(p1))·n_z
```

SE가 p1을 자유롭게 조정하여 경계점의 최적 위치를 찾습니다.

### 2.6 두 가지 제약 전략 비교

| 항목 | Boundary + Rim (원형 패드) | Constraint + Integral (사각/복잡 패드) |
|---|---|---|
| 위쪽 패드 | parametric BOUNDARY | CONSTRAINT + energy/content |
| 아래쪽 패드 | CONSTRAINT + rim constraint | CONSTRAINT + energy/content |
| 경계 점 이동 | 파라미터 p1 자유 이동 | fixed (고정) |
| 적용 형상 | 원형만 | 임의 형상 (원형, 사각, 타원, 불규칙...) |
| 메시 세분화 시 | 경계 위에서 보간 | 제약식 위에서 투영 |

---

## 3. 모듈별 상세 설명

### 3.1 STLReader (`stl_reader.py`)

**역할**: STL 파일 로딩 + 관심 영역 패치 추출

```python
reader = STLReader("pad_surface.stl")
patch = reader.extract_patch(center, radius)
```

**동작 과정**:
1. `trimesh.load()`: STL → 삼각형 메시 로딩
2. 중심점 투영: `center`를 메시 표면 위 최근접점으로 투영
3. 면적 가중 법선 계산: 패치 영역의 평균 표면 법선
4. 로컬 좌표계 구축: [u, v, n] 직교 좌표계
5. 원형 크롭: `radius × margin` 내의 면만 추출
6. 꼭짓점 재색인: 패치만의 독립 메시 생성

**출력**: `LocalPatch`
- `vertices`: (N, 3) 전역 좌표
- `local_coords`: (N, 3) 로컬 좌표 [u, v, w]
- `center`: (3,) 투영된 중심점
- `local_axes`: (3, 3) 변환 행렬 [u축, v축, n축]
- `radius`: 추출 반경

### 3.2 SurfaceFitter (`surface_fitter.py`)

**역할**: 로컬 패치에 해석적 곡면(다항식) 피팅

```python
fitter = SurfaceFitter(plane_tol=1e-4, quad_tol=1e-3)
fit = fitter.fit(patch)  # 자동 차수 선택
```

**자동 차수 선택 전략**:
```
1차 (PLANE):    z = c₀ + c₁u + c₂v
                 → RMS < plane_tol × scale 이면 채택
2차 (QUADRATIC): z = c₀ + c₁u + c₂v + c₃u² + c₄uv + c₅v²
                 → RMS < quad_tol × scale 이면 채택
4차 (QUARTIC):  z = ... + c₆u³ + ... + c₁₄v⁴
                 → 무조건 사용 (최종 폴백)
```

**수치 안정성**: 피팅 전에 `u, v`를 `scale = patch.radius`로 나누어 정규화. 피팅 후 계수를 원래 스케일로 복원.

**핵심 메서드**:

| 메서드 | 입력 | 출력 | 용도 |
|---|---|---|---|
| `eval_local(u, v)` | 로컬 좌표 | z값 | 표면 높이 계산 |
| `eval_global(points)` | (N,3) 전역 좌표 | F값 | 0=표면 위, +/- = 위/아래 |
| `is_planar` | - | bool | 평면 여부 |

### 3.3 ConstraintGenerator (`constraint_gen.py`)

**역할**: SurfaceFitResult → SE 제약식 문자열 생성

SymPy를 사용하여 수식을 기호적으로 유도한 후 SE 문법으로 변환합니다.

**생성되는 제약식 유형**:

| 메서드 | 생성물 | SE 요소 |
|---|---|---|
| `generate_surface_constraint()` | 표면 + 에너지/체적 적분 | CONSTRAINT + energy + content |
| `generate_rim_constraint()` | 원형 경계 유지 | CONSTRAINT (원 방정식) |
| `generate_parametric_boundary()` | 파라미터 경계 | BOUNDARY + energy + content |

**SE 문법 변환 (`_sympy_to_se`)**:
- `**` → `^` (거듭제곱)
- 유리수 → 소수 (예: `3/25` → `0.12`)
- 부동소수점 잡음 제거 (|v| < 1e-12 → 0)
- STL float32 노이즈 8자리 반올림

### 3.4 GeometryBuilder (`geometry_builder.py`)

**역할**: 초기 솔더 형상(원기둥/프리즘) 생성

두 패드 표면 사이에 단순한 초기 형상을 만듭니다. SE가 이를 진화시켜 평형 형상을 찾습니다.

**원형 패드 (`build`)**:
```
n개 꼭짓점 × 2 (위/아래) = 2n 꼭짓점
n개 바닥 엣지 + n개 윗면 엣지 + n개 수직 엣지 = 3n 엣지
n개 사각형 → n개 면 (각 면은 4개 부호 엣지)
1개 body = 모든 면 + 체적 제약
```

**사각 패드 (`build_rectangular`)**:
```
사각형 둘레를 n등분 → 균등 분포 꼭짓점
나머지 토폴로지는 원형과 동일
양쪽 모두 CONSTRAINT 사용 (parametric boundary 불필요)
```

### 3.5 FEWriter (`fe_writer.py`)

**역할**: 지오메트리 + 제약식 + 설정 → .fe 파일 렌더링

Jinja2 템플릿(`solder_basic.fe.j2`)을 사용합니다.

**`write_single()`**: 단일 조인트 .fe 생성
**`write_coupled()`**: 다중 조인트 커플링 .fe 생성 (ID 오프셋 자동 처리)

**.fe 파일 구조**:
```
// 헤더 + 물성 파라미터
parameter S_TENSION = 480
parameter SOLDER_DENSITY = 9.0
gravity_constant 980

// 제약식
constraint 1
formula: z
energy: ...
content: ...

// 기하 요소
vertices
1  x y z  constraints 1  fixed
...

edges
1  v1 v2  constraints 1  fixed
...

faces
1  e1 e2 e3  tension S_TENSION
...

bodies
1  f1 f2 ... volume V  density SOLDER_DENSITY

// 진화 스크립트
gogo := { u; g 10; r; g 10; r; g 10; r; g 10; hessian; hessian; hessian; }
gomore := { V; g 10; r; V; g 10; hessian; hessian; }
```

### 3.6 MeshPreprocessor (`mesh_preprocessor.py`) [Phase 7 신규]

**역할**: CAD STL 메시 정리 및 검증

CAD에서 내보낸 STL은 퇴화 삼각형, 불일치 법선, 비매니폴드 엣지 등의 문제가 있을 수 있습니다.

```python
preprocessor = MeshPreprocessor(
    min_area=1e-20,       # 퇴화 삼각형 면적 임계값
    smooth_iterations=0,  # 라플라시안 스무딩 반복 수
    smooth_factor=0.3,    # 스무딩 강도 (0~1)
    max_edge_length=0.0,  # 긴 엣지 분할 임계값 (0=비활성)
)
result = preprocessor.preprocess(mesh)
```

**전처리 파이프라인**:

```
입력 메시
  │
  ├─ 1. 퇴화 삼각형 제거 (area < min_area)
  │     └─ np.area_faces로 면적 계산 → 임계값 이하 면 제거
  │
  ├─ 2. 법선 방향 수정 (trimesh.repair.fix_normals)
  │     └─ 면 와인딩 일관성 보장 → 뒤집어진 법선 감지
  │
  ├─ 3. 밀폐 상태 확인 (mesh.is_watertight)
  │
  ├─ 4. [선택] 라플라시안 스무딩
  │     └─ v_new = v + λ · (avg(neighbors) - v)
  │     └─ CAD 메시의 계단 현상(staircase) 완화
  │
  ├─ 5. [선택] 긴 엣지 중점 분할
  │     └─ 엣지 > max_edge_length → 중점에 새 꼭짓점 삽입
  │     └─ SE 세분화 전 초기 메시 품질 향상
  │
  └─ 6. 품질 평가 (assess_quality)
        ├─ 종횡비 (aspect ratio): 최장 엣지 / (2 × 내접원 반경)
        ├─ 최소/최대 각도
        ├─ 비대칭도 (skewness): 1 - min_angle/60°
        └─ FEM 적합성 판정
```

**출력**: `PreprocessResult`
- `mesh`: 정리된 메시
- `is_watertight`: 밀폐 여부
- `n_removed_degenerate`: 제거된 퇴화 면 수
- `quality`: QualityReport (종횡비, 각도, 비대칭도)
- `warnings`: 처리 내역 메시지

### 3.7 BoundaryExtractor (`boundary_extractor.py`) [Phase 7 신규]

**역할**: 밀폐 솔더 메시 → 캡 면 감지/제거 → 경계 루프 추출

이 모듈이 Complex STL Pipeline의 **핵심**입니다.

```python
extractor = BoundaryExtractor(
    fit_bottom=fit_b,      # 아래 패드 곡면 피팅 결과
    fit_top=fit_t,         # 위 패드 곡면 피팅 결과
    on_surface_tol=None,   # 표면 위 판정 공차 (None=자동)
)
result = extractor.extract(solder_mesh)
```

**1단계: 캡 면 감지 (`_find_cap_faces`)**

CAD에서 내보낸 솔더 메시는 보통 밀폐 상태(watertight)입니다. 패드와 접촉하는 위/아래 캡 면을 제거해야 SE가 자유 표면만 진화시킬 수 있습니다.

```
캡 면 판정 기준:
  면의 3개 꼭짓점 모두에 대해 |F(x,y,z)| < tol

  F(x,y,z) = fit.eval_global(vertex)
  → 0이면 표면 위, 양수면 위쪽, 음수면 아래쪽

적응적 공차:
  tol = max(max(fit_bottom.residual_max, fit_top.residual_max) × 3, 1e-4)

  → 피팅 오차의 3배를 사용하여 곡면 위의 점도 정확히 감지
  → 최소 1e-4로 너무 작은 공차 방지
```

양쪽 표면 위에 동시에 있는 면(매우 얇은 솔더)은 무게중심이 더 가까운 쪽에 배정합니다.

**2단계: 캡 면 제거 (`_remove_faces`)**

```
keep_mask = ~(bottom_mask | top_mask)
lateral_mesh = mesh.faces[keep_mask]
→ 미사용 꼭짓점 정리 + 인덱스 재매핑
```

**3단계: 경계 엣지 추출 (`_extract_boundary_loops`)**

캡 면을 제거하면 열린 메시가 되고, 경계 엣지(=면 1개에만 속하는 엣지)가 생깁니다.

```
각 엣지의 인접 면 수 카운팅:
  → count = 2: 내부 엣지 (양쪽 면에 공유)
  → count = 1: 경계 엣지 (한쪽 면만 가짐)
```

**4단계: 엣지 체이닝 (`_chain_edges_into_loops`)**

경계 엣지들을 방향성 있는 닫힌 루프로 연결합니다:

```
인접 딕셔너리 구축: vertex → [(next_vertex, edge_index), ...]
시작점에서 출발 → 미사용 엣지 따라감 → 시작점 도달 → 루프 완성
최소 3개 엣지 이상인 루프만 유효
```

**5단계: 루프 분류 (`_classify_loop`)**

각 루프가 아래쪽 패드인지 위쪽 패드인지 판별:

```
루프의 모든 꼭짓점에 대해:
  mean_dist_bottom = mean(|fit_bottom.eval_global(verts)|)
  mean_dist_top    = mean(|fit_top.eval_global(verts)|)

  → mean_dist_bottom < mean_dist_top → "bottom"
  → mean_dist_top < mean_dist_bottom → "top"
  → 같으면 → "unknown" (경고)
```

**출력**: `ExtractionResult`
- `lateral_mesh`: 열린 측면 메시
- `boundary_loops`: BoundaryLoop 리스트
  - `vertex_ids`: 정렬된 꼭짓점 인덱스
  - `edge_pairs`: (v_start, v_end) 쌍
  - `pad_id`: "bottom" 또는 "top"
  - `constraint_id`: SE 제약 번호
- `n_cap_faces_removed`: 제거된 캡 면 수

### 3.8 MeshToSEConverter (`mesh_to_se.py`) [Phase 7 신규]

**역할**: trimesh 삼각형 메시 → SE 부호 엣지 토폴로지 변환

이 모듈은 가장 기술적으로 까다로운 부분입니다. trimesh의 (vertex, face) 표현을 SE의 (Vertex, Edge, Face, Body) 부호 엣지 표현으로 변환합니다.

```python
converter = MeshToSEConverter(
    tension=480.0,
    density=9.0,
    constraint_bottom_id=1,
    constraint_top_id=2,
)
result = converter.convert(lateral_mesh, boundary_loops, target_volume)
```

**1단계: 꼭짓점 생성 (`_build_vertices`)**

```
경계 루프에 속하는 꼭짓점:
  → Vertex(constraints=[pad_constraint_id], fixed=True)
  → SE에서 제약 표면 위에 고정

나머지 꼭짓점:
  → Vertex() (자유)
  → SE가 에너지 최소화 시 자유롭게 이동
```

**2단계: 유니크 엣지 추출 (`_build_edges`)**

```
모든 삼각형의 3개 엣지를 순회:
  정규 엣지 키: canonical = (min(se_v1, se_v2), max(se_v1, se_v2))

  중복 제거: edge_map[canonical] = edge_id

경계 엣지 판별:
  원본 mesh 좌표의 canonical이 boundary_edges_set에 있으면:
  → Edge(constraints=[pad_constraint_id], fixed=True)

내부 엣지:
  → Edge() (자유)
```

**3단계: 부호 엣지 루프 생성 (`_build_faces`)**

```
삼각형 (A, B, C)의 각 변:

  변 A→B:
    se_v1 = vertex_map[A]
    se_v2 = vertex_map[B]
    canonical = (min(se_v1, se_v2), max(se_v1, se_v2))
    edge_id = edge_map[canonical]

    부호 결정:
      se_v1 < se_v2 → +edge_id  (정방향 = 정규 방향)
      se_v1 > se_v2 → -edge_id  (역방향)

  Face(edges=[±e1, ±e2, ±e3])
```

이 알고리즘의 핵심: **정규 방향(canonical direction)**은 `(min, max)` 순서이고, 삼각형이 이 방향과 같은 방향으로 엣지를 순회하면 `+`, 반대면 `-`입니다.

**4단계: 법선 방향 일관성 확인 (`_ensure_consistent_orientation`)**

```
무게중심(centroid) → 각 면 중심까지의 벡터 to_face
면 법선 face_normals와 내적:
  dot > 0 → 외향 (정상)
  dot < 0 → 내향 (뒤집어야 함)

과반수가 내향이면 모든 면의 엣지 부호를 반전:
  face.edges = [-e for e in reversed(face.edges)]
```

**5단계: 체적 추정 (`_estimate_volume`)**

```
밀폐 메시 → abs(mesh.volume) (정확)
열린 메시 → bounding box 체적 × 0.4 (근사)
→ SE의 체적 제약이 실제 체적을 강제하므로 초기 추정의 정확도는 부차적
```

**출력**: `SETopologyResult`
- `geometry`: InitialGeometry (Vertex/Edge/Face/Body 리스트)
- `vertex_map`: trimesh 인덱스 → SE ID
- `edge_map`: canonical 쌍 → SE edge ID
- `boundary_vertex_ids`: 패드별 경계 꼭짓점 SE ID 집합
- `boundary_edge_ids`: 패드별 경계 엣지 SE ID 집합
- `computed_volume`: 계산된/지정된 체적

### 3.9 ComplexSTLPipeline (`complex_pipeline.py`) [Phase 7 신규]

**역할**: 3개 STL → .fe 파일 전체 오케스트레이션

```python
config = ComplexPipelineConfig(
    tension=480.0,          # 표면장력 (erg/cm²)
    density=9.0,            # 솔더 밀도 (g/cm³)
    gravity=980.0,          # 중력가속도 (cm/s²)
    contact_angle_bottom=30.0,  # 아래 패드 접촉각 (도)
    contact_angle_top=30.0,     # 위 패드 접촉각 (도)
    smooth_iterations=0,    # 스무딩 반복 수
    max_edge_length=0.0,    # 엣지 분할 임계값
    target_volume=None,     # 지정 체적 (None=자동 추정)
    joint_name="joint_1",   # .fe 파일 내 이름
)

pipeline = ComplexSTLPipeline(config)
fe_path = pipeline.run(
    bottom_pad_stl="bottom.stl",
    top_pad_stl="top.stl",
    solder_stl="solder.stl",
    output_path="output/joint.fe",
    center_bottom=None,     # None=자동 감지
    center_top=None,
)
```

**전체 실행 흐름**:

```
1. 솔더 메시 로딩 (trimesh.load)
       ↓
2. 메시 전처리 (MeshPreprocessor)
   └─ 퇴화 삼각형 제거 + 법선 수정 + [스무딩] + [세분화]
       ↓
3. 패드 중심 자동 감지
   └─ 솔더 bounding box의 XY 중점 → bottom z_min, top z_max
       ↓
4. 패드 추출 반경 추정
   └─ 솔더 꼭짓점의 XY 최대 거리 × 1.1 (10% 마진)
       ↓
5. 패드 표면 피팅
   ├─ STLReader.extract_patch(center, radius × 1.5)
   └─ SurfaceFitter.fit(patch) → SurfaceFitResult
       ↓
6. 경계 추출
   ├─ BoundaryExtractor(fit_bottom, fit_top)
   └─ .extract(solder_mesh) → lateral_mesh + boundary_loops
       ↓
7. SE 토폴로지 변환
   ├─ MeshToSEConverter(tension, density)
   └─ .convert(lateral_mesh, boundary_loops) → InitialGeometry
       ↓
8. 제약식 생성
   ├─ ConstraintGenerator.generate_surface_constraint(use_boundary_integrals=True)
   └─ 양쪽 패드 모두: CONSTRAINT + energy + content
       ↓
9. .fe 파일 출력
   └─ FEWriter.write_single(geometry, [c_bottom, c_top], [], config)
```

---

## 4. 파이프라인 흐름도

### 4.1 Standard Pipeline (파라미터 입력)

```
┌─────────────┐   ┌─────────────┐
│ 원형 패드    │   │ 사각 패드    │
│ (center, r)  │   │ (center, s) │
└──────┬──────┘   └──────┬──────┘
       │                  │
       ▼                  ▼
  generate_flat_     generate_square_
  pad_stl()          pad_stl()
       │                  │
       ▼                  ▼
  STLReader.extract_patch()
       │
       ▼
  SurfaceFitter.fit()
       │
       ▼
  ConstraintGenerator
  ├─ 원형: generate_surface_constraint()
  │        generate_rim_constraint()
  │        generate_parametric_boundary()
  └─ 사각: generate_surface_constraint(use_boundary_integrals=True) ×2
       │
       ▼
  GeometryBuilder
  ├─ 원형: build()
  └─ 사각: build_rectangular()
       │
       ▼
  FEWriter.write_single()
       │
       ▼
  ┌──────────┐
  │ joint.fe │
  └──────────┘
```

### 4.2 Complex STL Pipeline (CAD 입력)

```
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│ bottom_pad.stl│ │  top_pad.stl  │ │  solder.stl   │
└───────┬───────┘ └───────┬───────┘ └───────┬───────┘
        │                 │                  │
        ▼                 ▼                  ▼
   STLReader         STLReader        MeshPreprocessor
   extract_patch()   extract_patch()    preprocess()
        │                 │                  │
        ▼                 ▼                  │
   SurfaceFitter     SurfaceFitter          │
   fit()             fit()                   │
        │                 │                  │
        └────────┬────────┘                  │
                 │                           │
                 ▼                           ▼
          BoundaryExtractor  ◄────── solder_mesh
          extract()
                 │
         ┌───────┴───────┐
         │               │
    lateral_mesh    boundary_loops
         │               │
         └───────┬───────┘
                 │
                 ▼
          MeshToSEConverter
          convert()
                 │
                 ▼
          InitialGeometry
         (Vertex/Edge/Face/Body)
                 │
                 ▼
          ConstraintGenerator ×2
         (use_boundary_integrals=True)
                 │
                 ▼
          FEWriter.write_single()
                 │
                 ▼
          ┌──────────┐
          │ joint.fe │
          └──────────┘
```

---

## 5. 수학 공식 정리

### 5.1 좌표 변환

전역 좌표 (x, y, z) → 로컬 좌표 (u, v, w):

```
[u]         [x - cx]
[v] = R  ×  [y - cy]
[w]         [z - cz]
```

여기서 R = [u̅, v̅, n̅]ᵀ (3×3 직교 행렬), (cx, cy, cz)는 패치 중심.

### 5.2 곡면 피팅 다항식

**평면 (3 계수)**:
```
w = c₀ + c₁u + c₂v
```

**2차 (6 계수)**:
```
w = c₀ + c₁u + c₂v + c₃u² + c₄uv + c₅v²
```

**4차 (15 계수)**:
```
w = c₀ + c₁u + c₂v + c₃u² + c₄uv + c₅v²
  + c₆u³ + c₇u²v + c₈uv² + c₉v³
  + c₁₀u⁴ + c₁₁u³v + c₁₂u²v² + c₁₃uv³ + c₁₄v⁴
```

**암묵적 형태**:
```
F(x,y,z) = w - f(u,v) = 0

여기서 (u,v,w) = R × (P - C)이므로:

F(x,y,z) = [n̅·(P-C)] - f([u̅·(P-C)], [v̅·(P-C)])
```

### 5.3 에너지 경계 적분

SE에서 경계 적분은 3D Green 정리(Stokes 정리)의 적용입니다.

**접촉 에너지**:
```
E_contact = -σ·cos(θ) · A_wetted

Green 정리에 의해:
A_wetted = ∫∫_Ω dA = ∮_∂Ω x dy dz    (Ω: 패드 위의 젖음 영역)

→ SE 형식:
e2 = -σ·cos(θ)·x  (y방향 적분의 x 성분)
```

**중력 에너지 (경계 위)**:
```
E_gravity_cap = ρ·g · ∫∫∫_cap z dV

발산 정리:
∫∫∫ z dV = ∮ (1/2)·x·z² dy dz  (적절한 벡터장 선택)

→ SE 형식:
e2 += (1/2)·G·ρ·x·z²
```

**체적 보정**:
```
V_cap = ∫∫∫_cap dV

발산 정리:
∫∫∫ dV = (1/3) ∮ x⃗·n̂ dA

z방향 성분만:
∫∫ z dA = ∮ x·z dy dz

→ SE 형식:
c2 = x·z  (양의 부호: 경계 엣지가 body에서 음수로 나타나므로)
```

### 5.4 부호 엣지 알고리즘

**정규 엣지 정의**:
```
주어진 엣지 (v1, v2):
  canonical = (min(v1, v2), max(v1, v2))

edge_map[canonical] = edge_id
```

**삼각형의 부호 엣지 결정**:
```
삼각형 (A, B, C)에서 변 A→B:
  se_A = vertex_map[A]
  se_B = vertex_map[B]

  if se_A < se_B:
    signed_edge = +edge_map[(se_A, se_B)]    // 정방향
  else:
    signed_edge = -edge_map[(se_B, se_A)]    // 역방향
```

**일관성 검증**:
```
내부 엣지: 정확히 2개의 면에 나타남 (한번은 +, 한번은 -)
경계 엣지: 정확히 1개의 면에 나타남
```

### 5.5 오일러 특성

열린 곡면의 토폴로지 검증:
```
χ = V - E + F

원통형 (경계 2개): χ = 0
원판형 (경계 1개): χ = 1
구면 (경계 0개):   χ = 2
```

### 5.6 메시 품질 지표

```
종횡비 (Aspect Ratio):
  AR = L_max / (2·r_in)
  r_in = A / s  (내접원 반경 = 면적 / 반둘레)
  목표: AR ≤ 3.0

비대칭도 (Skewness):
  S = 1 - θ_min / 60°
  목표: S ≤ 0.7

각도 범위:
  목표: 20° ≤ θ ≤ 120°
```

---

## 6. 활용 가능 범위

### 6.1 지원되는 패드 형상

| 형상 | Standard Pipeline | Complex STL Pipeline |
|---|---|---|
| 원형 (평면) | O | O |
| 사각형 (평면) | O | O |
| 타원형 | X | O |
| L자형 | X | O |
| 다각형 | X | O |
| 곡면 (2차) | O (피팅) | O (피팅) |
| 곡면 (4차) | O (피팅) | O (피팅) |
| 임의 곡면 | X | O (4차까지 피팅) |

### 6.2 지원되는 솔더 초기 형상

| 형상 | Standard Pipeline | Complex STL Pipeline |
|---|---|---|
| 원기둥 | O (자동 생성) | O (STL 입력) |
| 프리즘 | O (자동 생성) | O (STL 입력) |
| 배럴형 | X | O (STL 입력) |
| 모래시계형 | X | O (STL 입력) |
| 임의 형상 | X | O (STL 입력) |

### 6.3 물리 파라미터 범위

| 파라미터 | 일반 범위 | 단위 | 비고 |
|---|---|---|---|
| 표면장력 σ | 400~550 | erg/cm² | SAC305: ~480 |
| 밀도 ρ | 7.0~9.0 | g/cm³ | SAC305: ~8.5 |
| 중력 g | 0~980 | cm/s² | 0: 무중력 해석 |
| 접촉각 θ | 5°~90° | 도 | 재질/표면처리 의존 |
| 체적 V | 1e-8~1e-2 | cm³ | 패드 크기 의존 |

### 6.4 실용 패키지 유형

| 유형 | 패드 크기 | 피치 | 적합 파이프라인 |
|---|---|---|---|
| BGA (0.3mm 볼) | r = 0.013 cm | 0.05 cm | Standard (원형) |
| BGA (0.5mm 볼) | r = 0.020 cm | 0.08 cm | Standard (원형) |
| QFN 패드 | 0.03×0.06 cm | 다양 | Standard (사각) |
| CSP | r = 0.010 cm | 0.04 cm | Standard (원형) |
| SiP 복합 패드 | 불규칙 | - | Complex STL |
| 3D 패키징 | 곡면 | - | Complex STL |
| MEMS 구조 | 임의 | - | Complex STL |

### 6.5 다중 조인트

| 기능 | 지원 | 구현 |
|---|---|---|
| 단일 조인트 | O | `FEWriter.write_single()` |
| 다중 조인트 (독립) | O | `batch/parallel_runner.py` |
| 다중 조인트 (커플링) | O | `FEWriter.write_coupled()` |
| 20×20 어레이 (400개) | O (테스트 완료) | 파라미터 sweep |

### 6.6 결과 내보내기

| 포맷 | 모듈 | 용도 |
|---|---|---|
| STL | `mesh/exporters/stl_export.py` | 시각화, 3D 프린팅 |
| VTK | `mesh/exporters/vtk_export.py` | ParaView 시각화 |
| GMSH | `mesh/exporters/gmsh_export.py` | 후속 FEM 해석 |
| ANSYS | `mesh/exporters/ansys_export.py` | 열-구조 해석 |
| LS-DYNA | `mesh/exporters/lsdyna_export.py` | 낙하 충격 해석 |

---

## 7. 사용 예제

### 7.1 Standard Pipeline: 원형 패드 BGA

```python
import numpy as np
from kse.core.stl_reader import STLReader
from kse.core.surface_fitter import SurfaceFitter
from kse.core.constraint_gen import ConstraintGenerator
from kse.core.geometry_builder import GeometryBuilder
from kse.core.fe_writer import FEWriter, SolderJointConfig

# 패드 STL 로딩 + 패치 추출
reader_bot = STLReader("bottom_pad.stl")
reader_top = STLReader("top_pad.stl")
patch_bot = reader_bot.extract_patch(center=np.array([0, 0, 0]), radius=0.015)
patch_top = reader_top.extract_patch(center=np.array([0, 0, 0.005]), radius=0.015)

# 곡면 피팅
fitter = SurfaceFitter()
fit_bot = fitter.fit(patch_bot)
fit_top = fitter.fit(patch_top)

# 제약식 생성
cgen = ConstraintGenerator()
c_bot = cgen.generate_surface_constraint(fit_bot, 1, contact_angle=30.0)
c_top = cgen.generate_surface_constraint(fit_top, 2, contact_angle=30.0,
                                          use_boundary_integrals=False)
rim = cgen.generate_rim_constraint(fit_bot, 3, radius=0.013)
bdry = cgen.generate_parametric_boundary(fit_top, 1, radius=0.013)

# 초기 형상 생성
builder = GeometryBuilder(n_segments=8)
volume = 3.14159 * 0.013**2 * 0.005  # 원기둥 체적
geom = builder.build(fit_bot, fit_top, radius=0.013, volume=volume)

# .fe 파일 출력
config = SolderJointConfig(tension=480, density=9.0, gravity=980,
                           radius=0.013, volume=volume)
writer = FEWriter()
writer.write_single("bga_joint.fe", geom, [c_bot, c_top, rim], [bdry], config)
```

### 7.2 Standard Pipeline: 사각 패드

```python
# 제약식: 양쪽 모두 boundary_integrals
c_bot = cgen.generate_surface_constraint(fit_bot, 1, contact_angle=30.0,
                                          use_boundary_integrals=True)
c_top = cgen.generate_surface_constraint(fit_top, 2, contact_angle=30.0,
                                          use_boundary_integrals=True)

# 사각 형상 생성
geom = builder.build_rectangular(fit_bot, fit_top,
                                  side_x=0.03, side_y=0.06,
                                  volume=0.03*0.06*0.005)

# .fe 파일: 경계(boundary) 없음, 제약(constraint)만
writer.write_single("qfn_joint.fe", geom, [c_bot, c_top], [], config)
```

### 7.3 Complex STL Pipeline: CAD 솔더

```python
from kse.core.complex_pipeline import ComplexSTLPipeline, ComplexPipelineConfig

config = ComplexPipelineConfig(
    tension=480.0,
    density=9.0,
    gravity=980.0,
    contact_angle_bottom=30.0,
    contact_angle_top=30.0,
    smooth_iterations=2,       # CAD 메시 스무딩
    target_volume=None,        # 자동 추정
    joint_name="sip_joint_1",
)

pipeline = ComplexSTLPipeline(config)
fe_path = pipeline.run(
    bottom_pad_stl="cad_exports/bottom_pad.stl",
    top_pad_stl="cad_exports/top_pad.stl",
    solder_stl="cad_exports/solder_initial.stl",
    output_path="output/sip_joint.fe",
)

print(f"Generated: {fe_path}")
# → output/sip_joint.fe
# → Surface Evolver로 실행: evolver -p1 sip_joint.fe
#   SE 내에서: gogo; gomore; dump "result.dmp";
```

### 7.4 SE 결과 해석

```python
from kse.solver.dump_parser import DumpParser

parser = DumpParser()
mesh = parser.parse("result.dmp")

print(f"Total energy: {mesh.total_energy:.6e} erg")
for bid, body in mesh.bodies.items():
    print(f"Body {bid}: volume = {body.actual_volume:.6e} cm³")

# 꼭짓점 좌표 → NumPy 배열
vertices = mesh.vertex_array  # (N, 3)
triangles = mesh.face_triangles  # (M, 3) — 전체 면
free_triangles = mesh.free_face_triangles  # 자유 표면만
```

### 7.5 개별 모듈 단독 사용

**경계 추출만**:
```python
from kse.core.boundary_extractor import BoundaryExtractor
import trimesh

solder = trimesh.load("solder.stl", force="mesh")
extractor = BoundaryExtractor(fit_bottom=fit_b, fit_top=fit_t)
result = extractor.extract(solder)

print(f"캡 면 제거: {result.n_cap_faces_removed}개")
print(f"경계 루프: {len(result.boundary_loops)}개")
for loop in result.boundary_loops:
    print(f"  {loop.pad_id}: {len(loop.vertex_ids)} 꼭짓점")
```

**SE 토폴로지 변환만**:
```python
from kse.core.mesh_to_se import MeshToSEConverter

converter = MeshToSEConverter(tension=480.0, density=9.0)
result = converter.convert(lateral_mesh, boundary_loops)

print(f"SE vertices: {len(result.geometry.vertices)}")
print(f"SE edges:    {len(result.geometry.edges)}")
print(f"SE faces:    {len(result.geometry.faces)}")
print(f"Volume:      {result.computed_volume:.6e} cm³")
```

**메시 품질 평가만**:
```python
from kse.mesh.quality import assess_quality

report = assess_quality(mesh.vertices, mesh.faces)
print(report.summary())
# Mesh Quality [PASS]
#   Triangles: 256
#   Aspect ratio: mean=1.23, max=2.15
#   Angles: min=28.3°, max=101.2°
#   Skewness: mean=0.120, max=0.528
#   Degenerate faces: 0
```

---

## 8. 검증 결과

### 8.1 테스트 현황

| Phase | 테스트 수 | 내용 | 상태 |
|---|---|---|---|
| Phase 0-4 | 60 | STL reader, fitter, constraint, geometry, FE writer | PASS |
| Phase 6 | 41 | 실용 예제 (원형/사각, SMD/NSMD, 배열, SE 수렴) | PASS |
| Phase 7 | 26 | Complex STL (캡 감지, 경계 추출, SE 변환, 파이프라인) | PASS |
| **합계** | **127** | | **ALL PASS** |

### 8.2 Phase 7 테스트 상세

| 테스트 클래스 | 항목 수 | 검증 내용 |
|---|---|---|
| TestCapDetection | 3 | 밀폐 원통 캡 감지, 열린 원통 감지 없음, 배럴형 캡 감지 |
| TestBoundaryExtraction | 3 | 루프 2개, 꼭짓점 수 일치, 제약 ID 할당 |
| TestMeshToSEConversion | 6 | 꼭짓점/면/엣지 수, 오일러 특성, 부호 일관성, 경계 고정 |
| TestComplexPipelineSimple | 5 | 원통/배럴/모래시계 .fe 생성, 적분 포함, 사각 패드 |
| TestComplexPipelineSE | 3 | SE 수렴 (원통/배럴/모래시계) |
| TestIrregularBoundary | 3 | 타원/삼엽 .fe 생성, 타원 SE 수렴 |
| TestPreprocessor | 2 | 클린 메시 통과, 스무딩 적용 |
| TestDiagnosticSummary | 1 | 전체 형상 요약 테이블 |

### 8.3 SE 수렴 확인된 형상

| 형상 | 에너지 수렴 | 체적 보존 | 비고 |
|---|---|---|---|
| 원형 패드 + 원기둥 | O | < 5% | Standard Pipeline |
| 사각 패드 + 프리즘 | O | < 5% | Standard Pipeline |
| 원형 패드 + 원통 (STL) | O | O | Complex Pipeline |
| 원형 패드 + 배럴 (STL) | O | O | Complex Pipeline |
| 원형 패드 + 모래시계 (STL) | O | O | Complex Pipeline |
| 원형 패드 + 타원 (STL) | O | O | Complex Pipeline |
| 사각 패드 + 원통 (STL) | O | O | Complex Pipeline |

### 8.4 알려진 제한사항

1. **곡면 피팅**: 최대 4차 다항식. 이보다 복잡한 곡면은 국소 패치 크기를 줄여야 함.
2. **경계 루프**: 패드당 1개 루프만 지원. 여러 개(구멍 있는 패드)는 미지원.
3. **밀폐 여부**: 솔더 STL이 밀폐가 아니면 캡 감지를 건너뛰고 기존 경계 사용.
4. **체적 추정**: 열린 메시의 체적은 bounding box × 0.4로 근사. 정확한 체적은 사용자 지정 필요.
5. **메시 밀도**: 매우 고밀도 CAD 메시(10만+ 면)는 SE 실행이 느릴 수 있음. `max_edge_length` 대신 decimation이 필요할 수 있음.
6. **접촉각**: 현재 패드당 단일 접촉각. 위치 의존 접촉각은 미지원.
