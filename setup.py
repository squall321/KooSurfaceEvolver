import os
import sys
from setuptools import setup, find_packages, Extension
from setuptools.command.build_ext import build_ext


class OptionalBuildExt(build_ext):
    """C extensions are optional - fall back to pure Python if build fails."""

    def build_extension(self, ext):
        try:
            super().build_extension(ext)
        except Exception as e:
            print(f"WARNING: Failed to build C extension '{ext.name}': {e}")
            print("Falling back to pure Python implementation.")


c_extensions = []
if os.environ.get("KSE_BUILD_C_EXT", "1") == "1":
    c_extensions = [
        Extension(
            "kse.csrc._c_ext",
            sources=[
                "kse/csrc/fast_sdf.c",
                "kse/csrc/patch_extract.c",
            ],
            include_dirs=["kse/csrc"],
            extra_compile_args=["-O3"] if sys.platform != "win32" else ["/O2"],
        ),
    ]

setup(
    name="kse",
    version="0.1.0",
    description="KooSolderEvolver: STL-based automatic solder joint simulation",
    packages=find_packages(),
    package_data={
        "kse": ["../templates/*.j2"],
    },
    install_requires=[
        "numpy>=1.21",
        "scipy>=1.7",
        "trimesh>=3.15",
        "rtree>=1.0",
        "jinja2>=3.0",
        "sympy>=1.10",
        "pyyaml>=6.0",
    ],
    extras_require={
        "step": ["cadquery>=2.3"],
        "fea": ["tetgen>=0.6"],
        "all": ["cadquery>=2.3", "tetgen>=0.6"],
    },
    ext_modules=c_extensions,
    cmdclass={"build_ext": OptionalBuildExt},
    entry_points={
        "console_scripts": [
            "kse=cli:main",
        ],
    },
    python_requires=">=3.12",
)
