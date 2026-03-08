#!/bin/bash
# KSE (KooSurfaceEvolver) Standalone Build Script — Linux
# Output: dist/kse/
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== KSE Standalone Build (Linux) ==="

# Check Python
python3 --version || { echo "ERROR: python3 not found"; exit 1; }

# Install PyInstaller if needed
pip install pyinstaller 2>/dev/null || pip install --user pyinstaller

# Ensure dependencies
pip install -e ".[step]" 2>/dev/null || true

# Make SE binary executable
chmod +x src/evolver 2>/dev/null || true

# Build
echo "Building standalone binary..."
pyinstaller kse.spec --clean --noconfirm

echo ""
echo "=== Build Complete ==="
echo "Output: dist/kse/"
echo "Run:    ./dist/kse/kse --help"
echo ""

# Quick smoke test
if [ -f dist/kse/kse ]; then
    echo "Smoke test: kse --help"
    ./dist/kse/kse --help | head -5
    echo "... OK"
fi
