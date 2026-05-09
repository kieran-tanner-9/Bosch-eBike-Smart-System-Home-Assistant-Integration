"""Property-based tests for feature-gated sensor availability.

**Validates: Requirements 7.6, 7.7, 8.1, 8.2**

Property 2: Feature-gated sensors are unavailable when feature is inactive

For any BikeData payload where has_flow_plus is False, all Flow+ sensor
entities SHALL return STATE_UNAVAILABLE regardless of the values of the
Flow+ fields. Conversely, for any payload where has_flow_plus is True and
the corresponding field is not None, the entity SHALL return the field value.

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
from hypothesis import given, settings
from hypothesis import strategies as st

from custom_components.bosch_ebike_ha.const import (
    CONF_UNIT_SYSTEM,
    DOMAIN,
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
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers.device_registry import DeviceInfo

# ---------------------------------------------------------------------------
# Flow+ sensor keys and their source field mapping
# ---------------------------------------------------------------------------

# Keys of all Flow+ sensors (requires_flow_plus=True)
_FLOW_PLUS_KEYS = [desc.key for desc in BIKE_SENSORS if desc.requires_flow_plus]

# Mapping from Flow+ sensor key → (sub-object attr on BikeData, field attr on sub-object)
# Used to construct BikeData with non-None Flow+ fields for the "active" case.
_FLOW_PLUS_RIDE_FIELDS = {
    "last_ride_avg_rider_power": "avg_rider_power_w",
    "last_ride_max_rider_power": "max_rider_power_w",
    "last_ride_avg_cadence": "avg_cadence_rpm",
    "last_ride_max_cadence": "max_cadence_rpm",
    "last_ride_motor_power_ratio": "motor_power_ratio_pct",
}

_FLOW_PLUS_BATTERY_FIELDS = {
    "battery_soc": "state_of_charge_pct",
    "battery_charging_status": "charging_status",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXED_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


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

_finite_float = st.floats(
    min_value=0.0,
    max_value=1e6,
    allow_nan=False,
    allow_infinity=False,
)

_opt_float = st.one_of(st.none(), _finite_float)

_opt_int = st.one_of(st.none(), st.integers(min_value=0, max_value=100))

_opt_nonneg_float = st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False)

_st_telemetry = st.builds(
    BikeTelemetry,
    odometer_km=_opt_float,
    motor_hours_total=_opt_float,
    motor_hours_with_assist=_opt_float,
    battery_charge_cycles=_opt_int,
    battery_lifetime_energy_wh=_opt_float,
    next_service_odometer_km=_opt_float,
    max_assist_speed_kmh=_opt_float,
)

_st_aggregate = st.builds(
    AggregateStats,
    total_rides=_opt_int,
    total_distance_km=_opt_float,
    total_ride_time_hours=_opt_float,
    total_calories_kcal=_opt_float,
    total_elevation_gain_m=_opt_float,
    average_speed_kmh=_opt_float,
)

# RideData with arbitrary Flow+ field values (may be None or non-None)
_st_ride_data_arbitrary_flow_plus = st.builds(
    RideData,
    ride_id=st.just("r1"),
    completed_at=st.just(_FIXED_NOW),
    distance_km=st.just(10.0),
    duration_minutes=st.just(30.0),
    average_speed_kmh=st.just(20.0),
    max_speed_kmh=st.just(35.0),
    elevation_gain_m=st.just(100.0),
    elevation_loss_m=st.just(90.0),
    calories_kcal=st.just(250.0),
    # Flow+ fields: arbitrary (None or non-None) — should not affect unavailability
    avg_rider_power_w=_opt_float,
    max_rider_power_w=_opt_float,
    avg_cadence_rpm=_opt_float,
    max_cadence_rpm=_opt_float,
    motor_power_ratio_pct=_opt_float,
)

# RideData with all Flow+ fields set to non-None values
_st_ride_data_flow_plus_active = st.builds(
    RideData,
    ride_id=st.just("r1"),
    completed_at=st.just(_FIXED_NOW),
    distance_km=st.just(10.0),
    duration_minutes=st.just(30.0),
    average_speed_kmh=st.just(20.0),
    max_speed_kmh=st.just(35.0),
    elevation_gain_m=st.just(100.0),
    elevation_loss_m=st.just(90.0),
    calories_kcal=st.just(250.0),
    avg_rider_power_w=_finite_float,
    max_rider_power_w=_finite_float,
    avg_cadence_rpm=_finite_float,
    max_cadence_rpm=_finite_float,
    motor_power_ratio_pct=_finite_float,
)

# BatteryStatus with arbitrary values (for inactive case)
_st_battery_arbitrary = st.one_of(
    st.none(),
    st.builds(
        BatteryStatus,
        state_of_charge_pct=_opt_int,
        charging_status=st.one_of(st.none(), st.sampled_from(["charging", "discharging", "full", "unknown"])),
    ),
)

# BatteryStatus with non-None fields (for active case)
_st_battery_active = st.builds(
    BatteryStatus,
    state_of_charge_pct=st.integers(min_value=0, max_value=100),
    charging_status=st.sampled_from(["charging", "discharging", "full", "unknown"]),
)

_st_last_updated = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2100, 1, 1),
    timezones=st.just(timezone.utc),
)

# BikeData with has_flow_plus=False and arbitrary Flow+ field values
_st_bike_data_flow_plus_inactive = st.builds(
    BikeData,
    info=st.just(BikeInfo(bike_id="bike1", name="Test Bike", model="Model X", serial_number="SN1")),
    telemetry=_st_telemetry,
    last_ride=st.one_of(st.none(), _st_ride_data_arbitrary_flow_plus),
    aggregate=_st_aggregate,
    battery=_st_battery_arbitrary,
    location=st.just(None),
    alarm=st.just(None),
    has_flow_plus=st.just(False),
    has_connect_module=st.just(False),
    last_updated=_st_last_updated,
)

# BikeData with has_flow_plus=True and all Flow+ fields non-None
_st_bike_data_flow_plus_active = st.builds(
    BikeData,
    info=st.just(BikeInfo(bike_id="bike1", name="Test Bike", model="Model X", serial_number="SN1")),
    telemetry=_st_telemetry,
    last_ride=_st_ride_data_flow_plus_active,
    aggregate=_st_aggregate,
    battery=_st_battery_active,
    location=st.just(None),
    alarm=st.just(None),
    has_flow_plus=st.just(True),
    has_connect_module=st.just(False),
    last_updated=_st_last_updated,
)


# ---------------------------------------------------------------------------
# Property 2a: Flow+ sensors return STATE_UNAVAILABLE when has_flow_plus=False
# ---------------------------------------------------------------------------


@given(bike_data=_st_bike_data_flow_plus_inactive)
@settings(max_examples=100)
def test_property2a_flow_plus_sensors_unavailable_when_inactive(
    bike_data: BikeData,
) -> None:
    """**Validates: Requirements 7.6, 7.7, 8.1, 8.2**

    For any BikeData with has_flow_plus=False:
    - All Flow+ sensor entities must have available=False
    - All Flow+ sensor entities must return STATE_UNAVAILABLE from native_value
    This holds regardless of the actual values of the Flow+ fields.
    """
    assert bike_data.has_flow_plus is False

    for key in _FLOW_PLUS_KEYS:
        desc = _get_description(key)
        sensor = _make_sensor(desc, bike_data)

        # available must be False
        assert sensor.available is False, (
            f"Sensor '{key}': expected available=False when has_flow_plus=False, "
            f"got available={sensor.available!r}"
        )

        # native_value must be STATE_UNAVAILABLE
        assert sensor.native_value == STATE_UNAVAILABLE, (
            f"Sensor '{key}': expected native_value=STATE_UNAVAILABLE when has_flow_plus=False, "
            f"got native_value={sensor.native_value!r}"
        )


# ---------------------------------------------------------------------------
# Property 2b: Flow+ sensors return field values when has_flow_plus=True
# ---------------------------------------------------------------------------


@given(bike_data=_st_bike_data_flow_plus_active)
@settings(max_examples=100)
def test_property2b_flow_plus_sensors_return_values_when_active(
    bike_data: BikeData,
) -> None:
    """**Validates: Requirements 7.6, 7.7, 8.1, 8.2**

    For any BikeData with has_flow_plus=True and non-None Flow+ fields:
    - All Flow+ sensor entities must have available=True
    - All Flow+ sensor entities must return the field value from native_value
    """
    assert bike_data.has_flow_plus is True
    assert bike_data.last_ride is not None
    assert bike_data.battery is not None

    for key in _FLOW_PLUS_KEYS:
        desc = _get_description(key)
        sensor = _make_sensor(desc, bike_data)

        # Determine the expected raw value
        if key in _FLOW_PLUS_RIDE_FIELDS:
            field_name = _FLOW_PLUS_RIDE_FIELDS[key]
            raw_value = getattr(bike_data.last_ride, field_name)
        elif key in _FLOW_PLUS_BATTERY_FIELDS:
            field_name = _FLOW_PLUS_BATTERY_FIELDS[key]
            raw_value = getattr(bike_data.battery, field_name)
        else:
            raise AssertionError(f"Unknown Flow+ sensor key: {key!r}")

        # All Flow+ fields are non-None in this strategy
        assert raw_value is not None, (
            f"Sensor '{key}': test setup error — expected non-None field value"
        )

        # available must be True
        assert sensor.available is True, (
            f"Sensor '{key}': expected available=True when has_flow_plus=True "
            f"and field={raw_value!r}, got available={sensor.available!r}"
        )

        # native_value must equal the raw field value (no unit_fn for Flow+ sensors)
        assert sensor.native_value == raw_value, (
            f"Sensor '{key}': expected native_value={raw_value!r}, "
            f"got native_value={sensor.native_value!r}"
        )

        # native_value must NOT be STATE_UNAVAILABLE
        assert sensor.native_value != STATE_UNAVAILABLE, (
            f"Sensor '{key}': native_value must not be STATE_UNAVAILABLE "
            f"when has_flow_plus=True and field is non-None"
        )
