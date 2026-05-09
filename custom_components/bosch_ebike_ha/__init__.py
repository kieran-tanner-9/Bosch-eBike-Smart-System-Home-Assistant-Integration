"""Bosch eBike (Smart System) Home Assistant integration.

Entry points:
- ``async_setup_entry``   — called by HA when a config entry is loaded.
- ``async_unload_entry``  — called by HA when a config entry is unloaded.

Setup sequence (``async_setup_entry``):
1. Create ``BoschEBikeApiClient`` from the HA-managed aiohttp session and the
   entry's OAuth2 session.
2. Call ``fetch_bikes`` to discover all bikes for the account.
3. Register a Home Assistant device entry for each bike.
4. Create one ``BikeCoordinator`` per bike and perform the first refresh.
5. For bikes where ``has_flow_plus`` is ``True``, create a
   ``BatteryCoordinator`` as well.
6. Store coordinators in ``hass.data[DOMAIN][entry.entry_id]``.
7. Forward platform setup to ``sensor``, ``binary_sensor``, and
   ``device_tracker``.
8. Register an ``update_listener`` so that options changes (e.g. unit system)
   trigger a config entry reload.

Requirements: 5.1, 6.1–6.4
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_entry_oauth2_flow

from .api import BoschEBikeApiClient
from .const import DOMAIN
from .coordinator import BatteryCoordinator, BikeCoordinator

_LOGGER = logging.getLogger(__name__)

# Platforms that this integration provides entities for.
PLATFORMS = ["sensor", "binary_sensor", "device_tracker"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Bosch eBike integration from a config entry.

    Creates API client, discovers bikes, registers device entries, creates
    coordinators, and forwards platform setup.

    Returns ``True`` on success, ``False`` if setup cannot be completed.
    """
    # ------------------------------------------------------------------
    # 1. Build the API client
    # ------------------------------------------------------------------
    session = async_get_clientsession(hass)
    oauth_session = config_entry_oauth2_flow.OAuth2Session(hass, entry, entry.domain)
    client = BoschEBikeApiClient(session, oauth_session)

    # ------------------------------------------------------------------
    # 2. Discover bikes
    # ------------------------------------------------------------------
    try:
        bikes = await client.fetch_bikes()
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Failed to fetch bikes during setup for entry %s", entry.entry_id)
        return False

    if not bikes:
        _LOGGER.warning(
            "No bikes found for entry %s — setup aborted", entry.entry_id
        )
        return False

    # ------------------------------------------------------------------
    # 3. Register device entries in the device registry
    # ------------------------------------------------------------------
    device_registry = dr.async_get(hass)
    for bike in bikes:
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, bike.bike_id)},
            name=bike.name,
            manufacturer="Bosch",
            model=bike.model,
        )

    # ------------------------------------------------------------------
    # 4. Create BikeCoordinators and perform first refresh
    #
    # Each bike is set up independently.  A failure in one bike's first
    # refresh is logged and skipped so that other bikes are not affected
    # (Requirement 6.3).
    # ------------------------------------------------------------------
    bike_coordinators: list[BikeCoordinator] = []
    battery_coordinators: list[BatteryCoordinator] = []

    for bike in bikes:
        coordinator = BikeCoordinator(hass, entry, client, bike.bike_id)
        try:
            await coordinator.async_config_entry_first_refresh()
        except Exception:  # noqa: BLE001
            _LOGGER.exception(
                "First refresh failed for bike %s — skipping this bike; "
                "other bikes will continue to be set up",
                bike.bike_id,
            )
            continue

        bike_coordinators.append(coordinator)

        # ------------------------------------------------------------------
        # 5. Create BatteryCoordinator for Flow+ bikes
        # ------------------------------------------------------------------
        if coordinator.data is not None and coordinator.data.has_flow_plus:
            battery_coordinator = BatteryCoordinator(hass, entry, client, bike.bike_id)
            try:
                await battery_coordinator.async_config_entry_first_refresh()
            except Exception:  # noqa: BLE001
                _LOGGER.exception(
                    "BatteryCoordinator first refresh failed for bike %s — "
                    "battery entities will be unavailable",
                    bike.bike_id,
                )
            else:
                battery_coordinators.append(battery_coordinator)
                _LOGGER.debug(
                    "Created BatteryCoordinator for Flow+ bike %s", bike.bike_id
                )

    # ------------------------------------------------------------------
    # 6. Store coordinators in hass.data
    # ------------------------------------------------------------------
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinators": bike_coordinators,
        "battery_coordinators": battery_coordinators,
        "client": client,
    }

    # ------------------------------------------------------------------
    # 7. Forward platform setup
    # ------------------------------------------------------------------
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # ------------------------------------------------------------------
    # 8. Register update_listener for options changes (e.g. unit system)
    # ------------------------------------------------------------------
    entry.async_on_unload(
        entry.add_update_listener(_async_update_listener)
    )

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options updates by reloading the config entry.

    Called when the user changes options (e.g. unit system) via the options
    flow.  Reloading the entry causes all entities to be re-created with the
    new settings applied.
    """
    _LOGGER.debug(
        "Options updated for entry %s — reloading integration", entry.entry_id
    )
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Bosch eBike config entry.

    Unloads all platforms and cancels all coordinator refresh tasks.

    Returns ``True`` if unloading succeeded, ``False`` otherwise.
    """
    # Unload all platforms first.
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        entry_data: dict[str, Any] = hass.data[DOMAIN].pop(entry.entry_id, {})

        # Cancel all BikeCoordinator refresh tasks.
        for coordinator in entry_data.get("coordinators", []):
            coordinator.async_shutdown()

        # Cancel all BatteryCoordinator refresh tasks.
        for coordinator in entry_data.get("battery_coordinators", []):
            coordinator.async_shutdown()

    return unload_ok
