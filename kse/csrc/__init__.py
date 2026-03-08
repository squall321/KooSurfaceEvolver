"""C acceleration module with Python fallback.

All C functions have pure-Python equivalents in _fallback.py.
The C extension is optional and only provides performance improvement.
"""

try:
    from ._c_ext import fast_extract_patch, fast_compute_sdf
    _HAS_C_EXT = True
except ImportError:
    from ._fallback import fast_extract_patch, fast_compute_sdf
    _HAS_C_EXT = False


def has_c_extension() -> bool:
    """Check if C extension is available."""
    return _HAS_C_EXT
