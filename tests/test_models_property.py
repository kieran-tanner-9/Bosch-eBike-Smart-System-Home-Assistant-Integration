"""Property-based tests for data model parsing round-trips.

Property 5: API response parsing round-trip preserves all field values.

For any valid API JSON response, parsing it into the corresponding dataclass
model and reading back each field SHALL yield a value equal to the original
JSON field. No field SHALL be silently dropped, defaulted, or mutated during
parsing.

Validates: Requirements 2.1–2.6, 3.1–3.8, 4.1–4.6
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

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
# Helpers: parse functions that mirror what the API client will do
# (constructing dataclasses from raw JSON dicts)
# ---------------------------------------------------------------------------

CHARGING_STATUSES = ["charging", "discharging", "full", "unknown"]


def parse_bike_info(data: dict) -> BikeInfo:
    return BikeInfo(
        bike_id=data["bike_id"],
        name=data["name"],
        model=data["model"],
        serial_number=data["serial_number"],
    )


def parse_bike_telemetry(data: dict) -> BikeTelemetry:
    return BikeTelemetry(
        odometer_km=data.get("odometer_km"),
        motor_hours_total=data.get("motor_hours_total"),
        motor_hours_with_assist=data.get("motor_hours_with_assist"),
        battery_charge_cycles=data.get("battery_charge_cycles"),
        battery_lifetime_energy_wh=data.get("battery_lifetime_energy_wh"),
        next_service_odometer_km=data.get("next_service_odometer_km"),
        max_assist_speed_kmh=data.get("max_assist_speed_kmh"),
    )


def parse_ride_data(data: dict) -> RideData:
    completed_at_raw = data.get("completed_at")
    completed_at = (
        datetime.fromisoformat(completed_at_raw) if completed_at_raw is not None else None
    )
    return RideData(
        ride_id=data["ride_id"],
        completed_at=completed_at,
        distance_km=data.get("distance_km"),
        duration_minutes=data.get("duration_minutes"),
        average_speed_kmh=data.get("average_speed_kmh"),
        max_speed_kmh=data.get("max_speed_kmh"),
        elevation_gain_m=data.get("elevation_gain_m"),
        elevation_loss_m=data.get("elevation_loss_m"),
        calories_kcal=data.get("calories_kcal"),
        avg_rider_power_w=data.get("avg_rider_power_w"),
        max_rider_power_w=data.get("max_rider_power_w"),
        avg_cadence_rpm=data.get("avg_cadence_rpm"),
        max_cadence_rpm=data.get("max_cadence_rpm"),
        motor_power_ratio_pct=data.get("motor_power_ratio_pct"),
    )


def parse_aggregate_stats(data: dict) -> AggregateStats:
    return AggregateStats(
        total_rides=data.get("total_rides"),
        total_distance_km=data.get("total_distance_km"),
        total_ride_time_hours=data.get("total_ride_time_hours"),
        total_calories_kcal=data.get("total_calories_kcal"),
        total_elevation_gain_m=data.get("total_elevation_gain_m"),
        average_speed_kmh=data.get("average_speed_kmh"),
    )


def parse_battery_status(data: dict) -> BatteryStatus:
    return BatteryStatus(
        state_of_charge_pct=data.get("state_of_charge_pct"),
        charging_status=data.get("charging_status"),
    )


def parse_location_data(data: dict) -> LocationData:
    timestamp_raw = data.get("timestamp")
    timestamp = (
        datetime.fromisoformat(timestamp_raw) if timestamp_raw is not None else None
    )
    return LocationData(
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        accuracy_m=data.get("accuracy_m"),
        timestamp=timestamp,
    )


def parse_alarm_status(data: dict) -> AlarmStatus:
    return AlarmStatus(
        alarm_triggered=data["alarm_triggered"],
        alarm_armed=data["alarm_armed"],
    )


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Non-NaN, non-infinite floats suitable for sensor values
finite_floats = st.floats(
    min_value=-1e9,
    max_value=1e9,
    allow_nan=False,
    allow_infinity=False,
)

# Non-empty strings for IDs and names
nonempty_text = st.text(min_size=1, max_size=64)

# UTC-aware datetimes serialised as ISO 8601 strings
utc_datetimes = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2099, 12, 31),
    timezones=st.just(timezone.utc),
)
iso_datetime_strings = utc_datetimes.map(lambda dt: dt.isoformat())

# Optional variants
opt_float = st.one_of(st.none(), finite_floats)
opt_int = st.one_of(st.none(), st.integers(min_value=0, max_value=100_000))
opt_datetime_str = st.one_of(st.none(), iso_datetime_strings)


@st.composite
def bike_info_dicts(draw):
    return {
        "bike_id": draw(nonempty_text),
        "name": draw(nonempty_text),
        "model": draw(nonempty_text),
        "serial_number": draw(nonempty_text),
    }


@st.composite
def bike_telemetry_dicts(draw):
    return {
        "odometer_km": draw(opt_float),
        "motor_hours_total": draw(opt_float),
        "motor_hours_with_assist": draw(opt_float),
        "battery_charge_cycles": draw(opt_int),
        "battery_lifetime_energy_wh": draw(opt_float),
        "next_service_odometer_km": draw(opt_float),
        "max_assist_speed_kmh": draw(opt_float),
    }


@st.composite
def ride_data_dicts(draw):
    return {
        "ride_id": draw(nonempty_text),
        "completed_at": draw(opt_datetime_str),
        "distance_km": draw(opt_float),
        "duration_minutes": draw(opt_float),
        "average_speed_kmh": draw(opt_float),
        "max_speed_kmh": draw(opt_float),
        "elevation_gain_m": draw(opt_float),
        "elevation_loss_m": draw(opt_float),
        "calories_kcal": draw(opt_float),
        "avg_rider_power_w": draw(opt_float),
        "max_rider_power_w": draw(opt_float),
        "avg_cadence_rpm": draw(opt_float),
        "max_cadence_rpm": draw(opt_float),
        "motor_power_ratio_pct": draw(opt_float),
    }


@st.composite
def aggregate_stats_dicts(draw):
    return {
        "total_rides": draw(opt_int),
        "total_distance_km": draw(opt_float),
        "total_ride_time_hours": draw(opt_float),
        "total_calories_kcal": draw(opt_float),
        "total_elevation_gain_m": draw(opt_float),
        "average_speed_kmh": draw(opt_float),
    }


@st.composite
def battery_status_dicts(draw):
    soc = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=100)))
    status = draw(st.one_of(st.none(), st.sampled_from(CHARGING_STATUSES)))
    return {"state_of_charge_pct": soc, "charging_status": status}


@st.composite
def location_data_dicts(draw):
    return {
        "latitude": draw(st.one_of(st.none(), st.floats(min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False))),
        "longitude": draw(st.one_of(st.none(), st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False))),
        "accuracy_m": draw(st.one_of(st.none(), st.floats(min_value=0.0, max_value=10_000.0, allow_nan=False, allow_infinity=False))),
        "timestamp": draw(opt_datetime_str),
    }


@st.composite
def alarm_status_dicts(draw):
    return {
        "alarm_triggered": draw(st.booleans()),
        "alarm_armed": draw(st.booleans()),
    }


# ---------------------------------------------------------------------------
# Property 5 tests
# Validates: Requirements 2.1–2.6, 3.1–3.8, 4.1–4.6
# ---------------------------------------------------------------------------


@given(data=bike_info_dicts())
@settings(max_examples=100)
def test_bike_info_round_trip(data):
    """**Validates: Requirements 2.1–2.6**

    Parsing a BikeInfo JSON dict preserves all field values exactly.
    """
    model = parse_bike_info(data)

    assert model.bike_id == data["bike_id"]
    assert model.name == data["name"]
    assert model.model == data["model"]
    assert model.serial_number == data["serial_number"]


@given(data=bike_telemetry_dicts())
@settings(max_examples=100)
def test_bike_telemetry_round_trip(data):
    """**Validates: Requirements 2.1–2.6**

    Parsing a BikeTelemetry JSON dict preserves all field values exactly,
    including None for absent optional fields.
    """
    model = parse_bike_telemetry(data)

    assert model.odometer_km == data["odometer_km"]
    assert model.motor_hours_total == data["motor_hours_total"]
    assert model.motor_hours_with_assist == data["motor_hours_with_assist"]
    assert model.battery_charge_cycles == data["battery_charge_cycles"]
    assert model.battery_lifetime_energy_wh == data["battery_lifetime_energy_wh"]
    assert model.next_service_odometer_km == data["next_service_odometer_km"]
    assert model.max_assist_speed_kmh == data["max_assist_speed_kmh"]


@given(data=ride_data_dicts())
@settings(max_examples=100)
def test_ride_data_round_trip(data):
    """**Validates: Requirements 3.1–3.8**

    Parsing a RideData JSON dict preserves all field values exactly.
    The completed_at ISO 8601 string is parsed to a datetime; the round-trip
    asserts the datetime reconstructs to the same ISO string.
    """
    model = parse_ride_data(data)

    assert model.ride_id == data["ride_id"]

    # datetime field: None stays None; string is parsed to datetime
    if data["completed_at"] is None:
        assert model.completed_at is None
    else:
        assert model.completed_at is not None
        assert isinstance(model.completed_at, datetime)
        assert model.completed_at.isoformat() == data["completed_at"]

    assert model.distance_km == data["distance_km"]
    assert model.duration_minutes == data["duration_minutes"]
    assert model.average_speed_kmh == data["average_speed_kmh"]
    assert model.max_speed_kmh == data["max_speed_kmh"]
    assert model.elevation_gain_m == data["elevation_gain_m"]
    assert model.elevation_loss_m == data["elevation_loss_m"]
    assert model.calories_kcal == data["calories_kcal"]
    assert model.avg_rider_power_w == data["avg_rider_power_w"]
    assert model.max_rider_power_w == data["max_rider_power_w"]
    assert model.avg_cadence_rpm == data["avg_cadence_rpm"]
    assert model.max_cadence_rpm == data["max_cadence_rpm"]
    assert model.motor_power_ratio_pct == data["motor_power_ratio_pct"]


@given(data=aggregate_stats_dicts())
@settings(max_examples=100)
def test_aggregate_stats_round_trip(data):
    """**Validates: Requirements 4.1–4.6**

    Parsing an AggregateStats JSON dict preserves all field values exactly.
    """
    model = parse_aggregate_stats(data)

    assert model.total_rides == data["total_rides"]
    assert model.total_distance_km == data["total_distance_km"]
    assert model.total_ride_time_hours == data["total_ride_time_hours"]
    assert model.total_calories_kcal == data["total_calories_kcal"]
    assert model.total_elevation_gain_m == data["total_elevation_gain_m"]
    assert model.average_speed_kmh == data["average_speed_kmh"]


@given(data=battery_status_dicts())
@settings(max_examples=100)
def test_battery_status_round_trip(data):
    """**Validates: Requirements 2.1–2.6 (BatteryStatus model fidelity)**

    Parsing a BatteryStatus JSON dict preserves state_of_charge_pct and
    charging_status exactly, including None for absent fields.
    """
    model = parse_battery_status(data)

    assert model.state_of_charge_pct == data["state_of_charge_pct"]
    assert model.charging_status == data["charging_status"]


@given(data=location_data_dicts())
@settings(max_examples=100)
def test_location_data_round_trip(data):
    """**Validates: Requirements 3.1–3.8 (LocationData model fidelity)**

    Parsing a LocationData JSON dict preserves latitude, longitude, accuracy_m,
    and timestamp exactly. The timestamp ISO string is parsed to a datetime.
    """
    model = parse_location_data(data)

    assert model.latitude == data["latitude"]
    assert model.longitude == data["longitude"]
    assert model.accuracy_m == data["accuracy_m"]

    if data["timestamp"] is None:
        assert model.timestamp is None
    else:
        assert model.timestamp is not None
        assert isinstance(model.timestamp, datetime)
        assert model.timestamp.isoformat() == data["timestamp"]


@given(data=alarm_status_dicts())
@settings(max_examples=100)
def test_alarm_status_round_trip(data):
    """**Validates: Requirements 3.1–3.8 (AlarmStatus model fidelity)**

    Parsing an AlarmStatus JSON dict preserves alarm_triggered and alarm_armed
    boolean values exactly.
    """
    model = parse_alarm_status(data)

    assert model.alarm_triggered == data["alarm_triggered"]
    assert model.alarm_armed == data["alarm_armed"]


@given(
    info=bike_info_dicts(),
    telemetry=bike_telemetry_dicts(),
    ride=st.one_of(st.none(), ride_data_dicts()),
    aggregate=aggregate_stats_dicts(),
    battery=st.one_of(st.none(), battery_status_dicts()),
    location=st.one_of(st.none(), location_data_dicts()),
    alarm=st.one_of(st.none(), alarm_status_dicts()),
    has_flow_plus=st.booleans(),
    has_connect_module=st.booleans(),
    last_updated=utc_datetimes,
)
@settings(max_examples=100)
def test_bike_data_round_trip(
    info,
    telemetry,
    ride,
    aggregate,
    battery,
    location,
    alarm,
    has_flow_plus,
    has_connect_module,
    last_updated,
):
    """**Validates: Requirements 2.1–2.6, 3.1–3.8, 4.1–4.6**

    Assembling a BikeData from parsed sub-models preserves all nested field
    values. No field is silently dropped, defaulted, or mutated.
    """
    info_model = parse_bike_info(info)
    telemetry_model = parse_bike_telemetry(telemetry)
    ride_model = parse_ride_data(ride) if ride is not None else None
    aggregate_model = parse_aggregate_stats(aggregate)
    battery_model = parse_battery_status(battery) if battery is not None else None
    location_model = parse_location_data(location) if location is not None else None
    alarm_model = parse_alarm_status(alarm) if alarm is not None else None

    bike_data = BikeData(
        info=info_model,
        telemetry=telemetry_model,
        last_ride=ride_model,
        aggregate=aggregate_model,
        battery=battery_model,
        location=location_model,
        alarm=alarm_model,
        has_flow_plus=has_flow_plus,
        has_connect_module=has_connect_module,
        last_updated=last_updated,
    )

    # --- BikeInfo fields ---
    assert bike_data.info.bike_id == info["bike_id"]
    assert bike_data.info.name == info["name"]
    assert bike_data.info.model == info["model"]
    assert bike_data.info.serial_number == info["serial_number"]

    # --- BikeTelemetry fields ---
    assert bike_data.telemetry.odometer_km == telemetry["odometer_km"]
    assert bike_data.telemetry.motor_hours_total == telemetry["motor_hours_total"]
    assert bike_data.telemetry.motor_hours_with_assist == telemetry["motor_hours_with_assist"]
    assert bike_data.telemetry.battery_charge_cycles == telemetry["battery_charge_cycles"]
    assert bike_data.telemetry.battery_lifetime_energy_wh == telemetry["battery_lifetime_energy_wh"]
    assert bike_data.telemetry.next_service_odometer_km == telemetry["next_service_odometer_km"]
    assert bike_data.telemetry.max_assist_speed_kmh == telemetry["max_assist_speed_kmh"]

    # --- RideData fields (when present) ---
    if ride is None:
        assert bike_data.last_ride is None
    else:
        assert bike_data.last_ride is not None
        assert bike_data.last_ride.ride_id == ride["ride_id"]
        assert bike_data.last_ride.distance_km == ride["distance_km"]
        assert bike_data.last_ride.duration_minutes == ride["duration_minutes"]
        assert bike_data.last_ride.average_speed_kmh == ride["average_speed_kmh"]
        assert bike_data.last_ride.max_speed_kmh == ride["max_speed_kmh"]
        assert bike_data.last_ride.elevation_gain_m == ride["elevation_gain_m"]
        assert bike_data.last_ride.elevation_loss_m == ride["elevation_loss_m"]
        assert bike_data.last_ride.calories_kcal == ride["calories_kcal"]
        assert bike_data.last_ride.avg_rider_power_w == ride["avg_rider_power_w"]
        assert bike_data.last_ride.max_rider_power_w == ride["max_rider_power_w"]
        assert bike_data.last_ride.avg_cadence_rpm == ride["avg_cadence_rpm"]
        assert bike_data.last_ride.max_cadence_rpm == ride["max_cadence_rpm"]
        assert bike_data.last_ride.motor_power_ratio_pct == ride["motor_power_ratio_pct"]

    # --- AggregateStats fields ---
    assert bike_data.aggregate.total_rides == aggregate["total_rides"]
    assert bike_data.aggregate.total_distance_km == aggregate["total_distance_km"]
    assert bike_data.aggregate.total_ride_time_hours == aggregate["total_ride_time_hours"]
    assert bike_data.aggregate.total_calories_kcal == aggregate["total_calories_kcal"]
    assert bike_data.aggregate.total_elevation_gain_m == aggregate["total_elevation_gain_m"]
    assert bike_data.aggregate.average_speed_kmh == aggregate["average_speed_kmh"]

    # --- BatteryStatus fields (when present) ---
    if battery is None:
        assert bike_data.battery is None
    else:
        assert bike_data.battery is not None
        assert bike_data.battery.state_of_charge_pct == battery["state_of_charge_pct"]
        assert bike_data.battery.charging_status == battery["charging_status"]

    # --- LocationData fields (when present) ---
    if location is None:
        assert bike_data.location is None
    else:
        assert bike_data.location is not None
        assert bike_data.location.latitude == location["latitude"]
        assert bike_data.location.longitude == location["longitude"]
        assert bike_data.location.accuracy_m == location["accuracy_m"]

    # --- AlarmStatus fields (when present) ---
    if alarm is None:
        assert bike_data.alarm is None
    else:
        assert bike_data.alarm is not None
        assert bike_data.alarm.alarm_triggered == alarm["alarm_triggered"]
        assert bike_data.alarm.alarm_armed == alarm["alarm_armed"]

    # --- Top-level BikeData flags ---
    assert bike_data.has_flow_plus == has_flow_plus
    assert bike_data.has_connect_module == has_connect_module
    assert bike_data.last_updated == last_updated
