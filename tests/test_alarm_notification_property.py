"""Property-based tests for TheftAlarmBinarySensor notification logic.

**Validates: Requirements 10.2**

Property 7: Alarm notification fires exactly once per False→True transition

For any sequence of ``alarm_triggered`` boolean values delivered by the
coordinator, the number of persistent notifications created SHALL equal
exactly the number of ``False → True`` transitions in that sequence.
Consecutive ``True`` values after the first SHALL NOT create additional
notifications.

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
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from custom_components.bosch_ebike_ha.binary_sensor import TheftAlarmBinarySensor
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
from homeassistant.helpers.device_registry import DeviceInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_bike_data(
    alarm_triggered: bool,
    *,
    has_connect_module: bool = True,
    bike_name: str = "Test Bike",
    bike_id: str = "bike1",
) -> BikeData:
    """Build a minimal BikeData with the given alarm_triggered value."""
    return BikeData(
        info=BikeInfo(
            bike_id=bike_id,
            name=bike_name,
            model="Cube Stereo",
            serial_number="SN123",
        ),
        telemetry=BikeTelemetry(
            odometer_km=1000.0,
            motor_hours_total=50.0,
            motor_hours_with_assist=40.0,
            battery_charge_cycles=30,
            battery_lifetime_energy_wh=3000.0,
            next_service_odometer_km=2000.0,
            max_assist_speed_kmh=25.0,
        ),
        last_ride=RideData(
            ride_id="r1",
            completed_at=_NOW,
            distance_km=20.0,
            duration_minutes=60.0,
            average_speed_kmh=20.0,
            max_speed_kmh=35.0,
            elevation_gain_m=100.0,
            elevation_loss_m=90.0,
            calories_kcal=400.0,
            avg_rider_power_w=None,
            max_rider_power_w=None,
            avg_cadence_rpm=None,
            max_cadence_rpm=None,
            motor_power_ratio_pct=None,
        ),
        aggregate=AggregateStats(
            total_rides=50,
            total_distance_km=2000.0,
            total_ride_time_hours=100.0,
            total_calories_kcal=20000.0,
            total_elevation_gain_m=5000.0,
            average_speed_kmh=20.0,
        ),
        battery=BatteryStatus(state_of_charge_pct=80, charging_status="discharging"),
        location=LocationData(
            latitude=51.5, longitude=-0.1, accuracy_m=5.0, timestamp=_NOW
        ),
        alarm=AlarmStatus(alarm_triggered=alarm_triggered, alarm_armed=True),
        has_flow_plus=False,
        has_connect_module=has_connect_module,
        last_updated=_NOW,
    )


def _make_sensor_with_hass(
    bike_id: str = "bike1",
) -> tuple[TheftAlarmBinarySensor, MagicMock]:
    """Create a TheftAlarmBinarySensor with a mock coordinator and hass.

    The sensor starts with _prev_alarm_triggered=False (initial state).
    Returns (sensor, mock_hass) so the caller can inspect notification calls.
    """
    # Start with alarm off so the sensor is in a clean initial state.
    initial_data = _make_bike_data(alarm_triggered=False, bike_id=bike_id)

    coordinator = MagicMock()
    coordinator.data = initial_data
    coordinator.last_update_success = True
    coordinator.bike_id = bike_id

    entry = MagicMock()
    entry.options = {}

    sensor = TheftAlarmBinarySensor.__new__(TheftAlarmBinarySensor)
    # Bypass CoordinatorEntity.__init__ to avoid needing a real hass instance.
    sensor.coordinator = coordinator
    sensor._entry = entry
    sensor._bike_id = bike_id
    sensor._attr_unique_id = f"{bike_id}_theft_alarm_active"
    sensor._prev_alarm_triggered = False
    sensor._attr_device_info = DeviceInfo(identifiers={(DOMAIN, bike_id)})

    mock_hass = MagicMock()
    sensor.hass = mock_hass

    return sensor, mock_hass


def _count_false_to_true_transitions(sequence: list[bool]) -> int:
    """Count the number of False→True transitions in a boolean sequence.

    The initial state before the sequence is always False (sensor starts off).
    """
    count = 0
    prev = False
    for value in sequence:
        if value and not prev:
            count += 1
        prev = value
    return count


def _simulate_alarm_sequence(
    sensor: TheftAlarmBinarySensor,
    sequence: list[bool],
) -> None:
    """Feed a sequence of alarm_triggered values into the sensor via coordinator updates."""
    for triggered in sequence:
        sensor.coordinator.data = _make_bike_data(
            alarm_triggered=triggered,
            bike_id=sensor._bike_id,
        )
        sensor._handle_coordinator_update()


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Generate non-empty boolean sequences of length 1–50.
_st_alarm_sequence = st.lists(
    st.booleans(),
    min_size=1,
    max_size=50,
)


# ---------------------------------------------------------------------------
# Property 7: Alarm notification fires exactly once per False→True transition
# ---------------------------------------------------------------------------


@given(sequence=_st_alarm_sequence)
@settings(max_examples=100)
def test_property7_notification_count_equals_transition_count(
    sequence: list[bool],
) -> None:
    """**Validates: Requirements 10.2**

    For any sequence of alarm_triggered boolean values, the number of
    persistent notifications created SHALL equal exactly the number of
    False→True transitions in that sequence.

    Consecutive True values after the first SHALL NOT create additional
    notifications.
    """
    sensor, mock_hass = _make_sensor_with_hass()

    expected_transitions = _count_false_to_true_transitions(sequence)

    _simulate_alarm_sequence(sensor, sequence)

    actual_calls = mock_hass.components.persistent_notification.async_create.call_count

    assert actual_calls == expected_transitions, (
        f"Sequence {sequence}: expected {expected_transitions} notification(s) "
        f"(False→True transitions), but got {actual_calls}. "
        f"Sensor _prev_alarm_triggered after sequence: {sensor._prev_alarm_triggered}"
    )


@given(sequence=_st_alarm_sequence)
@settings(max_examples=100)
def test_property7_no_notification_for_true_to_true(
    sequence: list[bool],
) -> None:
    """**Validates: Requirements 10.2**

    Consecutive True values after the first transition SHALL NOT create
    additional notifications. Verify by checking that runs of True values
    only produce one notification per run.
    """
    sensor, mock_hass = _make_sensor_with_hass()

    _simulate_alarm_sequence(sensor, sequence)

    # Count runs of consecutive True values (each run should produce at most
    # one notification — only on the False→True entry to the run).
    true_runs = 0
    in_true_run = False
    prev = False
    for value in sequence:
        if value and not prev:
            true_runs += 1
            in_true_run = True
        elif not value:
            in_true_run = False
        prev = value

    actual_calls = mock_hass.components.persistent_notification.async_create.call_count

    # The number of notifications must equal the number of True-runs (each
    # run starts with exactly one False→True transition).
    assert actual_calls == true_runs, (
        f"Sequence {sequence}: expected {true_runs} notification(s) "
        f"(one per True-run), but got {actual_calls}."
    )


@given(sequence=_st_alarm_sequence)
@settings(max_examples=100)
def test_property7_notification_message_contains_bike_name(
    sequence: list[bool],
) -> None:
    """**Validates: Requirements 10.2**

    Each notification fired on a False→True transition SHALL include the
    bike's name in the notification message.
    """
    bike_name = "My Test Cube"
    sensor, mock_hass = _make_sensor_with_hass()

    # Override bike data to use a specific bike name.
    for triggered in sequence:
        sensor.coordinator.data = _make_bike_data(
            alarm_triggered=triggered,
            bike_name=bike_name,
            bike_id=sensor._bike_id,
        )
        sensor._handle_coordinator_update()

    # For every call that was made, the message must contain the bike name.
    for call_args in mock_hass.components.persistent_notification.async_create.call_args_list:
        # async_create is called with keyword arguments: message=, title=, notification_id=
        kwargs = call_args.kwargs
        message = kwargs.get("message", "")
        assert bike_name in message, (
            f"Notification message {message!r} does not contain bike name {bike_name!r}"
        )


@given(sequence=_st_alarm_sequence)
@settings(max_examples=100)
def test_property7_no_notification_when_connect_module_absent(
    sequence: list[bool],
) -> None:
    """**Validates: Requirements 10.2**

    When has_connect_module is False, NO notifications SHALL be fired
    regardless of the alarm_triggered sequence.
    """
    sensor, mock_hass = _make_sensor_with_hass()

    # Feed the sequence with has_connect_module=False.
    for triggered in sequence:
        sensor.coordinator.data = _make_bike_data(
            alarm_triggered=triggered,
            has_connect_module=False,
            bike_id=sensor._bike_id,
        )
        sensor._handle_coordinator_update()

    actual_calls = mock_hass.components.persistent_notification.async_create.call_count

    assert actual_calls == 0, (
        f"Sequence {sequence}: expected 0 notifications when ConnectModule is absent, "
        f"but got {actual_calls}."
    )


@given(
    prefix=_st_alarm_sequence,
    suffix=_st_alarm_sequence,
)
@settings(max_examples=100)
def test_property7_state_is_preserved_across_updates(
    prefix: list[bool],
    suffix: list[bool],
) -> None:
    """**Validates: Requirements 10.2**

    The sensor correctly tracks state across multiple coordinator updates.
    Processing prefix + suffix in one go must produce the same notification
    count as processing them sequentially on the same sensor instance.
    """
    # Sensor A: process prefix then suffix sequentially.
    sensor_a, mock_hass_a = _make_sensor_with_hass(bike_id="bikeA")
    _simulate_alarm_sequence(sensor_a, prefix)
    _simulate_alarm_sequence(sensor_a, suffix)
    calls_sequential = mock_hass_a.components.persistent_notification.async_create.call_count

    # Sensor B: process the full concatenated sequence at once.
    sensor_b, mock_hass_b = _make_sensor_with_hass(bike_id="bikeB")
    _simulate_alarm_sequence(sensor_b, prefix + suffix)
    calls_combined = mock_hass_b.components.persistent_notification.async_create.call_count

    assert calls_sequential == calls_combined, (
        f"prefix={prefix}, suffix={suffix}: "
        f"sequential processing gave {calls_sequential} notifications, "
        f"combined processing gave {calls_combined}. "
        "State must be preserved across updates."
    )
