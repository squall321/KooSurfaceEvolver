@echo off
REM ============================================================
REM  KSE (KooSurfaceEvolver) Standalone Build Script - Windows
REM  Output: dist\kse\  (directory with kse.exe)
REM ============================================================
setlocal enabledelayedexpansion

echo.
echo ============================================================
echo  KSE Standalone Build (Windows)
echo ============================================================
echo.

REM ── Check Python ────────────────────────────────────────────
where python >NUL 2>NUL
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    echo Install Python 3.12+ from https://www.python.org/downloads/
    pause
    exit /b 1
)
python --version

REM ── Activate venv if available ──────────────────────────────
if exist ".venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call .venv\Scripts\activate.bat
) else (
    echo WARNING: No .venv found. Using system Python.
    echo Run install_windows.bat first to set up the environment.
    echo.
)

REM ── Install PyInstaller ─────────────────────────────────────
pip show pyinstaller >NUL 2>NUL
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller
    if errorlevel 1 (
        echo ERROR: Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

REM ── Ensure base dependencies ────────────────────────────────
echo.
echo Checking dependencies...
pip install -r requirements.txt >NUL 2>NUL
pip install -e . >NUL 2>NUL

REM ── Check SE binary ─────────────────────────────────────────
if not exist "src\evolver.exe" (
    echo.
    echo WARNING: src\evolver.exe not found!
    echo The standalone build will not include the Surface Evolver binary.
    echo.
)

REM ── Build ───────────────────────────────────────────────────
echo.
echo Building standalone executable...
echo This may take several minutes...
echo.
pyinstaller kse.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo ERROR: Build failed!
    echo.
    echo Common fixes:
    echo   1. Run install_windows.bat first
    echo   2. Install Visual C++ Build Tools for C extensions
    echo   3. Check that all dependencies are installed
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Build Complete!
echo ============================================================
echo.
echo  Output:  dist\kse\
echo  Run:     dist\kse\kse.exe --help
echo.

REM ── Smoke test ──────────────────────────────────────────────
if exist "dist\kse\kse.exe" (
    echo Smoke test...
    dist\kse\kse.exe --help > NUL 2>&1
    if errorlevel 1 (
        echo WARNING: Smoke test failed. The build may have issues.
    ) else (
        echo Smoke test: OK
    )
) else (
    echo WARNING: kse.exe not found in dist\kse\
)

echo.
pause
