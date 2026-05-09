"""Property-based tests for ConnectModule entity availability.

**Validates: Requirements 9.4, 9.5, 10.1, 10.3**

Property 3: ConnectModule entities are unavailable when module is absent,
and retain last known location on signal loss.

For any BikeData payload where has_connect_module is False:
- TheftAlarmBinarySensor.available must be False
- AlarmArmedBinarySensor.available must be False
- BikeTrackerEntity.state must be 'not_home'

For any sequence of coordinator updates where location data is present and
then becomes None:
- BikeTrackerEntity.state transitions to 'not_home'
- BikeTrackerEntity retains the last known latitude and longitude as attributes

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

from custom_components.bosch_ebike_ha.binary_sensor import (
    AlarmArmedBinarySensor,
    TheftAlarmBinarySensor,
)
from custom_components.bosch_ebike_ha.const import DOMAIN
from custom_components.bosch_ebike_ha.device_tracker import BikeTrackerEntity
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
from homeassistant.helpers.device_registry import DeviceInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXED_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

_BIKE_INFO = BikeInfo(
    bike_id="bike1",
    name="Test Bike",
    model="Cube Stereo",
    serial_number="SN123",
)

_TELEMETRY = BikeTelemetry(
    odometer_km=1234.5,
    motor_hours_total=100.0,
    motor_hours_with_assist=80.0,
    battery_charge_cycles=50,
    battery_lifetime_energy_wh=5000.0,
    next_service_odometer_km=2000.0,
    max_assist_speed_kmh=25.0,
)

_AGGREGATE = AggregateStats(
    total_rides=100,
    total_distance_km=5000.0,
    total_ride_time_hours=200.0,
    total_calories_kcal=50000.0,
    total_elevation_gain_m=10000.0,
    average_speed_kmh=25.0,
)

_LAST_RIDE = RideData(
    ride_id="r1",
    completed_at=_FIXED_NOW,
    distance_km=42.0,
    duration_minutes=90.0,
    average_speed_kmh=28.0,
    max_speed_kmh=45.0,
    elevation_gain_m=300.0,
    elevation_loss_m=280.0,
    calories_kcal=800.0,
    avg_rider_power_w=None,
    max_rider_power_w=None,
    avg_cadence_rpm=None,
    max_cadence_rpm=None,
    motor_power_ratio_pct=None,
)


def _make_coordinator(
    bike_data: BikeData,
    *,
    last_update_success: bool = True,
    bike_id: str = "bike1",
) -> MagicMock:
    coord = MagicMock()
    coord.data = bike_data
    coord.last_update_success = last_update_success
    coord.bike_id = bike_id
    coord._last_known_latitude = None
    coord._last_known_longitude = None
    return coord


def _make_entry() -> MagicMock:
    entry = MagicMock()
    entry.options = {}
    return entry


def _make_theft_sensor(coordinator: MagicMock) -> TheftAlarmBinarySensor:
    entry = _make_entry()
    sensor = TheftAlarmBinarySensor.__new__(TheftAlarmBinarySensor)
    sensor.coordinator = coordinator
    sensor._entry = entry
    sensor._bike_id = coordinator.bike_id
    sensor._attr_unique_id = f"{coordinator.bike_id}_theft_alarm_active"
    sensor._prev_alarm_triggered = False
    sensor._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.bike_id)})
    return sensor


def _make_armed_sensor(coordinator: MagicMock) -> AlarmArmedBinarySensor:
    entry = _make_entry()
    sensor = AlarmArmedBinarySensor.__new__(AlarmArmedBinarySensor)
    sensor.coordinator = coordinator
    sensor._entry = entry
    sensor._bike_id = coordinator.bike_id
    sensor._attr_unique_id = f"{coordinator.bike_id}_alarm_armed"
    sensor._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.bike_id)})
    return sensor


def _make_tracker(coordinator: MagicMock) -> BikeTrackerEntity:
    entry = _make_entry()
    tracker = BikeTrackerEntity.__new__(BikeTrackerEntity)
    tracker.coordinator = coordinator
    tracker._entry = entry
    tracker._bike_id = coordinator.bike_id
    tracker._attr_unique_id = f"{coordinator.bike_id}_bike_location"
    tracker._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.bike_id)})
    return tracker


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_finite_float = st.floats(
    min_value=-180.0,
    max_value=180.0,
    allow_nan=False,
    allow_infinity=False,
)

_lat_float = st.floats(min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False)
_lon_float = st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False)
_accuracy_float = st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False)

_st_location_data = st.builds(
    LocationData,
    latitude=_lat_float,
    longitude=_lon_float,
    accuracy_m=_accuracy_float,
    timestamp=st.just(_FIXED_NOW),
)

_st_alarm_status = st.builds(
    AlarmStatus,
    alarm_triggered=st.booleans(),
    alarm_armed=st.booleans(),
)

_st_last_updated = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2100, 1, 1),
    timezones=st.just(timezone.utc),
)

# BikeData with has_connect_module=False and arbitrary alarm/location values
_st_bike_data_no_connect_module = st.builds(
    BikeData,
    info=st.just(_BIKE_INFO),
    telemetry=st.just(_TELEMETRY),
    last_ride=st.just(_LAST_RIDE),
    aggregate=st.just(_AGGREGATE),
    battery=st.just(BatteryStatus(state_of_charge_pct=80, charging_status="discharging")),
    # location and alarm may be anything — should not affect unavailability
    location=st.one_of(st.none(), _st_location_data),
    alarm=st.one_of(st.none(), _st_alarm_status),
    has_flow_plus=st.booleans(),
    has_connect_module=st.just(False),
    last_updated=_st_last_updated,
)

# BikeData with has_connect_module=True and a valid location
_st_bike_data_with_location = st.builds(
    BikeData,
    info=st.just(_BIKE_INFO),
    telemetry=st.just(_TELEMETRY),
    last_ride=st.just(_LAST_RIDE),
    aggregate=st.just(_AGGREGATE),
    battery=st.just(BatteryStatus(state_of_charge_pct=80, charging_status="discharging")),
    location=_st_location_data,
    alarm=st.just(AlarmStatus(alarm_triggered=False, alarm_armed=True)),
    has_flow_plus=st.booleans(),
    has_connect_module=st.just(True),
    last_updated=_st_last_updated,
)

# BikeData with has_connect_module=True and location=None (signal loss)
_st_bike_data_location_lost = st.builds(
    BikeData,
    info=st.just(_BIKE_INFO),
    telemetry=st.just(_TELEMETRY),
    last_ride=st.just(_LAST_RIDE),
    aggregate=st.just(_AGGREGATE),
    battery=st.just(BatteryStatus(state_of_charge_pct=80, charging_status="discharging")),
    location=st.just(None),
    alarm=st.just(AlarmStatus(alarm_triggered=False, alarm_armed=True)),
    has_flow_plus=st.booleans(),
    has_connect_module=st.just(True),
    last_updated=_st_last_updated,
)

# A non-empty list of location updates ending with None (signal loss sequence)
_st_location_sequence = st.lists(
    _st_location_data,
    min_size=1,
    max_size=10,
).map(lambda locs: locs + [None])


# ---------------------------------------------------------------------------
# Property 3a: ConnectModule entities are unavailable when module is absent
# ---------------------------------------------------------------------------


@given(bike_data=_st_bike_data_no_connect_module)
@settings(max_examples=100)
def test_property3a_binary_sensors_unavailable_when_no_connect_module(
    bike_data: BikeData,
) -> None:
    """**Validates: Requirements 10.1, 10.3**

    For any BikeData with has_connect_module=False:
    - TheftAlarmBinarySensor.available must be False
    - AlarmArmedBinarySensor.available must be False
    This holds regardless of the alarm field values.
    """
    assert bike_data.has_connect_module is False

    coordinator = _make_coordinator(bike_data)

    theft_sensor = _make_theft_sensor(coordinator)
    armed_sensor = _make_armed_sensor(coordinator)

    assert theft_sensor.available is False, (
        f"TheftAlarmBinarySensor: expected available=False when has_connect_module=False, "
        f"got available={theft_sensor.available!r}"
    )
    assert armed_sensor.available is False, (
        f"AlarmArmedBinarySensor: expected available=False when has_connect_module=False, "
        f"got available={armed_sensor.available!r}"
    )


@given(bike_data=_st_bike_data_no_connect_module)
@settings(max_examples=100)
def test_property3b_tracker_not_home_when_no_connect_module(
    bike_data: BikeData,
) -> None:
    """**Validates: Requirements 9.4, 9.5**

    For any BikeData with has_connect_module=False:
    - BikeTrackerEntity.state must be 'not_home'
    This holds regardless of the location field values.
    """
    assert bike_data.has_connect_module is False

    coordinator = _make_coordinator(bike_data)
    tracker = _make_tracker(coordinator)

    assert tracker.state == "not_home", (
        f"BikeTrackerEntity: expected state='not_home' when has_connect_module=False, "
        f"got state={tracker.state!r}"
    )


# ---------------------------------------------------------------------------
# Property 3c: Tracker transitions to not_home on signal loss and retains
#              last known coordinates as attributes
# ---------------------------------------------------------------------------


@given(location_sequence=_st_location_sequence)
@settings(max_examples=100)
def test_property3c_tracker_retains_last_known_coords_on_signal_loss(
    location_sequence: list[LocationData | None],
) -> None:
    """**Validates: Requirements 9.4, 9.5**

    For any sequence of location updates ending with None:
    - After processing all updates, BikeTrackerEntity.state is 'not_home'
    - The last known latitude and longitude are retained as extra_state_attributes
    - The retained coordinates match the last non-None location in the sequence
    """
    # The sequence always ends with None (signal loss), and has at least one
    # non-None location before it (guaranteed by the strategy).
    assert location_sequence[-1] is None
    non_none_locations = [loc for loc in location_sequence if loc is not None]
    assert len(non_none_locations) >= 1

    last_known = non_none_locations[-1]
    assert last_known.latitude is not None
    assert last_known.longitude is not None

    # Build initial BikeData with the first location
    def _make_bike_data_with_location(loc: LocationData | None) -> BikeData:
        return BikeData(
            info=_BIKE_INFO,
            telemetry=_TELEMETRY,
            last_ride=_LAST_RIDE,
            aggregate=_AGGREGATE,
            battery=BatteryStatus(state_of_charge_pct=80, charging_status="discharging"),
            location=loc,
            alarm=AlarmStatus(alarm_triggered=False, alarm_armed=True),
            has_flow_plus=False,
            has_connect_module=True,
            last_updated=_FIXED_NOW,
        )

    initial_data = _make_bike_data_with_location(location_sequence[0])
    coordinator = _make_coordinator(initial_data)
    tracker = _make_tracker(coordinator)

    # Simulate each coordinator update in the sequence
    for loc in location_sequence:
        coordinator.data = _make_bike_data_with_location(loc)
        tracker._handle_coordinator_update()

    # After the final None update, state must be 'not_home'
    assert tracker.state == "not_home", (
        f"BikeTrackerEntity: expected state='not_home' after signal loss, "
        f"got state={tracker.state!r}"
    )

    # The last known coordinates must be retained in extra_state_attributes
    attrs = tracker.extra_state_attributes
    assert "last_known_latitude" in attrs, (
        "BikeTrackerEntity: expected 'last_known_latitude' in extra_state_attributes "
        "after signal loss"
    )
    assert "last_known_longitude" in attrs, (
        "BikeTrackerEntity: expected 'last_known_longitude' in extra_state_attributes "
        "after signal loss"
    )

    # The retained coordinates must match the last known valid location
    assert attrs["last_known_latitude"] == last_known.latitude, (
        f"BikeTrackerEntity: expected last_known_latitude={last_known.latitude!r}, "
        f"got {attrs['last_known_latitude']!r}"
    )
    assert attrs["last_known_longitude"] == last_known.longitude, (
        f"BikeTrackerEntity: expected last_known_longitude={last_known.longitude!r}, "
        f"got {attrs['last_known_longitude']!r}"
    )


# ---------------------------------------------------------------------------
# Property 3d: Tracker latitude/longitude fall back to cached values on signal loss
# ---------------------------------------------------------------------------


@given(
    bike_data_with_loc=_st_bike_data_with_location,
    bike_data_no_loc=_st_bike_data_location_lost,
)
@settings(max_examples=100)
def test_property3d_tracker_latitude_longitude_retained_after_signal_loss(
    bike_data_with_loc: BikeData,
    bike_data_no_loc: BikeData,
) -> None:
    """**Validates: Requirements 9.4, 9.5**

    After a valid location update followed by a None location update:
    - tracker.latitude returns the last known latitude (not None)
    - tracker.longitude returns the last known longitude (not None)
    - tracker.state is 'not_home'
    """
    assert bike_data_with_loc.location is not None
    assert bike_data_with_loc.location.latitude is not None
    assert bike_data_with_loc.location.longitude is not None
    assert bike_data_no_loc.location is None

    coordinator = _make_coordinator(bike_data_with_loc)
    tracker = _make_tracker(coordinator)

    # First update: valid location — cache coordinates
    tracker._handle_coordinator_update()

    expected_lat = bike_data_with_loc.location.latitude
    expected_lon = bike_data_with_loc.location.longitude

    # Second update: location lost
    coordinator.data = bike_data_no_loc
    tracker._handle_coordinator_update()

    # State must be 'not_home'
    assert tracker.state == "not_home", (
        f"BikeTrackerEntity: expected state='not_home' after signal loss, "
        f"got state={tracker.state!r}"
    )

    # Latitude and longitude must fall back to cached values
    assert tracker.latitude == expected_lat, (
        f"BikeTrackerEntity: expected latitude={expected_lat!r} after signal loss, "
        f"got latitude={tracker.latitude!r}"
    )
    assert tracker.longitude == expected_lon, (
        f"BikeTrackerEntity: expected longitude={expected_lon!r} after signal loss, "
        f"got longitude={tracker.longitude!r}"
    )
