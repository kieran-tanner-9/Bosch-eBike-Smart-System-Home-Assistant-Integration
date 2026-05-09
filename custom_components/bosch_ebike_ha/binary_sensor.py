"""Binary sensor entities for Bosch eBike (Smart System) integration.

Provides two binary sensor entities per bike when a ConnectModule is present:

- ``TheftAlarmBinarySensor`` — ``device_class=TAMPER``; fires a persistent
  notification when the alarm transitions from ``off`` to ``on``.
- ``AlarmArmedBinarySensor``  — ``device_class=SAFETY``; reflects whether the
  alarm is currently armed.

Both entities return ``STATE_UNAVAILABLE`` when
``coordinator.data.has_connect_module`` is ``False``.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BikeCoordinator

_LOGGER = logging.getLogger(__name__)

_NOTIFICATION_ID_PREFIX = "bosch_ebike_theft_alarm"


class _BoschEBikeBinarySensorBase(CoordinatorEntity[BikeCoordinator], BinarySensorEntity):
    """Shared base for Bosch eBike binary sensor entities.

    Handles:
    - ``unique_id`` construction
    - ``device_info`` linking to the bike device
    - ``available`` logic (coordinator success + ConnectModule present)
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BikeCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._bike_id = coordinator.bike_id

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._bike_id)},
        )

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """Return False when the coordinator failed or ConnectModule is absent."""
        if not self.coordinator.last_update_success:
            return False
        if self.coordinator.data is None:
            return False
        return self.coordinator.data.has_connect_module

    # ------------------------------------------------------------------
    # Extra state attributes
    # ------------------------------------------------------------------

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Include last_updated UTC timestamp from the coordinator."""
        attrs: dict[str, Any] = {}
        if self.coordinator.data is not None:
            attrs["last_updated"] = self.coordinator.data.last_updated.isoformat()
        return attrs


class TheftAlarmBinarySensor(_BoschEBikeBinarySensorBase):
    """Binary sensor that is ``on`` when the bike's theft alarm has been triggered.

    Overrides ``_handle_coordinator_update`` to detect ``False → True``
    transitions and fire a Home Assistant persistent notification.
    """

    _attr_device_class = BinarySensorDeviceClass.TAMPER
    _attr_translation_key = "theft_alarm_active"
    _attr_name = "Theft Alarm Active"

    def __init__(
        self,
        coordinator: BikeCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._bike_id}_theft_alarm_active"
        # Track the previous alarm state to detect False → True transitions.
        self._prev_alarm_triggered: bool = False

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def is_on(self) -> bool | None:
        """Return True when the alarm is triggered, None when unavailable."""
        if not self.available:
            return None
        if self.coordinator.data is None or self.coordinator.data.alarm is None:
            return None
        return self.coordinator.data.alarm.alarm_triggered

    # ------------------------------------------------------------------
    # Coordinator update hook
    # ------------------------------------------------------------------

    def _handle_coordinator_update(self) -> None:
        """Detect False → True alarm transitions and fire a persistent notification."""
        if (
            self.coordinator.data is not None
            and self.coordinator.data.alarm is not None
            and self.coordinator.data.has_connect_module
        ):
            new_triggered = self.coordinator.data.alarm.alarm_triggered
            if new_triggered and not self._prev_alarm_triggered:
                # Alarm just transitioned from off → on.
                bike_name = self.coordinator.data.info.name
                self.hass.components.persistent_notification.async_create(
                    message=f"eBike theft alarm triggered: {bike_name}",
                    title="eBike Theft Alarm",
                    notification_id=f"{_NOTIFICATION_ID_PREFIX}_{self._bike_id}",
                )
                _LOGGER.warning(
                    "Theft alarm triggered for bike '%s' (%s)",
                    bike_name,
                    self._bike_id,
                )
            self._prev_alarm_triggered = new_triggered

        super()._handle_coordinator_update()


class AlarmArmedBinarySensor(_BoschEBikeBinarySensorBase):
    """Binary sensor that is ``on`` when the bike's alarm is armed."""

    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_translation_key = "alarm_armed"
    _attr_name = "Alarm Armed"

    def __init__(
        self,
        coordinator: BikeCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._bike_id}_alarm_armed"

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def is_on(self) -> bool | None:
        """Return True when the alarm is armed, None when unavailable."""
        if not self.available:
            return None
        if self.coordinator.data is None or self.coordinator.data.alarm is None:
            return None
        return self.coordinator.data.alarm.alarm_armed


# ---------------------------------------------------------------------------
# async_setup_entry
# ---------------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bosch eBike binary sensor entities from a config entry.

    Retrieves all ``BikeCoordinator`` instances stored under
    ``hass.data[DOMAIN][entry.entry_id]`` and creates one
    ``TheftAlarmBinarySensor`` and one ``AlarmArmedBinarySensor`` per
    coordinator.
    """
    coordinators: list[BikeCoordinator] = hass.data[DOMAIN][entry.entry_id]["coordinators"]

    entities: list[_BoschEBikeBinarySensorBase] = []
    for coordinator in coordinators:
        entities.append(TheftAlarmBinarySensor(coordinator, entry))
        entities.append(AlarmArmedBinarySensor(coordinator, entry))

    async_add_entities(entities)
