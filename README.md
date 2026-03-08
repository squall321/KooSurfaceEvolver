# KSE (KooSurfaceEvolver)

STL/STEP 기반 솔더 조인트 형상 시뮬레이션 및 FEA 메시 생성 도구.

Surface Evolver 엔진을 사용하여 표면장력, 중력, 접촉각 조건에서 솔더 조인트의 최소 에너지 평형 형상을 계산합니다.

## Features

- **자동 파이프라인**: STL/STEP 패드 입력 → Surface Evolver .fe 생성 → 시뮬레이션 → 결과 메시 출력
- **다양한 패드 형상**: BGA (원형), LGA (직사각형), QFN, WLCSP, MLCC 필렛
- **FEA 체적 메시 출력**: TET4 사면체 (LS-DYNA .k, ANSYS .cdb, Gmsh .msh, VTK)
- **표면 메시 출력**: STL, VTK
- **STEP 조립체**: 단일/배열/브릿지/커플 조인트 자동 생성
- **배치 처리**: 병렬 독립 조인트, 커플 조인트
- **YAML 설정**: 파라메트릭 스윕 지원

---

## Requirements

- **Python 3.12+**
- **OS**: Windows 10/11, Linux (Ubuntu 20.04+)

---

## Windows 설치 (권장)

### 1. Python 설치

[Python 3.12+](https://www.python.org/downloads/) 다운로드 및 설치.
**반드시 "Add Python to PATH" 체크**.

### 2. 저장소 클론

```cmd
git clone https://github.com/squall321/KooSurfaceEvolver.git
cd KooSurfaceEvolver
```

### 3. 자동 설치

```cmd
install_windows.bat
```

이 스크립트가 자동으로:
- `.venv` 가상환경 생성
- 기본 의존성 설치 (numpy, scipy, trimesh, etc.)
- KSE 패키지 설치
- FEA/STEP 옵션 의존성 설치 여부 질문

### 4. 사용

```cmd
.venv\Scripts\activate.bat
kse run --help
```

---

## Windows 빌드 (독립 실행파일)

독립 실행파일(.exe)을 빌드하면 Python 설치 없이 다른 PC에서 사용 가능합니다.

```cmd
build.bat
```

빌드 결과: `dist\kse\kse.exe`

### 빌드 요구사항

- PyInstaller (build.bat이 자동 설치)
- (선택) [Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) - C 확장 컴파일용
  - 없으면 자동으로 순수 Python fallback 사용

---

## Linux 설치

```bash
git clone https://github.com/squall321/KooSurfaceEvolver.git
cd KooSurfaceEvolver
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

빌드: `bash build.sh`

---

## 수동 설치 (고급)

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
pip install -e .

REM FEA 체적 메시 (선택)
pip install -r requirements-fea.txt

REM STEP/CAD 지원 (선택)
pip install cadquery>=2.3
```

---

## 사용법

### CLI 명령어

```
kse <command> [options]

Commands:
  run        단일 솔더 조인트 시뮬레이션
  batch      병렬 독립 조인트 시뮬레이션
  coupled    상호작용 조인트 시뮬레이션
  validate   기준 예제 검증
  yaml       YAML 설정 파일로 실행
```

### 단일 조인트 실행 예시

```cmd
kse run --stl-a bottom.stl --stl-b top.stl ^
        --center-a 0,0,0 --center-b 0,0,0.05 ^
        --radius 0.025 --volume 1.5e-5 ^
        --format stl,lsdyna ^
        --output results
```

### YAML 설정 예시

```cmd
kse yaml config.yaml
kse yaml config.yaml --sweep     # 파라메트릭 스윕
kse yaml config.yaml --dry-run   # .fe 생성만
```

### 출력 형식

| 형식 | 플래그 | 설명 |
|------|--------|------|
| STL | `stl` | 표면 삼각형 메시 (ASCII) |
| STL Binary | `stl_bin` | 표면 삼각형 메시 (바이너리) |
| VTK | `vtk` | 표면 메시 (ParaView) |
| LS-DYNA | `lsdyna` | TET4 체적 메시 (.k) |
| ANSYS | `ansys` | TET4 체적 메시 (.cdb, SOLID285) |
| Gmsh | `gmsh` | TET4 체적 메시 (.msh) |
| VTK Solid | `vtk_solid` | TET4 체적 메시 (.vtk) |

### Surface Evolver 옵션

```cmd
--refine-steps N     메시 세분화 횟수 (기본: 5, 높을수록 정밀)
--contact-angle DEG  접촉각 (도)
--tension VALUE      표면장력 (erg/cm^2)
--gravity VALUE      중력 가속도 (cm/s^2)
```

---

## 프로젝트 구조

```
KooSurfaceEvolver/
├── cli.py                  # CLI 진입점
├── setup.py                # 패키지 설정
├── kse.spec                # PyInstaller 빌드 스펙
├── install_windows.bat     # Windows 자동 설치
├── build.bat               # Windows 빌드
├── build.sh                # Linux 빌드
├── requirements.txt        # 기본 의존성
├── requirements-fea.txt    # FEA 의존성 (선택)
│
├── kse/                    # 메인 패키지
│   ├── core/               # 파이프라인: STL→FEWriter
│   ├── solver/             # SE 실행 및 결과 파싱
│   ├── batch/              # 배치/커플 시뮬레이션
│   ├── mesh/               # 체적 메시 및 FEA 내보내기
│   │   ├── volume_mesher.py
│   │   ├── quality.py
│   │   └── exporters/      # STL, VTK, Gmsh, ANSYS, LS-DYNA
│   └── config/             # YAML 설정
│
├── src/
│   ├── evolver             # SE 바이너리 (Linux)
│   └── evolver.exe         # SE 바이너리 (Windows)
│
├── templates/              # Jinja2 .fe 템플릿
├── examples/               # 예제 .fe 파일 및 설정
│   ├── configs/            # YAML 설정 예제
│   └── lsdyna_k/           # LS-DYNA .k 출력 예제
│
└── tests/                  # 테스트
    ├── test_core.py
    └── validation/
```

---

## 의존성

### 기본 (필수)

| 패키지 | 용도 |
|--------|------|
| numpy | 수치 연산 |
| scipy | 최적화, 공간 연산 |
| trimesh | 메시 처리 |
| rtree | 공간 인덱싱 |
| jinja2 | .fe 템플릿 렌더링 |
| sympy | 적분 공식 생성 |
| pyyaml | YAML 설정 파싱 |

### FEA 체적 메시 (선택)

| 패키지 | 용도 |
|--------|------|
| tetgen | 사면체 메시 생성 |
| pymeshfix | 비다양체 메시 복구 |
| pyvista | pymeshfix 의존 |
| networkx | 메시 법선 수정 |

### STEP/CAD (선택)

| 패키지 | 용도 |
|--------|------|
| cadquery | STEP 파일 읽기/생성 |

---

## 테스트

```cmd
.venv\Scripts\activate.bat
pip install pytest
pytest tests/ -v
```

---

## API 참조

자세한 API 문서는 [KSE_API_REFERENCE.md](KSE_API_REFERENCE.md) 참조.

---

## License

Surface Evolver v2.70a by Ken Brakke.
KSE wrapper by squall321.
