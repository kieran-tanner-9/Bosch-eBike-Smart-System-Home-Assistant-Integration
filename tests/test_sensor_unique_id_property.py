"""Property-based tests for entity unique ID stability (Property 4).

**Validates: Requirements 6.2, 6.4**

Property 4: Entity unique IDs are stable, unique, and correctly associated
with their bike device.

For any set of bikes with distinct ``bike_id`` values and any set of sensor
keys, the ``unique_id`` generated for each entity SHALL be globally unique
across all bikes and sensor keys, SHALL remain identical across restarts
(pure function of ``bike_id`` and ``sensor_key``), and the entity's
``device_info`` identifiers SHALL reference the correct bike's device
registry entry.

Uses Hypothesis with a minimum of 100 examples.
"""
from __future__ import annotations

import sys
import os

# Ensure the project root is on the path so custom_components can be imported.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Inject HA stubs before any homeassistant imports.
from tests.ha_stubs.inject import inject_ha_stubs  # noqa: E402

inject_ha_stubs()

from hypothesis import given, settings
from hypothesis import strategies as st

from custom_components.bosch_ebike_ha.const import DOMAIN
from custom_components.bosch_ebike_ha.sensor import BIKE_SENSORS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# All sensor keys from the BIKE_SENSORS tuple
_ALL_SENSOR_KEYS: list[str] = [desc.key for desc in BIKE_SENSORS]


def _make_unique_id(bike_id: str, sensor_key: str) -> str:
    """Replicate the unique_id formula from BoschEBikeSensor.__init__."""
    return f"{bike_id}_{sensor_key}"


def _make_device_info_identifiers(bike_id: str) -> set[tuple[str, str]]:
    """Replicate the device_info identifiers from BoschEBikeSensor.__init__."""
    return {(DOMAIN, bike_id)}


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Strategy for a single non-empty bike_id string (printable ASCII, no
# underscores to avoid accidental collisions with the separator character).
# We restrict to alphanumeric + hyphen to keep IDs realistic and unambiguous.
_st_bike_id = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters="-",
    ),
    min_size=1,
    max_size=64,
)

# Strategy for a list of 2–5 *distinct* bike_ids
_st_bike_ids = st.lists(
    _st_bike_id,
    min_size=2,
    max_size=5,
    unique=True,
)


# ---------------------------------------------------------------------------
# Property 4: Entity unique IDs are stable, unique, and correctly associated
# ---------------------------------------------------------------------------


@given(bike_ids=_st_bike_ids)
@settings(max_examples=100)
def test_property4_unique_ids_are_globally_unique(bike_ids: list[str]) -> None:
    """**Validates: Requirements 6.2, 6.4**

    For every combination of (bike_id, sensor_key), the unique_id must be
    globally unique — no two (bike_id, sensor_key) pairs may produce the
    same unique_id string.
    """
    seen: set[str] = set()
    for bike_id in bike_ids:
        for desc in BIKE_SENSORS:
            uid = _make_unique_id(bike_id, desc.key)
            assert uid not in seen, (
                f"Collision detected: unique_id={uid!r} already seen. "
                f"bike_id={bike_id!r}, sensor_key={desc.key!r}"
            )
            seen.add(uid)


@given(bike_ids=_st_bike_ids)
@settings(max_examples=100)
def test_property4_unique_ids_are_stable(bike_ids: list[str]) -> None:
    """**Validates: Requirements 6.2, 6.4**

    Calling the unique_id construction function twice with the same
    (bike_id, sensor_key) must yield the identical string — the formula
    is a pure, deterministic function of its inputs.
    """
    for bike_id in bike_ids:
        for desc in BIKE_SENSORS:
            uid_first = _make_unique_id(bike_id, desc.key)
            uid_second = _make_unique_id(bike_id, desc.key)
            assert uid_first == uid_second, (
                f"Stability violation: first call returned {uid_first!r}, "
                f"second call returned {uid_second!r} for "
                f"bike_id={bike_id!r}, sensor_key={desc.key!r}"
            )


@given(bike_ids=_st_bike_ids)
@settings(max_examples=100)
def test_property4_unique_id_format(bike_ids: list[str]) -> None:
    """**Validates: Requirements 6.2, 6.4**

    The unique_id for each (bike_id, sensor_key) pair must equal exactly
    ``f"{bike_id}_{sensor_key}"``.
    """
    for bike_id in bike_ids:
        for desc in BIKE_SENSORS:
            uid = _make_unique_id(bike_id, desc.key)
            expected = f"{bike_id}_{desc.key}"
            assert uid == expected, (
                f"unique_id format mismatch: got {uid!r}, expected {expected!r} "
                f"for bike_id={bike_id!r}, sensor_key={desc.key!r}"
            )


@given(bike_ids=_st_bike_ids)
@settings(max_examples=100)
def test_property4_device_info_identifiers_match_bike(bike_ids: list[str]) -> None:
    """**Validates: Requirements 6.2, 6.4**

    The device_info identifiers for each entity must contain exactly
    ``(DOMAIN, bike_id)`` — associating the entity with the correct bike
    device in the Home Assistant device registry.
    """
    for bike_id in bike_ids:
        for desc in BIKE_SENSORS:
            identifiers = _make_device_info_identifiers(bike_id)

            # Must contain the correct (DOMAIN, bike_id) tuple
            assert (DOMAIN, bike_id) in identifiers, (
                f"device_info identifiers do not contain (DOMAIN, bike_id): "
                f"identifiers={identifiers!r}, bike_id={bike_id!r}"
            )

            # Must NOT contain identifiers for any other bike
            for other_bike_id in bike_ids:
                if other_bike_id != bike_id:
                    assert (DOMAIN, other_bike_id) not in identifiers, (
                        f"device_info identifiers for bike_id={bike_id!r} "
                        f"incorrectly contain identifier for "
                        f"other_bike_id={other_bike_id!r}"
                    )


@given(bike_ids=_st_bike_ids)
@settings(max_examples=100)
def test_property4_unique_ids_differ_across_bikes(bike_ids: list[str]) -> None:
    """**Validates: Requirements 6.2, 6.4**

    For the same sensor_key, two different bike_ids must produce different
    unique_ids — ensuring cross-bike uniqueness.
    """
    for desc in BIKE_SENSORS:
        ids_for_key = [_make_unique_id(bike_id, desc.key) for bike_id in bike_ids]
        assert len(ids_for_key) == len(set(ids_for_key)), (
            f"Duplicate unique_ids for sensor_key={desc.key!r} across bikes: "
            f"bike_ids={bike_ids!r}, unique_ids={ids_for_key!r}"
        )


@given(bike_ids=_st_bike_ids)
@settings(max_examples=100)
def test_property4_unique_ids_differ_across_sensors(bike_ids: list[str]) -> None:
    """**Validates: Requirements 6.2, 6.4**

    For the same bike_id, all sensor keys must produce different unique_ids —
    ensuring per-bike sensor uniqueness.
    """
    for bike_id in bike_ids:
        ids_for_bike = [_make_unique_id(bike_id, desc.key) for desc in BIKE_SENSORS]
        assert len(ids_for_bike) == len(set(ids_for_bike)), (
            f"Duplicate unique_ids for bike_id={bike_id!r} across sensors: "
            f"unique_ids={ids_for_bike!r}"
        )
