@echo off
REM KSE (KooSurfaceEvolver) Standalone Build Script — Windows
REM Output: dist\kse\

echo === KSE Standalone Build (Windows) ===

REM Check Python
python --version || (echo ERROR: python not found & exit /b 1)

REM Install PyInstaller if needed
pip install pyinstaller 2>NUL

REM Ensure dependencies
pip install -e ".[step]" 2>NUL

REM Build
echo Building standalone binary...
pyinstaller kse.spec --clean --noconfirm

echo.
echo === Build Complete ===
echo Output: dist\kse\
echo Run:    dist\kse\kse.exe --help
echo.

REM Quick smoke test
if exist dist\kse\kse.exe (
    echo Smoke test: kse --help
    dist\kse\kse.exe --help
)
