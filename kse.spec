# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for KSE (KooSurfaceEvolver) standalone build.

Build:
  Linux:   bash build.sh
  Windows: build.bat

Output: dist/kse/  (onedir mode)
"""

import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# ── Data files to bundle ───────────────────────────────────────────
datas = [
    ('templates/*.j2', 'templates'),
    ('examples/configs/*.yaml', 'examples/configs'),
    ('KSE_API_REFERENCE.md', '.'),
]

# Platform-specific SE binary
if sys.platform == 'win32':
    if os.path.exists('src/evolver.exe'):
        datas.append(('src/evolver.exe', 'src'))
else:
    if os.path.exists('src/evolver'):
        datas.append(('src/evolver', 'src'))

# ── Hidden imports (lazy imports in cli.py) ────────────────────────
hiddenimports = [
    # KSE internal modules (imported lazily in cli.py handlers)
    'kse.core.step_pipeline',
    'kse.core.complex_pipeline',
    'kse.core.stl_reader',
    'kse.core.surface_fitter',
    'kse.core.constraint_gen',
    'kse.core.geometry_builder',
    'kse.core.fe_writer',
    'kse.core.boundary_extractor',
    'kse.core.mesh_preprocessor',
    'kse.core.mesh_to_se',
    'kse.core.step_reader',
    'kse.core.units',
    'kse.solver.evolver_runner',
    'kse.solver.dump_parser',
    'kse.solver.evolution_scripts',
    'kse.solver.result_analyzer',
    'kse.batch.parallel_runner',
    'kse.batch.coupled_runner',
    'kse.batch.job_manager',
    'kse.batch.sweep_runner',
    'kse.mesh.quality',
    'kse.mesh.refiner',
    'kse.mesh.volume_mesher',
    'kse.mesh.exporters.stl_export',
    'kse.mesh.exporters.vtk_export',
    'kse.mesh.exporters.gmsh_export',
    'kse.mesh.exporters.ansys_export',
    'kse.mesh.exporters.lsdyna_export',
    'kse.config.yaml_config',
    'kse.csrc',
    'kse.csrc._fallback',
    # External dependencies
    'yaml',
    'jinja2',
    'sympy',
    'numpy',
    'scipy',
    'scipy.spatial',
    'scipy.optimize',
    'scipy.interpolate',
    'trimesh',
    'rtree',
]

# ── CadQuery + OCP collection (optional) ─────────────────────────
# Collect entire packages to ensure all native libs are bundled
binaries = []
for pkg in ['cadquery', 'OCP', 'ezdxf']:
    try:
        pkg_d, pkg_b, pkg_h = collect_all(pkg)
        datas += pkg_d
        binaries += pkg_b
        hiddenimports += pkg_h
    except Exception:
        pass

# Collect tetgen (optional FEA volume meshing dependency)
try:
    tetgen_datas, tetgen_binaries, tetgen_hiddenimports = collect_all('tetgen')
    datas += tetgen_datas
    binaries += tetgen_binaries
    hiddenimports += tetgen_hiddenimports
except Exception:
    pass

# Also collect casadi and nlopt (cadquery deps)
for pkg in ['casadi', 'nlopt', 'multimethod']:
    try:
        pkg_d, pkg_b, pkg_h = collect_all(pkg)
        datas += pkg_d
        binaries += pkg_b
        hiddenimports += pkg_h
    except Exception:
        pass

# Collect sympy submodules (many are loaded dynamically)
hiddenimports += collect_submodules('sympy')

# ── Analysis ───────────────────────────────────────────────────────
a = Analysis(
    ['cli.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'IPython', 'notebook',
        'pytest', 'sphinx', 'docutils',
    ],
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='kse',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='kse',
)
