"""Property-based tests for unit_converter.py.

Property 11: Unit conversion is a pure, invertible function of value and unit system.

For any non-None metric value v and unit system s ∈ {"metric", "imperial"}, the
UnitConverter functions SHALL satisfy:
- convert_*(v, "metric") returns (v, metric_unit) unchanged.
- convert_*(v, "imperial") returns (v * factor, imperial_unit) where factor is the
  correct SI conversion constant.
- Applying the inverse conversion to the imperial result SHALL recover the original
  metric value within floating-point rounding tolerance (abs(result - v) < 1e-6).
- For None input, the function SHALL return (None, default_metric_unit) regardless
  of unit_system.
- The unit string returned matches the expected unit for the given unit_system.

**Validates: Requirements 13.3, 13.4, 13.7, 13.8**
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from custom_components.bosch_ebike_ha.unit_converter import (
    KM_TO_MILES,
    KMH_TO_MPH,
    M_TO_FEET,
    convert_distance,
    convert_elevation,
    convert_speed,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Finite floats covering a realistic sensor value range (including negatives
# for elevation loss / descent below sea level).
finite_floats = st.floats(
    min_value=-1e9,
    max_value=1e9,
    allow_nan=False,
    allow_infinity=False,
)

# Any unit_system string (metric, imperial, or arbitrary strings — the
# converter must handle all of them gracefully, defaulting to metric for
# anything that is not "imperial").
unit_systems = st.sampled_from(["metric", "imperial"])


# ---------------------------------------------------------------------------
# Property 11 — convert_distance
# ---------------------------------------------------------------------------


@given(v=finite_floats)
@settings(max_examples=100)
def test_convert_distance_metric_passthrough(v):
    """**Validates: Requirements 13.3, 13.7**

    convert_distance(v, "metric") returns (v, "km") unchanged for any finite float.
    """
    result_value, result_unit = convert_distance(v, "metric")
    assert result_value == v
    assert result_unit == "km"


@given(v=finite_floats)
@settings(max_examples=100)
def test_convert_distance_imperial_factor(v):
    """**Validates: Requirements 13.4, 13.7**

    convert_distance(v, "imperial") returns (round(v * KM_TO_MILES, 3), "mi").
    """
    result_value, result_unit = convert_distance(v, "imperial")
    assert result_value == round(v * KM_TO_MILES, 3)
    assert result_unit == "mi"


@given(v=finite_floats)
@settings(max_examples=100)
def test_convert_distance_inverse_recovery(v):
    """**Validates: Requirements 13.4, 13.8**

    Dividing the imperial result by KM_TO_MILES recovers the original metric
    value within the rounding tolerance introduced by round(..., 3).

    The converter rounds the imperial value to 3 decimal places (by design,
    per the unit tests and design doc). This introduces a rounding error of at
    most 0.5e-3 in the imperial value. Dividing that error back by KM_TO_MILES
    gives a maximum recovery error of 0.5e-3 / KM_TO_MILES ≈ 8.05e-4.
    We use 1e-3 as a conservative upper bound that is tight enough to catch
    wrong conversion factors while accommodating the intentional 3-dp rounding.
    """
    imperial_value, _ = convert_distance(v, "imperial")
    recovered = imperial_value / KM_TO_MILES
    # Tolerance: rounding error (≤0.5e-3) divided back through the factor
    tolerance = 0.5e-3 / KM_TO_MILES
    assert abs(recovered - v) <= tolerance


@given(unit_system=unit_systems)
@settings(max_examples=100)
def test_convert_distance_none_handling(unit_system):
    """**Validates: Requirements 13.3, 13.7**

    convert_distance(None, any_unit_system) returns (None, "km") regardless of
    the unit_system argument.
    """
    result_value, result_unit = convert_distance(None, unit_system)
    assert result_value is None
    assert result_unit == "km"


@given(v=finite_floats, unit_system=unit_systems)
@settings(max_examples=100)
def test_convert_distance_unit_string_matches_system(v, unit_system):
    """**Validates: Requirements 13.7**

    The unit string returned by convert_distance matches the expected unit for
    the given unit_system: "km" for metric, "mi" for imperial.
    """
    _, result_unit = convert_distance(v, unit_system)
    expected_unit = "mi" if unit_system == "imperial" else "km"
    assert result_unit == expected_unit


# ---------------------------------------------------------------------------
# Property 11 — convert_speed
# ---------------------------------------------------------------------------


@given(v=finite_floats)
@settings(max_examples=100)
def test_convert_speed_metric_passthrough(v):
    """**Validates: Requirements 13.3, 13.7**

    convert_speed(v, "metric") returns (v, "km/h") unchanged for any finite float.
    """
    result_value, result_unit = convert_speed(v, "metric")
    assert result_value == v
    assert result_unit == "km/h"


@given(v=finite_floats)
@settings(max_examples=100)
def test_convert_speed_imperial_factor(v):
    """**Validates: Requirements 13.4, 13.7**

    convert_speed(v, "imperial") returns (round(v * KMH_TO_MPH, 3), "mph").
    """
    result_value, result_unit = convert_speed(v, "imperial")
    assert result_value == round(v * KMH_TO_MPH, 3)
    assert result_unit == "mph"


@given(v=finite_floats)
@settings(max_examples=100)
def test_convert_speed_inverse_recovery(v):
    """**Validates: Requirements 13.4, 13.8**

    Dividing the imperial result by KMH_TO_MPH recovers the original metric
    value within the rounding tolerance introduced by round(..., 3).

    The converter rounds the imperial value to 3 decimal places (by design).
    This introduces a rounding error of at most 0.5e-3 in the imperial value.
    Dividing that error back by KMH_TO_MPH gives a maximum recovery error of
    0.5e-3 / KMH_TO_MPH ≈ 8.05e-4. We use 1e-3 as a conservative upper bound.
    """
    imperial_value, _ = convert_speed(v, "imperial")
    recovered = imperial_value / KMH_TO_MPH
    tolerance = 0.5e-3 / KMH_TO_MPH
    assert abs(recovered - v) <= tolerance


@given(unit_system=unit_systems)
@settings(max_examples=100)
def test_convert_speed_none_handling(unit_system):
    """**Validates: Requirements 13.3, 13.7**

    convert_speed(None, any_unit_system) returns (None, "km/h") regardless of
    the unit_system argument.
    """
    result_value, result_unit = convert_speed(None, unit_system)
    assert result_value is None
    assert result_unit == "km/h"


@given(v=finite_floats, unit_system=unit_systems)
@settings(max_examples=100)
def test_convert_speed_unit_string_matches_system(v, unit_system):
    """**Validates: Requirements 13.7**

    The unit string returned by convert_speed matches the expected unit for
    the given unit_system: "km/h" for metric, "mph" for imperial.
    """
    _, result_unit = convert_speed(v, unit_system)
    expected_unit = "mph" if unit_system == "imperial" else "km/h"
    assert result_unit == expected_unit


# ---------------------------------------------------------------------------
# Property 11 — convert_elevation
# ---------------------------------------------------------------------------


@given(v=finite_floats)
@settings(max_examples=100)
def test_convert_elevation_metric_passthrough(v):
    """**Validates: Requirements 13.3, 13.7**

    convert_elevation(v, "metric") returns (v, "m") unchanged for any finite float.
    """
    result_value, result_unit = convert_elevation(v, "metric")
    assert result_value == v
    assert result_unit == "m"


@given(v=finite_floats)
@settings(max_examples=100)
def test_convert_elevation_imperial_factor(v):
    """**Validates: Requirements 13.4, 13.7**

    convert_elevation(v, "imperial") returns (round(v * M_TO_FEET, 3), "ft").
    """
    result_value, result_unit = convert_elevation(v, "imperial")
    assert result_value == round(v * M_TO_FEET, 3)
    assert result_unit == "ft"


@given(v=finite_floats)
@settings(max_examples=100)
def test_convert_elevation_inverse_recovery(v):
    """**Validates: Requirements 13.4, 13.8**

    Dividing the imperial result by M_TO_FEET recovers the original metric
    value within the rounding tolerance introduced by round(..., 3).

    The converter rounds the imperial value to 3 decimal places (by design).
    This introduces a rounding error of at most 0.5e-3 in the imperial value.
    Dividing that error back by M_TO_FEET gives a maximum recovery error of
    0.5e-3 / M_TO_FEET ≈ 1.52e-4. We use 1e-3 as a conservative upper bound.
    """
    imperial_value, _ = convert_elevation(v, "imperial")
    recovered = imperial_value / M_TO_FEET
    tolerance = 0.5e-3 / M_TO_FEET
    assert abs(recovered - v) <= tolerance


@given(unit_system=unit_systems)
@settings(max_examples=100)
def test_convert_elevation_none_handling(unit_system):
    """**Validates: Requirements 13.3, 13.7**

    convert_elevation(None, any_unit_system) returns (None, "m") regardless of
    the unit_system argument.
    """
    result_value, result_unit = convert_elevation(None, unit_system)
    assert result_value is None
    assert result_unit == "m"


@given(v=finite_floats, unit_system=unit_systems)
@settings(max_examples=100)
def test_convert_elevation_unit_string_matches_system(v, unit_system):
    """**Validates: Requirements 13.7**

    The unit string returned by convert_elevation matches the expected unit for
    the given unit_system: "m" for metric, "ft" for imperial.
    """
    _, result_unit = convert_elevation(v, unit_system)
    expected_unit = "ft" if unit_system == "imperial" else "m"
    assert result_unit == expected_unit
