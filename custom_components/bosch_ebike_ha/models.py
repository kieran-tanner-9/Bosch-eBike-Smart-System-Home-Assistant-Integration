"""Data models for Bosch eBike (Smart System) integration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class BikeInfo:
    bike_id: str
    name: str
    model: str
    serial_number: str


@dataclass
class BikeTelemetry:
    odometer_km: float | None
    motor_hours_total: float | None
    motor_hours_with_assist: float | None
    battery_charge_cycles: int | None
    battery_lifetime_energy_wh: float | None
    next_service_odometer_km: float | None
    max_assist_speed_kmh: float | None


@dataclass
class RideData:
    ride_id: str
    completed_at: datetime | None
    distance_km: float | None
    duration_minutes: float | None
    average_speed_kmh: float | None
    max_speed_kmh: float | None
    elevation_gain_m: float | None
    elevation_loss_m: float | None
    calories_kcal: float | None
    # Flow+ fields (None when subscription inactive)
    avg_rider_power_w: float | None
    max_rider_power_w: float | None
    avg_cadence_rpm: float | None
    max_cadence_rpm: float | None
    motor_power_ratio_pct: float | None


@dataclass
class AggregateStats:
    total_rides: int | None
    total_distance_km: float | None
    total_ride_time_hours: float | None
    total_calories_kcal: float | None
    total_elevation_gain_m: float | None
    average_speed_kmh: float | None


@dataclass
class BatteryStatus:
    state_of_charge_pct: int | None  # 0-100
    charging_status: str | None  # "charging" | "discharging" | "full" | "unknown"


@dataclass
class LocationData:
    latitude: float | None
    longitude: float | None
    accuracy_m: float | None
    timestamp: datetime | None


@dataclass
class AlarmStatus:
    alarm_triggered: bool
    alarm_armed: bool


@dataclass
class BikeData:
    """Aggregated data payload distributed by BikeCoordinator."""

    info: BikeInfo
    telemetry: BikeTelemetry
    last_ride: RideData | None  # None if no rides recorded
    aggregate: AggregateStats
    battery: BatteryStatus | None  # None if Flow+ inactive
    location: LocationData | None  # None if no ConnectModule
    alarm: AlarmStatus | None  # None if no ConnectModule
    has_flow_plus: bool
    has_connect_module: bool
    last_updated: datetime
