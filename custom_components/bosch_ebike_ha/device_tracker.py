"""Device tracker entity for Bosch eBike (Smart System) integration.

Provides ``BikeTrackerEntity`` — a GPS-based ``TrackerEntity`` that reports
the bike's last known location when a ConnectModule is paired.

Behaviour:
- ``source_type`` is always ``SourceType.GPS``.
- ``latitude`` / ``longitude`` / ``location_accuracy`` are read from
  ``coordinator.data.location``.
- When the API returns no location data (``location`` is ``None``) the entity
  state becomes ``not_home`` and the last known coordinates are retained as
  extra state attributes (cached in the coordinator).
- When ``coordinator.data.has_connect_module`` is ``False`` the entity state
  is ``not_home`` (no ConnectModule paired).
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BikeCoordinator

_LOGGER = logging.getLogger(__name__)


class BikeTrackerEntity(CoordinatorEntity[BikeCoordinator], TrackerEntity):
    """GPS device tracker for a Bosch eBike with ConnectModule.

    The entity is always registered at setup time.  When the ConnectModule is
    absent or the bike has no current GPS fix the state is ``not_home`` and
    the last known coordinates (if any) are exposed as extra state attributes.
    """

    _attr_has_entity_name = True
    _attr_name = "Location"

    def __init__(
        self,
        coordinator: BikeCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._bike_id = coordinator.bike_id

        self._attr_unique_id = f"{self._bike_id}_bike_location"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._bike_id)},
        )

        # Cache for last known coordinates — stored on the coordinator so that
        # it survives entity re-creation (e.g. after a config entry reload).
        if not hasattr(coordinator, "_last_known_latitude"):
            coordinator._last_known_latitude: float | None = None
        if not hasattr(coordinator, "_last_known_longitude"):
            coordinator._last_known_longitude: float | None = None

    # ------------------------------------------------------------------
    # TrackerEntity required properties
    # ------------------------------------------------------------------

    @property
    def source_type(self) -> SourceType:
        """Return GPS as the source type."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Return the current (or last known) latitude."""
        location = self._current_location
        if location is not None and location.latitude is not None:
            return location.latitude
        # Fall back to cached value
        return self.coordinator._last_known_latitude

    @property
    def longitude(self) -> float | None:
        """Return the current (or last known) longitude."""
        location = self._current_location
        if location is not None and location.longitude is not None:
            return location.longitude
        # Fall back to cached value
        return self.coordinator._last_known_longitude

    @property
    def location_accuracy(self) -> int:
        """Return GPS fix accuracy in metres (0 when unknown)."""
        location = self._current_location
        if location is not None and location.accuracy_m is not None:
            return int(location.accuracy_m)
        return 0

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        """Return 'home'/'not_home' based on location availability.

        Returns ``not_home`` when:
        - ConnectModule is not paired (``has_connect_module`` is ``False``).
        - The API returned no location data for this poll cycle.

        When a valid location is available the base ``TrackerEntity``
        implementation returns ``not_home`` by default (since we don't
        implement zone detection here); the latitude/longitude attributes
        are what matter for map display.
        """
        if not self._has_connect_module:
            return "not_home"
        if self._current_location is None:
            return "not_home"
        if (
            self._current_location.latitude is None
            or self._current_location.longitude is None
        ):
            return "not_home"
        # A valid fix is present — TrackerEntity base class returns "not_home"
        # unless zone detection is implemented; we return "not_home" here too
        # but with valid lat/lon attributes so the map card works correctly.
        return "not_home"

    # ------------------------------------------------------------------
    # Coordinator update hook — cache last known coordinates
    # ------------------------------------------------------------------

    def _handle_coordinator_update(self) -> None:
        """Cache coordinates whenever a valid fix is received."""
        location = self._current_location
        if (
            location is not None
            and location.latitude is not None
            and location.longitude is not None
        ):
            self.coordinator._last_known_latitude = location.latitude
            self.coordinator._last_known_longitude = location.longitude
        super()._handle_coordinator_update()

    # ------------------------------------------------------------------
    # Extra state attributes — expose last known coordinates
    # ------------------------------------------------------------------

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose last known coordinates and location timestamp."""
        attrs: dict[str, Any] = {}

        # Always include last known coordinates when available
        if self.coordinator._last_known_latitude is not None:
            attrs["last_known_latitude"] = self.coordinator._last_known_latitude
        if self.coordinator._last_known_longitude is not None:
            attrs["last_known_longitude"] = self.coordinator._last_known_longitude

        # Include location timestamp when a current fix is available
        location = self._current_location
        if location is not None and location.timestamp is not None:
            attrs["gps_timestamp"] = location.timestamp.isoformat()

        # Include last_updated from coordinator data
        if self.coordinator.data is not None:
            attrs["last_updated"] = self.coordinator.data.last_updated.isoformat()

        return attrs

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _has_connect_module(self) -> bool:
        """Return True when the coordinator data indicates a ConnectModule."""
        if not self.coordinator.last_update_success:
            return False
        if self.coordinator.data is None:
            return False
        return self.coordinator.data.has_connect_module

    @property
    def _current_location(self):
        """Return the current LocationData or None."""
        if not self.coordinator.last_update_success:
            return None
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.location


# ---------------------------------------------------------------------------
# async_setup_entry
# ---------------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bosch eBike device tracker entities from a config entry.

    Creates one ``BikeTrackerEntity`` per ``BikeCoordinator`` stored under
    ``hass.data[DOMAIN][entry.entry_id]["coordinators"]``.
    """
    coordinators: list[BikeCoordinator] = hass.data[DOMAIN][entry.entry_id]["coordinators"]

    entities: list[BikeTrackerEntity] = [
        BikeTrackerEntity(coordinator, entry) for coordinator in coordinators
    ]
    async_add_entities(entities)
