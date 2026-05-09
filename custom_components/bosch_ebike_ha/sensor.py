"""Sensor entities for Bosch eBike (Smart System) integration.

All sensor entities extend CoordinatorEntity[BikeCoordinator] and SensorEntity.
Unit conversion (distance/speed/elevation) is applied at the entity layer so
that the coordinator and data models always store API-native metric values.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_UNIT_SYSTEM, DOMAIN, UNIT_METRIC
from .coordinator import BikeCoordinator
from .models import BikeData
from .unit_converter import convert_distance, convert_elevation, convert_speed

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sensor description dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BoschEBikeSensorDescription(SensorEntityDescription):
    """Extended sensor description for Bosch eBike sensors.

    Attributes
    ----------
    value_fn:
        Callable that extracts the raw (metric) value from a ``BikeData``
        instance.  Returns ``None`` when the source field is absent.
    unit_fn:
        Optional callable that accepts ``(raw_value, unit_system)`` and
        returns ``(converted_value, unit_string)``.  When ``None`` the raw
        value is used directly and ``native_unit_of_measurement`` is taken
        from the description's ``native_unit_of_measurement`` field.
    requires_flow_plus:
        When ``True`` the entity returns ``STATE_UNAVAILABLE`` if
        ``coordinator.data.has_flow_plus`` is ``False``.
    requires_connect_module:
        When ``True`` the entity returns ``STATE_UNAVAILABLE`` if
        ``coordinator.data.has_connect_module`` is ``False``.
    """

    value_fn: Callable[[BikeData], Any] = lambda _: None  # noqa: E731
    unit_fn: Callable[[Any, str], tuple[Any, str]] | None = None
    requires_flow_plus: bool = False
    requires_connect_module: bool = False


# ---------------------------------------------------------------------------
# Sensor descriptions — one entry per sensor entity
# ---------------------------------------------------------------------------

BIKE_SENSORS: tuple[BoschEBikeSensorDescription, ...] = (
    # --- Bike telemetry ---
    BoschEBikeSensorDescription(
        key="odometer",
        translation_key="odometer",
        name="Odometer",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.telemetry.odometer_km,
        unit_fn=convert_distance,
    ),
    BoschEBikeSensorDescription(
        key="motor_hours",
        translation_key="motor_hours",
        name="Motor Hours",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="h",
        value_fn=lambda d: d.telemetry.motor_hours_total,
    ),
    BoschEBikeSensorDescription(
        key="battery_charge_cycles",
        translation_key="battery_charge_cycles",
        name="Battery Charge Cycles",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=None,
        value_fn=lambda d: d.telemetry.battery_charge_cycles,
    ),
    BoschEBikeSensorDescription(
        key="battery_lifetime_energy",
        translation_key="battery_lifetime_energy",
        name="Battery Lifetime Energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="Wh",
        value_fn=lambda d: d.telemetry.battery_lifetime_energy_wh,
    ),
    BoschEBikeSensorDescription(
        key="next_service_odometer",
        translation_key="next_service_odometer",
        name="Next Service Odometer",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.telemetry.next_service_odometer_km,
        unit_fn=convert_distance,
    ),
    BoschEBikeSensorDescription(
        key="max_assist_speed",
        translation_key="max_assist_speed",
        name="Max Assist Speed",
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.telemetry.max_assist_speed_kmh,
        unit_fn=convert_speed,
    ),
    # --- Last ride ---
    BoschEBikeSensorDescription(
        key="last_ride_distance",
        translation_key="last_ride_distance",
        name="Last Ride Distance",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.last_ride.distance_km if d.last_ride else None,
        unit_fn=convert_distance,
    ),
    BoschEBikeSensorDescription(
        key="last_ride_duration",
        translation_key="last_ride_duration",
        name="Last Ride Duration",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="min",
        value_fn=lambda d: d.last_ride.duration_minutes if d.last_ride else None,
    ),
    BoschEBikeSensorDescription(
        key="last_ride_avg_speed",
        translation_key="last_ride_avg_speed",
        name="Last Ride Average Speed",
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.last_ride.average_speed_kmh if d.last_ride else None,
        unit_fn=convert_speed,
    ),
    BoschEBikeSensorDescription(
        key="last_ride_max_speed",
        translation_key="last_ride_max_speed",
        name="Last Ride Max Speed",
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.last_ride.max_speed_kmh if d.last_ride else None,
        unit_fn=convert_speed,
    ),
    BoschEBikeSensorDescription(
        key="last_ride_elevation_gain",
        translation_key="last_ride_elevation_gain",
        name="Last Ride Elevation Gain",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.last_ride.elevation_gain_m if d.last_ride else None,
        unit_fn=convert_elevation,
    ),
    BoschEBikeSensorDescription(
        key="last_ride_elevation_loss",
        translation_key="last_ride_elevation_loss",
        name="Last Ride Elevation Loss",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.last_ride.elevation_loss_m if d.last_ride else None,
        unit_fn=convert_elevation,
    ),
    BoschEBikeSensorDescription(
        key="last_ride_calories",
        translation_key="last_ride_calories",
        name="Last Ride Calories",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="kcal",
        value_fn=lambda d: d.last_ride.calories_kcal if d.last_ride else None,
    ),
    BoschEBikeSensorDescription(
        key="last_ride_date",
        translation_key="last_ride_date",
        name="Last Ride Date",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.last_ride.completed_at if d.last_ride else None,
    ),
    # --- Aggregate stats ---
    BoschEBikeSensorDescription(
        key="total_rides",
        translation_key="total_rides",
        name="Total Rides",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=None,
        value_fn=lambda d: d.aggregate.total_rides,
    ),
    BoschEBikeSensorDescription(
        key="total_distance",
        translation_key="total_distance",
        name="Total Distance",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.aggregate.total_distance_km,
        unit_fn=convert_distance,
    ),
    BoschEBikeSensorDescription(
        key="total_ride_time",
        translation_key="total_ride_time",
        name="Total Ride Time",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="h",
        value_fn=lambda d: d.aggregate.total_ride_time_hours,
    ),
    BoschEBikeSensorDescription(
        key="total_calories",
        translation_key="total_calories",
        name="Total Calories",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="kcal",
        value_fn=lambda d: d.aggregate.total_calories_kcal,
    ),
    BoschEBikeSensorDescription(
        key="total_elevation_gain",
        translation_key="total_elevation_gain",
        name="Total Elevation Gain",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.aggregate.total_elevation_gain_m,
        unit_fn=convert_elevation,
    ),
    BoschEBikeSensorDescription(
        key="average_speed",
        translation_key="average_speed",
        name="Average Speed",
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.aggregate.average_speed_kmh,
        unit_fn=convert_speed,
    ),
    # --- Flow+ sensors ---
    BoschEBikeSensorDescription(
        key="last_ride_avg_rider_power",
        translation_key="last_ride_avg_rider_power",
        name="Last Ride Avg Rider Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        value_fn=lambda d: d.last_ride.avg_rider_power_w if d.last_ride else None,
        requires_flow_plus=True,
    ),
    BoschEBikeSensorDescription(
        key="last_ride_max_rider_power",
        translation_key="last_ride_max_rider_power",
        name="Last Ride Max Rider Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        value_fn=lambda d: d.last_ride.max_rider_power_w if d.last_ride else None,
        requires_flow_plus=True,
    ),
    BoschEBikeSensorDescription(
        key="last_ride_avg_cadence",
        translation_key="last_ride_avg_cadence",
        name="Last Ride Avg Cadence",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="RPM",
        value_fn=lambda d: d.last_ride.avg_cadence_rpm if d.last_ride else None,
        requires_flow_plus=True,
    ),
    BoschEBikeSensorDescription(
        key="last_ride_max_cadence",
        translation_key="last_ride_max_cadence",
        name="Last Ride Max Cadence",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="RPM",
        value_fn=lambda d: d.last_ride.max_cadence_rpm if d.last_ride else None,
        requires_flow_plus=True,
    ),
    BoschEBikeSensorDescription(
        key="last_ride_motor_power_ratio",
        translation_key="last_ride_motor_power_ratio",
        name="Last Ride Motor Power Ratio",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        value_fn=lambda d: d.last_ride.motor_power_ratio_pct if d.last_ride else None,
        requires_flow_plus=True,
    ),
    BoschEBikeSensorDescription(
        key="battery_soc",
        translation_key="battery_soc",
        name="Battery State of Charge",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        value_fn=lambda d: d.battery.state_of_charge_pct if d.battery else None,
        requires_flow_plus=True,
    ),
    BoschEBikeSensorDescription(
        key="battery_charging_status",
        translation_key="battery_charging_status",
        name="Battery Charging Status",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=None,
        value_fn=lambda d: d.battery.charging_status if d.battery else None,
        requires_flow_plus=True,
    ),
    # --- ConnectModule sensors ---
    BoschEBikeSensorDescription(
        key="bike_location_accuracy",
        translation_key="bike_location_accuracy",
        name="Bike Location Accuracy",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.location.accuracy_m if d.location else None,
        unit_fn=convert_elevation,  # m → ft, same factor as elevation
        requires_connect_module=True,
    ),
    BoschEBikeSensorDescription(
        key="bike_location_timestamp",
        translation_key="bike_location_timestamp",
        name="Bike Location Timestamp",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.location.timestamp if d.location else None,
        requires_connect_module=True,
    ),
)


# ---------------------------------------------------------------------------
# Base sensor entity
# ---------------------------------------------------------------------------


class BoschEBikeSensor(CoordinatorEntity[BikeCoordinator], SensorEntity):
    """Base class for all Bosch eBike sensor entities.

    Handles:
    - ``unique_id`` construction
    - ``device_info`` linking to the bike device
    - ``available`` logic (coordinator success + source field not None)
    - ``extra_state_attributes`` with ``last_updated`` UTC timestamp
    - Unit conversion via ``description.unit_fn``
    - Feature-gate checks (Flow+, ConnectModule)
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BikeCoordinator,
        entry: ConfigEntry,
        description: BoschEBikeSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description: BoschEBikeSensorDescription = description
        self._entry = entry
        self._bike_id = coordinator.bike_id

        self._attr_unique_id = f"{self._bike_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._bike_id)},
        )

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """Return False when the coordinator failed or the source field is None."""
        if not self.coordinator.last_update_success:
            return False
        if self.coordinator.data is None:
            return False
        # Feature-gate checks
        if self.entity_description.requires_flow_plus and not self.coordinator.data.has_flow_plus:
            return False
        if self.entity_description.requires_connect_module and not self.coordinator.data.has_connect_module:
            return False
        # Source field must be non-None
        return self.entity_description.value_fn(self.coordinator.data) is not None

    # ------------------------------------------------------------------
    # Native value and unit
    # ------------------------------------------------------------------

    @property
    def native_value(self) -> Any:
        """Return the sensor value, applying unit conversion where applicable."""
        if not self.coordinator.last_update_success or self.coordinator.data is None:
            return None

        # Feature-gate: return STATE_UNAVAILABLE string for gated sensors
        if self.entity_description.requires_flow_plus and not self.coordinator.data.has_flow_plus:
            return STATE_UNAVAILABLE
        if self.entity_description.requires_connect_module and not self.coordinator.data.has_connect_module:
            return STATE_UNAVAILABLE

        raw = self.entity_description.value_fn(self.coordinator.data)
        if raw is None:
            return None

        if self.entity_description.unit_fn is not None:
            unit_system = self._entry.options.get(CONF_UNIT_SYSTEM, UNIT_METRIC)
            converted, _unit = self.entity_description.unit_fn(raw, unit_system)
            return converted

        return raw

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit string, dynamically resolved for convertible sensors."""
        if self.entity_description.unit_fn is None:
            return self.entity_description.native_unit_of_measurement

        # Derive unit from the converter using a sentinel value (0.0)
        # so we get the correct unit string without needing real data.
        unit_system = self._entry.options.get(CONF_UNIT_SYSTEM, UNIT_METRIC)
        _value, unit = self.entity_description.unit_fn(0.0, unit_system)
        return unit

    # ------------------------------------------------------------------
    # Extra state attributes
    # ------------------------------------------------------------------

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Include last_updated UTC timestamp from the coordinator."""
        attrs: dict[str, Any] = {}
        if self.coordinator.data is not None:
            last_updated: datetime = self.coordinator.data.last_updated
            attrs["last_updated"] = last_updated.isoformat()
        return attrs


# ---------------------------------------------------------------------------
# BatterySocSensor — SoC change-detection subclass
# ---------------------------------------------------------------------------

_BATTERY_SOC_KEY = "battery_soc"


class BatterySocSensor(BoschEBikeSensor):
    """Sensor for battery state-of-charge with 1 % change-detection filtering.

    Overrides ``_handle_coordinator_update`` so that a Home Assistant
    state-changed event is only fired when the SoC value changes by at least
    1 percentage point.  Smaller fluctuations are silently suppressed.

    Requirements: 8.3
    """

    def __init__(
        self,
        coordinator: BikeCoordinator,
        entry: ConfigEntry,
        description: BoschEBikeSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, description)
        # Track the last SoC value that was written to HA state.
        # Initialise to None so the very first update always propagates.
        self._prev_soc: int | None = None

    # ------------------------------------------------------------------
    # Coordinator update hook
    # ------------------------------------------------------------------

    def _handle_coordinator_update(self) -> None:
        """Only propagate the update when SoC has changed by ≥ 1 %."""
        new_soc: int | None = None
        if (
            self.coordinator.data is not None
            and self.coordinator.data.battery is not None
        ):
            new_soc = self.coordinator.data.battery.state_of_charge_pct

        if new_soc is None or self._prev_soc is None:
            # Always propagate when either value is unknown.
            self._prev_soc = new_soc
            super()._handle_coordinator_update()
            return

        if abs(new_soc - self._prev_soc) >= 1:
            self._prev_soc = new_soc
            super()._handle_coordinator_update()
        # else: change < 1 % — suppress the state write entirely.


# ---------------------------------------------------------------------------
# async_setup_entry
# ---------------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bosch eBike sensor entities from a config entry.

    Retrieves all ``BikeCoordinator`` instances stored under
    ``hass.data[DOMAIN][entry.entry_id]`` and creates one
    ``BoschEBikeSensor`` (or ``BatterySocSensor`` for the battery SoC entity)
    per coordinator per sensor description.
    """
    coordinators: list[BikeCoordinator] = hass.data[DOMAIN][entry.entry_id]["coordinators"]

    entities: list[BoschEBikeSensor] = []
    for coordinator in coordinators:
        for description in BIKE_SENSORS:
            if description.key == _BATTERY_SOC_KEY:
                entities.append(BatterySocSensor(coordinator, entry, description))
            else:
                entities.append(BoschEBikeSensor(coordinator, entry, description))

    async_add_entities(entities)
