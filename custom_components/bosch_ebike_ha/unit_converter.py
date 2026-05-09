"""Unit conversion helper for Bosch eBike (Smart System) integration.

All API-native values are metric. These pure functions translate them to
imperial when the user's unit_system preference is "imperial".
"""

from .const import UNIT_IMPERIAL

KM_TO_MILES = 0.621371
KMH_TO_MPH = 0.621371
M_TO_FEET = 3.28084


def convert_distance(value_km: float | None, unit_system: str) -> tuple[float | None, str]:
    """Return (converted_value, unit_string) for a distance in kilometres.

    Metric pass-through returns the value unchanged with "km".
    Imperial conversion multiplies by KM_TO_MILES and returns "mi".
    None input returns (None, "km") regardless of unit_system.
    """
    if value_km is None:
        return None, "km"
    if unit_system == UNIT_IMPERIAL:
        return round(value_km * KM_TO_MILES, 3), "mi"
    return value_km, "km"


def convert_speed(value_kmh: float | None, unit_system: str) -> tuple[float | None, str]:
    """Return (converted_value, unit_string) for a speed in km/h.

    Metric pass-through returns the value unchanged with "km/h".
    Imperial conversion multiplies by KMH_TO_MPH and returns "mph".
    None input returns (None, "km/h") regardless of unit_system.
    """
    if value_kmh is None:
        return None, "km/h"
    if unit_system == UNIT_IMPERIAL:
        return round(value_kmh * KMH_TO_MPH, 3), "mph"
    return value_kmh, "km/h"


def convert_elevation(value_m: float | None, unit_system: str) -> tuple[float | None, str]:
    """Return (converted_value, unit_string) for an elevation in metres.

    Metric pass-through returns the value unchanged with "m".
    Imperial conversion multiplies by M_TO_FEET and returns "ft".
    None input returns (None, "m") regardless of unit_system.
    """
    if value_m is None:
        return None, "m"
    if unit_system == UNIT_IMPERIAL:
        return round(value_m * M_TO_FEET, 3), "ft"
    return value_m, "m"
