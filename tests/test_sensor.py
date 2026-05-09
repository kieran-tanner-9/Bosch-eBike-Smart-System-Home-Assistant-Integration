"""Unit tests for sensor.py — BoschEBikeSensor entities.

Tests cover:
- unique_id construction
- device_info identifiers
- available logic (coordinator failure, None source field, feature gates)
- native_value (raw, unit-converted, feature-gated)
- native_unit_of_measurement (dynamic for convertible sensors)
- extra_state_attributes (last_updated)
- async_setup_entry entity count
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

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
    BatterySocSensor,
    BoschEBikeSensor,
    BoschEBikeSensorDescription,
)
from custom_components.bosch_ebike_ha.unit_converter import (
    KM_TO_MILES,
    KMH_TO_MPH,
    M_TO_FEET,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_bike_data(
    *,
    has_flow_plus: bool = True,
    has_connect_module: bool = True,
    odometer_km: float | None = 1234.5,
    motor_hours: float | None = 100.0,
    battery_cycles: int | None = 50,
    battery_energy: float | None = 5000.0,
    next_service: float | None = 2000.0,
    max_speed: float | None = 25.0,
    last_ride: RideData | None = None,
    battery: BatteryStatus | None = None,
    location: LocationData | None = None,
) -> BikeData:
    if last_ride is None:
        last_ride = RideData(
            ride_id="r1",
            completed_at=_NOW,
            distance_km=42.0,
            duration_minutes=90.0,
            average_speed_kmh=28.0,
            max_speed_kmh=45.0,
            elevation_gain_m=300.0,
            elevation_loss_m=280.0,
            calories_kcal=800.0,
            avg_rider_power_w=150.0,
            max_rider_power_w=400.0,
            avg_cadence_rpm=80.0,
            max_cadence_rpm=110.0,
            motor_power_ratio_pct=60.0,
        )
    if battery is None:
        battery = BatteryStatus(state_of_charge_pct=85, charging_status="discharging")
    if location is None:
        location = LocationData(
            latitude=51.5, longitude=-0.1, accuracy_m=5.0, timestamp=_NOW
        )
    return BikeData(
        info=BikeInfo(
            bike_id="bike1",
            name="My Bike",
            model="Cube Stereo",
            serial_number="SN123",
        ),
        telemetry=BikeTelemetry(
            odometer_km=odometer_km,
            motor_hours_total=motor_hours,
            motor_hours_with_assist=80.0,
            battery_charge_cycles=battery_cycles,
            battery_lifetime_energy_wh=battery_energy,
            next_service_odometer_km=next_service,
            max_assist_speed_kmh=max_speed,
        ),
        last_ride=last_ride,
        aggregate=AggregateStats(
            total_rides=100,
            total_distance_km=5000.0,
            total_ride_time_hours=200.0,
            total_calories_kcal=50000.0,
            total_elevation_gain_m=10000.0,
            average_speed_kmh=25.0,
        ),
        battery=battery,
        location=location,
        alarm=AlarmStatus(alarm_triggered=False, alarm_armed=True),
        has_flow_plus=has_flow_plus,
        has_connect_module=has_connect_module,
        last_updated=_NOW,
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
    return coord


def _make_entry(unit_system: str = UNIT_METRIC) -> MagicMock:
    entry = MagicMock()
    entry.options = {CONF_UNIT_SYSTEM: unit_system}
    return entry


def _make_sensor(
    description: BoschEBikeSensorDescription,
    bike_data: BikeData | None = None,
    *,
    unit_system: str = UNIT_METRIC,
    last_update_success: bool = True,
    bike_id: str = "bike1",
) -> BoschEBikeSensor:
    if bike_data is None:
        bike_data = _make_bike_data()
    coordinator = _make_coordinator(
        bike_data, last_update_success=last_update_success, bike_id=bike_id
    )
    entry = _make_entry(unit_system)
    sensor = BoschEBikeSensor.__new__(BoschEBikeSensor)
    # Bypass CoordinatorEntity.__init__ to avoid needing a real hass instance
    sensor.coordinator = coordinator
    sensor.entity_description = description
    sensor._entry = entry
    sensor._bike_id = bike_id
    sensor._attr_unique_id = f"{bike_id}_{description.key}"
    from homeassistant.helpers.device_registry import DeviceInfo
    sensor._attr_device_info = DeviceInfo(identifiers={(DOMAIN, bike_id)})
    return sensor


def _get_description(key: str) -> BoschEBikeSensorDescription:
    for desc in BIKE_SENSORS:
        if desc.key == key:
            return desc
    raise KeyError(f"No sensor description with key={key!r}")


# ---------------------------------------------------------------------------
# Tests: unique_id and device_info
# ---------------------------------------------------------------------------


class TestUniqueIdAndDeviceInfo:
    def test_unique_id_format(self):
        desc = _get_description("odometer")
        sensor = _make_sensor(desc, bike_id="bike42")
        assert sensor.unique_id == "bike42_odometer"

    def test_unique_id_includes_sensor_key(self):
        desc = _get_description("battery_soc")
        sensor = _make_sensor(desc, bike_id="myBike")
        assert sensor.unique_id == "myBike_battery_soc"

    def test_device_info_identifiers(self):
        desc = _get_description("odometer")
        sensor = _make_sensor(desc, bike_id="bike99")
        assert (DOMAIN, "bike99") in sensor.device_info["identifiers"]

    def test_unique_ids_are_unique_across_sensors(self):
        bike_id = "bike1"
        ids = [f"{bike_id}_{desc.key}" for desc in BIKE_SENSORS]
        assert len(ids) == len(set(ids)), "Duplicate unique_id keys found"

    def test_unique_ids_are_unique_across_bikes(self):
        all_ids = []
        for bike_id in ["bike1", "bike2"]:
            for desc in BIKE_SENSORS:
                all_ids.append(f"{bike_id}_{desc.key}")
        assert len(all_ids) == len(set(all_ids))


# ---------------------------------------------------------------------------
# Tests: available property
# ---------------------------------------------------------------------------


class TestAvailable:
    def test_available_when_coordinator_success_and_field_not_none(self):
        desc = _get_description("odometer")
        sensor = _make_sensor(desc, _make_bike_data(odometer_km=100.0))
        assert sensor.available is True

    def test_unavailable_when_coordinator_failed(self):
        desc = _get_description("odometer")
        sensor = _make_sensor(
            desc, _make_bike_data(odometer_km=100.0), last_update_success=False
        )
        assert sensor.available is False

    def test_unavailable_when_source_field_is_none(self):
        desc = _get_description("odometer")
        sensor = _make_sensor(desc, _make_bike_data(odometer_km=None))
        assert sensor.available is False

    def test_unavailable_when_coordinator_data_is_none(self):
        desc = _get_description("odometer")
        coordinator = _make_coordinator(None)  # type: ignore[arg-type]
        coordinator.data = None
        entry = _make_entry()
        sensor = BoschEBikeSensor.__new__(BoschEBikeSensor)
        sensor.coordinator = coordinator
        sensor.entity_description = desc
        sensor._entry = entry
        sensor._bike_id = "bike1"
        from homeassistant.helpers.device_registry import DeviceInfo
        sensor._attr_device_info = DeviceInfo(identifiers={(DOMAIN, "bike1")})
        assert sensor.available is False

    def test_flow_plus_sensor_unavailable_when_no_flow_plus(self):
        desc = _get_description("battery_soc")
        sensor = _make_sensor(desc, _make_bike_data(has_flow_plus=False))
        assert sensor.available is False

    def test_flow_plus_sensor_available_when_flow_plus_active(self):
        desc = _get_description("battery_soc")
        sensor = _make_sensor(desc, _make_bike_data(has_flow_plus=True))
        assert sensor.available is True

    def test_connect_module_sensor_unavailable_when_no_module(self):
        desc = _get_description("bike_location_accuracy")
        sensor = _make_sensor(desc, _make_bike_data(has_connect_module=False))
        assert sensor.available is False

    def test_connect_module_sensor_available_when_module_present(self):
        desc = _get_description("bike_location_accuracy")
        sensor = _make_sensor(desc, _make_bike_data(has_connect_module=True))
        assert sensor.available is True


# ---------------------------------------------------------------------------
# Tests: native_value
# ---------------------------------------------------------------------------


class TestNativeValue:
    def test_odometer_metric(self):
        desc = _get_description("odometer")
        sensor = _make_sensor(desc, _make_bike_data(odometer_km=1234.5))
        assert sensor.native_value == 1234.5

    def test_odometer_imperial(self):
        desc = _get_description("odometer")
        sensor = _make_sensor(
            desc, _make_bike_data(odometer_km=1000.0), unit_system=UNIT_IMPERIAL
        )
        assert sensor.native_value == round(1000.0 * KM_TO_MILES, 3)

    def test_max_assist_speed_metric(self):
        desc = _get_description("max_assist_speed")
        sensor = _make_sensor(desc, _make_bike_data(max_speed=25.0))
        assert sensor.native_value == 25.0

    def test_max_assist_speed_imperial(self):
        desc = _get_description("max_assist_speed")
        sensor = _make_sensor(
            desc, _make_bike_data(max_speed=25.0), unit_system=UNIT_IMPERIAL
        )
        assert sensor.native_value == round(25.0 * KMH_TO_MPH, 3)

    def test_motor_hours_no_conversion(self):
        desc = _get_description("motor_hours")
        sensor = _make_sensor(desc, _make_bike_data(motor_hours=100.0))
        assert sensor.native_value == 100.0

    def test_battery_charge_cycles_no_conversion(self):
        desc = _get_description("battery_charge_cycles")
        sensor = _make_sensor(desc, _make_bike_data(battery_cycles=50))
        assert sensor.native_value == 50

    def test_last_ride_distance_metric(self):
        desc = _get_description("last_ride_distance")
        sensor = _make_sensor(desc)
        assert sensor.native_value == 42.0

    def test_last_ride_distance_imperial(self):
        desc = _get_description("last_ride_distance")
        sensor = _make_sensor(desc, unit_system=UNIT_IMPERIAL)
        assert sensor.native_value == round(42.0 * KM_TO_MILES, 3)

    def test_last_ride_elevation_gain_imperial(self):
        desc = _get_description("last_ride_elevation_gain")
        sensor = _make_sensor(desc, unit_system=UNIT_IMPERIAL)
        assert sensor.native_value == round(300.0 * M_TO_FEET, 3)

    def test_total_distance_metric(self):
        desc = _get_description("total_distance")
        sensor = _make_sensor(desc)
        assert sensor.native_value == 5000.0

    def test_total_distance_imperial(self):
        desc = _get_description("total_distance")
        sensor = _make_sensor(desc, unit_system=UNIT_IMPERIAL)
        assert sensor.native_value == round(5000.0 * KM_TO_MILES, 3)

    def test_battery_soc_value(self):
        desc = _get_description("battery_soc")
        sensor = _make_sensor(desc, _make_bike_data(has_flow_plus=True))
        assert sensor.native_value == 85

    def test_battery_soc_unavailable_when_no_flow_plus(self):
        from homeassistant.const import STATE_UNAVAILABLE
        desc = _get_description("battery_soc")
        sensor = _make_sensor(desc, _make_bike_data(has_flow_plus=False))
        assert sensor.native_value == STATE_UNAVAILABLE

    def test_connect_module_sensor_unavailable_when_no_module(self):
        from homeassistant.const import STATE_UNAVAILABLE
        desc = _get_description("bike_location_accuracy")
        sensor = _make_sensor(desc, _make_bike_data(has_connect_module=False))
        assert sensor.native_value == STATE_UNAVAILABLE

    def test_bike_location_accuracy_metric(self):
        desc = _get_description("bike_location_accuracy")
        sensor = _make_sensor(desc, _make_bike_data(has_connect_module=True))
        assert sensor.native_value == 5.0

    def test_bike_location_accuracy_imperial(self):
        desc = _get_description("bike_location_accuracy")
        sensor = _make_sensor(
            desc, _make_bike_data(has_connect_module=True), unit_system=UNIT_IMPERIAL
        )
        assert sensor.native_value == round(5.0 * M_TO_FEET, 3)

    def test_none_when_coordinator_failed(self):
        desc = _get_description("odometer")
        sensor = _make_sensor(
            desc, _make_bike_data(odometer_km=100.0), last_update_success=False
        )
        assert sensor.native_value is None

    def test_none_when_source_field_is_none(self):
        desc = _get_description("odometer")
        sensor = _make_sensor(desc, _make_bike_data(odometer_km=None))
        assert sensor.native_value is None

    def test_last_ride_none_when_no_rides(self):
        desc = _get_description("last_ride_distance")
        data = _make_bike_data()
        data = BikeData(
            info=data.info,
            telemetry=data.telemetry,
            last_ride=None,
            aggregate=data.aggregate,
            battery=data.battery,
            location=data.location,
            alarm=data.alarm,
            has_flow_plus=data.has_flow_plus,
            has_connect_module=data.has_connect_module,
            last_updated=data.last_updated,
        )
        sensor = _make_sensor(desc, data)
        assert sensor.native_value is None


# ---------------------------------------------------------------------------
# Tests: native_unit_of_measurement
# ---------------------------------------------------------------------------


class TestNativeUnitOfMeasurement:
    def test_odometer_metric_unit(self):
        desc = _get_description("odometer")
        sensor = _make_sensor(desc)
        assert sensor.native_unit_of_measurement == "km"

    def test_odometer_imperial_unit(self):
        desc = _get_description("odometer")
        sensor = _make_sensor(desc, unit_system=UNIT_IMPERIAL)
        assert sensor.native_unit_of_measurement == "mi"

    def test_speed_metric_unit(self):
        desc = _get_description("max_assist_speed")
        sensor = _make_sensor(desc)
        assert sensor.native_unit_of_measurement == "km/h"

    def test_speed_imperial_unit(self):
        desc = _get_description("max_assist_speed")
        sensor = _make_sensor(desc, unit_system=UNIT_IMPERIAL)
        assert sensor.native_unit_of_measurement == "mph"

    def test_elevation_metric_unit(self):
        desc = _get_description("last_ride_elevation_gain")
        sensor = _make_sensor(desc)
        assert sensor.native_unit_of_measurement == "m"

    def test_elevation_imperial_unit(self):
        desc = _get_description("last_ride_elevation_gain")
        sensor = _make_sensor(desc, unit_system=UNIT_IMPERIAL)
        assert sensor.native_unit_of_measurement == "ft"

    def test_motor_hours_unit_is_h(self):
        desc = _get_description("motor_hours")
        sensor = _make_sensor(desc)
        assert sensor.native_unit_of_measurement == "h"

    def test_battery_soc_unit_is_percent(self):
        desc = _get_description("battery_soc")
        sensor = _make_sensor(desc)
        assert sensor.native_unit_of_measurement == "%"

    def test_cadence_unit_is_rpm(self):
        desc = _get_description("last_ride_avg_cadence")
        sensor = _make_sensor(desc)
        assert sensor.native_unit_of_measurement == "RPM"

    def test_power_unit_is_watts(self):
        desc = _get_description("last_ride_avg_rider_power")
        sensor = _make_sensor(desc)
        assert sensor.native_unit_of_measurement == "W"


# ---------------------------------------------------------------------------
# Tests: extra_state_attributes
# ---------------------------------------------------------------------------


class TestExtraStateAttributes:
    def test_last_updated_present(self):
        desc = _get_description("odometer")
        sensor = _make_sensor(desc)
        attrs = sensor.extra_state_attributes
        assert "last_updated" in attrs

    def test_last_updated_is_iso_string(self):
        desc = _get_description("odometer")
        sensor = _make_sensor(desc)
        attrs = sensor.extra_state_attributes
        # Should be parseable as ISO 8601
        parsed = datetime.fromisoformat(attrs["last_updated"])
        assert parsed == _NOW

    def test_last_updated_empty_when_no_data(self):
        desc = _get_description("odometer")
        coordinator = _make_coordinator(None)  # type: ignore[arg-type]
        coordinator.data = None
        entry = _make_entry()
        sensor = BoschEBikeSensor.__new__(BoschEBikeSensor)
        sensor.coordinator = coordinator
        sensor.entity_description = desc
        sensor._entry = entry
        sensor._bike_id = "bike1"
        from homeassistant.helpers.device_registry import DeviceInfo
        sensor._attr_device_info = DeviceInfo(identifiers={(DOMAIN, "bike1")})
        attrs = sensor.extra_state_attributes
        assert "last_updated" not in attrs


# ---------------------------------------------------------------------------
# Tests: sensor description coverage
# ---------------------------------------------------------------------------


class TestSensorDescriptions:
    def test_all_expected_keys_present(self):
        expected_keys = {
            # Bike telemetry
            "odometer",
            "motor_hours",
            "battery_charge_cycles",
            "battery_lifetime_energy",
            "next_service_odometer",
            "max_assist_speed",
            # Last ride
            "last_ride_distance",
            "last_ride_duration",
            "last_ride_avg_speed",
            "last_ride_max_speed",
            "last_ride_elevation_gain",
            "last_ride_elevation_loss",
            "last_ride_calories",
            "last_ride_date",
            # Aggregate
            "total_rides",
            "total_distance",
            "total_ride_time",
            "total_calories",
            "total_elevation_gain",
            "average_speed",
            # Flow+
            "last_ride_avg_rider_power",
            "last_ride_max_rider_power",
            "last_ride_avg_cadence",
            "last_ride_max_cadence",
            "last_ride_motor_power_ratio",
            "battery_soc",
            "battery_charging_status",
            # ConnectModule
            "bike_location_accuracy",
            "bike_location_timestamp",
        }
        actual_keys = {desc.key for desc in BIKE_SENSORS}
        assert expected_keys == actual_keys

    def test_flow_plus_sensors_have_flag(self):
        flow_plus_keys = {
            "last_ride_avg_rider_power",
            "last_ride_max_rider_power",
            "last_ride_avg_cadence",
            "last_ride_max_cadence",
            "last_ride_motor_power_ratio",
            "battery_soc",
            "battery_charging_status",
        }
        for desc in BIKE_SENSORS:
            if desc.key in flow_plus_keys:
                assert desc.requires_flow_plus, f"{desc.key} should have requires_flow_plus=True"
            else:
                assert not desc.requires_flow_plus, f"{desc.key} should not have requires_flow_plus=True"

    def test_connect_module_sensors_have_flag(self):
        connect_keys = {"bike_location_accuracy", "bike_location_timestamp"}
        for desc in BIKE_SENSORS:
            if desc.key in connect_keys:
                assert desc.requires_connect_module, f"{desc.key} should have requires_connect_module=True"
            else:
                assert not desc.requires_connect_module, f"{desc.key} should not have requires_connect_module=True"

    def test_distance_sensors_have_unit_fn(self):
        distance_keys = {
            "odometer",
            "next_service_odometer",
            "last_ride_distance",
            "last_ride_elevation_gain",
            "last_ride_elevation_loss",
            "total_distance",
            "total_elevation_gain",
            "bike_location_accuracy",
        }
        for desc in BIKE_SENSORS:
            if desc.key in distance_keys:
                assert desc.unit_fn is not None, f"{desc.key} should have a unit_fn"

    def test_speed_sensors_have_unit_fn(self):
        speed_keys = {
            "max_assist_speed",
            "last_ride_avg_speed",
            "last_ride_max_speed",
            "average_speed",
        }
        for desc in BIKE_SENSORS:
            if desc.key in speed_keys:
                assert desc.unit_fn is not None, f"{desc.key} should have a unit_fn"

    def test_non_convertible_sensors_have_no_unit_fn(self):
        no_convert_keys = {
            "motor_hours",
            "battery_charge_cycles",
            "battery_lifetime_energy",
            "last_ride_duration",
            "last_ride_calories",
            "last_ride_date",
            "total_rides",
            "total_ride_time",
            "total_calories",
            "last_ride_avg_rider_power",
            "last_ride_max_rider_power",
            "last_ride_avg_cadence",
            "last_ride_max_cadence",
            "last_ride_motor_power_ratio",
            "battery_soc",
            "battery_charging_status",
            "bike_location_timestamp",
        }
        for desc in BIKE_SENSORS:
            if desc.key in no_convert_keys:
                assert desc.unit_fn is None, f"{desc.key} should not have a unit_fn"


# ---------------------------------------------------------------------------
# Tests: backward-compatibility default for missing unit_system option
# (Requirement 13.9)
# ---------------------------------------------------------------------------


class TestUnitSystemBackwardCompatibility:
    """Verify that sensors default to metric when unit_system is absent from options.

    Requirement 13.9: When the unit_system option is absent from the config entry
    (e.g. for entries created before this feature was introduced), the integration
    SHALL default to "metric" to preserve backward compatibility.
    """

    def _make_sensor_no_unit_option(
        self, key: str, bike_data: BikeData | None = None
    ) -> BoschEBikeSensor:
        """Create a sensor whose config entry has NO unit_system key in options."""
        if bike_data is None:
            bike_data = _make_bike_data()
        coordinator = _make_coordinator(bike_data)
        # Entry with empty options — simulates a pre-unit-system config entry
        entry = MagicMock()
        entry.options = {}  # unit_system key is absent
        sensor = BoschEBikeSensor.__new__(BoschEBikeSensor)
        sensor.coordinator = coordinator
        sensor.entity_description = _get_description(key)
        sensor._entry = entry
        sensor._bike_id = "bike1"
        sensor._attr_unique_id = f"bike1_{key}"
        from homeassistant.helpers.device_registry import DeviceInfo
        sensor._attr_device_info = DeviceInfo(identifiers={(DOMAIN, "bike1")})
        return sensor

    def test_odometer_native_value_defaults_to_metric(self):
        """native_value for a distance sensor defaults to km (no conversion) when option absent."""
        sensor = self._make_sensor_no_unit_option("odometer", _make_bike_data(odometer_km=1000.0))
        # Metric: value unchanged
        assert sensor.native_value == 1000.0

    def test_odometer_native_unit_defaults_to_km(self):
        """native_unit_of_measurement for a distance sensor defaults to 'km' when option absent."""
        sensor = self._make_sensor_no_unit_option("odometer")
        assert sensor.native_unit_of_measurement == "km"

    def test_speed_native_value_defaults_to_metric(self):
        """native_value for a speed sensor defaults to km/h (no conversion) when option absent."""
        sensor = self._make_sensor_no_unit_option("max_assist_speed", _make_bike_data(max_speed=25.0))
        assert sensor.native_value == 25.0

    def test_speed_native_unit_defaults_to_kmh(self):
        """native_unit_of_measurement for a speed sensor defaults to 'km/h' when option absent."""
        sensor = self._make_sensor_no_unit_option("max_assist_speed")
        assert sensor.native_unit_of_measurement == "km/h"

    def test_elevation_native_value_defaults_to_metric(self):
        """native_value for an elevation sensor defaults to metres (no conversion) when option absent."""
        sensor = self._make_sensor_no_unit_option("last_ride_elevation_gain")
        assert sensor.native_value == 300.0  # raw metres from _make_bike_data

    def test_elevation_native_unit_defaults_to_m(self):
        """native_unit_of_measurement for an elevation sensor defaults to 'm' when option absent."""
        sensor = self._make_sensor_no_unit_option("last_ride_elevation_gain")
        assert sensor.native_unit_of_measurement == "m"

    def test_all_convertible_sensors_default_to_metric_unit(self):
        """Every sensor with a unit_fn must return a metric unit when options is empty."""
        metric_units = {"km", "km/h", "m"}
        for desc in BIKE_SENSORS:
            if desc.unit_fn is None:
                continue
            sensor = self._make_sensor_no_unit_option(desc.key)
            unit = sensor.native_unit_of_measurement
            assert unit in metric_units, (
                f"Sensor '{desc.key}' returned unit '{unit}' when options is empty; "
                f"expected one of {metric_units} (metric default)"
            )


# ---------------------------------------------------------------------------
# Helper for BatterySocSensor tests
# ---------------------------------------------------------------------------


def _make_battery_soc_sensor(
    soc: int | None = 80,
    *,
    has_flow_plus: bool = True,
    prev_soc: int | None = None,
) -> BatterySocSensor:
    """Create a BatterySocSensor with the given SoC value and previous SoC."""
    # Build a BikeData with the exact battery we want (including None battery).
    battery = BatteryStatus(state_of_charge_pct=soc, charging_status="discharging") if soc is not None else None
    # Build bike_data and override the battery field directly (dataclass is mutable).
    bike_data = _make_bike_data(has_flow_plus=has_flow_plus)
    bike_data.battery = battery
    desc = _get_description("battery_soc")
    coordinator = _make_coordinator(bike_data)
    entry = _make_entry()

    sensor = BatterySocSensor.__new__(BatterySocSensor)
    sensor.coordinator = coordinator
    sensor.entity_description = desc
    sensor._entry = entry
    sensor._bike_id = "bike1"
    sensor._attr_unique_id = "bike1_battery_soc"
    sensor._prev_soc = prev_soc
    from homeassistant.helpers.device_registry import DeviceInfo
    sensor._attr_device_info = DeviceInfo(identifiers={(DOMAIN, "bike1")})
    return sensor


# ---------------------------------------------------------------------------
# Tests: BatterySocSensor — _handle_coordinator_update change detection
# ---------------------------------------------------------------------------


class TestBatterySocSensor:
    """Tests for BatterySocSensor._handle_coordinator_update SoC filtering."""

    def _call_update(self, sensor: BatterySocSensor) -> bool:
        """Call _handle_coordinator_update and return whether super() was called.

        We detect super() calls by patching CoordinatorEntity._handle_coordinator_update
        on the stub class.
        """
        from unittest.mock import patch
        from homeassistant.helpers.update_coordinator import CoordinatorEntity

        called = []

        original = CoordinatorEntity._handle_coordinator_update

        def recording_super(self_inner):
            called.append(True)

        with patch.object(CoordinatorEntity, "_handle_coordinator_update", recording_super):
            sensor._handle_coordinator_update()

        return bool(called)

    # --- First update (prev_soc is None) ---

    def test_first_update_always_propagates(self):
        """When prev_soc is None, the first update always fires."""
        sensor = _make_battery_soc_sensor(soc=80, prev_soc=None)
        propagated = self._call_update(sensor)
        assert propagated is True

    def test_first_update_sets_prev_soc(self):
        """After the first update, _prev_soc is set to the new value."""
        sensor = _make_battery_soc_sensor(soc=80, prev_soc=None)
        self._call_update(sensor)
        assert sensor._prev_soc == 80

    # --- Change >= 1 % ---

    def test_change_of_exactly_1_propagates(self):
        """A change of exactly 1 % must fire the state-changed event."""
        sensor = _make_battery_soc_sensor(soc=81, prev_soc=80)
        propagated = self._call_update(sensor)
        assert propagated is True

    def test_change_of_more_than_1_propagates(self):
        """A change of more than 1 % must fire the state-changed event."""
        sensor = _make_battery_soc_sensor(soc=90, prev_soc=80)
        propagated = self._call_update(sensor)
        assert propagated is True

    def test_decrease_of_1_propagates(self):
        """A decrease of exactly 1 % must fire the state-changed event."""
        sensor = _make_battery_soc_sensor(soc=79, prev_soc=80)
        propagated = self._call_update(sensor)
        assert propagated is True

    def test_prev_soc_updated_after_propagating_change(self):
        """After a propagated update, _prev_soc reflects the new value."""
        sensor = _make_battery_soc_sensor(soc=85, prev_soc=80)
        self._call_update(sensor)
        assert sensor._prev_soc == 85

    # --- Change < 1 % ---

    def test_no_change_suppressed(self):
        """Identical SoC values must NOT fire the state-changed event."""
        sensor = _make_battery_soc_sensor(soc=80, prev_soc=80)
        propagated = self._call_update(sensor)
        assert propagated is False

    def test_prev_soc_unchanged_when_suppressed(self):
        """When the update is suppressed, _prev_soc must not change."""
        sensor = _make_battery_soc_sensor(soc=80, prev_soc=80)
        self._call_update(sensor)
        assert sensor._prev_soc == 80

    # --- None SoC ---

    def test_none_soc_always_propagates(self):
        """When new SoC is None, the update must always propagate."""
        sensor = _make_battery_soc_sensor(soc=None, prev_soc=80)
        propagated = self._call_update(sensor)
        assert propagated is True

    def test_none_soc_sets_prev_soc_to_none(self):
        """When new SoC is None, _prev_soc is set to None."""
        sensor = _make_battery_soc_sensor(soc=None, prev_soc=80)
        self._call_update(sensor)
        assert sensor._prev_soc is None

    # --- async_setup_entry creates BatterySocSensor for battery_soc key ---

    @pytest.mark.asyncio
    async def test_async_setup_entry_creates_battery_soc_sensor(self):
        """async_setup_entry must create a BatterySocSensor for battery_soc."""
        from custom_components.bosch_ebike_ha.sensor import async_setup_entry

        mock_hass = MagicMock()
        mock_entry = _make_entry()

        bike_data = _make_bike_data()
        coord = _make_coordinator(bike_data)
        mock_hass.data = {DOMAIN: {mock_entry.entry_id: {"coordinators": [coord]}}}

        added_entities: list[Any] = []
        await async_setup_entry(mock_hass, mock_entry, lambda e: added_entities.extend(e))

        battery_soc_entities = [e for e in added_entities if isinstance(e, BatterySocSensor)]
        assert len(battery_soc_entities) == 1

    @pytest.mark.asyncio
    async def test_async_setup_entry_other_sensors_are_base_class(self):
        """Non-battery_soc sensors must be plain BoschEBikeSensor instances."""
        from custom_components.bosch_ebike_ha.sensor import async_setup_entry

        mock_hass = MagicMock()
        mock_entry = _make_entry()

        bike_data = _make_bike_data()
        coord = _make_coordinator(bike_data)
        mock_hass.data = {DOMAIN: {mock_entry.entry_id: {"coordinators": [coord]}}}

        added_entities: list[Any] = []
        await async_setup_entry(mock_hass, mock_entry, lambda e: added_entities.extend(e))

        non_soc = [e for e in added_entities if not isinstance(e, BatterySocSensor)]
        # All non-BatterySocSensor entities should still be BoschEBikeSensor instances
        for entity in non_soc:
            assert isinstance(entity, BoschEBikeSensor)
