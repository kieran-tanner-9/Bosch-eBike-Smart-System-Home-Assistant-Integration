"""HACS manifest validation tests.

Validates that hacs.json and manifest.json contain all required fields with
correct types and values.

Validates: Requirements 11.1, 11.2
"""
import json
import re
from pathlib import Path

import pytest

# Resolve paths relative to the repo root (two levels up from this file)
REPO_ROOT = Path(__file__).parent.parent
HACS_JSON_PATH = REPO_ROOT / "hacs.json"
MANIFEST_JSON_PATH = REPO_ROOT / "custom_components" / "bosch_ebike_ha" / "manifest.json"

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def hacs_manifest() -> dict:
    """Load and return the parsed hacs.json."""
    assert HACS_JSON_PATH.exists(), f"hacs.json not found at {HACS_JSON_PATH}"
    with HACS_JSON_PATH.open() as f:
        return json.load(f)


@pytest.fixture(scope="module")
def component_manifest() -> dict:
    """Load and return the parsed manifest.json."""
    assert MANIFEST_JSON_PATH.exists(), f"manifest.json not found at {MANIFEST_JSON_PATH}"
    with MANIFEST_JSON_PATH.open() as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# hacs.json tests
# ---------------------------------------------------------------------------

class TestHacsJson:
    """Tests for hacs.json required fields and values."""

    def test_hacs_json_exists(self):
        """hacs.json must exist at the repository root."""
        assert HACS_JSON_PATH.exists(), f"hacs.json not found at {HACS_JSON_PATH}"

    def test_hacs_json_is_valid_json(self):
        """hacs.json must be valid JSON."""
        with HACS_JSON_PATH.open() as f:
            data = json.load(f)
        assert isinstance(data, dict)

    def test_hacs_name_field_present(self, hacs_manifest):
        """hacs.json must contain a 'name' field."""
        assert "name" in hacs_manifest, "hacs.json is missing required field 'name'"

    def test_hacs_name_is_non_empty_string(self, hacs_manifest):
        """hacs.json 'name' must be a non-empty string."""
        name = hacs_manifest["name"]
        assert isinstance(name, str), f"hacs.json 'name' must be a string, got {type(name)}"
        assert name.strip(), "hacs.json 'name' must not be empty"

    def test_hacs_homeassistant_field_present(self, hacs_manifest):
        """hacs.json must contain a 'homeassistant' field."""
        assert "homeassistant" in hacs_manifest, (
            "hacs.json is missing required field 'homeassistant'"
        )

    def test_hacs_homeassistant_is_string(self, hacs_manifest):
        """hacs.json 'homeassistant' must be a string."""
        ha_version = hacs_manifest["homeassistant"]
        assert isinstance(ha_version, str), (
            f"hacs.json 'homeassistant' must be a string, got {type(ha_version)}"
        )

    def test_hacs_homeassistant_minimum_version(self, hacs_manifest):
        """hacs.json 'homeassistant' must be exactly '2024.1.0' as the minimum version."""
        ha_version = hacs_manifest["homeassistant"]
        assert ha_version == "2024.1.0", (
            f"hacs.json 'homeassistant' must be '2024.1.0', got '{ha_version}'"
        )


# ---------------------------------------------------------------------------
# manifest.json tests
# ---------------------------------------------------------------------------

class TestManifestJson:
    """Tests for manifest.json required fields and values."""

    def test_manifest_json_exists(self):
        """manifest.json must exist in the custom_components directory."""
        assert MANIFEST_JSON_PATH.exists(), (
            f"manifest.json not found at {MANIFEST_JSON_PATH}"
        )

    def test_manifest_json_is_valid_json(self):
        """manifest.json must be valid JSON."""
        with MANIFEST_JSON_PATH.open() as f:
            data = json.load(f)
        assert isinstance(data, dict)

    def test_manifest_domain_present(self, component_manifest):
        """manifest.json must contain a 'domain' field."""
        assert "domain" in component_manifest, (
            "manifest.json is missing required field 'domain'"
        )

    def test_manifest_domain_is_non_empty_string(self, component_manifest):
        """manifest.json 'domain' must be a non-empty string."""
        domain = component_manifest["domain"]
        assert isinstance(domain, str), (
            f"manifest.json 'domain' must be a string, got {type(domain)}"
        )
        assert domain.strip(), "manifest.json 'domain' must not be empty"

    def test_manifest_domain_value(self, component_manifest):
        """manifest.json 'domain' must be 'bosch_ebike_ha'."""
        assert component_manifest["domain"] == "bosch_ebike_ha", (
            f"manifest.json 'domain' must be 'bosch_ebike_ha', got '{component_manifest['domain']}'"
        )

    def test_manifest_name_present(self, component_manifest):
        """manifest.json must contain a 'name' field."""
        assert "name" in component_manifest, (
            "manifest.json is missing required field 'name'"
        )

    def test_manifest_name_is_non_empty_string(self, component_manifest):
        """manifest.json 'name' must be a non-empty string."""
        name = component_manifest["name"]
        assert isinstance(name, str), (
            f"manifest.json 'name' must be a string, got {type(name)}"
        )
        assert name.strip(), "manifest.json 'name' must not be empty"

    def test_manifest_version_present(self, component_manifest):
        """manifest.json must contain a 'version' field."""
        assert "version" in component_manifest, (
            "manifest.json is missing required field 'version'"
        )

    def test_manifest_version_is_string(self, component_manifest):
        """manifest.json 'version' must be a string."""
        version = component_manifest["version"]
        assert isinstance(version, str), (
            f"manifest.json 'version' must be a string, got {type(version)}"
        )

    def test_manifest_version_follows_semver(self, component_manifest):
        """manifest.json 'version' must follow semantic versioning (MAJOR.MINOR.PATCH)."""
        version = component_manifest["version"]
        assert SEMVER_RE.match(version), (
            f"manifest.json 'version' must follow semver (e.g. '1.0.0'), got '{version}'"
        )

    def test_manifest_dependencies_present(self, component_manifest):
        """manifest.json must contain a 'dependencies' field."""
        assert "dependencies" in component_manifest, (
            "manifest.json is missing required field 'dependencies'"
        )

    def test_manifest_dependencies_is_list(self, component_manifest):
        """manifest.json 'dependencies' must be a list."""
        deps = component_manifest["dependencies"]
        assert isinstance(deps, list), (
            f"manifest.json 'dependencies' must be a list, got {type(deps)}"
        )

    def test_manifest_dependencies_contains_application_credentials(self, component_manifest):
        """manifest.json 'dependencies' must include 'application_credentials'."""
        assert "application_credentials" in component_manifest["dependencies"], (
            "manifest.json 'dependencies' must include 'application_credentials'"
        )

    def test_manifest_config_flow_present(self, component_manifest):
        """manifest.json must contain a 'config_flow' field."""
        assert "config_flow" in component_manifest, (
            "manifest.json is missing required field 'config_flow'"
        )

    def test_manifest_config_flow_is_bool(self, component_manifest):
        """manifest.json 'config_flow' must be a boolean."""
        config_flow = component_manifest["config_flow"]
        assert isinstance(config_flow, bool), (
            f"manifest.json 'config_flow' must be a bool, got {type(config_flow)}"
        )

    def test_manifest_config_flow_is_true(self, component_manifest):
        """manifest.json 'config_flow' must be True."""
        assert component_manifest["config_flow"] is True, (
            "manifest.json 'config_flow' must be True"
        )

    def test_manifest_iot_class_present(self, component_manifest):
        """manifest.json must contain an 'iot_class' field."""
        assert "iot_class" in component_manifest, (
            "manifest.json is missing required field 'iot_class'"
        )

    def test_manifest_iot_class_is_string(self, component_manifest):
        """manifest.json 'iot_class' must be a string."""
        iot_class = component_manifest["iot_class"]
        assert isinstance(iot_class, str), (
            f"manifest.json 'iot_class' must be a string, got {type(iot_class)}"
        )

    def test_manifest_iot_class_value(self, component_manifest):
        """manifest.json 'iot_class' must be 'cloud_polling'."""
        assert component_manifest["iot_class"] == "cloud_polling", (
            f"manifest.json 'iot_class' must be 'cloud_polling', got '{component_manifest['iot_class']}'"
        )

    def test_manifest_requirements_present(self, component_manifest):
        """manifest.json must contain a 'requirements' field."""
        assert "requirements" in component_manifest, (
            "manifest.json is missing required field 'requirements'"
        )

    def test_manifest_requirements_is_list(self, component_manifest):
        """manifest.json 'requirements' must be a list."""
        reqs = component_manifest["requirements"]
        assert isinstance(reqs, list), (
            f"manifest.json 'requirements' must be a list, got {type(reqs)}"
        )

    def test_manifest_requirements_contains_aiohttp(self, component_manifest):
        """manifest.json 'requirements' must include an aiohttp dependency."""
        reqs = component_manifest["requirements"]
        aiohttp_reqs = [r for r in reqs if r.startswith("aiohttp")]
        assert aiohttp_reqs, (
            "manifest.json 'requirements' must include an 'aiohttp' dependency"
        )
