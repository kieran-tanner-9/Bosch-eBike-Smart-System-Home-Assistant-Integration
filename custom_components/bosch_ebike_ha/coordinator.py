"""Data update coordinators for Bosch eBike (Smart System) integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiAuthError, ApiError, BoschEBikeApiClient
from .const import BATTERY_POLL_INTERVAL_MINUTES, DEFAULT_POLL_INTERVAL_MINUTES, MAX_RETRY_INTERVAL_MINUTES
from .models import BatteryStatus, BikeData

_LOGGER = logging.getLogger(__name__)

_BASE_INTERVAL_SECONDS = DEFAULT_POLL_INTERVAL_MINUTES * 60
_MAX_INTERVAL_SECONDS = MAX_RETRY_INTERVAL_MINUTES * 60


class BikeCoordinator(DataUpdateCoordinator[BikeData]):
    """Coordinator for a single bike.

    Polls the Bosch Data Act API for all bike data and distributes it to
    registered entities. Implements exponential back-off on consecutive
    failures, capped at MAX_RETRY_INTERVAL_MINUTES minutes.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: BoschEBikeApiClient,
        bike_id: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"bosch_ebike_{bike_id}",
            config_entry=config_entry,
            update_interval=timedelta(seconds=_BASE_INTERVAL_SECONDS),
        )
        self.client = client
        self.bike_id = bike_id
        self._consecutive_failures: int = 0

    async def _async_update_data(self) -> BikeData:
        """Fetch all data for this bike from the Bosch API.

        Maps API exceptions to HA coordinator exceptions:
        - ``ApiAuthError``  → ``ConfigEntryAuthFailed`` (triggers re-auth flow)
        - ``ApiError``      → ``UpdateFailed`` (marks entities unavailable)
        """
        try:
            return await self.client.fetch_bike_data(self.bike_id)
        except ApiAuthError as err:
            raise ConfigEntryAuthFailed from err
        except ApiError as err:
            raise UpdateFailed(str(err)) from err

    async def _async_refresh(self) -> None:
        """Override refresh to apply exponential back-off on consecutive failures.

        Calls the parent implementation, then adjusts ``update_interval``
        based on whether the refresh succeeded or failed:

        - On success: reset ``_consecutive_failures`` to 0 and restore the
          base polling interval.
        - On failure: increment ``_consecutive_failures`` and compute the
          next retry interval as::

              min(base * 2**n, MAX_RETRY_INTERVAL_MINUTES * 60)

        After 2 hours of continuous failure the coordinator's built-in
        ``last_update_success = False`` causes all entities to report
        ``unavailable``.
        """
        await super()._async_refresh()

        if self.last_update_success:
            # Successful refresh — reset back-off state.
            self._consecutive_failures = 0
            self.update_interval = timedelta(seconds=_BASE_INTERVAL_SECONDS)
        else:
            # Failed refresh — increment counter and apply back-off.
            self._consecutive_failures += 1
            retry_seconds = min(
                _BASE_INTERVAL_SECONDS * (2 ** self._consecutive_failures),
                _MAX_INTERVAL_SECONDS,
            )
            self.update_interval = timedelta(seconds=retry_seconds)
            _LOGGER.debug(
                "Bike %s: consecutive failures=%d, next retry in %ds",
                self.bike_id,
                self._consecutive_failures,
                retry_seconds,
            )


_BATTERY_INTERVAL_SECONDS = BATTERY_POLL_INTERVAL_MINUTES * 60


class BatteryCoordinator(DataUpdateCoordinator[BatteryStatus]):
    """Coordinator for battery state-of-charge polling (Flow+ bikes only).

    Only instantiated when ``coordinator.data.has_flow_plus`` is ``True``.
    Polls at ``BATTERY_POLL_INTERVAL_MINUTES`` (default 15 minutes).
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: BoschEBikeApiClient,
        bike_id: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"bosch_ebike_battery_{bike_id}",
            config_entry=config_entry,
            update_interval=timedelta(seconds=_BATTERY_INTERVAL_SECONDS),
        )
        self.client = client
        self.bike_id = bike_id

    async def _async_update_data(self) -> BatteryStatus:
        """Fetch battery SoC for this bike from the Bosch API.

        Maps API exceptions to HA coordinator exceptions:
        - ``ApiAuthError``  → ``ConfigEntryAuthFailed`` (triggers re-auth flow)
        - ``ApiError``      → ``UpdateFailed`` (marks entities unavailable)
        """
        try:
            return await self.client.fetch_battery_soc(self.bike_id)
        except ApiAuthError as err:
            raise ConfigEntryAuthFailed from err
        except ApiError as err:
            raise UpdateFailed(str(err)) from err
