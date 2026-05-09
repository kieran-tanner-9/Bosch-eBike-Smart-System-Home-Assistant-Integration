"""Unit tests for unit_converter.py.

Tests cover:
- Metric pass-through (value unchanged, correct unit string)
- Imperial conversion (correct factor applied, rounded to 3 dp, correct unit string)
- None input (returns (None, default_metric_unit) regardless of unit_system)
"""
import pytest

from custom_components.bosch_ebike_ha.unit_converter import (
    KM_TO_MILES,
    KMH_TO_MPH,
    M_TO_FEET,
    convert_distance,
    convert_elevation,
    convert_speed,
)

# ---------------------------------------------------------------------------
# convert_distance
# ---------------------------------------------------------------------------


class TestConvertDistance:
    def test_metric_returns_value_unchanged(self):
        value, unit = convert_distance(10.0, "metric")
        assert value == 10.0
        assert unit == "km"

    def test_metric_zero(self):
        value, unit = convert_distance(0.0, "metric")
        assert value == 0.0
        assert unit == "km"

    def test_imperial_applies_factor(self):
        value, unit = convert_distance(100.0, "imperial")
        assert value == round(100.0 * KM_TO_MILES, 3)
        assert unit == "mi"

    def test_imperial_rounds_to_3dp(self):
        value, unit = convert_distance(1.0, "imperial")
        assert value == round(KM_TO_MILES, 3)
        assert unit == "mi"

    def test_none_metric_returns_none_km(self):
        value, unit = convert_distance(None, "metric")
        assert value is None
        assert unit == "km"

    def test_none_imperial_returns_none_km(self):
        """None input must return (None, 'km') even when unit_system is imperial."""
        value, unit = convert_distance(None, "imperial")
        assert value is None
        assert unit == "km"

    def test_large_value_imperial(self):
        value, unit = convert_distance(1000.0, "imperial")
        assert value == round(1000.0 * KM_TO_MILES, 3)
        assert unit == "mi"

    def test_fractional_value_metric(self):
        value, unit = convert_distance(3.14159, "metric")
        assert value == 3.14159
        assert unit == "km"


# ---------------------------------------------------------------------------
# convert_speed
# ---------------------------------------------------------------------------


class TestConvertSpeed:
    def test_metric_returns_value_unchanged(self):
        value, unit = convert_speed(50.0, "metric")
        assert value == 50.0
        assert unit == "km/h"

    def test_metric_zero(self):
        value, unit = convert_speed(0.0, "metric")
        assert value == 0.0
        assert unit == "km/h"

    def test_imperial_applies_factor(self):
        value, unit = convert_speed(100.0, "imperial")
        assert value == round(100.0 * KMH_TO_MPH, 3)
        assert unit == "mph"

    def test_imperial_rounds_to_3dp(self):
        value, unit = convert_speed(1.0, "imperial")
        assert value == round(KMH_TO_MPH, 3)
        assert unit == "mph"

    def test_none_metric_returns_none_kmh(self):
        value, unit = convert_speed(None, "metric")
        assert value is None
        assert unit == "km/h"

    def test_none_imperial_returns_none_kmh(self):
        """None input must return (None, 'km/h') even when unit_system is imperial."""
        value, unit = convert_speed(None, "imperial")
        assert value is None
        assert unit == "km/h"

    def test_max_assist_speed_example(self):
        """25 km/h (EU legal limit) converts correctly."""
        value, unit = convert_speed(25.0, "imperial")
        assert value == round(25.0 * KMH_TO_MPH, 3)
        assert unit == "mph"


# ---------------------------------------------------------------------------
# convert_elevation
# ---------------------------------------------------------------------------


class TestConvertElevation:
    def test_metric_returns_value_unchanged(self):
        value, unit = convert_elevation(500.0, "metric")
        assert value == 500.0
        assert unit == "m"

    def test_metric_zero(self):
        value, unit = convert_elevation(0.0, "metric")
        assert value == 0.0
        assert unit == "m"

    def test_imperial_applies_factor(self):
        value, unit = convert_elevation(100.0, "imperial")
        assert value == round(100.0 * M_TO_FEET, 3)
        assert unit == "ft"

    def test_imperial_rounds_to_3dp(self):
        value, unit = convert_elevation(1.0, "imperial")
        assert value == round(M_TO_FEET, 3)
        assert unit == "ft"

    def test_none_metric_returns_none_m(self):
        value, unit = convert_elevation(None, "metric")
        assert value is None
        assert unit == "m"

    def test_none_imperial_returns_none_m(self):
        """None input must return (None, 'm') even when unit_system is imperial."""
        value, unit = convert_elevation(None, "imperial")
        assert value is None
        assert unit == "m"

    def test_negative_elevation_imperial(self):
        """Negative elevation (descent below sea level) converts correctly."""
        value, unit = convert_elevation(-50.0, "imperial")
        assert value == round(-50.0 * M_TO_FEET, 3)
        assert unit == "ft"
