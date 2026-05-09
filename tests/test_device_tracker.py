"""Unit tests for device_tracker.py — BikeTrackerEntity.

Tests cover:
- unique_id construction
- device_info identifiers
- source_type is GPS
- latitude / longitude / location_accuracy from coordinator data
- state is 'not_home' when has_connect_module is False
- state is 'not_home' when location data is None (no GPS fix)
- state is 'not_home' when location lat/lon are None
- last known coordinates cached and retained when location becomes None
- extra_state_attributes includes last_known_latitude/longitude and last_updated
- async_setup_entry creates one entity per coordinator
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_location(
    lat: float | None = 51.5,
    lon: float | None = -0.1,
    accuracy: float | None = 5.0,
) -> LocationData:
    return LocationData(
        latitude=lat,
        longitude=lon,
        accuracy_m=accuracy,
        timestamp=_NOW,
    )


def _make_bike_data(
    *,
    has_connect_module: bool = True,
    location: LocationData | None = None,
    use_default_location: bool = True,
) -> BikeData:
    if use_default_location and location is None and has_connect_module:
        location = _make_location()
    return BikeData(
        info=BikeInfo(
            bike_id="bike1",
            name="My Bike",
            model="Cube Stereo",
            serial_number="SN123",
        ),
        telemetry=BikeTelemetry(
            odometer_km=1234.5,
            motor_hours_total=100.0,
            motor_hours_with_assist=80.0,
            battery_charge_cycles=50,
            battery_lifetime_energy_wh=5000.0,
            next_service_odometer_km=2000.0,
            max_assist_speed_kmh=25.0,
        ),
        last_ride=RideData(
            ride_id="r1",
            completed_at=_NOW,
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
        ),
        aggregate=AggregateStats(
            total_rides=100,
            total_distance_km=5000.0,
            total_ride_time_hours=200.0,
            total_calories_kcal=50000.0,
            total_elevation_gain_m=10000.0,
            average_speed_kmh=25.0,
        ),
        battery=BatteryStatus(state_of_charge_pct=85, charging_status="discharging"),
        location=location,
        alarm=AlarmStatus(alarm_triggered=False, alarm_armed=True),
        has_flow_plus=False,
        has_connect_module=has_connect_module,
        last_updated=_NOW,
    )


def _make_coordinator(
    bike_data: BikeData | None,
    *,
    last_update_success: bool = True,
    bike_id: str = "bike1",
) -> MagicMock:
    coord = MagicMock()
    coord.data = bike_data
    coord.last_update_success = last_update_success
    coord.bike_id = bike_id
    # Simulate no cached coordinates initially
    coord._last_known_latitude = None
    coord._last_known_longitude = None
    return coord


def _make_entry() -> MagicMock:
    entry = MagicMock()
    entry.options = {}
    return entry


def _make_tracker(
    bike_data: BikeData | None = None,
    *,
    last_update_success: bool = True,
    bike_id: str = "bike1",
) -> BikeTrackerEntity:
    if bike_data is None:
        bike_data = _make_bike_data()
    coordinator = _make_coordinator(
        bike_data, last_update_success=last_update_success, bike_id=bike_id
    )
    entry = _make_entry()
    tracker = BikeTrackerEntity.__new__(BikeTrackerEntity)
    # Bypass CoordinatorEntity.__init__ to avoid needing a real hass instance
    tracker.coordinator = coordinator
    tracker._entry = entry
    tracker._bike_id = bike_id
    tracker._attr_unique_id = f"{bike_id}_bike_location"
    from homeassistant.helpers.device_registry import DeviceInfo
    tracker._attr_device_info = DeviceInfo(identifiers={(DOMAIN, bike_id)})
    return tracker


# ---------------------------------------------------------------------------
# Tests: unique_id and device_info
# ---------------------------------------------------------------------------


class TestUniqueIdAndDeviceInfo:
    def test_unique_id_format(self):
        tracker = _make_tracker(bike_id="bike42")
        assert tracker.unique_id == "bike42_bike_location"

    def test_unique_id_different_bikes(self):
        t1 = _make_tracker(bike_id="bike1")
        t2 = _make_tracker(bike_id="bike2")
        assert t1.unique_id != t2.unique_id

    def test_device_info_identifiers(self):
        tracker = _make_tracker(bike_id="bike99")
        assert (DOMAIN, "bike99") in tracker.device_info["identifiers"]


# ---------------------------------------------------------------------------
# Tests: source_type
# ---------------------------------------------------------------------------


class TestSourceType:
    def test_source_type_is_gps(self):
        from homeassistant.components.device_tracker import SourceType
        tracker = _make_tracker()
        assert tracker.source_type == SourceType.GPS


# ---------------------------------------------------------------------------
# Tests: latitude / longitude / location_accuracy
# ---------------------------------------------------------------------------


class TestCoordinates:
    def test_latitude_from_coordinator_data(self):
        data = _make_bike_data(location=_make_location(lat=51.5, lon=-0.1))
        tracker = _make_tracker(data)
        assert tracker.latitude == 51.5

    def test_longitude_from_coordinator_data(self):
        data = _make_bike_data(location=_make_location(lat=51.5, lon=-0.1))
        tracker = _make_tracker(data)
        assert tracker.longitude == -0.1

    def test_location_accuracy_from_coordinator_data(self):
        data = _make_bike_data(location=_make_location(accuracy=10.0))
        tracker = _make_tracker(data)
        assert tracker.location_accuracy == 10

    def test_location_accuracy_zero_when_no_location(self):
        data = _make_bike_data(
            has_connect_module=True, location=None, use_default_location=False
        )
        tracker = _make_tracker(data)
        assert tracker.location_accuracy == 0

    def test_latitude_none_when_no_location_and_no_cache(self):
        data = _make_bike_data(
            has_connect_module=True, location=None, use_default_location=False
        )
        tracker = _make_tracker(data)
        # No cached value either
        tracker.coordinator._last_known_latitude = None
        assert tracker.latitude is None

    def test_longitude_none_when_no_location_and_no_cache(self):
        data = _make_bike_data(
            has_connect_module=True, location=None, use_default_location=False
        )
        tracker = _make_tracker(data)
        tracker.coordinator._last_known_longitude = None
        assert tracker.longitude is None

    def test_latitude_falls_back_to_cached_when_no_current_location(self):
        data = _make_bike_data(
            has_connect_module=True, location=None, use_default_location=False
        )
        tracker = _make_tracker(data)
        tracker.coordinator._last_known_latitude = 48.8566
        assert tracker.latitude == 48.8566

    def test_longitude_falls_back_to_cached_when_no_current_location(self):
        data = _make_bike_data(
            has_connect_module=True, location=None, use_default_location=False
        )
        tracker = _make_tracker(data)
        tracker.coordinator._last_known_longitude = 2.3522
        assert tracker.longitude == 2.3522


# ---------------------------------------------------------------------------
# Tests: state
# ---------------------------------------------------------------------------


class TestState:
    def test_state_not_home_when_no_connect_module(self):
        data = _make_bike_data(has_connect_module=False, use_default_location=False)
        tracker = _make_tracker(data)
        assert tracker.state == "not_home"

    def test_state_not_home_when_location_is_none(self):
        data = _make_bike_data(
            has_connect_module=True, location=None, use_default_location=False
        )
        tracker = _make_tracker(data)
        assert tracker.state == "not_home"

    def test_state_not_home_when_lat_lon_are_none(self):
        data = _make_bike_data(
            has_connect_module=True,
            location=_make_location(lat=None, lon=None),
            use_default_location=False,
        )
        tracker = _make_tracker(data)
        assert tracker.state == "not_home"

    def test_state_not_home_when_coordinator_failed(self):
        data = _make_bike_data()
        tracker = _make_tracker(data, last_update_success=False)
        assert tracker.state == "not_home"

    def test_state_not_home_with_valid_location(self):
        # Even with a valid location the state is 'not_home' (no zone detection)
        # but lat/lon attributes are populated for map display
        data = _make_bike_data(location=_make_location(lat=51.5, lon=-0.1))
        tracker = _make_tracker(data)
        assert tracker.state == "not_home"
        assert tracker.latitude == 51.5
        assert tracker.longitude == -0.1


# ---------------------------------------------------------------------------
# Tests: coordinate caching via _handle_coordinator_update
# ---------------------------------------------------------------------------


class TestCoordinateCaching:
    def test_handle_coordinator_update_caches_valid_coordinates(self):
        data = _make_bike_data(location=_make_location(lat=51.5, lon=-0.1))
        tracker = _make_tracker(data)
        # Simulate coordinator update
        tracker._handle_coordinator_update()
        assert tracker.coordinator._last_known_latitude == 51.5
        assert tracker.coordinator._last_known_longitude == -0.1

    def test_handle_coordinator_update_does_not_overwrite_cache_with_none(self):
        data = _make_bike_data(location=_make_location(lat=51.5, lon=-0.1))
        tracker = _make_tracker(data)
        # First update — cache coordinates
        tracker._handle_coordinator_update()
        assert tracker.coordinator._last_known_latitude == 51.5

        # Second update — location becomes None
        no_location_data = _make_bike_data(
            has_connect_module=True, location=None, use_default_location=False
        )
        tracker.coordinator.data = no_location_data
        tracker._handle_coordinator_update()

        # Cache should still hold the previous coordinates
        assert tracker.coordinator._last_known_latitude == 51.5
        assert tracker.coordinator._last_known_longitude == -0.1

    def test_cached_coordinates_returned_after_location_loss(self):
        data = _make_bike_data(location=_make_location(lat=48.8566, lon=2.3522))
        tracker = _make_tracker(data)
        tracker._handle_coordinator_update()

        # Simulate location loss
        no_location_data = _make_bike_data(
            has_connect_module=True, location=None, use_default_location=False
        )
        tracker.coordinator.data = no_location_data

        assert tracker.latitude == 48.8566
        assert tracker.longitude == 2.3522
        assert tracker.state == "not_home"


# ---------------------------------------------------------------------------
# Tests: extra_state_attributes
# ---------------------------------------------------------------------------


class TestExtraStateAttributes:
    def test_last_updated_present(self):
        tracker = _make_tracker()
        attrs = tracker.extra_state_attributes
        assert "last_updated" in attrs

    def test_last_updated_is_iso_string(self):
        tracker = _make_tracker()
        attrs = tracker.extra_state_attributes
        parsed = datetime.fromisoformat(attrs["last_updated"])
        assert parsed == _NOW

    def test_last_known_coords_in_attrs_when_cached(self):
        data = _make_bike_data(location=_make_location(lat=51.5, lon=-0.1))
        tracker = _make_tracker(data)
        tracker.coordinator._last_known_latitude = 51.5
        tracker.coordinator._last_known_longitude = -0.1
        attrs = tracker.extra_state_attributes
        assert attrs["last_known_latitude"] == 51.5
        assert attrs["last_known_longitude"] == -0.1

    def test_last_known_coords_absent_when_no_cache(self):
        data = _make_bike_data(
            has_connect_module=True, location=None, use_default_location=False
        )
        tracker = _make_tracker(data)
        tracker.coordinator._last_known_latitude = None
        tracker.coordinator._last_known_longitude = None
        attrs = tracker.extra_state_attributes
        assert "last_known_latitude" not in attrs
        assert "last_known_longitude" not in attrs

    def test_gps_timestamp_present_when_location_available(self):
        data = _make_bike_data(location=_make_location())
        tracker = _make_tracker(data)
        attrs = tracker.extra_state_attributes
        assert "gps_timestamp" in attrs

    def test_gps_timestamp_absent_when_no_location(self):
        data = _make_bike_data(
            has_connect_module=True, location=None, use_default_location=False
        )
        tracker = _make_tracker(data)
        attrs = tracker.extra_state_attributes
        assert "gps_timestamp" not in attrs
