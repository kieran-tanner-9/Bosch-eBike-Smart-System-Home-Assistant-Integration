"""Property-based tests for BatterySocSensor state-changed event firing.

**Validates: Requirements 8.3**

Property 8: Battery SoC state-changed event fires if and only if change is ≥ 1%

For any two consecutive BatteryStatus values, a Home Assistant state-changed
event for the battery_soc entity SHALL be fired if and only if
``abs(new_soc - old_soc) >= 1``.  Changes of less than 1 percentage point
SHALL NOT trigger an additional event beyond the normal coordinator update
cycle.

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
from unittest.mock import MagicMock, patch, call

from hypothesis import given, settings
from hypothesis import strategies as st

from custom_components.bosch_ebike_ha.const import CONF_UNIT_SYSTEM, DOMAIN, UNIT_METRIC
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
    BoschEBikeSensorDescription,
)
from homeassistant.helpers.device_registry import DeviceInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

# The battery_soc sensor description from the global list.
_BATTERY_SOC_DESC: BoschEBikeSensorDescription = next(
    desc for desc in BIKE_SENSORS if desc.key == "battery_soc"
)


def _make_bike_data(soc: int | None, *, has_flow_plus: bool = True) -> BikeData:
    """Build a minimal BikeData with the given battery SoC value."""
    battery = (
        BatteryStatus(state_of_charge_pct=soc, charging_status="discharging")
        if soc is not None
        else None
    )
    return BikeData(
        info=BikeInfo(
            bike_id="bike1",
            name="Test Bike",
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
        battery=battery,
        location=None,
        alarm=None,
        has_flow_plus=has_flow_plus,
        has_connect_module=False,
        last_updated=_NOW,
    )


def _make_sensor(initial_soc: int | None = None) -> BatterySocSensor:
    """Create a BatterySocSensor with a mock coordinator.

    The sensor's _prev_soc is set to ``initial_soc`` to simulate a prior state.
    ``_handle_coordinator_update`` is patched on the *parent* class so we can
    count how many times the state write is propagated upward.
    """
    coordinator = MagicMock()
    coordinator.data = _make_bike_data(initial_soc)
    coordinator.last_update_success = True
    coordinator.bike_id = "bike1"

    entry = MagicMock()
    entry.options = {CONF_UNIT_SYSTEM: UNIT_METRIC}

    sensor = BatterySocSensor.__new__(BatterySocSensor)
    # Bypass CoordinatorEntity.__init__ to avoid needing a real hass instance.
    sensor.coordinator = coordinator
    sensor.entity_description = _BATTERY_SOC_DESC
    sensor._entry = entry
    sensor._bike_id = "bike1"
    sensor._attr_unique_id = "bike1_battery_soc"
    sensor._attr_device_info = DeviceInfo(identifiers={(DOMAIN, "bike1")})
    sensor._prev_soc = initial_soc

    return sensor


def _count_expected_events(soc_sequence: list[int | None]) -> int:
    """Count how many state-changed events should fire for a SoC sequence.

    Rules (matching BatterySocSensor._handle_coordinator_update):
    - If either prev or new SoC is None → always propagate (count it).
    - If abs(new - prev) >= 1 → propagate (count it).
    - Otherwise → suppress (don't count).

    The sensor starts with _prev_soc=None (no prior state).
    """
    count = 0
    prev: int | None = None
    for new_soc in soc_sequence:
        if new_soc is None or prev is None:
            count += 1
            prev = new_soc
        elif abs(new_soc - prev) >= 1:
            count += 1
            prev = new_soc
        # else: change < 1 % — suppressed, prev stays the same
    return count


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Integer SoC values in the valid 0–100 range.
_st_soc_int = st.integers(min_value=0, max_value=100)

# A pair of integer SoC values (old, new).
_st_soc_pair = st.tuples(_st_soc_int, _st_soc_int)

# A sequence of integer SoC values (1–50 elements).
_st_soc_sequence = st.lists(_st_soc_int, min_size=1, max_size=50)


# ---------------------------------------------------------------------------
# Property 8a: Single-step — event fires iff |new - old| >= 1
# ---------------------------------------------------------------------------


@given(old_soc=_st_soc_int, new_soc=_st_soc_int)
@settings(max_examples=200)
def test_property8a_event_fires_iff_change_ge_1(old_soc: int, new_soc: int) -> None:
    """**Validates: Requirements 8.3**

    For any pair of integer SoC values (0–100), a state-changed event SHALL
    be fired if and only if ``abs(new_soc - old_soc) >= 1``.

    Verifies the single-step case: sensor has a known prior SoC (old_soc),
    then receives a coordinator update with new_soc.
    """
    sensor = _make_sensor(initial_soc=old_soc)

    propagate_count = 0

    # Patch the parent class's _handle_coordinator_update to count propagations.
    original_parent_update = MagicMock()

    with patch.object(
        type(sensor).__mro__[1],  # BoschEBikeSensor (direct parent)
        "_handle_coordinator_update",
        original_parent_update,
    ):
        sensor.coordinator.data = _make_bike_data(new_soc)
        sensor._handle_coordinator_update()
        propagate_count = original_parent_update.call_count

    expected_change = abs(new_soc - old_soc) >= 1

    if expected_change:
        assert propagate_count == 1, (
            f"old_soc={old_soc}, new_soc={new_soc}: "
            f"expected 1 state-changed event (|{new_soc}-{old_soc}|={abs(new_soc-old_soc)} >= 1), "
            f"but got {propagate_count}."
        )
    else:
        assert propagate_count == 0, (
            f"old_soc={old_soc}, new_soc={new_soc}: "
            f"expected 0 state-changed events (|{new_soc}-{old_soc}|={abs(new_soc-old_soc)} < 1), "
            f"but got {propagate_count}."
        )


# ---------------------------------------------------------------------------
# Property 8b: Same SoC → no event
# ---------------------------------------------------------------------------


@given(soc=_st_soc_int)
@settings(max_examples=100)
def test_property8b_no_event_when_soc_unchanged(soc: int) -> None:
    """**Validates: Requirements 8.3**

    When the SoC value does not change between polls, no state-changed event
    SHALL be fired.
    """
    sensor = _make_sensor(initial_soc=soc)

    with patch.object(
        type(sensor).__mro__[1],
        "_handle_coordinator_update",
    ) as mock_parent:
        sensor.coordinator.data = _make_bike_data(soc)
        sensor._handle_coordinator_update()
        assert mock_parent.call_count == 0, (
            f"soc={soc}: expected 0 events when SoC is unchanged, "
            f"got {mock_parent.call_count}."
        )


# ---------------------------------------------------------------------------
# Property 8c: Multi-step sequence — total event count matches expected
# ---------------------------------------------------------------------------


@given(soc_sequence=_st_soc_sequence)
@settings(max_examples=100)
def test_property8c_event_count_matches_expected_over_sequence(
    soc_sequence: list[int],
) -> None:
    """**Validates: Requirements 8.3**

    For any sequence of integer SoC values (0–100), the total number of
    state-changed events fired SHALL equal the number of steps where
    ``abs(new_soc - prev_soc) >= 1`` (or where prev_soc was None).

    The sensor starts with _prev_soc=None (no prior state), so the very
    first update always fires an event.
    """
    sensor = _make_sensor(initial_soc=None)

    expected_count = _count_expected_events(soc_sequence)

    with patch.object(
        type(sensor).__mro__[1],
        "_handle_coordinator_update",
    ) as mock_parent:
        for soc in soc_sequence:
            sensor.coordinator.data = _make_bike_data(soc)
            sensor._handle_coordinator_update()

        actual_count = mock_parent.call_count

    assert actual_count == expected_count, (
        f"soc_sequence={soc_sequence}: "
        f"expected {expected_count} state-changed event(s), "
        f"got {actual_count}."
    )


# ---------------------------------------------------------------------------
# Property 8d: prev_soc is updated only when event fires
# ---------------------------------------------------------------------------


@given(old_soc=_st_soc_int, new_soc=_st_soc_int)
@settings(max_examples=200)
def test_property8d_prev_soc_updated_only_on_significant_change(
    old_soc: int, new_soc: int
) -> None:
    """**Validates: Requirements 8.3**

    When a change of < 1% is suppressed, _prev_soc SHALL remain at old_soc
    (not advance to new_soc), so that subsequent small changes do not
    accumulate into a missed event.

    When a change of >= 1% fires an event, _prev_soc SHALL be updated to
    new_soc so the next comparison is relative to the new baseline.
    """
    sensor = _make_sensor(initial_soc=old_soc)

    with patch.object(type(sensor).__mro__[1], "_handle_coordinator_update"):
        sensor.coordinator.data = _make_bike_data(new_soc)
        sensor._handle_coordinator_update()

    if abs(new_soc - old_soc) >= 1:
        assert sensor._prev_soc == new_soc, (
            f"old_soc={old_soc}, new_soc={new_soc}: "
            f"expected _prev_soc={new_soc} after significant change, "
            f"got {sensor._prev_soc}."
        )
    else:
        assert sensor._prev_soc == old_soc, (
            f"old_soc={old_soc}, new_soc={new_soc}: "
            f"expected _prev_soc={old_soc} (unchanged) after suppressed change, "
            f"got {sensor._prev_soc}."
        )


# ---------------------------------------------------------------------------
# Property 8e: None SoC always propagates (unknown state)
# ---------------------------------------------------------------------------


@given(old_soc=st.one_of(st.none(), _st_soc_int))
@settings(max_examples=100)
def test_property8e_none_soc_always_propagates(old_soc: int | None) -> None:
    """**Validates: Requirements 8.3**

    When the new SoC is None (battery data unavailable), the update SHALL
    always propagate so the entity can transition to unavailable state.
    Similarly, when prev_soc is None (first update), the update always fires.
    """
    sensor = _make_sensor(initial_soc=old_soc)

    with patch.object(
        type(sensor).__mro__[1],
        "_handle_coordinator_update",
    ) as mock_parent:
        # Simulate a coordinator update where battery data is absent.
        sensor.coordinator.data = _make_bike_data(None)
        sensor._handle_coordinator_update()

        assert mock_parent.call_count == 1, (
            f"old_soc={old_soc}, new_soc=None: "
            f"expected 1 propagation when new SoC is None, "
            f"got {mock_parent.call_count}."
        )
