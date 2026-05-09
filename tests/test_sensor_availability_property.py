"""Property-based tests for BoschEBikeSensor availability and value.

**Validates: Requirements 2.7, 3.9, 5.4, 5.5**

Property 1: Sensor availability and value reflect data presence
- For non-feature-gated sensors, `entity.available` is True iff the source
  field is not None (and coordinator.last_update_success is True).
- `entity.native_value` equals the converted field value (via unit_fn) or the
  raw value when no unit_fn is present.
- `extra_state_attributes["last_updated"]` is a valid UTC ISO-8601 datetime
  string.

Uses Hypothesis with a minimum of 100 examples.
"""
from __future__ import annotations

import sys
import os

# Ensure the project root is on the path so custom_components can be imported.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Inject HA stubs before any homeassistant imports.
from tests.ha_stubs.inject import inject_ha_stubs  # noqa: E402

inject_ha_stubs()

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from custom_components.bosch_ebike_ha.const import (
    CONF_UNIT_SYSTEM,
    DOMAIN,
    UNIT_IMPERIAL,
    UNIT_METRIC,
)
from custom_components.bosch_ebike_ha.models import (
    AggregateStats,
    AlarmStatus,
    BatteryStatus,
    BikeData,
    BikeInfo,
    BikeTelemetry,
    LocationData,
    RideData,
)
from custom_components.bosch_ebike_ha.sensor import (
    BIKE_SENSORS,
    BoschEBikeSensor,
    BoschEBikeSensorDescription,
)
from homeassistant.helpers.device_registry import DeviceInfo

# ---------------------------------------------------------------------------
# Helpers (mirrors test_sensor.py pattern)
# ---------------------------------------------------------------------------

_FIXED_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

# Non-feature-gated sensor keys (no requires_flow_plus, no requires_connect_module)
_NON_GATED_KEYS = {
    desc.key
    for desc in BIKE_SENSORS
    if not desc.requires_flow_plus and not desc.requires_connect_module
}

# Mapping from sensor key → the BikeData field it reads (for None/non-None control)
# We only need to know which top-level sub-object or field drives availability.
# For sensors that read from telemetry, last_ride, or aggregate we can set the
# individual field to None by constructing the appropriate sub-object.

# Sensors whose source field lives in BikeTelemetry
_TELEMETRY_SENSORS = {
    "odometer": "odometer_km",
    "motor_hours": "motor_hours_total",
    "battery_charge_cycles": "battery_charge_cycles",
    "battery_lifetime_energy": "battery_lifetime_energy_wh",
    "next_service_odometer": "next_service_odometer_km",
    "max_assist_speed": "max_assist_speed_kmh",
}

# Sensors whose source field lives in AggregateStats
_AGGREGATE_SENSORS = {
    "total_rides": "total_rides",
    "total_distance": "total_distance_km",
    "total_ride_time": "total_ride_time_hours",
    "total_calories": "total_calories_kcal",
    "total_elevation_gain": "total_elevation_gain_m",
    "average_speed": "average_speed_kmh",
}

# Sensors whose source field lives in RideData (last_ride may be None itself)
_LAST_RIDE_SENSORS = {
    "last_ride_distance": "distance_km",
    "last_ride_duration": "duration_minutes",
    "last_ride_avg_speed": "average_speed_kmh",
    "last_ride_max_speed": "max_speed_kmh",
    "last_ride_elevation_gain": "elevation_gain_m",
    "last_ride_elevation_loss": "elevation_loss_m",
    "last_ride_calories": "calories_kcal",
    "last_ride_date": "completed_at",
}


def _make_coordinator(bike_data: BikeData, *, last_update_success: bool = True) -> MagicMock:
    coord = MagicMock()
    coord.data = bike_data
    coord.last_update_success = last_update_success
    coord.bike_id = "bike1"
    return coord


def _make_entry(unit_system: str = UNIT_METRIC) -> MagicMock:
    entry = MagicMock()
    entry.options = {CONF_UNIT_SYSTEM: unit_system}
    return entry


def _make_sensor(
    description: BoschEBikeSensorDescription,
    bike_data: BikeData,
    *,
    unit_system: str = UNIT_METRIC,
) -> BoschEBikeSensor:
    coordinator = _make_coordinator(bike_data)
    entry = _make_entry(unit_system)
    sensor = BoschEBikeSensor.__new__(BoschEBikeSensor)
    sensor.coordinator = coordinator
    sensor.entity_description = description
    sensor._entry = entry
    sensor._bike_id = "bike1"
    sensor._attr_unique_id = f"bike1_{description.key}"
    sensor._attr_device_info = DeviceInfo(identifiers={(DOMAIN, "bike1")})
    return sensor


def _get_description(key: str) -> BoschEBikeSensorDescription:
    for desc in BIKE_SENSORS:
        if desc.key == key:
            return desc
    raise KeyError(f"No sensor description with key={key!r}")


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# A finite float that is not NaN/inf — suitable for sensor values
_finite_float = st.floats(
    min_value=-1e9,
    max_value=1e9,
    allow_nan=False,
    allow_infinity=False,
)

# Optional finite float: either None or a finite float
_opt_float = st.one_of(st.none(), _finite_float)

# Optional non-negative float (distances, speeds, durations are non-negative)
_opt_nonneg_float = st.one_of(st.none(), st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False))

# Optional int (battery cycles, total rides)
_opt_int = st.one_of(st.none(), st.integers(min_value=0, max_value=100_000))

# Optional datetime (UTC)
_opt_datetime = st.one_of(
    st.none(),
    st.datetimes(
        min_value=datetime(2000, 1, 1),
        max_value=datetime(2100, 1, 1),
        timezones=st.just(timezone.utc),
    ),
)

# Strategy for BikeTelemetry with arbitrary None/non-None fields
_st_telemetry = st.builds(
    BikeTelemetry,
    odometer_km=_opt_nonneg_float,
    motor_hours_total=_opt_nonneg_float,
    motor_hours_with_assist=_opt_nonneg_float,
    battery_charge_cycles=_opt_int,
    battery_lifetime_energy_wh=_opt_nonneg_float,
    next_service_odometer_km=_opt_nonneg_float,
    max_assist_speed_kmh=_opt_nonneg_float,
)

# Strategy for AggregateStats with arbitrary None/non-None fields
_st_aggregate = st.builds(
    AggregateStats,
    total_rides=_opt_int,
    total_distance_km=_opt_nonneg_float,
    total_ride_time_hours=_opt_nonneg_float,
    total_calories_kcal=_opt_nonneg_float,
    total_elevation_gain_m=_opt_nonneg_float,
    average_speed_kmh=_opt_nonneg_float,
)

# Strategy for RideData with arbitrary None/non-None fields
_st_ride_data = st.builds(
    RideData,
    ride_id=st.just("r1"),
    completed_at=_opt_datetime,
    distance_km=_opt_nonneg_float,
    duration_minutes=_opt_nonneg_float,
    average_speed_kmh=_opt_nonneg_float,
    max_speed_kmh=_opt_nonneg_float,
    elevation_gain_m=_opt_nonneg_float,
    elevation_loss_m=_opt_nonneg_float,
    calories_kcal=_opt_nonneg_float,
    avg_rider_power_w=_opt_nonneg_float,
    max_rider_power_w=_opt_nonneg_float,
    avg_cadence_rpm=_opt_nonneg_float,
    max_cadence_rpm=_opt_nonneg_float,
    motor_power_ratio_pct=_opt_nonneg_float,
)

# Strategy for BikeData with arbitrary telemetry, aggregate, and last_ride
_st_bike_data = st.builds(
    BikeData,
    info=st.just(BikeInfo(bike_id="bike1", name="Test Bike", model="Model X", serial_number="SN1")),
    telemetry=_st_telemetry,
    last_ride=st.one_of(st.none(), _st_ride_data),
    aggregate=_st_aggregate,
    battery=st.just(BatteryStatus(state_of_charge_pct=80, charging_status="discharging")),
    location=st.just(LocationData(latitude=51.5, longitude=-0.1, accuracy_m=5.0, timestamp=_FIXED_NOW)),
    alarm=st.just(AlarmStatus(alarm_triggered=False, alarm_armed=True)),
    has_flow_plus=st.just(True),
    has_connect_module=st.just(True),
    last_updated=st.datetimes(
        min_value=datetime(2000, 1, 1),
        max_value=datetime(2100, 1, 1),
        timezones=st.just(timezone.utc),
    ),
)

# Unit system strategy
_st_unit_system = st.sampled_from([UNIT_METRIC, UNIT_IMPERIAL])


# ---------------------------------------------------------------------------
# Property 1: Sensor availability and value reflect data presence
# ---------------------------------------------------------------------------


@given(bike_data=_st_bike_data, unit_system=_st_unit_system)
@settings(max_examples=100)
def test_property1_telemetry_sensor_availability_and_value(
    bike_data: BikeData, unit_system: str
) -> None:
    """**Validates: Requirements 2.7, 3.9, 5.4, 5.5**

    For each non-feature-gated telemetry sensor:
    - available == (source field is not None)
    - native_value == converted field value (or raw if no unit_fn)
    - extra_state_attributes["last_updated"] is a valid UTC ISO-8601 string
    """
    for key, field_name in _TELEMETRY_SENSORS.items():
        desc = _get_description(key)
        sensor = _make_sensor(desc, bike_data, unit_system=unit_system)

        raw_value = getattr(bike_data.telemetry, field_name)
        field_is_present = raw_value is not None

        # --- Availability ---
        assert sensor.available == field_is_present, (
            f"Sensor '{key}': expected available={field_is_present} "
            f"when {field_name}={raw_value!r}"
        )

        # --- Native value ---
        if not field_is_present:
            assert sensor.native_value is None, (
                f"Sensor '{key}': expected native_value=None when field is None"
            )
        else:
            if desc.unit_fn is not None:
                expected_value, _ = desc.unit_fn(raw_value, unit_system)
            else:
                expected_value = raw_value
            assert sensor.native_value == expected_value, (
                f"Sensor '{key}': expected native_value={expected_value!r}, "
                f"got {sensor.native_value!r} (raw={raw_value!r}, unit_system={unit_system!r})"
            )

        # --- last_updated attribute ---
        attrs = sensor.extra_state_attributes
        assert "last_updated" in attrs, f"Sensor '{key}': missing 'last_updated' in extra_state_attributes"
        parsed = datetime.fromisoformat(attrs["last_updated"])
        assert parsed.tzinfo is not None, (
            f"Sensor '{key}': last_updated must be timezone-aware, got {attrs['last_updated']!r}"
        )
        assert parsed.tzinfo == timezone.utc or parsed.utcoffset().total_seconds() == 0, (
            f"Sensor '{key}': last_updated must be UTC, got tzinfo={parsed.tzinfo!r}"
        )


@given(bike_data=_st_bike_data, unit_system=_st_unit_system)
@settings(max_examples=100)
def test_property1_aggregate_sensor_availability_and_value(
    bike_data: BikeData, unit_system: str
) -> None:
    """**Validates: Requirements 2.7, 3.9, 5.4, 5.5**

    For each non-feature-gated aggregate sensor:
    - available == (source field is not None)
    - native_value == converted field value (or raw if no unit_fn)
    - extra_state_attributes["last_updated"] is a valid UTC ISO-8601 string
    """
    for key, field_name in _AGGREGATE_SENSORS.items():
        desc = _get_description(key)
        sensor = _make_sensor(desc, bike_data, unit_system=unit_system)

        raw_value = getattr(bike_data.aggregate, field_name)
        field_is_present = raw_value is not None

        # --- Availability ---
        assert sensor.available == field_is_present, (
            f"Sensor '{key}': expected available={field_is_present} "
            f"when {field_name}={raw_value!r}"
        )

        # --- Native value ---
        if not field_is_present:
            assert sensor.native_value is None, (
                f"Sensor '{key}': expected native_value=None when field is None"
            )
        else:
            if desc.unit_fn is not None:
                expected_value, _ = desc.unit_fn(raw_value, unit_system)
            else:
                expected_value = raw_value
            assert sensor.native_value == expected_value, (
                f"Sensor '{key}': expected native_value={expected_value!r}, "
                f"got {sensor.native_value!r} (raw={raw_value!r}, unit_system={unit_system!r})"
            )

        # --- last_updated attribute ---
        attrs = sensor.extra_state_attributes
        assert "last_updated" in attrs, f"Sensor '{key}': missing 'last_updated' in extra_state_attributes"
        parsed = datetime.fromisoformat(attrs["last_updated"])
        assert parsed.tzinfo is not None, (
            f"Sensor '{key}': last_updated must be timezone-aware"
        )


@given(bike_data=_st_bike_data, unit_system=_st_unit_system)
@settings(max_examples=100)
def test_property1_last_ride_sensor_availability_and_value(
    bike_data: BikeData, unit_system: str
) -> None:
    """**Validates: Requirements 2.7, 3.9, 5.4, 5.5**

    For each non-feature-gated last-ride sensor:
    - available == (last_ride is not None AND source field is not None)
    - native_value == converted field value (or raw if no unit_fn)
    - extra_state_attributes["last_updated"] is a valid UTC ISO-8601 string
    """
    for key, field_name in _LAST_RIDE_SENSORS.items():
        desc = _get_description(key)
        sensor = _make_sensor(desc, bike_data, unit_system=unit_system)

        if bike_data.last_ride is None:
            raw_value = None
        else:
            raw_value = getattr(bike_data.last_ride, field_name)

        field_is_present = raw_value is not None

        # --- Availability ---
        assert sensor.available == field_is_present, (
            f"Sensor '{key}': expected available={field_is_present} "
            f"when last_ride={bike_data.last_ride!r}, {field_name}={raw_value!r}"
        )

        # --- Native value ---
        if not field_is_present:
            assert sensor.native_value is None, (
                f"Sensor '{key}': expected native_value=None when field is None"
            )
        else:
            if desc.unit_fn is not None:
                expected_value, _ = desc.unit_fn(raw_value, unit_system)
            else:
                expected_value = raw_value
            assert sensor.native_value == expected_value, (
                f"Sensor '{key}': expected native_value={expected_value!r}, "
                f"got {sensor.native_value!r} (raw={raw_value!r}, unit_system={unit_system!r})"
            )

        # --- last_updated attribute ---
        attrs = sensor.extra_state_attributes
        assert "last_updated" in attrs, f"Sensor '{key}': missing 'last_updated' in extra_state_attributes"
        parsed = datetime.fromisoformat(attrs["last_updated"])
        assert parsed.tzinfo is not None, (
            f"Sensor '{key}': last_updated must be timezone-aware"
        )
