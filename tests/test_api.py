"""Unit tests for BoschEBikeApiClient.

Covers:
- Correct endpoint construction for each public method
- HTTP 401 → force refresh → retry → ApiAuthError path
- HTTP 4xx/5xx → correct exception types and log levels
- Timeout → ApiTimeoutError
- Token never appears in log output (log capture assertion)

Requirements: 12.1–12.5
"""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.bosch_ebike_ha.api import (
    ApiAuthError,
    ApiClientError,
    ApiServerError,
    ApiTimeoutError,
    BoschEBikeApiClient,
)
from custom_components.bosch_ebike_ha.models import (
    AggregateStats,
    AlarmStatus,
    BatteryStatus,
    BikeInfo,
    BikeTelemetry,
    LocationData,
    RideData,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_TOKEN = "super-secret-access-token-abc123"
BIKE_ID = "bike-001"


def make_oauth_session(token: str = FAKE_TOKEN) -> MagicMock:
    """Return a mock OAuth2Session with a known access token."""
    session = MagicMock()
    session.async_ensure_token_valid = AsyncMock()
    session.token = {"access_token": token}
    return session


def make_response(status: int, json_data: object = None) -> AsyncMock:
    """Return a mock aiohttp response."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {})
    return resp


def make_client_session(response: AsyncMock) -> MagicMock:
    """Return a mock aiohttp.ClientSession whose request() returns *response*."""
    session = MagicMock()
    session.request = AsyncMock(return_value=response)
    return session


# ---------------------------------------------------------------------------
# Endpoint construction
# ---------------------------------------------------------------------------


class TestEndpointConstruction:
    """Each public method must call the correct URL."""

    async def test_fetch_bikes_url(self):
        resp = make_response(200, [])
        http = make_client_session(resp)
        client = BoschEBikeApiClient(http, make_oauth_session())

        await client.fetch_bikes()

        http.request.assert_called_once()
        _, kwargs = http.request.call_args
        args = http.request.call_args.args
        assert args[1].endswith("/v1/bikes")

    async def test_fetch_bike_telemetry_url(self):
        resp = make_response(200, {})
        http = make_client_session(resp)
        client = BoschEBikeApiClient(http, make_oauth_session())

        await client.fetch_bike_telemetry(BIKE_ID)

        args = http.request.call_args.args
        assert args[1].endswith(f"/v1/bikes/{BIKE_ID}/telemetry")

    async def test_fetch_ride_history_url(self):
        resp = make_response(200, [])
        http = make_client_session(resp)
        client = BoschEBikeApiClient(http, make_oauth_session())

        await client.fetch_ride_history(BIKE_ID)

        args = http.request.call_args.args
        assert args[1].endswith(f"/v1/bikes/{BIKE_ID}/rides")
        # Params should include limit=1 and sort=desc
        kwargs = http.request.call_args.kwargs
        assert kwargs.get("params") == {"limit": "1", "sort": "desc"}

    async def test_fetch_aggregate_stats_url(self):
        resp = make_response(200, {})
        http = make_client_session(resp)
        client = BoschEBikeApiClient(http, make_oauth_session())

        await client.fetch_aggregate_stats(BIKE_ID)

        args = http.request.call_args.args
        assert args[1].endswith(f"/v1/bikes/{BIKE_ID}/stats")

    async def test_fetch_flow_plus_ride_url(self):
        resp = make_response(200, {"id": "r1"})
        http = make_client_session(resp)
        client = BoschEBikeApiClient(http, make_oauth_session())

        await client.fetch_flow_plus_ride(BIKE_ID)

        args = http.request.call_args.args
        assert args[1].endswith(f"/v1/bikes/{BIKE_ID}/rides/latest/flow-plus")

    async def test_fetch_battery_soc_url(self):
        resp = make_response(200, {})
        http = make_client_session(resp)
        client = BoschEBikeApiClient(http, make_oauth_session())

        await client.fetch_battery_soc(BIKE_ID)

        args = http.request.call_args.args
        assert args[1].endswith(f"/v1/bikes/{BIKE_ID}/battery")

    async def test_fetch_location_url(self):
        resp = make_response(200, {})
        http = make_client_session(resp)
        client = BoschEBikeApiClient(http, make_oauth_session())

        await client.fetch_location(BIKE_ID)

        args = http.request.call_args.args
        assert args[1].endswith(f"/v1/bikes/{BIKE_ID}/location")

    async def test_fetch_alarm_status_url(self):
        resp = make_response(200, {})
        http = make_client_session(resp)
        client = BoschEBikeApiClient(http, make_oauth_session())

        await client.fetch_alarm_status(BIKE_ID)

        args = http.request.call_args.args
        assert args[1].endswith(f"/v1/bikes/{BIKE_ID}/alarm")


# ---------------------------------------------------------------------------
# 401 retry logic
# ---------------------------------------------------------------------------


class TestAuthRetry:
    """HTTP 401 → force refresh → retry → ApiAuthError on second 401."""

    async def test_401_triggers_force_refresh_and_retry(self):
        """First 401 should force-refresh the token and retry the request."""
        first_resp = make_response(401)
        second_resp = make_response(200, [])
        http = MagicMock()
        http.request = AsyncMock(side_effect=[first_resp, second_resp])
        oauth = make_oauth_session()

        client = BoschEBikeApiClient(http, oauth)
        await client.fetch_bikes()

        # async_ensure_token_valid called twice: once normally, once with force_refresh
        assert oauth.async_ensure_token_valid.call_count == 2
        calls = oauth.async_ensure_token_valid.call_args_list
        # Second call must have force_refresh=True
        assert calls[1].kwargs.get("force_refresh") is True

    async def test_401_twice_raises_api_auth_error(self):
        """Two consecutive 401s should raise ApiAuthError."""
        resp_401 = make_response(401)
        http = MagicMock()
        http.request = AsyncMock(return_value=resp_401)
        oauth = make_oauth_session()

        client = BoschEBikeApiClient(http, oauth)
        with pytest.raises(ApiAuthError):
            await client.fetch_bikes()

    async def test_401_once_then_success_returns_data(self):
        """After a 401 + force-refresh, a successful retry should return data."""
        bikes_payload = [{"id": "b1", "name": "My Bike", "model": "X", "serialNumber": "SN1"}]
        first_resp = make_response(401)
        second_resp = make_response(200, bikes_payload)
        http = MagicMock()
        http.request = AsyncMock(side_effect=[first_resp, second_resp])
        oauth = make_oauth_session()

        client = BoschEBikeApiClient(http, oauth)
        result = await client.fetch_bikes()

        assert len(result) == 1
        assert result[0].bike_id == "b1"


# ---------------------------------------------------------------------------
# 4xx / 5xx error handling
# ---------------------------------------------------------------------------


class TestHttpErrors:
    """4xx and 5xx responses raise the correct exceptions with correct log levels."""

    @pytest.mark.parametrize("status", [400, 403, 404, 422, 429])
    async def test_4xx_raises_api_client_error(self, status, caplog):
        resp = make_response(status)
        http = make_client_session(resp)
        client = BoschEBikeApiClient(http, make_oauth_session())

        with caplog.at_level(logging.ERROR):
            with pytest.raises(ApiClientError) as exc_info:
                await client.fetch_bikes()

        assert exc_info.value.status == status
        # Must log at ERROR level with status and endpoint
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) >= 1
        assert str(status) in error_records[0].message
        assert "/v1/bikes" in error_records[0].message

    @pytest.mark.parametrize("status", [500, 502, 503, 504])
    async def test_5xx_raises_api_server_error(self, status, caplog):
        resp = make_response(status)
        http = make_client_session(resp)
        client = BoschEBikeApiClient(http, make_oauth_session())

        with caplog.at_level(logging.WARNING):
            with pytest.raises(ApiServerError) as exc_info:
                await client.fetch_bikes()

        assert exc_info.value.status == status
        # Must log at WARNING level with status and endpoint
        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) >= 1
        assert str(status) in warning_records[0].message
        assert "/v1/bikes" in warning_records[0].message

    async def test_4xx_does_not_log_at_warning(self, caplog):
        """4xx errors must log at ERROR, not WARNING."""
        resp = make_response(422)
        http = make_client_session(resp)
        client = BoschEBikeApiClient(http, make_oauth_session())

        with caplog.at_level(logging.DEBUG):
            with pytest.raises(ApiClientError):
                await client.fetch_bikes()

        # No WARNING record should contain the status code
        warning_records = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and "422" in r.message
        ]
        assert len(warning_records) == 0

    async def test_5xx_does_not_log_at_error(self, caplog):
        """5xx errors must log at WARNING, not ERROR."""
        resp = make_response(503)
        http = make_client_session(resp)
        client = BoschEBikeApiClient(http, make_oauth_session())

        with caplog.at_level(logging.DEBUG):
            with pytest.raises(ApiServerError):
                await client.fetch_bikes()

        error_records = [
            r for r in caplog.records
            if r.levelno == logging.ERROR and "503" in r.message
        ]
        assert len(error_records) == 0


# ---------------------------------------------------------------------------
# Timeout handling
# ---------------------------------------------------------------------------


class TestTimeout:
    """asyncio.TimeoutError should be caught and re-raised as ApiTimeoutError."""

    async def test_timeout_raises_api_timeout_error(self, caplog):
        http = MagicMock()
        http.request = AsyncMock(side_effect=asyncio.TimeoutError())
        client = BoschEBikeApiClient(http, make_oauth_session())

        with caplog.at_level(logging.WARNING):
            with pytest.raises(ApiTimeoutError):
                await client.fetch_bikes()

    async def test_timeout_logs_warning_with_endpoint_and_timeout(self, caplog):
        from custom_components.bosch_ebike_ha.const import REQUEST_TIMEOUT_SECONDS

        http = MagicMock()
        http.request = AsyncMock(side_effect=asyncio.TimeoutError())
        client = BoschEBikeApiClient(http, make_oauth_session())

        with caplog.at_level(logging.WARNING):
            with pytest.raises(ApiTimeoutError):
                await client.fetch_bikes()

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) >= 1
        msg = warning_records[0].message
        assert "/v1/bikes" in msg
        assert str(REQUEST_TIMEOUT_SECONDS) in msg


# ---------------------------------------------------------------------------
# Credential safety
# ---------------------------------------------------------------------------


class TestCredentialSafety:
    """Access tokens must never appear in any log record."""

    async def test_token_not_in_logs_on_success(self, caplog):
        resp = make_response(200, [])
        http = make_client_session(resp)
        oauth = make_oauth_session(token=FAKE_TOKEN)
        client = BoschEBikeApiClient(http, oauth)

        with caplog.at_level(logging.DEBUG):
            await client.fetch_bikes()

        for record in caplog.records:
            assert FAKE_TOKEN not in record.getMessage()

    async def test_token_not_in_logs_on_401_retry(self, caplog):
        first_resp = make_response(401)
        second_resp = make_response(401)
        http = MagicMock()
        http.request = AsyncMock(side_effect=[first_resp, second_resp])
        oauth = make_oauth_session(token=FAKE_TOKEN)
        client = BoschEBikeApiClient(http, oauth)

        with caplog.at_level(logging.DEBUG):
            with pytest.raises(ApiAuthError):
                await client.fetch_bikes()

        for record in caplog.records:
            assert FAKE_TOKEN not in record.getMessage()

    async def test_token_not_in_logs_on_4xx_error(self, caplog):
        resp = make_response(403)
        http = make_client_session(resp)
        oauth = make_oauth_session(token=FAKE_TOKEN)
        client = BoschEBikeApiClient(http, oauth)

        with caplog.at_level(logging.DEBUG):
            with pytest.raises(ApiClientError):
                await client.fetch_bikes()

        for record in caplog.records:
            assert FAKE_TOKEN not in record.getMessage()

    async def test_token_not_in_logs_on_5xx_error(self, caplog):
        resp = make_response(500)
        http = make_client_session(resp)
        oauth = make_oauth_session(token=FAKE_TOKEN)
        client = BoschEBikeApiClient(http, oauth)

        with caplog.at_level(logging.DEBUG):
            with pytest.raises(ApiServerError):
                await client.fetch_bikes()

        for record in caplog.records:
            assert FAKE_TOKEN not in record.getMessage()

    async def test_token_not_in_logs_on_timeout(self, caplog):
        http = MagicMock()
        http.request = AsyncMock(side_effect=asyncio.TimeoutError())
        oauth = make_oauth_session(token=FAKE_TOKEN)
        client = BoschEBikeApiClient(http, oauth)

        with caplog.at_level(logging.DEBUG):
            with pytest.raises(ApiTimeoutError):
                await client.fetch_bikes()

        for record in caplog.records:
            assert FAKE_TOKEN not in record.getMessage()


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


class TestResponseParsing:
    """Public methods should correctly parse API JSON into dataclass instances."""

    async def test_fetch_bikes_parses_list(self):
        payload = [
            {"id": "b1", "name": "Cube Stereo", "model": "Stereo 140", "serialNumber": "SN001"},
            {"id": "b2", "name": "Cube Reaction", "model": "Reaction 625", "serialNumber": "SN002"},
        ]
        resp = make_response(200, payload)
        http = make_client_session(resp)
        client = BoschEBikeApiClient(http, make_oauth_session())

        result = await client.fetch_bikes()

        assert len(result) == 2
        assert isinstance(result[0], BikeInfo)
        assert result[0].bike_id == "b1"
        assert result[0].name == "Cube Stereo"
        assert result[1].bike_id == "b2"

    async def test_fetch_bikes_parses_wrapped_list(self):
        """API may return {"bikes": [...]} instead of a bare list."""
        payload = {"bikes": [{"id": "b1", "name": "Bike", "model": "M", "serialNumber": "S"}]}
        resp = make_response(200, payload)
        http = make_client_session(resp)
        client = BoschEBikeApiClient(http, make_oauth_session())

        result = await client.fetch_bikes()
        assert len(result) == 1
        assert result[0].bike_id == "b1"

    async def test_fetch_bike_telemetry_parses_fields(self):
        payload = {
            "odometerKm": 1234.5,
            "motorHoursTotal": 56.7,
            "motorHoursWithAssist": 40.0,
            "batteryChargeCycles": 120,
            "batteryLifetimeEnergyWh": 9876.0,
            "nextServiceOdometerKm": 2000.0,
            "maxAssistSpeedKmh": 25.0,
        }
        resp = make_response(200, payload)
        http = make_client_session(resp)
        client = BoschEBikeApiClient(http, make_oauth_session())

        result = await client.fetch_bike_telemetry(BIKE_ID)

        assert isinstance(result, BikeTelemetry)
        assert result.odometer_km == 1234.5
        assert result.motor_hours_total == 56.7
        assert result.battery_charge_cycles == 120
        assert result.max_assist_speed_kmh == 25.0

    async def test_fetch_ride_history_returns_none_for_empty(self):
        resp = make_response(200, [])
        http = make_client_session(resp)
        client = BoschEBikeApiClient(http, make_oauth_session())

        result = await client.fetch_ride_history(BIKE_ID)
        assert result is None

    async def test_fetch_ride_history_parses_first_ride(self):
        payload = [
            {
                "id": "ride-1",
                "completedAt": "2024-06-01T10:00:00+00:00",
                "distanceKm": 42.0,
                "durationMinutes": 120.0,
                "averageSpeedKmh": 21.0,
                "maxSpeedKmh": 35.0,
                "elevationGainM": 500.0,
                "elevationLossM": 490.0,
                "caloriesKcal": 800.0,
            }
        ]
        resp = make_response(200, payload)
        http = make_client_session(resp)
        client = BoschEBikeApiClient(http, make_oauth_session())

        result = await client.fetch_ride_history(BIKE_ID)

        assert isinstance(result, RideData)
        assert result.ride_id == "ride-1"
        assert result.distance_km == 42.0
        assert result.duration_minutes == 120.0

    async def test_fetch_aggregate_stats_parses_fields(self):
        payload = {
            "totalRides": 50,
            "totalDistanceKm": 2000.0,
            "totalRideTimeHours": 100.0,
            "totalCaloriesKcal": 40000.0,
            "totalElevationGainM": 25000.0,
            "averageSpeedKmh": 20.0,
        }
        resp = make_response(200, payload)
        http = make_client_session(resp)
        client = BoschEBikeApiClient(http, make_oauth_session())

        result = await client.fetch_aggregate_stats(BIKE_ID)

        assert isinstance(result, AggregateStats)
        assert result.total_rides == 50
        assert result.total_distance_km == 2000.0

    async def test_fetch_battery_soc_parses_fields(self):
        payload = {"stateOfChargePct": 85, "chargingStatus": "discharging"}
        resp = make_response(200, payload)
        http = make_client_session(resp)
        client = BoschEBikeApiClient(http, make_oauth_session())

        result = await client.fetch_battery_soc(BIKE_ID)

        assert isinstance(result, BatteryStatus)
        assert result.state_of_charge_pct == 85
        assert result.charging_status == "discharging"

    async def test_fetch_location_parses_fields(self):
        payload = {
            "latitude": 51.5074,
            "longitude": -0.1278,
            "accuracyM": 10.0,
            "timestamp": "2024-06-01T12:00:00+00:00",
        }
        resp = make_response(200, payload)
        http = make_client_session(resp)
        client = BoschEBikeApiClient(http, make_oauth_session())

        result = await client.fetch_location(BIKE_ID)

        assert isinstance(result, LocationData)
        assert result.latitude == 51.5074
        assert result.longitude == -0.1278
        assert result.accuracy_m == 10.0
        assert result.timestamp is not None

    async def test_fetch_alarm_status_parses_fields(self):
        payload = {"alarmTriggered": True, "alarmArmed": False}
        resp = make_response(200, payload)
        http = make_client_session(resp)
        client = BoschEBikeApiClient(http, make_oauth_session())

        result = await client.fetch_alarm_status(BIKE_ID)

        assert isinstance(result, AlarmStatus)
        assert result.alarm_triggered is True
        assert result.alarm_armed is False


# ---------------------------------------------------------------------------
# fetch_bike_data assembly
# ---------------------------------------------------------------------------


class TestFetchBikeData:
    """fetch_bike_data should assemble BikeData correctly."""

    def _make_responses(
        self,
        *,
        flow_plus_status: int = 200,
        battery_status: int = 200,
        location_status: int = 200,
        alarm_status: int = 200,
    ):
        """Build a sequence of mock responses for all endpoints."""
        bikes_resp = make_response(200, [
            {"id": BIKE_ID, "name": "My Bike", "model": "X", "serialNumber": "SN1"}
        ])
        telemetry_resp = make_response(200, {"odometerKm": 100.0})
        rides_resp = make_response(200, [{"id": "r1", "distanceKm": 10.0}])
        stats_resp = make_response(200, {"totalRides": 5})
        flow_plus_resp = make_response(
            flow_plus_status,
            {"id": "r1", "avgRiderPowerW": 150.0} if flow_plus_status == 200 else {},
        )
        battery_resp = make_response(
            battery_status,
            {"stateOfChargePct": 80} if battery_status == 200 else {},
        )
        location_resp = make_response(
            location_status,
            {"latitude": 51.0, "longitude": 0.0} if location_status == 200 else {},
        )
        alarm_resp = make_response(
            alarm_status,
            {"alarmTriggered": False, "alarmArmed": True} if alarm_status == 200 else {},
        )
        return [
            bikes_resp, telemetry_resp, rides_resp, stats_resp,
            flow_plus_resp, battery_resp, location_resp, alarm_resp,
        ]

    async def test_fetch_bike_data_returns_bike_data(self):
        responses = self._make_responses()
        http = MagicMock()
        http.request = AsyncMock(side_effect=responses)
        client = BoschEBikeApiClient(http, make_oauth_session())

        from custom_components.bosch_ebike_ha.models import BikeData
        result = await client.fetch_bike_data(BIKE_ID)

        assert isinstance(result, BikeData)
        assert result.info.bike_id == BIKE_ID
        assert result.last_updated is not None

    async def test_fetch_bike_data_has_flow_plus_true_when_flow_plus_fields_present(self):
        responses = self._make_responses(flow_plus_status=200)
        http = MagicMock()
        http.request = AsyncMock(side_effect=responses)
        client = BoschEBikeApiClient(http, make_oauth_session())

        result = await client.fetch_bike_data(BIKE_ID)
        assert result.has_flow_plus is True

    async def test_fetch_bike_data_has_flow_plus_false_when_404(self):
        """When the Flow+ ride endpoint returns 404, has_flow_plus is False.

        Battery SoC is a separate endpoint and may still return data independently.
        """
        responses = self._make_responses(flow_plus_status=404)
        http = MagicMock()
        http.request = AsyncMock(side_effect=responses)
        client = BoschEBikeApiClient(http, make_oauth_session())

        result = await client.fetch_bike_data(BIKE_ID)
        assert result.has_flow_plus is False
        # Flow+ ride fields on last_ride should all be None (no flow-plus data merged)
        if result.last_ride is not None:
            assert result.last_ride.avg_rider_power_w is None

    async def test_fetch_bike_data_has_connect_module_true_when_location_present(self):
        responses = self._make_responses(location_status=200, alarm_status=200)
        http = MagicMock()
        http.request = AsyncMock(side_effect=responses)
        client = BoschEBikeApiClient(http, make_oauth_session())

        result = await client.fetch_bike_data(BIKE_ID)
        assert result.has_connect_module is True

    async def test_fetch_bike_data_has_connect_module_false_when_both_404(self):
        responses = self._make_responses(location_status=404, alarm_status=404)
        http = MagicMock()
        http.request = AsyncMock(side_effect=responses)
        client = BoschEBikeApiClient(http, make_oauth_session())

        result = await client.fetch_bike_data(BIKE_ID)
        assert result.has_connect_module is False
        assert result.location is None
        assert result.alarm is None

    async def test_fetch_bike_data_last_updated_is_utc(self):
        from datetime import timezone

        responses = self._make_responses()
        http = MagicMock()
        http.request = AsyncMock(side_effect=responses)
        client = BoschEBikeApiClient(http, make_oauth_session())

        result = await client.fetch_bike_data(BIKE_ID)
        assert result.last_updated.tzinfo == timezone.utc
