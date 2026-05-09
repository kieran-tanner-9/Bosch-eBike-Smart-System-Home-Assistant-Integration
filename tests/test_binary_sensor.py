"""Unit tests for binary_sensor.py — TheftAlarmBinarySensor and AlarmArmedBinarySensor.

Tests cover:
- unique_id construction
- device_info identifiers
- available logic (coordinator failure, ConnectModule absent/present)
- is_on state (alarm triggered / armed)
- _handle_coordinator_update: False→True transition fires persistent notification
- _handle_coordinator_update: True→True does NOT fire additional notification
- _handle_coordinator_update: True→False does NOT fire notification
- async_setup_entry creates correct entities per coordinator
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, call

import pytest

from custom_components.bosch_ebike_ha.binary_sensor import (
    AlarmArmedBinarySensor,
    TheftAlarmBinarySensor,
)
from custom_components.bosch_ebike_ha.const import DOMAIN
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


def _make_bike_data(
    *,
    has_connect_module: bool = True,
    alarm_triggered: bool = False,
    alarm_armed: bool = True,
    bike_name: str = "My Bike",
    bike_id: str = "bike1",
) -> BikeData:
    return BikeData(
        info=BikeInfo(
            bike_id=bike_id,
            name=bike_name,
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
        location=LocationData(latitude=51.5, longitude=-0.1, accuracy_m=5.0, timestamp=_NOW),
        alarm=AlarmStatus(alarm_triggered=alarm_triggered, alarm_armed=alarm_armed),
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
    return coord


def _make_entry() -> MagicMock:
    entry = MagicMock()
    entry.options = {}
    return entry


def _make_theft_sensor(
    bike_data: BikeData | None = None,
    *,
    last_update_success: bool = True,
    bike_id: str = "bike1",
) -> TheftAlarmBinarySensor:
    if bike_data is None:
        bike_data = _make_bike_data(bike_id=bike_id)
    coordinator = _make_coordinator(bike_data, last_update_success=last_update_success, bike_id=bike_id)
    entry = _make_entry()
    sensor = TheftAlarmBinarySensor.__new__(TheftAlarmBinarySensor)
    # Bypass CoordinatorEntity.__init__ to avoid needing a real hass instance
    sensor.coordinator = coordinator
    sensor._entry = entry
    sensor._bike_id = bike_id
    sensor._attr_unique_id = f"{bike_id}_theft_alarm_active"
    sensor._prev_alarm_triggered = False
    from homeassistant.helpers.device_registry import DeviceInfo
    sensor._attr_device_info = DeviceInfo(identifiers={(DOMAIN, bike_id)})
    return sensor


def _make_armed_sensor(
    bike_data: BikeData | None = None,
    *,
    last_update_success: bool = True,
    bike_id: str = "bike1",
) -> AlarmArmedBinarySensor:
    if bike_data is None:
        bike_data = _make_bike_data(bike_id=bike_id)
    coordinator = _make_coordinator(bike_data, last_update_success=last_update_success, bike_id=bike_id)
    entry = _make_entry()
    sensor = AlarmArmedBinarySensor.__new__(AlarmArmedBinarySensor)
    sensor.coordinator = coordinator
    sensor._entry = entry
    sensor._bike_id = bike_id
    sensor._attr_unique_id = f"{bike_id}_alarm_armed"
    from homeassistant.helpers.device_registry import DeviceInfo
    sensor._attr_device_info = DeviceInfo(identifiers={(DOMAIN, bike_id)})
    return sensor


# ---------------------------------------------------------------------------
# Tests: unique_id and device_info
# ---------------------------------------------------------------------------


class TestUniqueIdAndDeviceInfo:
    def test_theft_sensor_unique_id(self):
        sensor = _make_theft_sensor(bike_id="bike42")
        assert sensor.unique_id == "bike42_theft_alarm_active"

    def test_armed_sensor_unique_id(self):
        sensor = _make_armed_sensor(bike_id="bike42")
        assert sensor.unique_id == "bike42_alarm_armed"

    def test_theft_sensor_device_info(self):
        sensor = _make_theft_sensor(bike_id="bike99")
        assert (DOMAIN, "bike99") in sensor.device_info["identifiers"]

    def test_armed_sensor_device_info(self):
        sensor = _make_armed_sensor(bike_id="bike99")
        assert (DOMAIN, "bike99") in sensor.device_info["identifiers"]

    def test_unique_ids_differ_between_sensor_types(self):
        theft = _make_theft_sensor(bike_id="bike1")
        armed = _make_armed_sensor(bike_id="bike1")
        assert theft.unique_id != armed.unique_id

    def test_unique_ids_differ_across_bikes(self):
        theft1 = _make_theft_sensor(bike_id="bike1")
        theft2 = _make_theft_sensor(bike_id="bike2")
        assert theft1.unique_id != theft2.unique_id


# ---------------------------------------------------------------------------
# Tests: available property
# ---------------------------------------------------------------------------


class TestAvailable:
    def test_available_when_connect_module_present(self):
        sensor = _make_theft_sensor(_make_bike_data(has_connect_module=True))
        assert sensor.available is True

    def test_unavailable_when_no_connect_module(self):
        sensor = _make_theft_sensor(_make_bike_data(has_connect_module=False))
        assert sensor.available is False

    def test_unavailable_when_coordinator_failed(self):
        sensor = _make_theft_sensor(
            _make_bike_data(has_connect_module=True), last_update_success=False
        )
        assert sensor.available is False

    def test_unavailable_when_coordinator_data_is_none(self):
        sensor = _make_theft_sensor()
        sensor.coordinator.data = None
        assert sensor.available is False

    def test_armed_available_when_connect_module_present(self):
        sensor = _make_armed_sensor(_make_bike_data(has_connect_module=True))
        assert sensor.available is True

    def test_armed_unavailable_when_no_connect_module(self):
        sensor = _make_armed_sensor(_make_bike_data(has_connect_module=False))
        assert sensor.available is False


# ---------------------------------------------------------------------------
# Tests: is_on (TheftAlarmBinarySensor)
# ---------------------------------------------------------------------------


class TestTheftAlarmIsOn:
    def test_is_on_when_alarm_triggered(self):
        sensor = _make_theft_sensor(_make_bike_data(alarm_triggered=True))
        assert sensor.is_on is True

    def test_is_off_when_alarm_not_triggered(self):
        sensor = _make_theft_sensor(_make_bike_data(alarm_triggered=False))
        assert sensor.is_on is False

    def test_is_none_when_unavailable(self):
        sensor = _make_theft_sensor(_make_bike_data(has_connect_module=False))
        assert sensor.is_on is None

    def test_is_none_when_coordinator_data_is_none(self):
        sensor = _make_theft_sensor()
        sensor.coordinator.data = None
        assert sensor.is_on is None

    def test_is_none_when_alarm_is_none(self):
        data = _make_bike_data(has_connect_module=True)
        data.alarm = None
        sensor = _make_theft_sensor(data)
        assert sensor.is_on is None


# ---------------------------------------------------------------------------
# Tests: is_on (AlarmArmedBinarySensor)
# ---------------------------------------------------------------------------


class TestAlarmArmedIsOn:
    def test_is_on_when_armed(self):
        sensor = _make_armed_sensor(_make_bike_data(alarm_armed=True))
        assert sensor.is_on is True

    def test_is_off_when_disarmed(self):
        sensor = _make_armed_sensor(_make_bike_data(alarm_armed=False))
        assert sensor.is_on is False

    def test_is_none_when_unavailable(self):
        sensor = _make_armed_sensor(_make_bike_data(has_connect_module=False))
        assert sensor.is_on is None

    def test_is_none_when_coordinator_data_is_none(self):
        sensor = _make_armed_sensor()
        sensor.coordinator.data = None
        assert sensor.is_on is None

    def test_is_none_when_alarm_is_none(self):
        data = _make_bike_data(has_connect_module=True)
        data.alarm = None
        sensor = _make_armed_sensor(data)
        assert sensor.is_on is None


# ---------------------------------------------------------------------------
# Tests: device_class
# ---------------------------------------------------------------------------


class TestDeviceClass:
    def test_theft_sensor_device_class_is_tamper(self):
        from homeassistant.components.binary_sensor import BinarySensorDeviceClass
        sensor = _make_theft_sensor()
        assert sensor._attr_device_class == BinarySensorDeviceClass.TAMPER

    def test_armed_sensor_device_class_is_safety(self):
        from homeassistant.components.binary_sensor import BinarySensorDeviceClass
        sensor = _make_armed_sensor()
        assert sensor._attr_device_class == BinarySensorDeviceClass.SAFETY


# ---------------------------------------------------------------------------
# Tests: _handle_coordinator_update — notification logic
# ---------------------------------------------------------------------------


class TestHandleCoordinatorUpdate:
    def _make_sensor_with_hass(
        self,
        bike_data: BikeData,
        *,
        prev_alarm_triggered: bool = False,
    ) -> tuple[TheftAlarmBinarySensor, MagicMock]:
        """Create a TheftAlarmBinarySensor with a mock hass attached."""
        sensor = _make_theft_sensor(bike_data)
        sensor._prev_alarm_triggered = prev_alarm_triggered
        mock_hass = MagicMock()
        sensor.hass = mock_hass
        return sensor, mock_hass

    def test_notification_fired_on_false_to_true_transition(self):
        """False → True: persistent notification must be created."""
        data = _make_bike_data(alarm_triggered=True, bike_name="My Cube")
        sensor, mock_hass = self._make_sensor_with_hass(data, prev_alarm_triggered=False)

        sensor._handle_coordinator_update()

        mock_hass.components.persistent_notification.async_create.assert_called_once()
        call_kwargs = mock_hass.components.persistent_notification.async_create.call_args
        # The message should mention the bike name
        assert "My Cube" in call_kwargs.kwargs.get("message", "") or \
               "My Cube" in str(call_kwargs)

    def test_no_notification_on_true_to_true(self):
        """True → True: no additional notification should be fired."""
        data = _make_bike_data(alarm_triggered=True)
        sensor, mock_hass = self._make_sensor_with_hass(data, prev_alarm_triggered=True)

        sensor._handle_coordinator_update()

        mock_hass.components.persistent_notification.async_create.assert_not_called()

    def test_no_notification_on_false_to_false(self):
        """False → False: no notification should be fired."""
        data = _make_bike_data(alarm_triggered=False)
        sensor, mock_hass = self._make_sensor_with_hass(data, prev_alarm_triggered=False)

        sensor._handle_coordinator_update()

        mock_hass.components.persistent_notification.async_create.assert_not_called()

    def test_no_notification_on_true_to_false(self):
        """True → False: no notification should be fired."""
        data = _make_bike_data(alarm_triggered=False)
        sensor, mock_hass = self._make_sensor_with_hass(data, prev_alarm_triggered=True)

        sensor._handle_coordinator_update()

        mock_hass.components.persistent_notification.async_create.assert_not_called()

    def test_prev_state_updated_after_update(self):
        """After update, _prev_alarm_triggered should reflect the new state."""
        data = _make_bike_data(alarm_triggered=True)
        sensor, mock_hass = self._make_sensor_with_hass(data, prev_alarm_triggered=False)

        sensor._handle_coordinator_update()

        assert sensor._prev_alarm_triggered is True

    def test_prev_state_updated_to_false(self):
        """After update with alarm off, _prev_alarm_triggered should be False."""
        data = _make_bike_data(alarm_triggered=False)
        sensor, mock_hass = self._make_sensor_with_hass(data, prev_alarm_triggered=True)

        sensor._handle_coordinator_update()

        assert sensor._prev_alarm_triggered is False

    def test_multiple_transitions_fire_notification_each_time(self):
        """Each False→True transition should fire exactly one notification."""
        sensor, mock_hass = self._make_sensor_with_hass(
            _make_bike_data(alarm_triggered=False), prev_alarm_triggered=False
        )

        # Sequence: False → True → False → True
        # Transition 1: False → True
        sensor.coordinator.data = _make_bike_data(alarm_triggered=True)
        sensor._handle_coordinator_update()

        # Transition 2: True → False
        sensor.coordinator.data = _make_bike_data(alarm_triggered=False)
        sensor._handle_coordinator_update()

        # Transition 3: False → True
        sensor.coordinator.data = _make_bike_data(alarm_triggered=True)
        sensor._handle_coordinator_update()

        assert mock_hass.components.persistent_notification.async_create.call_count == 2

    def test_no_notification_when_no_connect_module(self):
        """No notification when ConnectModule is absent, even if alarm field is True."""
        data = _make_bike_data(has_connect_module=False, alarm_triggered=True)
        sensor, mock_hass = self._make_sensor_with_hass(data, prev_alarm_triggered=False)

        sensor._handle_coordinator_update()

        mock_hass.components.persistent_notification.async_create.assert_not_called()

    def test_no_notification_when_coordinator_data_is_none(self):
        """No notification when coordinator data is None."""
        data = _make_bike_data(alarm_triggered=True)
        sensor, mock_hass = self._make_sensor_with_hass(data, prev_alarm_triggered=False)
        sensor.coordinator.data = None

        sensor._handle_coordinator_update()

        mock_hass.components.persistent_notification.async_create.assert_not_called()

    def test_no_notification_when_alarm_is_none(self):
        """No notification when alarm field is None."""
        data = _make_bike_data(alarm_triggered=True)
        data.alarm = None
        sensor, mock_hass = self._make_sensor_with_hass(data, prev_alarm_triggered=False)

        sensor._handle_coordinator_update()

        mock_hass.components.persistent_notification.async_create.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: extra_state_attributes
# ---------------------------------------------------------------------------


class TestExtraStateAttributes:
    def test_last_updated_present(self):
        sensor = _make_theft_sensor()
        attrs = sensor.extra_state_attributes
        assert "last_updated" in attrs

    def test_last_updated_is_iso_string(self):
        sensor = _make_theft_sensor()
        attrs = sensor.extra_state_attributes
        parsed = datetime.fromisoformat(attrs["last_updated"])
        assert parsed == _NOW

    def test_last_updated_absent_when_no_data(self):
        sensor = _make_theft_sensor()
        sensor.coordinator.data = None
        attrs = sensor.extra_state_attributes
        assert "last_updated" not in attrs


# ---------------------------------------------------------------------------
# Tests: async_setup_entry
# ---------------------------------------------------------------------------


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_two_entities_per_coordinator(self):
        """async_setup_entry should create TheftAlarm + AlarmArmed per bike."""
        from custom_components.bosch_ebike_ha.binary_sensor import async_setup_entry

        mock_hass = MagicMock()
        mock_entry = MagicMock()
        mock_entry.options = {}

        coord1 = _make_coordinator(_make_bike_data(bike_id="bike1"), bike_id="bike1")
        coord2 = _make_coordinator(_make_bike_data(bike_id="bike2"), bike_id="bike2")

        mock_hass.data = {DOMAIN: {mock_entry.entry_id: {"coordinators": [coord1, coord2]}}}

        added_entities: list[Any] = []

        def capture(entities: list[Any]) -> None:
            added_entities.extend(entities)

        await async_setup_entry(mock_hass, mock_entry, capture)

        assert len(added_entities) == 4  # 2 entities × 2 bikes

        theft_sensors = [e for e in added_entities if isinstance(e, TheftAlarmBinarySensor)]
        armed_sensors = [e for e in added_entities if isinstance(e, AlarmArmedBinarySensor)]
        assert len(theft_sensors) == 2
        assert len(armed_sensors) == 2

    @pytest.mark.asyncio
    async def test_entities_have_correct_bike_ids(self):
        """Each entity should be associated with the correct bike coordinator."""
        from custom_components.bosch_ebike_ha.binary_sensor import async_setup_entry

        mock_hass = MagicMock()
        mock_entry = MagicMock()
        mock_entry.options = {}

        coord = _make_coordinator(_make_bike_data(bike_id="myBike"), bike_id="myBike")
        mock_hass.data = {DOMAIN: {mock_entry.entry_id: {"coordinators": [coord]}}}

        added_entities: list[Any] = []
        await async_setup_entry(mock_hass, mock_entry, lambda e: added_entities.extend(e))

        for entity in added_entities:
            assert entity._bike_id == "myBike"
