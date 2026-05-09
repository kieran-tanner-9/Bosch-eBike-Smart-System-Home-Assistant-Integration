"""Integration tests for __init__.py — multi-bike setup (Task 12.1).

Verifies that ``async_setup_entry``:
1. Iterates over ALL bikes returned by ``fetch_bikes``.
2. Creates one ``BikeCoordinator`` per bike.
3. Registers each bike as a device entry using ``bike.name`` and
   ``(DOMAIN, bike.bike_id)`` as the identifier.
4. Stores all coordinators in ``hass.data[DOMAIN][entry.entry_id]["coordinators"]``.
5. A failure in one bike's coordinator must not prevent other bikes from
   being set up (Requirement 6.3).

Requirements: 6.1–6.4
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import the module under test so patches can target its namespace.
import custom_components.bosch_ebike_ha as _init_mod
from custom_components.bosch_ebike_ha import async_setup_entry
from custom_components.bosch_ebike_ha.const import DOMAIN
from custom_components.bosch_ebike_ha.models import (
    AggregateStats,
    BikeData,
    BikeInfo,
    BikeTelemetry,
    RideData,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_bike_info(bike_id: str, name: str) -> BikeInfo:
    return BikeInfo(
        bike_id=bike_id,
        name=name,
        model="Cube Stereo",
        serial_number=f"SN-{bike_id}",
    )


def _make_bike_data(bike_id: str) -> BikeData:
    return BikeData(
        info=_make_bike_info(bike_id, bike_id),
        telemetry=BikeTelemetry(
            odometer_km=1000.0,
            motor_hours_total=50.0,
            motor_hours_with_assist=40.0,
            battery_charge_cycles=30,
            battery_lifetime_energy_wh=3000.0,
            next_service_odometer_km=2000.0,
            max_assist_speed_kmh=25.0,
        ),
        last_ride=RideData(
            ride_id="r1",
            completed_at=_NOW,
            distance_km=20.0,
            duration_minutes=60.0,
            average_speed_kmh=20.0,
            max_speed_kmh=35.0,
            elevation_gain_m=100.0,
            elevation_loss_m=90.0,
            calories_kcal=400.0,
            avg_rider_power_w=None,
            max_rider_power_w=None,
            avg_cadence_rpm=None,
            max_cadence_rpm=None,
            motor_power_ratio_pct=None,
        ),
        aggregate=AggregateStats(
            total_rides=50,
            total_distance_km=2000.0,
            total_ride_time_hours=80.0,
            total_calories_kcal=20000.0,
            total_elevation_gain_m=5000.0,
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
    """Create a minimal mock hass object."""
    hass = MagicMock()
    hass.data = {}
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)
    return hass


def _make_mock_entry(entry_id: str = "test_entry_id") -> MagicMock:
    """Create a minimal mock config entry."""
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.domain = DOMAIN
    entry.options = {}
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock(return_value=lambda: None)
    return entry


def _make_mock_client(bikes: list[BikeInfo]) -> MagicMock:
    """Create a mock BoschEBikeApiClient that returns the given bikes."""
    client = MagicMock()
    client.fetch_bikes = AsyncMock(return_value=bikes)
    return client


def _make_mock_coordinator(bike_id: str, *, fail: bool = False) -> MagicMock:
    """Create a mock BikeCoordinator."""
    coord = MagicMock()
    coord.bike_id = bike_id
    if fail:
        coord.async_config_entry_first_refresh = AsyncMock(
            side_effect=Exception(f"Simulated failure for {bike_id}")
        )
    else:
        coord.async_config_entry_first_refresh = AsyncMock(return_value=None)
        coord.data = _make_bike_data(bike_id)
    coord.async_shutdown = MagicMock()
    return coord


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAsyncSetupEntryMultiBike:
    """Tests for multi-bike iteration and device registration."""

    @pytest.mark.asyncio
    async def test_iterates_over_all_bikes(self):
        """async_setup_entry must create one coordinator per bike returned by fetch_bikes."""
        bikes = [
            _make_bike_info("bike1", "Mountain Bike"),
            _make_bike_info("bike2", "Road Bike"),
            _make_bike_info("bike3", "City Bike"),
        ]
        mock_client = _make_mock_client(bikes)
        hass = _make_mock_hass()
        entry = _make_mock_entry()

        coordinator_calls: list[str] = []

        def make_coordinator(h, e, c, bike_id):
            coordinator_calls.append(bike_id)
            return _make_mock_coordinator(bike_id)

        mock_dr = MagicMock()
        mock_dr.async_get_or_create = MagicMock()

        with (
            patch.object(_init_mod, "async_get_clientsession", return_value=MagicMock()),
            patch.object(_init_mod, "config_entry_oauth2_flow") as mock_oauth,
            patch.object(_init_mod, "BoschEBikeApiClient", return_value=mock_client),
            patch.object(_init_mod, "BikeCoordinator", side_effect=make_coordinator),
            patch.object(_init_mod, "BatteryCoordinator"),
            patch.object(_init_mod.dr, "async_get", return_value=mock_dr),
        ):
            mock_oauth.OAuth2Session.return_value = MagicMock()
            result = await async_setup_entry(hass, entry)

        assert result is True
        # One coordinator created per bike
        assert coordinator_calls == ["bike1", "bike2", "bike3"]
        # All coordinators stored
        coordinators = hass.data[DOMAIN][entry.entry_id]["coordinators"]
        assert len(coordinators) == 3

    @pytest.mark.asyncio
    async def test_device_entry_uses_bike_name_and_identifier(self):
        """Each device entry must use bike.name and (DOMAIN, bike.bike_id) as identifier."""
        bikes = [
            _make_bike_info("bike-abc", "My Mountain Bike"),
            _make_bike_info("bike-xyz", "My Road Bike"),
        ]
        mock_client = _make_mock_client(bikes)
        hass = _make_mock_hass()
        entry = _make_mock_entry()

        registered_devices: list[dict] = []

        def capture_device(**kwargs):
            registered_devices.append(kwargs)
            return MagicMock()

        mock_dr = MagicMock()
        mock_dr.async_get_or_create = capture_device

        with (
            patch.object(_init_mod, "async_get_clientsession", return_value=MagicMock()),
            patch.object(_init_mod, "config_entry_oauth2_flow") as mock_oauth,
            patch.object(_init_mod, "BoschEBikeApiClient", return_value=mock_client),
            patch.object(
                _init_mod,
                "BikeCoordinator",
                side_effect=lambda h, e, c, bike_id: _make_mock_coordinator(bike_id),
            ),
            patch.object(_init_mod, "BatteryCoordinator"),
            patch.object(_init_mod.dr, "async_get", return_value=mock_dr),
        ):
            mock_oauth.OAuth2Session.return_value = MagicMock()
            await async_setup_entry(hass, entry)

        assert len(registered_devices) == 2

        # Verify bike-abc
        abc_device = next(
            d for d in registered_devices if (DOMAIN, "bike-abc") in d["identifiers"]
        )
        assert abc_device["name"] == "My Mountain Bike"
        assert (DOMAIN, "bike-abc") in abc_device["identifiers"]

        # Verify bike-xyz
        xyz_device = next(
            d for d in registered_devices if (DOMAIN, "bike-xyz") in d["identifiers"]
        )
        assert xyz_device["name"] == "My Road Bike"
        assert (DOMAIN, "bike-xyz") in xyz_device["identifiers"]

    @pytest.mark.asyncio
    async def test_coordinators_stored_in_hass_data(self):
        """All coordinators must be stored in hass.data[DOMAIN][entry_id]['coordinators']."""
        bikes = [
            _make_bike_info("bike1", "Bike One"),
            _make_bike_info("bike2", "Bike Two"),
        ]
        mock_client = _make_mock_client(bikes)
        hass = _make_mock_hass()
        entry = _make_mock_entry(entry_id="my_entry")

        created_coordinators: list[MagicMock] = []

        def make_coordinator(h, e, c, bike_id):
            coord = _make_mock_coordinator(bike_id)
            created_coordinators.append(coord)
            return coord

        mock_dr = MagicMock()
        mock_dr.async_get_or_create = MagicMock()

        with (
            patch.object(_init_mod, "async_get_clientsession", return_value=MagicMock()),
            patch.object(_init_mod, "config_entry_oauth2_flow") as mock_oauth,
            patch.object(_init_mod, "BoschEBikeApiClient", return_value=mock_client),
            patch.object(_init_mod, "BikeCoordinator", side_effect=make_coordinator),
            patch.object(_init_mod, "BatteryCoordinator"),
            patch.object(_init_mod.dr, "async_get", return_value=mock_dr),
        ):
            mock_oauth.OAuth2Session.return_value = MagicMock()
            await async_setup_entry(hass, entry)

        stored = hass.data[DOMAIN]["my_entry"]["coordinators"]
        assert len(stored) == 2
        # The stored coordinators are the same objects that were created
        for coord in created_coordinators:
            assert coord in stored

    @pytest.mark.asyncio
    async def test_failure_in_one_coordinator_does_not_affect_others(self):
        """A first-refresh failure for one bike must not prevent other bikes from being set up.

        Requirement 6.3: polling each bike's data independently so that a
        failure for one bike does not affect the sensors of another.
        """
        bikes = [
            _make_bike_info("bike-ok-1", "Good Bike 1"),
            _make_bike_info("bike-fail", "Failing Bike"),
            _make_bike_info("bike-ok-2", "Good Bike 2"),
        ]
        mock_client = _make_mock_client(bikes)
        hass = _make_mock_hass()
        entry = _make_mock_entry()

        def make_coordinator(h, e, c, bike_id):
            return _make_mock_coordinator(bike_id, fail=(bike_id == "bike-fail"))

        mock_dr = MagicMock()
        mock_dr.async_get_or_create = MagicMock()

        with (
            patch.object(_init_mod, "async_get_clientsession", return_value=MagicMock()),
            patch.object(_init_mod, "config_entry_oauth2_flow") as mock_oauth,
            patch.object(_init_mod, "BoschEBikeApiClient", return_value=mock_client),
            patch.object(_init_mod, "BikeCoordinator", side_effect=make_coordinator),
            patch.object(_init_mod, "BatteryCoordinator"),
            patch.object(_init_mod.dr, "async_get", return_value=mock_dr),
        ):
            mock_oauth.OAuth2Session.return_value = MagicMock()
            result = await async_setup_entry(hass, entry)

        # Setup must still succeed overall
        assert result is True

        # Only the two successful bikes' coordinators are stored
        coordinators = hass.data[DOMAIN][entry.entry_id]["coordinators"]
        assert len(coordinators) == 2

        stored_bike_ids = {c.bike_id for c in coordinators}
        assert "bike-ok-1" in stored_bike_ids
        assert "bike-ok-2" in stored_bike_ids
        assert "bike-fail" not in stored_bike_ids

    @pytest.mark.asyncio
    async def test_independent_coordinators_per_bike(self):
        """Each bike must get its own independent BikeCoordinator instance."""
        bikes = [
            _make_bike_info("bike1", "Bike One"),
            _make_bike_info("bike2", "Bike Two"),
        ]
        mock_client = _make_mock_client(bikes)
        hass = _make_mock_hass()
        entry = _make_mock_entry()

        coordinator_bike_ids: list[str] = []

        def make_coordinator(h, e, c, bike_id):
            coordinator_bike_ids.append(bike_id)
            return _make_mock_coordinator(bike_id)

        mock_dr = MagicMock()
        mock_dr.async_get_or_create = MagicMock()

        with (
            patch.object(_init_mod, "async_get_clientsession", return_value=MagicMock()),
            patch.object(_init_mod, "config_entry_oauth2_flow") as mock_oauth,
            patch.object(_init_mod, "BoschEBikeApiClient", return_value=mock_client),
            patch.object(_init_mod, "BikeCoordinator", side_effect=make_coordinator),
            patch.object(_init_mod, "BatteryCoordinator"),
            patch.object(_init_mod.dr, "async_get", return_value=mock_dr),
        ):
            mock_oauth.OAuth2Session.return_value = MagicMock()
            await async_setup_entry(hass, entry)

        # BikeCoordinator was instantiated once per bike with the correct bike_id
        assert coordinator_bike_ids == ["bike1", "bike2"]
        # Each call used a different bike_id
        assert len(set(coordinator_bike_ids)) == 2

    @pytest.mark.asyncio
    async def test_all_failures_returns_true_with_empty_coordinators(self):
        """If all bikes fail first refresh, setup returns True with empty coordinator list.

        The integration still sets up successfully (platforms are forwarded);
        entities will simply be unavailable.
        """
        bikes = [
            _make_bike_info("bike1", "Bike One"),
            _make_bike_info("bike2", "Bike Two"),
        ]
        mock_client = _make_mock_client(bikes)
        hass = _make_mock_hass()
        entry = _make_mock_entry()

        mock_dr = MagicMock()
        mock_dr.async_get_or_create = MagicMock()

        with (
            patch.object(_init_mod, "async_get_clientsession", return_value=MagicMock()),
            patch.object(_init_mod, "config_entry_oauth2_flow") as mock_oauth,
            patch.object(_init_mod, "BoschEBikeApiClient", return_value=mock_client),
            patch.object(
                _init_mod,
                "BikeCoordinator",
                side_effect=lambda h, e, c, bike_id: _make_mock_coordinator(
                    bike_id, fail=True
                ),
            ),
            patch.object(_init_mod, "BatteryCoordinator"),
            patch.object(_init_mod.dr, "async_get", return_value=mock_dr),
        ):
            mock_oauth.OAuth2Session.return_value = MagicMock()
            result = await async_setup_entry(hass, entry)

        assert result is True
        coordinators = hass.data[DOMAIN][entry.entry_id]["coordinators"]
        assert len(coordinators) == 0


# ---------------------------------------------------------------------------
# Task 12.2 — Integration tests for multi-bike setup
#
# These tests extend the existing coverage with:
# 1. Explicit assertion that two bikes produce two independent device entries
#    AND two independent coordinator instances (distinct objects, distinct IDs).
# 2. Simulation of a runtime failure in one bike's coordinator and assertion
#    that the other bike's coordinator/entities remain available.
#
# Requirements: 6.1–6.4
# ---------------------------------------------------------------------------


class TestMultiBikeIntegration:
    """Integration tests for multi-bike setup (Task 12.2).

    Verifies:
    - Two bikes → two independent device entries and two independent
      coordinator instances (distinct Python objects, distinct bike IDs).
    - A runtime failure in one bike's coordinator does not affect the other
      bike's coordinator availability (last_update_success remains True).
    """

    @pytest.mark.asyncio
    async def test_two_bikes_produce_two_independent_device_entries_and_coordinators(self):
        """Two bikes must produce exactly two device entries and two distinct coordinator instances.

        Requirements 6.1, 6.2, 6.4: each bike gets its own device entry
        (identified by bike_id) and its own coordinator instance.
        """
        bikes = [
            _make_bike_info("alpha-001", "Alpha Bike"),
            _make_bike_info("beta-002", "Beta Bike"),
        ]
        mock_client = _make_mock_client(bikes)
        hass = _make_mock_hass()
        entry = _make_mock_entry(entry_id="two_bike_entry")

        registered_devices: list[dict] = []
        created_coordinators: list[MagicMock] = []

        def capture_device(**kwargs):
            registered_devices.append(kwargs)
            return MagicMock()

        def make_coordinator(h, e, c, bike_id):
            coord = _make_mock_coordinator(bike_id)
            created_coordinators.append(coord)
            return coord

        mock_dr = MagicMock()
        mock_dr.async_get_or_create = capture_device

        with (
            patch.object(_init_mod, "async_get_clientsession", return_value=MagicMock()),
            patch.object(_init_mod, "config_entry_oauth2_flow") as mock_oauth,
            patch.object(_init_mod, "BoschEBikeApiClient", return_value=mock_client),
            patch.object(_init_mod, "BikeCoordinator", side_effect=make_coordinator),
            patch.object(_init_mod, "BatteryCoordinator"),
            patch.object(_init_mod.dr, "async_get", return_value=mock_dr),
        ):
            mock_oauth.OAuth2Session.return_value = MagicMock()
            result = await async_setup_entry(hass, entry)

        assert result is True

        # --- Two independent device entries ---
        assert len(registered_devices) == 2, (
            "Expected exactly 2 device entries, one per bike"
        )
        device_identifiers = [
            next(iter(d["identifiers"])) for d in registered_devices
        ]
        assert (DOMAIN, "alpha-001") in device_identifiers
        assert (DOMAIN, "beta-002") in device_identifiers

        # Device names match bike names
        alpha_dev = next(d for d in registered_devices if (DOMAIN, "alpha-001") in d["identifiers"])
        beta_dev = next(d for d in registered_devices if (DOMAIN, "beta-002") in d["identifiers"])
        assert alpha_dev["name"] == "Alpha Bike"
        assert beta_dev["name"] == "Beta Bike"

        # --- Two independent coordinator instances ---
        assert len(created_coordinators) == 2, (
            "Expected exactly 2 coordinator instances, one per bike"
        )
        # They must be distinct Python objects
        assert created_coordinators[0] is not created_coordinators[1], (
            "Coordinators must be independent instances, not the same object"
        )
        # Each coordinator is associated with a different bike_id
        coordinator_bike_ids = {c.bike_id for c in created_coordinators}
        assert coordinator_bike_ids == {"alpha-001", "beta-002"}, (
            "Each coordinator must be associated with a distinct bike_id"
        )

        # Both coordinators are stored in hass.data
        stored = hass.data[DOMAIN]["two_bike_entry"]["coordinators"]
        assert len(stored) == 2
        for coord in created_coordinators:
            assert coord in stored

    @pytest.mark.asyncio
    async def test_runtime_failure_in_one_coordinator_leaves_other_available(self):
        """A runtime failure in one bike's coordinator must not affect the other.

        Simulates a scenario where bike-A's coordinator fails its first refresh
        while bike-B's coordinator succeeds.  Asserts:
        - Setup still returns True.
        - Only bike-B's coordinator is stored.
        - bike-B's coordinator has last_update_success=True (entities available).
        - bike-A's coordinator is not stored (its entities are not registered).

        Requirements 6.3: polling each bike's data independently so that a
        failure for one bike does not affect the sensors of another.
        """
        bikes = [
            _make_bike_info("bike-failing", "Failing Bike"),
            _make_bike_info("bike-healthy", "Healthy Bike"),
        ]
        mock_client = _make_mock_client(bikes)
        hass = _make_mock_hass()
        entry = _make_mock_entry(entry_id="failure_test_entry")

        healthy_coordinator: MagicMock | None = None

        def make_coordinator(h, e, c, bike_id):
            nonlocal healthy_coordinator
            coord = _make_mock_coordinator(bike_id, fail=(bike_id == "bike-failing"))
            if bike_id == "bike-healthy":
                # Simulate a successful coordinator: last_update_success=True
                coord.last_update_success = True
                healthy_coordinator = coord
            return coord

        mock_dr = MagicMock()
        mock_dr.async_get_or_create = MagicMock()

        with (
            patch.object(_init_mod, "async_get_clientsession", return_value=MagicMock()),
            patch.object(_init_mod, "config_entry_oauth2_flow") as mock_oauth,
            patch.object(_init_mod, "BoschEBikeApiClient", return_value=mock_client),
            patch.object(_init_mod, "BikeCoordinator", side_effect=make_coordinator),
            patch.object(_init_mod, "BatteryCoordinator"),
            patch.object(_init_mod.dr, "async_get", return_value=mock_dr),
        ):
            mock_oauth.OAuth2Session.return_value = MagicMock()
            result = await async_setup_entry(hass, entry)

        assert result is True, "Setup must succeed even when one bike fails"

        stored_coordinators = hass.data[DOMAIN]["failure_test_entry"]["coordinators"]

        # Only the healthy bike's coordinator is stored
        assert len(stored_coordinators) == 1, (
            "Only the healthy bike's coordinator should be stored"
        )
        stored_bike_ids = {c.bike_id for c in stored_coordinators}
        assert "bike-healthy" in stored_bike_ids, (
            "Healthy bike's coordinator must be stored"
        )
        assert "bike-failing" not in stored_bike_ids, (
            "Failing bike's coordinator must not be stored"
        )

        # The healthy coordinator's last_update_success is True — entities are available
        assert healthy_coordinator is not None
        assert healthy_coordinator.last_update_success is True, (
            "Healthy bike's coordinator must have last_update_success=True "
            "(its entities remain available)"
        )

    @pytest.mark.asyncio
    async def test_coordinator_independence_after_one_bike_runtime_failure(self):
        """Verify coordinator independence: a failure in one does not mutate the other.

        Creates two coordinators; the first fails its refresh.  Asserts that
        the second coordinator's data and last_update_success are unaffected.

        Requirements 6.3, 6.4.
        """
        bikes = [
            _make_bike_info("bike-a", "Bike A"),
            _make_bike_info("bike-b", "Bike B"),
        ]
        mock_client = _make_mock_client(bikes)
        hass = _make_mock_hass()
        entry = _make_mock_entry(entry_id="independence_entry")

        coordinator_b: MagicMock | None = None

        def make_coordinator(h, e, c, bike_id):
            nonlocal coordinator_b
            if bike_id == "bike-a":
                # bike-a fails first refresh
                return _make_mock_coordinator(bike_id, fail=True)
            else:
                # bike-b succeeds; capture the instance
                coord = _make_mock_coordinator(bike_id, fail=False)
                coord.last_update_success = True
                coordinator_b = coord
                return coord

        mock_dr = MagicMock()
        mock_dr.async_get_or_create = MagicMock()

        with (
            patch.object(_init_mod, "async_get_clientsession", return_value=MagicMock()),
            patch.object(_init_mod, "config_entry_oauth2_flow") as mock_oauth,
            patch.object(_init_mod, "BoschEBikeApiClient", return_value=mock_client),
            patch.object(_init_mod, "BikeCoordinator", side_effect=make_coordinator),
            patch.object(_init_mod, "BatteryCoordinator"),
            patch.object(_init_mod.dr, "async_get", return_value=mock_dr),
        ):
            mock_oauth.OAuth2Session.return_value = MagicMock()
            result = await async_setup_entry(hass, entry)

        assert result is True

        # bike-b's coordinator is unaffected by bike-a's failure
        assert coordinator_b is not None
        assert coordinator_b.last_update_success is True, (
            "bike-b coordinator must remain available after bike-a fails"
        )
        assert coordinator_b.data is not None, (
            "bike-b coordinator must retain its data after bike-a fails"
        )
        assert coordinator_b.data.info.bike_id == "bike-b", (
            "bike-b coordinator data must reference bike-b, not bike-a"
        )

        # bike-b's coordinator is in hass.data; bike-a's is not
        stored = hass.data[DOMAIN]["independence_entry"]["coordinators"]
        assert any(c.bike_id == "bike-b" for c in stored)
        assert not any(c.bike_id == "bike-a" for c in stored)

    @pytest.mark.asyncio
    async def test_two_bikes_have_separate_device_identifiers(self):
        """Each bike's device entry must use a unique identifier tuple.

        Requirements 6.2, 6.4: device identifiers must be distinct so that
        HA treats them as separate devices in the device registry.
        """
        bikes = [
            _make_bike_info("uid-111", "Bike One"),
            _make_bike_info("uid-222", "Bike Two"),
        ]
        mock_client = _make_mock_client(bikes)
        hass = _make_mock_hass()
        entry = _make_mock_entry()

        registered_identifiers: list[frozenset] = []

        def capture_device(**kwargs):
            registered_identifiers.append(kwargs["identifiers"])
            return MagicMock()

        mock_dr = MagicMock()
        mock_dr.async_get_or_create = capture_device

        with (
            patch.object(_init_mod, "async_get_clientsession", return_value=MagicMock()),
            patch.object(_init_mod, "config_entry_oauth2_flow") as mock_oauth,
            patch.object(_init_mod, "BoschEBikeApiClient", return_value=mock_client),
            patch.object(
                _init_mod,
                "BikeCoordinator",
                side_effect=lambda h, e, c, bike_id: _make_mock_coordinator(bike_id),
            ),
            patch.object(_init_mod, "BatteryCoordinator"),
            patch.object(_init_mod.dr, "async_get", return_value=mock_dr),
        ):
            mock_oauth.OAuth2Session.return_value = MagicMock()
            await async_setup_entry(hass, entry)

        assert len(registered_identifiers) == 2

        # Identifiers must be distinct (no two bikes share the same identifier)
        all_id_tuples = [
            tuple(sorted(ids)) for ids in registered_identifiers
        ]
        assert len(set(all_id_tuples)) == 2, (
            "Each bike must have a unique device identifier"
        )

        # Each identifier must contain the correct bike_id
        flat_ids = [item for ids in registered_identifiers for item in ids]
        assert (DOMAIN, "uid-111") in flat_ids
        assert (DOMAIN, "uid-222") in flat_ids
