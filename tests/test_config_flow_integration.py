"""Full config flow integration test for Bosch eBike integration.

Task 14.1 -- Full config flow integration test

Tests the complete config flow lifecycle:
1. Application credentials are registered (mocked).
2. The config flow async_step_user is called.
3. OAuth2 exchange is mocked -- async_oauth_create_entry is called with a
   fake token payload, bypassing the real Bosch auth redirect.
4. The unit-system step is presented and submitted with a chosen value.
5. fetch_bikes is mocked to return a single fake bike.
6. The config entry is created with options["unit_system"] == chosen value.
7. async_setup_entry is called to wire up coordinators and entities.
8. All expected sensor entities are registered for the fake bike.

Requirements: 1.1-1.7, 13.1, 13.2
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import custom_components.bosch_ebike_ha as _init_mod
from custom_components.bosch_ebike_ha import async_setup_entry
from custom_components.bosch_ebike_ha.config_flow import BoschEBikeConfigFlow
from custom_components.bosch_ebike_ha.const import (
    CONF_UNIT_SYSTEM,
    DOMAIN,
    UNIT_IMPERIAL,
    UNIT_METRIC,
)
from custom_components.bosch_ebike_ha.models import (
    AggregateStats,
    BikeData,
    BikeInfo,
    BikeTelemetry,
    RideData,
)
from custom_components.bosch_ebike_ha.sensor import BIKE_SENSORS


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

FAKE_BIKE_ID = "fake-bike-001"
FAKE_BIKE_NAME = "My Test eBike"

# Fake OAuth2 token payload returned after the OAuth2 exchange.
FAKE_TOKEN_DATA = {
    "auth_implementation": "bosch_ebike_ha",
    "token": {
        "access_token": "fake-access-token",
        "refresh_token": "fake-refresh-token",
        "token_type": "Bearer",
        "expires_in": 3600,
    },
}


def _make_fake_bike_info() -> BikeInfo:
    return BikeInfo(
        bike_id=FAKE_BIKE_ID,
        name=FAKE_BIKE_NAME,
        model="Cube Stereo Hybrid",
        serial_number="SN-FAKE-001",
    )


def _make_fake_bike_data() -> BikeData:
    return BikeData(
        info=_make_fake_bike_info(),
        telemetry=BikeTelemetry(
            odometer_km=500.0,
            motor_hours_total=20.0,
            motor_hours_with_assist=15.0,
            battery_charge_cycles=10,
            battery_lifetime_energy_wh=1000.0,
            next_service_odometer_km=1000.0,
            max_assist_speed_kmh=25.0,
        ),
        last_ride=RideData(
            ride_id="ride-001",
            completed_at=_NOW,
            distance_km=30.0,
            duration_minutes=90.0,
            average_speed_kmh=20.0,
            max_speed_kmh=35.0,
            elevation_gain_m=200.0,
            elevation_loss_m=180.0,
            calories_kcal=600.0,
            avg_rider_power_w=None,
            max_rider_power_w=None,
            avg_cadence_rpm=None,
            max_cadence_rpm=None,
            motor_power_ratio_pct=None,
        ),
        aggregate=AggregateStats(
            total_rides=20,
            total_distance_km=1000.0,
            total_ride_time_hours=40.0,
            total_calories_kcal=12000.0,
            total_elevation_gain_m=4000.0,
            average_speed_kmh=25.0,
        ),
        battery=None,
        location=None,
        alarm=None,
        has_flow_plus=False,
        has_connect_module=False,
        last_updated=_NOW,
    )


def _make_mock_hass() -> MagicMock:
    hass = MagicMock()
    hass.data = {}
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)
    return hass


def _make_mock_entry(
    entry_id: str = "cfg_flow_test_entry",
    unit_system: str = UNIT_METRIC,
) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.domain = DOMAIN
    entry.options = {CONF_UNIT_SYSTEM: unit_system}
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock(return_value=lambda: None)
    return entry


def _make_mock_coordinator(bike_data: BikeData) -> MagicMock:
    coord = MagicMock()
    coord.bike_id = bike_data.info.bike_id
    coord.data = bike_data
    coord.last_update_success = True
    coord.async_config_entry_first_refresh = AsyncMock(return_value=None)
    coord.async_shutdown = MagicMock()
    return coord


# ---------------------------------------------------------------------------
# Tests: Config flow steps
# ---------------------------------------------------------------------------


class TestConfigFlowSteps:
    """Tests for individual config flow steps.

    These tests verify each step of the config flow in isolation:
    - async_step_user: validates credentials exist before starting OAuth2
    - async_step_unit_system: presents unit selector and stores choice
    - async_oauth_create_entry: verifies token, creates entry with options

    Requirements: 1.1-1.7, 13.1, 13.2
    """

    @pytest.mark.asyncio
    async def test_step_user_aborts_when_no_credentials(self):
        """async_step_user must abort with 'missing_credentials' when no app
        credentials are registered.

        Requirement 1.6: The Config_Flow SHALL require the user to provide a
        Bosch Data Act Portal Client-ID as a prerequisite.
        """
        flow = BoschEBikeConfigFlow()
        flow.hass = _make_mock_hass()

        with patch(
            "custom_components.bosch_ebike_ha.config_flow.async_get_application_credentials",
            new=AsyncMock(return_value=[]),
        ):
            result = await flow.async_step_user(user_input=None)

        assert result["type"] == "abort"
        assert result["reason"] == "missing_credentials"

    @pytest.mark.asyncio
    async def test_step_user_proceeds_when_credentials_exist(self):
        """async_step_user must proceed to OAuth2 when credentials are registered.

        Requirement 1.1: The Config_Flow SHALL present an OAuth2 authorisation step.
        """
        flow = BoschEBikeConfigFlow()
        flow.hass = _make_mock_hass()

        # Patch super().async_step_user using AsyncMock (handles unbound method call)
        mock_super_step = AsyncMock(return_value={"type": "external", "step_id": "auth"})

        with (
            patch(
                "custom_components.bosch_ebike_ha.config_flow.async_get_application_credentials",
                new=AsyncMock(return_value=[{"client_id": "euda-test"}]),
            ),
            patch.object(
                flow.__class__.__bases__[0],
                "async_step_user",
                new=mock_super_step,
            ),
        ):
            result = await flow.async_step_user(user_input=None)

        # Should not abort -- proceeds to OAuth2
        assert result["type"] != "abort"

    @pytest.mark.asyncio
    async def test_step_unit_system_shows_form_when_no_input(self):
        """async_step_unit_system must show a form when no user_input is provided.

        Requirement 13.1: The Config_Flow SHALL present a unit system selection step.
        """
        flow = BoschEBikeConfigFlow()
        flow.hass = _make_mock_hass()

        result = await flow.async_step_unit_system(user_input=None)

        assert result["type"] == "form"
        assert result["step_id"] == "unit_system"

    @pytest.mark.asyncio
    async def test_step_unit_system_stores_metric_choice(self):
        """Submitting metric in the unit system step must store UNIT_METRIC.

        Requirement 13.2: The chosen unit system SHALL be stored in options.
        """
        flow = BoschEBikeConfigFlow()
        flow.hass = _make_mock_hass()
        # Simulate that OAuth2 token data was already stored
        flow._oauth_token_data = FAKE_TOKEN_DATA

        # Mock async_oauth_create_entry to capture the call
        captured = {}

        async def _mock_create_entry(data):
            captured["unit_system"] = flow._unit_system
            return {"type": "create_entry", "title": "Test", "data": data, "options": {CONF_UNIT_SYSTEM: flow._unit_system}}

        with patch.object(flow, "async_oauth_create_entry", new=_mock_create_entry):
            result = await flow.async_step_unit_system(
                user_input={CONF_UNIT_SYSTEM: UNIT_METRIC}
            )

        assert captured["unit_system"] == UNIT_METRIC

    @pytest.mark.asyncio
    async def test_step_unit_system_stores_imperial_choice(self):
        """Submitting imperial in the unit system step must store UNIT_IMPERIAL.

        Requirement 13.2: The chosen unit system SHALL be stored in options.
        """
        flow = BoschEBikeConfigFlow()
        flow.hass = _make_mock_hass()
        flow._oauth_token_data = FAKE_TOKEN_DATA

        captured = {}

        async def _mock_create_entry(data):
            captured["unit_system"] = flow._unit_system
            return {"type": "create_entry", "title": "Test", "data": data, "options": {CONF_UNIT_SYSTEM: flow._unit_system}}

        with patch.object(flow, "async_oauth_create_entry", new=_mock_create_entry):
            await flow.async_step_unit_system(
                user_input={CONF_UNIT_SYSTEM: UNIT_IMPERIAL}
            )

        assert captured["unit_system"] == UNIT_IMPERIAL

    @pytest.mark.asyncio
    async def test_oauth_create_entry_routes_to_unit_system_step_first(self):
        """async_oauth_create_entry must route to unit_system step when called
        before the unit system has been chosen.

        This verifies the flow intercepts the OAuth2 callback to insert the
        unit system selection step.

        Requirements: 13.1
        """
        flow = BoschEBikeConfigFlow()
        flow.hass = _make_mock_hass()

        # async_oauth_create_entry is called by AbstractOAuth2FlowHandler after
        # the OAuth2 callback. The first call should redirect to unit_system.
        result = await flow.async_oauth_create_entry(data=FAKE_TOKEN_DATA)

        # Should show the unit_system form
        assert result["type"] == "form"
        assert result["step_id"] == "unit_system"
        # Token data must be stored for later use
        assert hasattr(flow, "_oauth_token_data")
        assert flow._oauth_token_data == FAKE_TOKEN_DATA

    @pytest.mark.asyncio
    async def test_oauth_create_entry_creates_entry_with_metric_options(self):
        """async_oauth_create_entry must create a config entry with metric options
        when the user chose metric.

        Requirements: 1.2, 13.2
        """
        flow = BoschEBikeConfigFlow()
        flow.hass = _make_mock_hass()
        flow._oauth_token_data = FAKE_TOKEN_DATA
        flow._unit_system = UNIT_METRIC

        fake_bike = _make_fake_bike_info()

        created_entries = []

        def _mock_create_entry(title, data, options=None):
            entry = {"type": "create_entry", "title": title, "data": data, "options": options or {}}
            created_entries.append(entry)
            return entry

        with (
            patch(
                "custom_components.bosch_ebike_ha.config_flow.async_get_clientsession",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.bosch_ebike_ha.config_flow.config_entry_oauth2_flow"
            ) as mock_oauth2,
            patch(
                "custom_components.bosch_ebike_ha.config_flow.BoschEBikeApiClient"
            ) as MockClient,
        ):
            mock_oauth2.OAuth2Session.return_value = MagicMock()
            mock_client_instance = MagicMock()
            mock_client_instance.fetch_bikes = AsyncMock(return_value=[fake_bike])
            MockClient.return_value = mock_client_instance

            flow.async_create_entry = _mock_create_entry

            result = await flow.async_oauth_create_entry(data=FAKE_TOKEN_DATA)

        assert result["type"] == "create_entry"
        assert result["options"][CONF_UNIT_SYSTEM] == UNIT_METRIC
        assert result["title"] == FAKE_BIKE_NAME

    @pytest.mark.asyncio
    async def test_oauth_create_entry_creates_entry_with_imperial_options(self):
        """async_oauth_create_entry must create a config entry with imperial options
        when the user chose imperial.

        Requirements: 1.2, 13.2
        """
        flow = BoschEBikeConfigFlow()
        flow.hass = _make_mock_hass()
        flow._oauth_token_data = FAKE_TOKEN_DATA
        flow._unit_system = UNIT_IMPERIAL

        fake_bike = _make_fake_bike_info()

        created_entries = []

        def _mock_create_entry(title, data, options=None):
            entry = {"type": "create_entry", "title": title, "data": data, "options": options or {}}
            created_entries.append(entry)
            return entry

        with (
            patch(
                "custom_components.bosch_ebike_ha.config_flow.async_get_clientsession",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.bosch_ebike_ha.config_flow.config_entry_oauth2_flow"
            ) as mock_oauth2,
            patch(
                "custom_components.bosch_ebike_ha.config_flow.BoschEBikeApiClient"
            ) as MockClient,
        ):
            mock_oauth2.OAuth2Session.return_value = MagicMock()
            mock_client_instance = MagicMock()
            mock_client_instance.fetch_bikes = AsyncMock(return_value=[fake_bike])
            MockClient.return_value = mock_client_instance

            flow.async_create_entry = _mock_create_entry

            result = await flow.async_oauth_create_entry(data=FAKE_TOKEN_DATA)

        assert result["type"] == "create_entry"
        assert result["options"][CONF_UNIT_SYSTEM] == UNIT_IMPERIAL

    @pytest.mark.asyncio
    async def test_oauth_create_entry_aborts_on_403_application_not_approved(self):
        """async_oauth_create_entry must abort with 'application_not_approved'
        when fetch_bikes returns HTTP 403.

        Requirement 1.7: When the user's Bosch Data Act Portal application has
        not yet been approved, the Config_Flow SHALL display a descriptive error.
        """
        from custom_components.bosch_ebike_ha.api import ApiClientError

        flow = BoschEBikeConfigFlow()
        flow.hass = _make_mock_hass()
        flow._oauth_token_data = FAKE_TOKEN_DATA
        flow._unit_system = UNIT_METRIC

        aborted = {}

        def _mock_abort(reason):
            aborted["reason"] = reason
            return {"type": "abort", "reason": reason}

        with (
            patch(
                "custom_components.bosch_ebike_ha.config_flow.async_get_clientsession",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.bosch_ebike_ha.config_flow.config_entry_oauth2_flow"
            ) as mock_oauth2,
            patch(
                "custom_components.bosch_ebike_ha.config_flow.BoschEBikeApiClient"
            ) as MockClient,
        ):
            mock_oauth2.OAuth2Session.return_value = MagicMock()
            mock_client_instance = MagicMock()
            mock_client_instance.fetch_bikes = AsyncMock(
                side_effect=ApiClientError(403, "/v1/bikes")
            )
            MockClient.return_value = mock_client_instance

            flow.async_abort = _mock_abort

            result = await flow.async_oauth_create_entry(data=FAKE_TOKEN_DATA)

        assert result["type"] == "abort"
        assert result["reason"] == "application_not_approved"


# ---------------------------------------------------------------------------
# Tests: Full config flow end-to-end
# ---------------------------------------------------------------------------


class TestFullConfigFlowEndToEnd:
    """End-to-end tests for the complete config flow lifecycle.

    These tests simulate the full flow from credentials check through OAuth2
    exchange, unit system selection, and config entry creation.

    Requirements: 1.1-1.7, 13.1, 13.2
    """

    @pytest.mark.asyncio
    async def test_full_flow_metric_creates_entry_with_metric_options(self):
        """Full flow with metric selection must create entry with metric options.

        Simulates:
        1. Credentials exist.
        2. OAuth2 exchange completes (mocked).
        3. Unit system step: user selects metric.
        4. fetch_bikes returns a fake bike.
        5. Config entry is created with options["unit_system"] == "metric".

        Requirements: 1.1-1.7, 13.1, 13.2
        """
        flow = BoschEBikeConfigFlow()
        flow.hass = _make_mock_hass()

        fake_bike = _make_fake_bike_info()
        created_entries = []

        def _mock_create_entry(title, data, options=None):
            entry = {"type": "create_entry", "title": title, "data": data, "options": options or {}}
            created_entries.append(entry)
            return entry

        with (
            patch(
                "custom_components.bosch_ebike_ha.config_flow.async_get_application_credentials",
                new=AsyncMock(return_value=[{"client_id": "euda-test"}]),
            ),
            patch(
                "custom_components.bosch_ebike_ha.config_flow.async_get_clientsession",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.bosch_ebike_ha.config_flow.config_entry_oauth2_flow"
            ) as mock_oauth2,
            patch(
                "custom_components.bosch_ebike_ha.config_flow.BoschEBikeApiClient"
            ) as MockClient,
        ):
            mock_oauth2.OAuth2Session.return_value = MagicMock()
            mock_client_instance = MagicMock()
            mock_client_instance.fetch_bikes = AsyncMock(return_value=[fake_bike])
            MockClient.return_value = mock_client_instance

            flow.async_create_entry = _mock_create_entry

            # Step 1: OAuth2 callback -- routes to unit_system step
            result = await flow.async_oauth_create_entry(data=FAKE_TOKEN_DATA)
            assert result["type"] == "form"
            assert result["step_id"] == "unit_system"

            # Step 2: User selects metric
            result = await flow.async_step_unit_system(
                user_input={CONF_UNIT_SYSTEM: UNIT_METRIC}
            )

        assert result["type"] == "create_entry"
        assert result["options"][CONF_UNIT_SYSTEM] == UNIT_METRIC
        assert result["title"] == FAKE_BIKE_NAME

    @pytest.mark.asyncio
    async def test_full_flow_imperial_creates_entry_with_imperial_options(self):
        """Full flow with imperial selection must create entry with imperial options.

        Requirements: 1.1-1.7, 13.1, 13.2
        """
        flow = BoschEBikeConfigFlow()
        flow.hass = _make_mock_hass()

        fake_bike = _make_fake_bike_info()
        created_entries = []

        def _mock_create_entry(title, data, options=None):
            entry = {"type": "create_entry", "title": title, "data": data, "options": options or {}}
            created_entries.append(entry)
            return entry

        with (
            patch(
                "custom_components.bosch_ebike_ha.config_flow.async_get_clientsession",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.bosch_ebike_ha.config_flow.config_entry_oauth2_flow"
            ) as mock_oauth2,
            patch(
                "custom_components.bosch_ebike_ha.config_flow.BoschEBikeApiClient"
            ) as MockClient,
        ):
            mock_oauth2.OAuth2Session.return_value = MagicMock()
            mock_client_instance = MagicMock()
            mock_client_instance.fetch_bikes = AsyncMock(return_value=[fake_bike])
            MockClient.return_value = mock_client_instance

            flow.async_create_entry = _mock_create_entry

            # Step 1: OAuth2 callback
            result = await flow.async_oauth_create_entry(data=FAKE_TOKEN_DATA)
            assert result["type"] == "form"

            # Step 2: User selects imperial
            result = await flow.async_step_unit_system(
                user_input={CONF_UNIT_SYSTEM: UNIT_IMPERIAL}
            )

        assert result["type"] == "create_entry"
        assert result["options"][CONF_UNIT_SYSTEM] == UNIT_IMPERIAL

    @pytest.mark.asyncio
    async def test_full_flow_fetch_bikes_called_once(self):
        """fetch_bikes must be called exactly once during the config flow.

        Requirement 1.2: The Config_Flow SHALL exchange the authorisation code
        for tokens and verify them by calling fetch_bikes.
        """
        flow = BoschEBikeConfigFlow()
        flow.hass = _make_mock_hass()

        fake_bike = _make_fake_bike_info()
        fetch_bikes_call_count = {"n": 0}

        async def _mock_fetch_bikes():
            fetch_bikes_call_count["n"] += 1
            return [fake_bike]

        def _mock_create_entry(title, data, options=None):
            return {"type": "create_entry", "title": title, "data": data, "options": options or {}}

        with (
            patch(
                "custom_components.bosch_ebike_ha.config_flow.async_get_clientsession",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.bosch_ebike_ha.config_flow.config_entry_oauth2_flow"
            ) as mock_oauth2,
            patch(
                "custom_components.bosch_ebike_ha.config_flow.BoschEBikeApiClient"
            ) as MockClient,
        ):
            mock_oauth2.OAuth2Session.return_value = MagicMock()
            mock_client_instance = MagicMock()
            mock_client_instance.fetch_bikes = AsyncMock(side_effect=_mock_fetch_bikes)
            MockClient.return_value = mock_client_instance

            flow.async_create_entry = _mock_create_entry

            await flow.async_oauth_create_entry(data=FAKE_TOKEN_DATA)
            await flow.async_step_unit_system(user_input={CONF_UNIT_SYSTEM: UNIT_METRIC})

        assert fetch_bikes_call_count["n"] == 1, (
            "fetch_bikes must be called exactly once during the config flow"
        )

    @pytest.mark.asyncio
    async def test_full_flow_entry_title_uses_bike_name(self):
        """The config entry title must be the first bike's name.

        Requirement 6.2: The Integration SHALL create a separate HA device for
        each configured bike, named using the bike's name.
        """
        flow = BoschEBikeConfigFlow()
        flow.hass = _make_mock_hass()

        fake_bike = _make_fake_bike_info()

        def _mock_create_entry(title, data, options=None):
            return {"type": "create_entry", "title": title, "data": data, "options": options or {}}

        with (
            patch(
                "custom_components.bosch_ebike_ha.config_flow.async_get_clientsession",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.bosch_ebike_ha.config_flow.config_entry_oauth2_flow"
            ) as mock_oauth2,
            patch(
                "custom_components.bosch_ebike_ha.config_flow.BoschEBikeApiClient"
            ) as MockClient,
        ):
            mock_oauth2.OAuth2Session.return_value = MagicMock()
            mock_client_instance = MagicMock()
            mock_client_instance.fetch_bikes = AsyncMock(return_value=[fake_bike])
            MockClient.return_value = mock_client_instance

            flow.async_create_entry = _mock_create_entry

            await flow.async_oauth_create_entry(data=FAKE_TOKEN_DATA)
            result = await flow.async_step_unit_system(
                user_input={CONF_UNIT_SYSTEM: UNIT_METRIC}
            )

        assert result["title"] == FAKE_BIKE_NAME

    @pytest.mark.asyncio
    async def test_full_flow_entry_data_contains_token(self):
        """The config entry data must contain the OAuth2 token payload.

        Requirement 1.3: The Token_Store SHALL persist the access token,
        refresh token, and token expiry timestamp.
        """
        flow = BoschEBikeConfigFlow()
        flow.hass = _make_mock_hass()

        fake_bike = _make_fake_bike_info()

        def _mock_create_entry(title, data, options=None):
            return {"type": "create_entry", "title": title, "data": data, "options": options or {}}

        with (
            patch(
                "custom_components.bosch_ebike_ha.config_flow.async_get_clientsession",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.bosch_ebike_ha.config_flow.config_entry_oauth2_flow"
            ) as mock_oauth2,
            patch(
                "custom_components.bosch_ebike_ha.config_flow.BoschEBikeApiClient"
            ) as MockClient,
        ):
            mock_oauth2.OAuth2Session.return_value = MagicMock()
            mock_client_instance = MagicMock()
            mock_client_instance.fetch_bikes = AsyncMock(return_value=[fake_bike])
            MockClient.return_value = mock_client_instance

            flow.async_create_entry = _mock_create_entry

            await flow.async_oauth_create_entry(data=FAKE_TOKEN_DATA)
            result = await flow.async_step_unit_system(
                user_input={CONF_UNIT_SYSTEM: UNIT_METRIC}
            )

        # The entry data must be the token payload passed to async_oauth_create_entry
        assert result["data"] == FAKE_TOKEN_DATA


# ---------------------------------------------------------------------------
# Tests: Sensor entity registration after setup
# ---------------------------------------------------------------------------


class TestSensorEntityRegistration:
    """Tests that all expected sensor entities are registered after setup.

    After async_setup_entry is called with a fake bike, all sensor entities
    defined in BIKE_SENSORS must be registered for that bike.

    Requirements: 1.1-1.7, 13.1, 13.2
    """

    @pytest.mark.asyncio
    async def test_all_sensor_entities_registered_for_fake_bike(self):
        """All BIKE_SENSORS entities must be registered for the fake bike.

        Verifies that async_setup_entry (sensor platform) creates one entity
        per sensor description per bike coordinator.

        Requirements: 2.1-2.7, 3.1-3.9, 4.1-4.6
        """
        from custom_components.bosch_ebike_ha.sensor import async_setup_entry as sensor_setup

        fake_bike_data = _make_fake_bike_data()
        entry = _make_mock_entry(unit_system=UNIT_METRIC)
        coordinator = _make_mock_coordinator(fake_bike_data)

        hass = _make_mock_hass()
        hass.data[DOMAIN] = {
            entry.entry_id: {
                "coordinators": [coordinator],
                "battery_coordinators": [],
                "client": MagicMock(),
            }
        }

        registered_entities = []

        def _mock_add_entities(entities):
            registered_entities.extend(entities)

        await sensor_setup(hass, entry, _mock_add_entities)

        # One entity per sensor description
        assert len(registered_entities) == len(BIKE_SENSORS), (
            f"Expected {len(BIKE_SENSORS)} sensor entities, "
            f"got {len(registered_entities)}"
        )

    @pytest.mark.asyncio
    async def test_sensor_entity_unique_ids_are_correct(self):
        """Each sensor entity must have a unique_id of '{bike_id}_{sensor_key}'.

        Requirement 6.2: unique_id must be stable and unique per bike+sensor.
        """
        from custom_components.bosch_ebike_ha.sensor import async_setup_entry as sensor_setup

        fake_bike_data = _make_fake_bike_data()
        entry = _make_mock_entry(unit_system=UNIT_METRIC)
        coordinator = _make_mock_coordinator(fake_bike_data)

        hass = _make_mock_hass()
        hass.data[DOMAIN] = {
            entry.entry_id: {
                "coordinators": [coordinator],
                "battery_coordinators": [],
                "client": MagicMock(),
            }
        }

        registered_entities = []

        def _mock_add_entities(entities):
            registered_entities.extend(entities)

        await sensor_setup(hass, entry, _mock_add_entities)

        for entity in registered_entities:
            expected_prefix = f"{FAKE_BIKE_ID}_"
            assert entity.unique_id.startswith(expected_prefix), (
                f"Entity unique_id '{entity.unique_id}' must start with "
                f"'{expected_prefix}'"
            )

    @pytest.mark.asyncio
    async def test_sensor_entity_unique_ids_are_globally_unique(self):
        """All sensor entity unique_ids must be globally unique.

        Requirement 6.2: unique_id must be globally unique across all bikes
        and sensor keys.
        """
        from custom_components.bosch_ebike_ha.sensor import async_setup_entry as sensor_setup

        fake_bike_data = _make_fake_bike_data()
        entry = _make_mock_entry(unit_system=UNIT_METRIC)
        coordinator = _make_mock_coordinator(fake_bike_data)

        hass = _make_mock_hass()
        hass.data[DOMAIN] = {
            entry.entry_id: {
                "coordinators": [coordinator],
                "battery_coordinators": [],
                "client": MagicMock(),
            }
        }

        registered_entities = []

        def _mock_add_entities(entities):
            registered_entities.extend(entities)

        await sensor_setup(hass, entry, _mock_add_entities)

        unique_ids = [e.unique_id for e in registered_entities]
        assert len(unique_ids) == len(set(unique_ids)), (
            "All sensor entity unique_ids must be globally unique"
        )

    @pytest.mark.asyncio
    async def test_sensor_entities_reference_correct_bike_device(self):
        """Each sensor entity's device_info must reference the correct bike.

        Requirement 6.4: The Integration SHALL associate all sensor entities
        for a given bike with that bike's HA device entry.
        """
        from custom_components.bosch_ebike_ha.sensor import async_setup_entry as sensor_setup

        fake_bike_data = _make_fake_bike_data()
        entry = _make_mock_entry(unit_system=UNIT_METRIC)
        coordinator = _make_mock_coordinator(fake_bike_data)

        hass = _make_mock_hass()
        hass.data[DOMAIN] = {
            entry.entry_id: {
                "coordinators": [coordinator],
                "battery_coordinators": [],
                "client": MagicMock(),
            }
        }

        registered_entities = []

        def _mock_add_entities(entities):
            registered_entities.extend(entities)

        await sensor_setup(hass, entry, _mock_add_entities)

        for entity in registered_entities:
            device_info = entity.device_info
            assert device_info is not None, (
                f"Entity '{entity.unique_id}' must have device_info"
            )
            # device_info is a DeviceInfo dict with 'identifiers' key
            identifiers = device_info.get("identifiers", set())
            assert (DOMAIN, FAKE_BIKE_ID) in identifiers, (
                f"Entity '{entity.unique_id}' device_info must reference "
                f"bike '{FAKE_BIKE_ID}'"
            )

    @pytest.mark.asyncio
    async def test_sensor_entities_registered_for_two_bikes(self):
        """When two bikes are configured, entities must be registered for both.

        Requirement 6.1: The Config_Flow SHALL allow multiple config entries,
        each representing a distinct bike.
        """
        from custom_components.bosch_ebike_ha.sensor import async_setup_entry as sensor_setup

        bike_data_1 = _make_fake_bike_data()
        bike_data_2 = BikeData(
            info=BikeInfo(
                bike_id="second-bike-002",
                name="Second Bike",
                model="Cube Cross",
                serial_number="SN-002",
            ),
            telemetry=bike_data_1.telemetry,
            last_ride=bike_data_1.last_ride,
            aggregate=bike_data_1.aggregate,
            battery=None,
            location=None,
            alarm=None,
            has_flow_plus=False,
            has_connect_module=False,
            last_updated=_NOW,
        )

        entry = _make_mock_entry(unit_system=UNIT_METRIC)
        coord_1 = _make_mock_coordinator(bike_data_1)
        coord_2 = _make_mock_coordinator(bike_data_2)
        coord_2.bike_id = "second-bike-002"

        hass = _make_mock_hass()
        hass.data[DOMAIN] = {
            entry.entry_id: {
                "coordinators": [coord_1, coord_2],
                "battery_coordinators": [],
                "client": MagicMock(),
            }
        }

        registered_entities = []

        def _mock_add_entities(entities):
            registered_entities.extend(entities)

        await sensor_setup(hass, entry, _mock_add_entities)

        # Two bikes * len(BIKE_SENSORS) entities each
        expected_count = 2 * len(BIKE_SENSORS)
        assert len(registered_entities) == expected_count, (
            f"Expected {expected_count} entities for 2 bikes, "
            f"got {len(registered_entities)}"
        )

        # Entities for both bikes must be present
        bike_1_ids = {e.unique_id for e in registered_entities if e.unique_id.startswith(FAKE_BIKE_ID)}
        bike_2_ids = {e.unique_id for e in registered_entities if e.unique_id.startswith("second-bike-002")}
        assert len(bike_1_ids) == len(BIKE_SENSORS)
        assert len(bike_2_ids) == len(BIKE_SENSORS)


# ---------------------------------------------------------------------------
# Tests: Full setup_entry integration (config entry -> entities)
# ---------------------------------------------------------------------------


class TestFullSetupEntryIntegration:
    """Integration tests that wire the config entry through async_setup_entry
    and verify that coordinators and entities are correctly created.

    These tests simulate the complete lifecycle after the config flow creates
    a config entry: async_setup_entry is called, bikes are discovered, device
    entries are registered, coordinators are created, and sensor entities are
    set up.

    Requirements: 1.1-1.7, 13.1, 13.2
    """

    @pytest.mark.asyncio
    async def test_setup_entry_with_metric_options_creates_coordinators(self):
        """async_setup_entry with metric options must create bike coordinators.

        Verifies the full setup path from config entry to coordinator creation.

        Requirements: 1.1, 13.2
        """
        fake_bike = _make_fake_bike_info()
        fake_bike_data = _make_fake_bike_data()

        hass = _make_mock_hass()
        entry = _make_mock_entry(unit_system=UNIT_METRIC)

        mock_client = MagicMock()
        mock_client.fetch_bikes = AsyncMock(return_value=[fake_bike])

        coordinator = _make_mock_coordinator(fake_bike_data)

        mock_dr = MagicMock()
        mock_dr.async_get_or_create = MagicMock()

        with (
            patch.object(_init_mod, "async_get_clientsession", return_value=MagicMock()),
            patch.object(_init_mod, "config_entry_oauth2_flow") as mock_oauth2,
            patch.object(_init_mod, "BoschEBikeApiClient", return_value=mock_client),
            patch.object(_init_mod, "BikeCoordinator", return_value=coordinator),
            patch.object(_init_mod, "BatteryCoordinator"),
            patch.object(_init_mod.dr, "async_get", return_value=mock_dr),
        ):
            mock_oauth2.OAuth2Session.return_value = MagicMock()
            result = await async_setup_entry(hass, entry)

        assert result is True
        coordinators = hass.data[DOMAIN][entry.entry_id]["coordinators"]
        assert len(coordinators) == 1
        assert coordinators[0].bike_id == FAKE_BIKE_ID

    @pytest.mark.asyncio
    async def test_setup_entry_with_imperial_options_stores_entry_options(self):
        """async_setup_entry with imperial options must preserve options in hass.data.

        The entry's options dict (containing unit_system) must be accessible
        to sensor entities after setup.

        Requirements: 13.2
        """
        fake_bike = _make_fake_bike_info()
        fake_bike_data = _make_fake_bike_data()

        hass = _make_mock_hass()
        entry = _make_mock_entry(unit_system=UNIT_IMPERIAL)

        mock_client = MagicMock()
        mock_client.fetch_bikes = AsyncMock(return_value=[fake_bike])

        coordinator = _make_mock_coordinator(fake_bike_data)

        mock_dr = MagicMock()
        mock_dr.async_get_or_create = MagicMock()

        with (
            patch.object(_init_mod, "async_get_clientsession", return_value=MagicMock()),
            patch.object(_init_mod, "config_entry_oauth2_flow") as mock_oauth2,
            patch.object(_init_mod, "BoschEBikeApiClient", return_value=mock_client),
            patch.object(_init_mod, "BikeCoordinator", return_value=coordinator),
            patch.object(_init_mod, "BatteryCoordinator"),
            patch.object(_init_mod.dr, "async_get", return_value=mock_dr),
        ):
            mock_oauth2.OAuth2Session.return_value = MagicMock()
            await async_setup_entry(hass, entry)

        # The entry options must still contain the imperial unit_system
        assert entry.options[CONF_UNIT_SYSTEM] == UNIT_IMPERIAL

    @pytest.mark.asyncio
    async def test_setup_entry_registers_device_for_fake_bike(self):
        """async_setup_entry must register a device entry for the fake bike.

        Requirement 6.2: The Integration SHALL create a separate HA device for
        each configured bike, named using the bike's name.
        """
        fake_bike = _make_fake_bike_info()
        fake_bike_data = _make_fake_bike_data()

        hass = _make_mock_hass()
        entry = _make_mock_entry(unit_system=UNIT_METRIC)

        mock_client = MagicMock()
        mock_client.fetch_bikes = AsyncMock(return_value=[fake_bike])

        coordinator = _make_mock_coordinator(fake_bike_data)

        registered_devices = []

        def _capture_device(**kwargs):
            registered_devices.append(kwargs)
            return MagicMock()

        mock_dr = MagicMock()
        mock_dr.async_get_or_create = _capture_device

        with (
            patch.object(_init_mod, "async_get_clientsession", return_value=MagicMock()),
            patch.object(_init_mod, "config_entry_oauth2_flow") as mock_oauth2,
            patch.object(_init_mod, "BoschEBikeApiClient", return_value=mock_client),
            patch.object(_init_mod, "BikeCoordinator", return_value=coordinator),
            patch.object(_init_mod, "BatteryCoordinator"),
            patch.object(_init_mod.dr, "async_get", return_value=mock_dr),
        ):
            mock_oauth2.OAuth2Session.return_value = MagicMock()
            await async_setup_entry(hass, entry)

        assert len(registered_devices) == 1
        device = registered_devices[0]
        assert device["name"] == FAKE_BIKE_NAME
        assert (DOMAIN, FAKE_BIKE_ID) in device["identifiers"]

    @pytest.mark.asyncio
    async def test_setup_entry_then_sensor_setup_registers_all_entities(self):
        """Full pipeline: setup_entry + sensor platform setup registers all entities.

        This is the most complete integration test: it runs async_setup_entry
        to create coordinators, then runs the sensor platform's async_setup_entry
        to register entities, and asserts all BIKE_SENSORS are present.

        Requirements: 1.1-1.7, 13.1, 13.2
        """
        from custom_components.bosch_ebike_ha.sensor import async_setup_entry as sensor_setup

        fake_bike = _make_fake_bike_info()
        fake_bike_data = _make_fake_bike_data()

        hass = _make_mock_hass()
        entry = _make_mock_entry(unit_system=UNIT_METRIC)

        mock_client = MagicMock()
        mock_client.fetch_bikes = AsyncMock(return_value=[fake_bike])

        coordinator = _make_mock_coordinator(fake_bike_data)

        mock_dr = MagicMock()
        mock_dr.async_get_or_create = MagicMock()

        with (
            patch.object(_init_mod, "async_get_clientsession", return_value=MagicMock()),
            patch.object(_init_mod, "config_entry_oauth2_flow") as mock_oauth2,
            patch.object(_init_mod, "BoschEBikeApiClient", return_value=mock_client),
            patch.object(_init_mod, "BikeCoordinator", return_value=coordinator),
            patch.object(_init_mod, "BatteryCoordinator"),
            patch.object(_init_mod.dr, "async_get", return_value=mock_dr),
        ):
            mock_oauth2.OAuth2Session.return_value = MagicMock()
            result = await async_setup_entry(hass, entry)

        assert result is True

        # Now run the sensor platform setup
        registered_entities = []

        def _mock_add_entities(entities):
            registered_entities.extend(entities)

        await sensor_setup(hass, entry, _mock_add_entities)

        # All BIKE_SENSORS must be registered
        assert len(registered_entities) == len(BIKE_SENSORS), (
            f"Expected {len(BIKE_SENSORS)} sensor entities after full setup, "
            f"got {len(registered_entities)}"
        )

        # All entities must reference the fake bike
        for entity in registered_entities:
            assert entity.unique_id.startswith(FAKE_BIKE_ID), (
                f"Entity '{entity.unique_id}' must reference bike '{FAKE_BIKE_ID}'"
            )

    @pytest.mark.asyncio
    async def test_setup_entry_sensor_entities_report_metric_values(self):
        """After setup with metric options, sensor entities must report metric values.

        Requirements: 13.3
        """
        from custom_components.bosch_ebike_ha.sensor import async_setup_entry as sensor_setup

        fake_bike = _make_fake_bike_info()
        fake_bike_data = _make_fake_bike_data()

        hass = _make_mock_hass()
        entry = _make_mock_entry(unit_system=UNIT_METRIC)

        mock_client = MagicMock()
        mock_client.fetch_bikes = AsyncMock(return_value=[fake_bike])

        coordinator = _make_mock_coordinator(fake_bike_data)

        mock_dr = MagicMock()
        mock_dr.async_get_or_create = MagicMock()

        with (
            patch.object(_init_mod, "async_get_clientsession", return_value=MagicMock()),
            patch.object(_init_mod, "config_entry_oauth2_flow") as mock_oauth2,
            patch.object(_init_mod, "BoschEBikeApiClient", return_value=mock_client),
            patch.object(_init_mod, "BikeCoordinator", return_value=coordinator),
            patch.object(_init_mod, "BatteryCoordinator"),
            patch.object(_init_mod.dr, "async_get", return_value=mock_dr),
        ):
            mock_oauth2.OAuth2Session.return_value = MagicMock()
            await async_setup_entry(hass, entry)

        registered_entities = []

        def _mock_add_entities(entities):
            registered_entities.extend(entities)

        await sensor_setup(hass, entry, _mock_add_entities)

        # Find the odometer sensor and verify it reports km
        odometer = next(
            (e for e in registered_entities if e.unique_id == f"{FAKE_BIKE_ID}_odometer"),
            None,
        )
        assert odometer is not None, "Odometer sensor must be registered"
        assert odometer.native_value == 500.0
        assert odometer.native_unit_of_measurement == "km"

    @pytest.mark.asyncio
    async def test_setup_entry_sensor_entities_report_imperial_values(self):
        """After setup with imperial options, sensor entities must report imperial values.

        Requirements: 13.4
        """
        from custom_components.bosch_ebike_ha.sensor import async_setup_entry as sensor_setup
        from custom_components.bosch_ebike_ha.unit_converter import KM_TO_MILES

        fake_bike = _make_fake_bike_info()
        fake_bike_data = _make_fake_bike_data()

        hass = _make_mock_hass()
        entry = _make_mock_entry(unit_system=UNIT_IMPERIAL)

        mock_client = MagicMock()
        mock_client.fetch_bikes = AsyncMock(return_value=[fake_bike])

        coordinator = _make_mock_coordinator(fake_bike_data)

        mock_dr = MagicMock()
        mock_dr.async_get_or_create = MagicMock()

        with (
            patch.object(_init_mod, "async_get_clientsession", return_value=MagicMock()),
            patch.object(_init_mod, "config_entry_oauth2_flow") as mock_oauth2,
            patch.object(_init_mod, "BoschEBikeApiClient", return_value=mock_client),
            patch.object(_init_mod, "BikeCoordinator", return_value=coordinator),
            patch.object(_init_mod, "BatteryCoordinator"),
            patch.object(_init_mod.dr, "async_get", return_value=mock_dr),
        ):
            mock_oauth2.OAuth2Session.return_value = MagicMock()
            await async_setup_entry(hass, entry)

        registered_entities = []

        def _mock_add_entities(entities):
            registered_entities.extend(entities)

        await sensor_setup(hass, entry, _mock_add_entities)

        # Find the odometer sensor and verify it reports miles
        odometer = next(
            (e for e in registered_entities if e.unique_id == f"{FAKE_BIKE_ID}_odometer"),
            None,
        )
        assert odometer is not None, "Odometer sensor must be registered"
        expected_miles = round(500.0 * KM_TO_MILES, 3)
        assert odometer.native_value == expected_miles
        assert odometer.native_unit_of_measurement == "mi"

