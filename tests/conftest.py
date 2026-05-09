"""Pytest configuration and shared fixtures for Bosch eBike integration tests.

Fixtures and helpers will be added here as tests are implemented in later tasks.
"""
import pytest

# Inject minimal Home Assistant stubs so that sensor.py (and other modules that
# import from homeassistant.*) can be imported without a full HA installation.
# This must happen before any test module is collected.
from tests.ha_stubs.inject import inject_ha_stubs

inject_ha_stubs()

# TODO: Add shared fixtures (e.g. mock hass, mock config entry, mock API client)
#       as test modules are implemented in Tasks 2–14.
