"""Options flow integration test for Bosch eBike (Smart System) integration.

Task 14.2 — Options flow integration test

Scenario:
1. Start with a config entry whose ``unit_system`` option is ``"metric"``.
2. Submit the options flow with ``unit_system = "imperial"``.
3. Assert the config entry is reloaded (``hass.config_entries.async_reload``
   is called with the entry's ``entry_id``).
4. After the reload, simulate a coordinator update and assert that all
   distance, speed, and elevation sensor entities report imperial values
   and units.

Requirements: 13.5, 13.6
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Integration imports
# ---------------------------------------------------------------------------
from custom_components.bosch_ebike_ha.config_flow import BoschEBikeOptionsFlow
from custom_components.bosch_ebike_ha.const import (
    CONF_UNIT_SYSTEM,
    DOMAIN,
    UNIT_IMPERIAL,
    UNIT_METRIC,
)
from custom_components.bosch_ebike_ha.models import (
    AggregateStats,
    BikeData,
    BikeInfo,
    BikeTelemetry,
    RideData,
)
from custom_components.bosch_ebike_ha.sensor import BIKE_SENSORS, BoschEBikeSensor
from custom_components.bosch_ebike_ha.unit_converter import (
    KM_TO_MILES,
    KMH_TO_MPH,
    M_TO_FEET,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

# Known metric values used in the test BikeData fixture.
_ODOMETER_KM = 1234.5
_NEXT_SERVICE_KM = 2000.0
_MAX_ASSIST_SPEED_KMH = 25.0
_LAST_RIDE_DISTANCE_KM = 42.0
_LAST_RIDE_AVG_SPEED_KMH = 21.0
_LAST_RIDE_MAX_SPEED_KMH = 38.5
_LAST_RIDE_ELEVATION_GAIN_M = 350.0
_LAST_RIDE_ELEVATION_LOSS_M = 320.0
_TOTAL_DISTANCE_KM = 5000.0
_TOTAL_ELEVATION_GAIN_M = 12000.0
_AVERAGE_SPEED_KMH = 22.5


def _make_bike_data() -> BikeData:
    """Return a fully-populated BikeData instance with known metric values."""
    return BikeData(
        info=BikeInfo(
            bike_id="test-bike-001",
            name="Test Bike",
            model="Cube Stereo",
            serial_number="SN-001",
        ),
        telemetry=BikeTelemetry(
            odometer_km=_ODOMETER_KM,
            motor_hours_total=50.0,
            motor_hours_with_assist=40.0,
            battery_charge_cycles=30,
            battery_lifetime_energy_wh=3000.0,
            next_service_odometer_km=_NEXT_SERVICE_KM,
            max_assist_speed_kmh=_MAX_ASSIST_SPEED_KMH,
        ),
        last_ride=RideData(
            ride_id="r1",
            completed_at=_NOW,
            distance_km=_LAST_RIDE_DISTANCE_KM,
            duration_minutes=120.0,
            average_speed_kmh=_LAST_RIDE_AVG_SPEED_KMH,
            max_speed_kmh=_LAST_RIDE_MAX_SPEED_KMH,
            elevation_gain_m=_LAST_RIDE_ELEVATION_GAIN_M,
            elevation_loss_m=_LAST_RIDE_ELEVATION_LOSS_M,
            calories_kcal=800.0,
            avg_rider_power_w=None,
            max_rider_power_w=None,
            avg_cadence_rpm=None,
            max_cadence_rpm=None,
            motor_power_ratio_pct=None,
        ),
        aggregate=AggregateStats(
            total_rides=100,
            total_distance_km=_TOTAL_DISTANCE_KM,
            total_ride_time_hours=200.0,
            total_calories_kcal=50000.0,
            total_elevation_gain_m=_TOTAL_ELEVATION_GAIN_M,
            average_speed_kmh=_AVERAGE_SPEED_KMH,
        ),
        battery=None,
        location=None,
        alarm=None,
        has_flow_plus=False,
        has_connect_module=False,
        last_updated=_NOW,
    )


def _make_config_entry(unit_system: str = UNIT_METRIC) -> MagicMock:
    """Return a mock ConfigEntry with the given unit_system option."""
    entry = MagicMock()
    entry.entry_id = "options_flow_test_entry"
    entry.domain = DOMAIN
    entry.options = {CONF_UNIT_SYSTEM: unit_system}
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock(return_value=lambda: None)
    return entry


def _make_coordinator(entry: MagicMock, bike_data: BikeData) -> MagicMock:
    """Return a mock BikeCoordinator with the given data."""
    coord = MagicMock()
    coord.bike_id = bike_data.info.bike_id
    coord.data = bike_data
    coord.last_update_success = True
    return coord


def _make_sensor(
    coordinator: MagicMock,
    entry: MagicMock,
    description_key: str,
) -> BoschEBikeSensor | None:
    """Instantiate a BoschEBikeSensor for the given description key."""
    for desc in BIKE_SENSORS:
        if desc.key == description_key:
            return BoschEBikeSensor(coordinator, entry, desc)
    return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOptionsFlowSubmit:
    """Unit tests for BoschEBikeOptionsFlow.async_step_init."""

    @pytest.mark.asyncio
    async def test_options_flow_shows_form_when_no_input(self):
        """async_step_init with no user_input must return a form."""
        entry = _make_config_entry(UNIT_METRIC)
        flow = BoschEBikeOptionsFlow(entry)

        result = await flow.async_step_init(user_input=None)

        assert result["type"] == "form"
        assert result["step_id"] == "init"

    @pytest.mark.asyncio
    async def test_options_flow_creates_entry_with_imperial(self):
        """Submitting imperial must return async_create_entry with imperial data."""
        entry = _make_config_entry(UNIT_METRIC)
        flow = BoschEBikeOptionsFlow(entry)

        result = await flow.async_step_init(user_input={CONF_UNIT_SYSTEM: UNIT_IMPERIAL})

        assert result["type"] == "create_entry"
        assert result["data"][CONF_UNIT_SYSTEM] == UNIT_IMPERIAL

    @pytest.mark.asyncio
    async def test_options_flow_creates_entry_with_metric(self):
        """Submitting metric must return async_create_entry with metric data."""
        entry = _make_config_entry(UNIT_IMPERIAL)
        flow = BoschEBikeOptionsFlow(entry)

        result = await flow.async_step_init(user_input={CONF_UNIT_SYSTEM: UNIT_METRIC})

        assert result["type"] == "create_entry"
        assert result["data"][CONF_UNIT_SYSTEM] == UNIT_METRIC

    @pytest.mark.asyncio
    async def test_options_flow_form_prepopulated_with_current_value(self):
        """The form schema default must reflect the current unit_system option."""
        entry = _make_config_entry(UNIT_IMPERIAL)
        flow = BoschEBikeOptionsFlow(entry)

        result = await flow.async_step_init(user_input=None)

        # The schema should be present and the default should be imperial
        assert result["type"] == "form"
        schema = result.get("data_schema")
        assert schema is not None
        # Inspect the schema's default for CONF_UNIT_SYSTEM
        for key in schema.schema:
            if hasattr(key, "schema") and key.schema == CONF_UNIT_SYSTEM:
                assert key.default() == UNIT_IMPERIAL
                break


class TestConfigEntryReloadOnOptionsChange:
    """Assert that changing unit_system triggers a config entry reload.

    The update_listener registered in async_setup_entry calls
    ``hass.config_entries.async_reload(entry.entry_id)`` when options change.
    This test verifies that wiring by calling the listener directly.

    Requirements: 13.5, 13.6
    """

    @pytest.mark.asyncio
    async def test_update_listener_calls_async_reload(self):
        """The update_listener must call hass.config_entries.async_reload."""
        import custom_components.bosch_ebike_ha as _init_mod
        from custom_components.bosch_ebike_ha import _async_update_listener

        hass = MagicMock()
        hass.config_entries = MagicMock()
        hass.config_entries.async_reload = AsyncMock(return_value=None)

        entry = _make_config_entry(UNIT_IMPERIAL)

        await _async_update_listener(hass, entry)

        hass.config_entries.async_reload.assert_called_once_with(entry.entry_id)

    @pytest.mark.asyncio
    async def test_setup_entry_registers_update_listener(self):
        """async_setup_entry must register an update_listener on the entry.

        Verifies that entry.add_update_listener is called during setup,
        which is the mechanism that triggers reload on options change.

        Requirements: 13.6
        """
        import custom_components.bosch_ebike_ha as _init_mod
        from custom_components.bosch_ebike_ha import async_setup_entry

        bike_info = BikeInfo(
            bike_id="bike-listener-test",
            name="Listener Test Bike",
            model="Test Model",
            serial_number="SN-LT",
        )
        mock_client = MagicMock()
        mock_client.fetch_bikes = AsyncMock(return_value=[bike_info])

        hass = MagicMock()
        hass.data = {}
        hass.config_entries = MagicMock()
        hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)

        entry = _make_config_entry(UNIT_METRIC)
        # Track whether add_update_listener was called
        listener_calls: list[Any] = []
        entry.add_update_listener = MagicMock(
            side_effect=lambda fn: listener_calls.append(fn) or (lambda: None)
        )

        mock_coordinator = MagicMock()
        mock_coordinator.bike_id = "bike-listener-test"
        mock_coordinator.async_config_entry_first_refresh = AsyncMock(return_value=None)
        mock_coordinator.data = _make_bike_data()
        mock_coordinator.data.has_flow_plus = False

        mock_dr = MagicMock()
        mock_dr.async_get_or_create = MagicMock()

        with (
            patch.object(_init_mod, "async_get_clientsession", return_value=MagicMock()),
            patch.object(_init_mod, "config_entry_oauth2_flow") as mock_oauth,
            patch.object(_init_mod, "BoschEBikeApiClient", return_value=mock_client),
            patch.object(_init_mod, "BikeCoordinator", return_value=mock_coordinator),
            patch.object(_init_mod, "BatteryCoordinator"),
            patch.object(_init_mod.dr, "async_get", return_value=mock_dr),
        ):
            mock_oauth.OAuth2Session.return_value = MagicMock()
            result = await async_setup_entry(hass, entry)

        assert result is True
        assert len(listener_calls) == 1, (
            "add_update_listener must be called exactly once during setup"
        )


class TestSensorImperialValuesAfterOptionsChange:
    """Assert that sensor entities report imperial values after unit_system changes.

    Simulates the state after a config entry reload with unit_system=imperial:
    - The entry.options dict is updated to imperial.
    - A coordinator update delivers fresh BikeData (metric values).
    - Sensor entities must report converted imperial values and units.

    Requirements: 13.3, 13.4, 13.5, 13.6, 13.7, 13.8
    """

    # ------------------------------------------------------------------
    # Distance sensors
    # ------------------------------------------------------------------

    def test_odometer_reports_miles_after_imperial_change(self):
        """Odometer sensor must report miles after switching to imperial."""
        entry = _make_config_entry(UNIT_IMPERIAL)
        coord = _make_coordinator(entry, _make_bike_data())
        sensor = _make_sensor(coord, entry, "odometer")
        assert sensor is not None

        expected_value = round(_ODOMETER_KM * KM_TO_MILES, 3)
        assert sensor.native_value == expected_value
        assert sensor.native_unit_of_measurement == "mi"

    def test_odometer_reports_km_in_metric(self):
        """Odometer sensor must report km when unit_system is metric."""
        entry = _make_config_entry(UNIT_METRIC)
        coord = _make_coordinator(entry, _make_bike_data())
        sensor = _make_sensor(coord, entry, "odometer")
        assert sensor is not None

        assert sensor.native_value == _ODOMETER_KM
        assert sensor.native_unit_of_measurement == "km"

    def test_next_service_odometer_reports_miles_after_imperial_change(self):
        """Next service odometer must report miles after switching to imperial."""
        entry = _make_config_entry(UNIT_IMPERIAL)
        coord = _make_coordinator(entry, _make_bike_data())
        sensor = _make_sensor(coord, entry, "next_service_odometer")
        assert sensor is not None

        expected_value = round(_NEXT_SERVICE_KM * KM_TO_MILES, 3)
        assert sensor.native_value == expected_value
        assert sensor.native_unit_of_measurement == "mi"

    def test_last_ride_distance_reports_miles_after_imperial_change(self):
        """Last ride distance must report miles after switching to imperial."""
        entry = _make_config_entry(UNIT_IMPERIAL)
        coord = _make_coordinator(entry, _make_bike_data())
        sensor = _make_sensor(coord, entry, "last_ride_distance")
        assert sensor is not None

        expected_value = round(_LAST_RIDE_DISTANCE_KM * KM_TO_MILES, 3)
        assert sensor.native_value == expected_value
        assert sensor.native_unit_of_measurement == "mi"

    def test_total_distance_reports_miles_after_imperial_change(self):
        """Total distance must report miles after switching to imperial."""
        entry = _make_config_entry(UNIT_IMPERIAL)
        coord = _make_coordinator(entry, _make_bike_data())
        sensor = _make_sensor(coord, entry, "total_distance")
        assert sensor is not None

        expected_value = round(_TOTAL_DISTANCE_KM * KM_TO_MILES, 3)
        assert sensor.native_value == expected_value
        assert sensor.native_unit_of_measurement == "mi"

    # ------------------------------------------------------------------
    # Speed sensors
    # ------------------------------------------------------------------

    def test_max_assist_speed_reports_mph_after_imperial_change(self):
        """Max assist speed must report mph after switching to imperial."""
        entry = _make_config_entry(UNIT_IMPERIAL)
        coord = _make_coordinator(entry, _make_bike_data())
        sensor = _make_sensor(coord, entry, "max_assist_speed")
        assert sensor is not None

        expected_value = round(_MAX_ASSIST_SPEED_KMH * KMH_TO_MPH, 3)
        assert sensor.native_value == expected_value
        assert sensor.native_unit_of_measurement == "mph"

    def test_last_ride_avg_speed_reports_mph_after_imperial_change(self):
        """Last ride average speed must report mph after switching to imperial."""
        entry = _make_config_entry(UNIT_IMPERIAL)
        coord = _make_coordinator(entry, _make_bike_data())
        sensor = _make_sensor(coord, entry, "last_ride_avg_speed")
        assert sensor is not None

        expected_value = round(_LAST_RIDE_AVG_SPEED_KMH * KMH_TO_MPH, 3)
        assert sensor.native_value == expected_value
        assert sensor.native_unit_of_measurement == "mph"

    def test_last_ride_max_speed_reports_mph_after_imperial_change(self):
        """Last ride max speed must report mph after switching to imperial."""
        entry = _make_config_entry(UNIT_IMPERIAL)
        coord = _make_coordinator(entry, _make_bike_data())
        sensor = _make_sensor(coord, entry, "last_ride_max_speed")
        assert sensor is not None

        expected_value = round(_LAST_RIDE_MAX_SPEED_KMH * KMH_TO_MPH, 3)
        assert sensor.native_value == expected_value
        assert sensor.native_unit_of_measurement == "mph"

    def test_average_speed_reports_mph_after_imperial_change(self):
        """Aggregate average speed must report mph after switching to imperial."""
        entry = _make_config_entry(UNIT_IMPERIAL)
        coord = _make_coordinator(entry, _make_bike_data())
        sensor = _make_sensor(coord, entry, "average_speed")
        assert sensor is not None

        expected_value = round(_AVERAGE_SPEED_KMH * KMH_TO_MPH, 3)
        assert sensor.native_value == expected_value
        assert sensor.native_unit_of_measurement == "mph"

    # ------------------------------------------------------------------
    # Elevation sensors
    # ------------------------------------------------------------------

    def test_last_ride_elevation_gain_reports_feet_after_imperial_change(self):
        """Last ride elevation gain must report feet after switching to imperial."""
        entry = _make_config_entry(UNIT_IMPERIAL)
        coord = _make_coordinator(entry, _make_bike_data())
        sensor = _make_sensor(coord, entry, "last_ride_elevation_gain")
        assert sensor is not None

        expected_value = round(_LAST_RIDE_ELEVATION_GAIN_M * M_TO_FEET, 3)
        assert sensor.native_value == expected_value
        assert sensor.native_unit_of_measurement == "ft"

    def test_last_ride_elevation_loss_reports_feet_after_imperial_change(self):
        """Last ride elevation loss must report feet after switching to imperial."""
        entry = _make_config_entry(UNIT_IMPERIAL)
        coord = _make_coordinator(entry, _make_bike_data())
        sensor = _make_sensor(coord, entry, "last_ride_elevation_loss")
        assert sensor is not None

        expected_value = round(_LAST_RIDE_ELEVATION_LOSS_M * M_TO_FEET, 3)
        assert sensor.native_value == expected_value
        assert sensor.native_unit_of_measurement == "ft"

    def test_total_elevation_gain_reports_feet_after_imperial_change(self):
        """Total elevation gain must report feet after switching to imperial."""
        entry = _make_config_entry(UNIT_IMPERIAL)
        coord = _make_coordinator(entry, _make_bike_data())
        sensor = _make_sensor(coord, entry, "total_elevation_gain")
        assert sensor is not None

        expected_value = round(_TOTAL_ELEVATION_GAIN_M * M_TO_FEET, 3)
        assert sensor.native_value == expected_value
        assert sensor.native_unit_of_measurement == "ft"

    # ------------------------------------------------------------------
    # Non-converted sensors must be unaffected
    # ------------------------------------------------------------------

    def test_motor_hours_unaffected_by_imperial_change(self):
        """Motor hours sensor must not be converted — always reports hours."""
        entry = _make_config_entry(UNIT_IMPERIAL)
        coord = _make_coordinator(entry, _make_bike_data())
        sensor = _make_sensor(coord, entry, "motor_hours")
        assert sensor is not None

        assert sensor.native_value == 50.0
        assert sensor.native_unit_of_measurement == "h"

    def test_last_ride_calories_unaffected_by_imperial_change(self):
        """Calories sensor must not be converted — always reports kcal."""
        entry = _make_config_entry(UNIT_IMPERIAL)
        coord = _make_coordinator(entry, _make_bike_data())
        sensor = _make_sensor(coord, entry, "last_ride_calories")
        assert sensor is not None

        assert sensor.native_value == 800.0
        assert sensor.native_unit_of_measurement == "kcal"

    def test_total_rides_unaffected_by_imperial_change(self):
        """Total rides sensor must not be converted — always a count."""
        entry = _make_config_entry(UNIT_IMPERIAL)
        coord = _make_coordinator(entry, _make_bike_data())
        sensor = _make_sensor(coord, entry, "total_rides")
        assert sensor is not None

        assert sensor.native_value == 100
        assert sensor.native_unit_of_measurement is None


class TestMetricToImperialTransition:
    """End-to-end simulation of the metric → imperial options flow transition.

    Simulates the full lifecycle:
    1. Entry starts with metric options.
    2. Sensors report metric values.
    3. Options flow is submitted with imperial.
    4. Entry options are updated (simulating the reload).
    5. Sensors now report imperial values on the next coordinator update.

    Requirements: 13.5, 13.6
    """

    def test_sensor_values_change_when_entry_options_updated(self):
        """Sensor values must change from metric to imperial when options are updated.

        This simulates what happens after a config entry reload: the entry
        object's options dict is updated to imperial, and the sensor reads
        the new value on the next property access.
        """
        # Start with metric
        entry = _make_config_entry(UNIT_METRIC)
        bike_data = _make_bike_data()
        coord = _make_coordinator(entry, bike_data)

        odometer_sensor = _make_sensor(coord, entry, "odometer")
        avg_speed_sensor = _make_sensor(coord, entry, "average_speed")
        elevation_sensor = _make_sensor(coord, entry, "last_ride_elevation_gain")

        assert odometer_sensor is not None
        assert avg_speed_sensor is not None
        assert elevation_sensor is not None

        # --- Phase 1: metric ---
        assert odometer_sensor.native_value == _ODOMETER_KM
        assert odometer_sensor.native_unit_of_measurement == "km"
        assert avg_speed_sensor.native_value == _AVERAGE_SPEED_KMH
        assert avg_speed_sensor.native_unit_of_measurement == "km/h"
        assert elevation_sensor.native_value == _LAST_RIDE_ELEVATION_GAIN_M
        assert elevation_sensor.native_unit_of_measurement == "m"

        # --- Phase 2: simulate options flow submission + entry reload ---
        # After the options flow saves imperial and the entry is reloaded,
        # the new entry object has options = {CONF_UNIT_SYSTEM: UNIT_IMPERIAL}.
        # We simulate this by mutating the mock entry's options dict.
        entry.options = {CONF_UNIT_SYSTEM: UNIT_IMPERIAL}

        # --- Phase 3: imperial (next coordinator update) ---
        assert odometer_sensor.native_value == round(_ODOMETER_KM * KM_TO_MILES, 3)
        assert odometer_sensor.native_unit_of_measurement == "mi"
        assert avg_speed_sensor.native_value == round(_AVERAGE_SPEED_KMH * KMH_TO_MPH, 3)
        assert avg_speed_sensor.native_unit_of_measurement == "mph"
        assert elevation_sensor.native_value == round(_LAST_RIDE_ELEVATION_GAIN_M * M_TO_FEET, 3)
        assert elevation_sensor.native_unit_of_measurement == "ft"

    def test_all_convertible_sensors_switch_to_imperial(self):
        """All distance, speed, and elevation sensors must switch to imperial.

        Iterates over every sensor description that has a unit_fn and verifies
        that after switching to imperial the unit string is one of the expected
        imperial units.

        Requirements: 13.8
        """
        entry = _make_config_entry(UNIT_IMPERIAL)
        bike_data = _make_bike_data()
        coord = _make_coordinator(entry, bike_data)

        imperial_units = {"mi", "mph", "ft"}
        metric_units = {"km", "km/h", "m"}

        for desc in BIKE_SENSORS:
            if desc.unit_fn is None:
                continue  # Not a convertible sensor — skip

            sensor = BoschEBikeSensor(coord, entry, desc)
            unit = sensor.native_unit_of_measurement
            assert unit in imperial_units, (
                f"Sensor '{desc.key}' reported unit '{unit}' in imperial mode; "
                f"expected one of {imperial_units}"
            )
            # Also verify the value is not None (data is present)
            value = sensor.native_value
            assert value is not None, (
                f"Sensor '{desc.key}' returned None in imperial mode with valid data"
            )

    def test_all_convertible_sensors_stay_metric_when_not_changed(self):
        """All convertible sensors must stay metric when unit_system is metric.

        Requirements: 13.3
        """
        entry = _make_config_entry(UNIT_METRIC)
        bike_data = _make_bike_data()
        coord = _make_coordinator(entry, bike_data)

        metric_units = {"km", "km/h", "m"}

        for desc in BIKE_SENSORS:
            if desc.unit_fn is None:
                continue  # Not a convertible sensor — skip
            # Skip ConnectModule sensors (location data is None in our fixture)
            if desc.requires_connect_module:
                continue

            sensor = BoschEBikeSensor(coord, entry, desc)
            unit = sensor.native_unit_of_measurement
            assert unit in metric_units, (
                f"Sensor '{desc.key}' reported unit '{unit}' in metric mode; "
                f"expected one of {metric_units}"
            )

    @pytest.mark.asyncio
    async def test_options_flow_result_contains_correct_unit_system(self):
        """The options flow result data must contain the submitted unit_system.

        Verifies the contract between the options flow and the config entry
        options dict that sensors read from.

        Requirements: 13.5
        """
        # Start with metric, submit imperial
        entry = _make_config_entry(UNIT_METRIC)
        flow = BoschEBikeOptionsFlow(entry)
        result = await flow.async_step_init(user_input={CONF_UNIT_SYSTEM: UNIT_IMPERIAL})

        assert result["type"] == "create_entry"
        assert result["data"] == {CONF_UNIT_SYSTEM: UNIT_IMPERIAL}

        # Simulate HA applying the result data to entry.options
        entry.options = result["data"]

        # Now sensors must report imperial
        bike_data = _make_bike_data()
        coord = _make_coordinator(entry, bike_data)
        odometer = _make_sensor(coord, entry, "odometer")
        assert odometer is not None
        assert odometer.native_unit_of_measurement == "mi"
        assert odometer.native_value == round(_ODOMETER_KM * KM_TO_MILES, 3)
