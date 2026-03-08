@echo off
REM ============================================================
REM  KSE (KooSurfaceEvolver) - Windows Installation Script
REM  Creates virtual environment and installs all dependencies.
REM ============================================================
setlocal enabledelayedexpansion

echo.
echo ============================================================
echo  KSE (KooSurfaceEvolver) - Windows Setup
echo ============================================================
echo.

REM ── Check Python ────────────────────────────────────────────
where python >NUL 2>NUL
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    echo Please install Python 3.12+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo Found Python %PYVER%

REM ── Create virtual environment ──────────────────────────────
if not exist ".venv" (
    echo.
    echo Creating virtual environment (.venv^)...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Virtual environment created.
) else (
    echo Virtual environment (.venv^) already exists.
)

REM ── Activate venv ───────────────────────────────────────────
echo Activating virtual environment...
call .venv\Scripts\activate.bat

REM ── Upgrade pip ─────────────────────────────────────────────
echo.
echo Upgrading pip...
python -m pip install --upgrade pip

REM ── Install base dependencies ───────────────────────────────
echo.
echo Installing base dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install base dependencies.
    pause
    exit /b 1
)

REM ── Install KSE package (editable) ─────────────────────────
echo.
echo Installing KSE package (editable mode^)...
pip install -e .
if errorlevel 1 (
    echo WARNING: Editable install failed (C compiler may be missing^).
    echo Trying without C extensions...
    set KSE_BUILD_C_EXT=0
    pip install -e .
)

REM ── Optional: FEA dependencies ──────────────────────────────
echo.
set /p INSTALL_FEA="Install FEA volume mesh dependencies (tetgen, pymeshfix)? [y/N]: "
if /i "!INSTALL_FEA!"=="y" (
    echo Installing FEA dependencies...
    pip install -r requirements-fea.txt
    if errorlevel 1 (
        echo WARNING: Some FEA dependencies failed to install.
        echo You can install them manually later: pip install -r requirements-fea.txt
    ) else (
        echo FEA dependencies installed successfully.
    )
)

REM ── Optional: STEP dependencies ─────────────────────────────
echo.
set /p INSTALL_STEP="Install STEP/CAD dependencies (cadquery)? [y/N]: "
if /i "!INSTALL_STEP!"=="y" (
    echo Installing CadQuery (this may take a few minutes^)...
    pip install cadquery>=2.3
    if errorlevel 1 (
        echo WARNING: CadQuery installation failed.
        echo You can install it manually later: pip install cadquery
    ) else (
        echo CadQuery installed successfully.
    )
)

REM ── Verify installation ─────────────────────────────────────
echo.
echo ============================================================
echo  Verifying installation...
echo ============================================================
python -c "import kse; print('  kse package: OK')" 2>NUL || echo   kse package: FAILED
python -c "import numpy; print('  numpy:', numpy.__version__)" 2>NUL || echo   numpy: FAILED
python -c "import scipy; print('  scipy:', scipy.__version__)" 2>NUL || echo   scipy: FAILED
python -c "import trimesh; print('  trimesh:', trimesh.__version__)" 2>NUL || echo   trimesh: FAILED
python -c "import jinja2; print('  jinja2:', jinja2.__version__)" 2>NUL || echo   jinja2: FAILED
python -c "import sympy; print('  sympy:', sympy.__version__)" 2>NUL || echo   sympy: FAILED
python -c "import tetgen; print('  tetgen: OK (FEA ready)')" 2>NUL || echo   tetgen: not installed (optional)
python -c "import cadquery; print('  cadquery: OK (STEP ready)')" 2>NUL || echo   cadquery: not installed (optional)

REM ── Check SE binary ─────────────────────────────────────────
echo.
if exist "src\evolver.exe" (
    echo  Surface Evolver binary: src\evolver.exe (OK^)
) else (
    echo  WARNING: src\evolver.exe not found!
    echo  The Surface Evolver binary is required for simulation.
)

echo.
echo ============================================================
echo  Installation complete!
echo ============================================================
echo.
echo  Usage:
echo    .venv\Scripts\activate.bat       (activate environment)
echo    kse run --help                   (see CLI options)
echo    python cli.py run --help         (alternative)
echo.
echo  Build standalone .exe:
echo    build.bat
echo.
pause
