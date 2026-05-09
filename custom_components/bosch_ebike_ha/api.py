"""Bosch eBike API client for the Home Assistant integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .const import BASE_URL, REQUEST_TIMEOUT_SECONDS
from .models import (
    AggregateStats,
    AlarmStatus,
    BatteryStatus,
    BikeData,
    BikeInfo,
    BikeTelemetry,
    LocationData,
    RideData,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class ApiError(Exception):
    """Base class for all API errors."""


class ApiAuthError(ApiError):
    """Raised when authentication fails after a retry (HTTP 401 twice)."""


class ApiClientError(ApiError):
    """Raised for HTTP 4xx errors (excluding 401)."""

    def __init__(self, status: int, url: str) -> None:
        super().__init__(f"Client error {status} calling {url}")
        self.status = status
        self.url = url


class ApiServerError(ApiError):
    """Raised for HTTP 5xx errors."""

    def __init__(self, status: int, url: str) -> None:
        super().__init__(f"Server error {status} calling {url}")
        self.status = status
        self.url = url


class ApiTimeoutError(ApiError):
    """Raised when a request times out."""

    def __init__(self, url: str) -> None:
        super().__init__(f"Timeout calling {url}")
        self.url = url


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------


class BoschEBikeApiClient:
    """HTTP client for the Bosch Data Act API.

    Parameters
    ----------
    session:
        An ``aiohttp.ClientSession`` provided by Home Assistant via
        ``homeassistant.helpers.aiohttp_client.async_get_clientsession``.
    oauth_session:
        A ``config_entry_oauth2_flow.OAuth2Session`` that manages token
        refresh transparently.
    """

    def __init__(self, session: aiohttp.ClientSession, oauth_session: Any) -> None:
        self._session = session
        self._oauth_session = oauth_session

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Make an authenticated HTTP request.

        Handles:
        - Token validation before every request.
        - Timeout enforcement.
        - 401 → force-refresh + single retry.
        - 4xx (non-401) → ``ApiClientError`` with ERROR log.
        - 5xx → ``ApiServerError`` with WARNING log.
        - Timeout → ``ApiTimeoutError`` with WARNING log.

        Credentials are never included in log messages.
        """
        await self._oauth_session.async_ensure_token_valid()
        url = f"{BASE_URL}{path}"

        response = await self._do_request(method, url, **kwargs)

        if response.status == 401:
            # Force a token refresh and retry exactly once.
            await self._oauth_session.async_ensure_token_valid(force_refresh=True)
            response = await self._do_request(method, url, **kwargs)
            if response.status == 401:
                raise ApiAuthError("Authentication failed after token refresh")

        await self._raise_for_status(response, url)
        return await response.json()

    async def _do_request(
        self, method: str, url: str, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """Execute a single HTTP request with timeout and auth header."""
        headers = kwargs.pop("headers", {})
        # Access token is read from the session object; never logged.
        headers["Authorization"] = (
            f"Bearer {self._oauth_session.token['access_token']}"
        )
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                return await self._session.request(
                    method, url, headers=headers, **kwargs
                )
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "Timeout calling %s (timeout=%ss)", url, REQUEST_TIMEOUT_SECONDS
            )
            raise ApiTimeoutError(url)

    @staticmethod
    async def _raise_for_status(
        response: aiohttp.ClientResponse, url: str
    ) -> None:
        """Raise the appropriate exception for non-2xx responses."""
        status = response.status
        if 400 <= status < 500:
            _LOGGER.error("API error %s calling %s", status, url)
            raise ApiClientError(status, url)
        if status >= 500:
            _LOGGER.warning("API server error %s calling %s", status, url)
            raise ApiServerError(status, url)

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def fetch_bikes(self) -> list[BikeInfo]:
        """GET /v1/bikes — return all bikes for the authenticated account."""
        data = await self._request("GET", "/v1/bikes")
        bikes: list[BikeInfo] = []
        for item in data if isinstance(data, list) else data.get("bikes", []):
            bikes.append(
                BikeInfo(
                    bike_id=item["id"],
                    name=item.get("name", ""),
                    model=item.get("model", ""),
                    serial_number=item.get("serialNumber", ""),
                )
            )
        return bikes

    async def fetch_bike_telemetry(self, bike_id: str) -> BikeTelemetry:
        """GET /v1/bikes/{id}/telemetry."""
        data = await self._request("GET", f"/v1/bikes/{bike_id}/telemetry")
        return BikeTelemetry(
            odometer_km=data.get("odometerKm"),
            motor_hours_total=data.get("motorHoursTotal"),
            motor_hours_with_assist=data.get("motorHoursWithAssist"),
            battery_charge_cycles=data.get("batteryChargeCycles"),
            battery_lifetime_energy_wh=data.get("batteryLifetimeEnergyWh"),
            next_service_odometer_km=data.get("nextServiceOdometerKm"),
            max_assist_speed_kmh=data.get("maxAssistSpeedKmh"),
        )

    async def fetch_ride_history(self, bike_id: str) -> RideData | None:
        """GET /v1/bikes/{id}/rides?limit=1&sort=desc — most recent ride."""
        data = await self._request(
            "GET",
            f"/v1/bikes/{bike_id}/rides",
            params={"limit": "1", "sort": "desc"},
        )
        rides = data if isinstance(data, list) else data.get("rides", [])
        if not rides:
            return None
        return _parse_ride(rides[0])

    async def fetch_aggregate_stats(self, bike_id: str) -> AggregateStats:
        """GET /v1/bikes/{id}/stats."""
        data = await self._request("GET", f"/v1/bikes/{bike_id}/stats")
        return AggregateStats(
            total_rides=data.get("totalRides"),
            total_distance_km=data.get("totalDistanceKm"),
            total_ride_time_hours=data.get("totalRideTimeHours"),
            total_calories_kcal=data.get("totalCaloriesKcal"),
            total_elevation_gain_m=data.get("totalElevationGainM"),
            average_speed_kmh=data.get("averageSpeedKmh"),
        )

    async def fetch_flow_plus_ride(self, bike_id: str) -> RideData | None:
        """GET /v1/bikes/{id}/rides/latest/flow-plus — Flow+ enhanced ride."""
        data = await self._request(
            "GET", f"/v1/bikes/{bike_id}/rides/latest/flow-plus"
        )
        return _parse_ride(data)

    async def fetch_battery_soc(self, bike_id: str) -> BatteryStatus:
        """GET /v1/bikes/{id}/battery."""
        data = await self._request("GET", f"/v1/bikes/{bike_id}/battery")
        return BatteryStatus(
            state_of_charge_pct=data.get("stateOfChargePct"),
            charging_status=data.get("chargingStatus"),
        )

    async def fetch_location(self, bike_id: str) -> LocationData:
        """GET /v1/bikes/{id}/location."""
        data = await self._request("GET", f"/v1/bikes/{bike_id}/location")
        raw_ts = data.get("timestamp")
        timestamp: datetime | None = None
        if raw_ts:
            try:
                timestamp = datetime.fromisoformat(raw_ts)
            except ValueError:
                _LOGGER.warning("Could not parse location timestamp: %s", raw_ts)
        return LocationData(
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            accuracy_m=data.get("accuracyM"),
            timestamp=timestamp,
        )

    async def fetch_alarm_status(self, bike_id: str) -> AlarmStatus:
        """GET /v1/bikes/{id}/alarm."""
        data = await self._request("GET", f"/v1/bikes/{bike_id}/alarm")
        return AlarmStatus(
            alarm_triggered=bool(data.get("alarmTriggered", False)),
            alarm_armed=bool(data.get("alarmArmed", False)),
        )

    # ------------------------------------------------------------------
    # Aggregated fetch
    # ------------------------------------------------------------------

    async def fetch_bike_data(self, bike_id: str) -> BikeData:
        """Fetch all data for a single bike and assemble a ``BikeData`` instance.

        Optional endpoints (Flow+ and ConnectModule) are fetched with 404
        treated as "feature not present" rather than an error.
        """
        # Mandatory endpoints — let errors propagate.
        info_list = await self.fetch_bikes()
        info = next((b for b in info_list if b.bike_id == bike_id), None)
        if info is None:
            # Fallback: construct a minimal BikeInfo from the bike_id alone.
            info = BikeInfo(
                bike_id=bike_id, name=bike_id, model="", serial_number=""
            )

        telemetry = await self.fetch_bike_telemetry(bike_id)
        last_ride = await self.fetch_ride_history(bike_id)
        aggregate = await self.fetch_aggregate_stats(bike_id)

        # Optional: Flow+ ride data
        flow_plus_ride: RideData | None = await _fetch_optional(
            self.fetch_flow_plus_ride, bike_id
        )

        # Optional: Battery SoC (Flow+)
        battery: BatteryStatus | None = await _fetch_optional(
            self.fetch_battery_soc, bike_id
        )

        # Optional: Location (ConnectModule)
        location: LocationData | None = await _fetch_optional(
            self.fetch_location, bike_id
        )

        # Optional: Alarm (ConnectModule)
        alarm: AlarmStatus | None = await _fetch_optional(
            self.fetch_alarm_status, bike_id
        )

        # Merge Flow+ ride fields into last_ride when available.
        if flow_plus_ride is not None and last_ride is not None:
            last_ride = _merge_flow_plus(last_ride, flow_plus_ride)

        # Feature detection
        has_flow_plus = _has_flow_plus_data(flow_plus_ride)
        has_connect_module = location is not None or alarm is not None

        return BikeData(
            info=info,
            telemetry=telemetry,
            last_ride=last_ride,
            aggregate=aggregate,
            battery=battery,
            location=location,
            alarm=alarm,
            has_flow_plus=has_flow_plus,
            has_connect_module=has_connect_module,
            last_updated=datetime.now(timezone.utc),
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_ride(data: dict[str, Any]) -> RideData:
    """Parse a raw ride JSON dict into a ``RideData`` dataclass."""
    raw_ts = data.get("completedAt")
    completed_at: datetime | None = None
    if raw_ts:
        try:
            completed_at = datetime.fromisoformat(raw_ts)
        except ValueError:
            _LOGGER.warning("Could not parse ride completedAt timestamp: %s", raw_ts)

    return RideData(
        ride_id=data.get("id", ""),
        completed_at=completed_at,
        distance_km=data.get("distanceKm"),
        duration_minutes=data.get("durationMinutes"),
        average_speed_kmh=data.get("averageSpeedKmh"),
        max_speed_kmh=data.get("maxSpeedKmh"),
        elevation_gain_m=data.get("elevationGainM"),
        elevation_loss_m=data.get("elevationLossM"),
        calories_kcal=data.get("caloriesKcal"),
        avg_rider_power_w=data.get("avgRiderPowerW"),
        max_rider_power_w=data.get("maxRiderPowerW"),
        avg_cadence_rpm=data.get("avgCadenceRpm"),
        max_cadence_rpm=data.get("maxCadenceRpm"),
        motor_power_ratio_pct=data.get("motorPowerRatioPct"),
    )


def _merge_flow_plus(base: RideData, flow: RideData) -> RideData:
    """Return a new ``RideData`` with Flow+ fields copied from *flow* into *base*."""
    return RideData(
        ride_id=base.ride_id,
        completed_at=base.completed_at,
        distance_km=base.distance_km,
        duration_minutes=base.duration_minutes,
        average_speed_kmh=base.average_speed_kmh,
        max_speed_kmh=base.max_speed_kmh,
        elevation_gain_m=base.elevation_gain_m,
        elevation_loss_m=base.elevation_loss_m,
        calories_kcal=base.calories_kcal,
        avg_rider_power_w=flow.avg_rider_power_w,
        max_rider_power_w=flow.max_rider_power_w,
        avg_cadence_rpm=flow.avg_cadence_rpm,
        max_cadence_rpm=flow.max_cadence_rpm,
        motor_power_ratio_pct=flow.motor_power_ratio_pct,
    )


def _has_flow_plus_data(ride: RideData | None) -> bool:
    """Return True if the Flow+ ride contains at least one non-None Flow+ field."""
    if ride is None:
        return False
    return any(
        v is not None
        for v in (
            ride.avg_rider_power_w,
            ride.max_rider_power_w,
            ride.avg_cadence_rpm,
            ride.max_cadence_rpm,
            ride.motor_power_ratio_pct,
        )
    )


async def _fetch_optional(coro_fn: Any, bike_id: str) -> Any:
    """Call *coro_fn(bike_id)* and return ``None`` on 404 (feature absent)."""
    try:
        return await coro_fn(bike_id)
    except ApiClientError as exc:
        if exc.status == 404:
            return None
        raise
