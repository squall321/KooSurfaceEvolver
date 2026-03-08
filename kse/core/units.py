"""Unit system definitions for KSE.

Supports CGS (cm-gram-second) and mm (millimeter-gram-second) unit systems.
Surface Evolver uses consistent unit systems internally; this module
provides default physical constants for each system.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class UnitSystem:
    """Physical unit system with default constants."""

    name: str
    length: str
    tension_unit: str
    density_unit: str
    gravity: float
    default_tension: float
    default_density: float

    def __str__(self) -> str:
        return self.name


CGS = UnitSystem(
    name="CGS",
    length="cm",
    tension_unit="erg/cm^2",
    density_unit="g/cm^3",
    gravity=980.0,
    default_tension=480.0,
    default_density=9.0,
)

MM = UnitSystem(
    name="mm",
    length="mm",
    tension_unit="mN/m",
    density_unit="g/mm^3",
    gravity=9800.0,
    default_tension=480.0,
    default_density=0.009,
)

UNIT_SYSTEMS = {"CGS": CGS, "mm": MM}


def get_unit_system(name: str) -> UnitSystem:
    """Get a unit system by name (case-insensitive)."""
    key = name.upper() if name.upper() in UNIT_SYSTEMS else name
    if key not in UNIT_SYSTEMS:
        raise ValueError(
            f"Unknown unit system '{name}'. Available: {list(UNIT_SYSTEMS.keys())}"
        )
    return UNIT_SYSTEMS[key]
