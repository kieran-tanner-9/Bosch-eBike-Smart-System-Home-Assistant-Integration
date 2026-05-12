"""Inject minimal Home Assistant stubs into sys.modules.

Call ``inject_ha_stubs()`` before importing any module that depends on
``homeassistant.*``.  This avoids the need for a full HA installation in the
test environment.
"""
from __future__ import annotations

import sys
import types
from enum import Enum
from typing import Any


def _make_module(name: str, **attrs: Any) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


def inject_ha_stubs() -> None:
    """Register minimal HA stubs in sys.modules if not already present."""
    if "homeassistant" in sys.modules:
        return  # Already injected or real HA is installed

    # -----------------------------------------------------------------------
    # homeassistant (top-level)
    # -----------------------------------------------------------------------
    ha = _make_module("homeassistant")
    sys.modules["homeassistant"] = ha

    # -----------------------------------------------------------------------
    # homeassistant.const
    # -----------------------------------------------------------------------
    ha_const = _make_module("homeassistant.const", STATE_UNAVAILABLE="unavailable")
    sys.modules["homeassistant.const"] = ha_const

    # -----------------------------------------------------------------------
    # homeassistant.core
    # -----------------------------------------------------------------------
    def callback(func: Any) -> Any:
        """Minimal callback decorator stub — returns the function unchanged."""
        return func

    ha_core = _make_module("homeassistant.core", HomeAssistant=object, callback=callback)
    sys.modules["homeassistant.core"] = ha_core

    # -----------------------------------------------------------------------
    # homeassistant.config_entries
    # -----------------------------------------------------------------------
    class ConfigEntry:
        options: dict = {}

    class OptionsFlow:
        """Minimal OptionsFlow stub."""

        def __init__(self, config_entry: Any = None) -> None:
            self.config_entry = config_entry

        def async_create_entry(self, title: str = "", data: dict | None = None) -> dict:
            return {"type": "create_entry", "title": title, "data": data or {}}

        def async_show_form(
            self,
            step_id: str = "",
            data_schema: Any = None,
            errors: dict | None = None,
        ) -> dict:
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": errors or {},
            }

    ha_ce = _make_module(
        "homeassistant.config_entries",
        ConfigEntry=ConfigEntry,
        OptionsFlow=OptionsFlow,
    )
    sys.modules["homeassistant.config_entries"] = ha_ce

    # -----------------------------------------------------------------------
    # homeassistant.exceptions
    # -----------------------------------------------------------------------
    ha_exc = _make_module(
        "homeassistant.exceptions",
        ConfigEntryAuthFailed=Exception,
    )
    sys.modules["homeassistant.exceptions"] = ha_exc

    # -----------------------------------------------------------------------
    # homeassistant.helpers (parent package — must be registered first)
    # -----------------------------------------------------------------------
    ha_helpers = _make_module("homeassistant.helpers")
    sys.modules["homeassistant.helpers"] = ha_helpers

    # -----------------------------------------------------------------------
    # homeassistant.helpers.aiohttp_client
    # -----------------------------------------------------------------------
    ha_aiohttp = _make_module(
        "homeassistant.helpers.aiohttp_client",
        async_get_clientsession=lambda hass: None,
    )
    sys.modules["homeassistant.helpers.aiohttp_client"] = ha_aiohttp
    ha_helpers.aiohttp_client = ha_aiohttp  # type: ignore[attr-defined]

    # -----------------------------------------------------------------------
    # homeassistant.helpers.config_entry_oauth2_flow
    # -----------------------------------------------------------------------
    class OAuth2Session:
        """Minimal OAuth2Session stub."""

        def __init__(self, hass: Any, entry: Any, implementation: Any = None) -> None:
            self.hass = hass
            self.entry = entry
            self.token: dict = {"access_token": "stub_token"}

        async def async_ensure_token_valid(self, force_refresh: bool = False) -> None:
            pass

    ha_oauth2_helpers = _make_module(
        "homeassistant.helpers.config_entry_oauth2_flow",
        OAuth2Session=OAuth2Session,
    )
    sys.modules["homeassistant.helpers.config_entry_oauth2_flow"] = ha_oauth2_helpers
    ha_helpers.config_entry_oauth2_flow = ha_oauth2_helpers  # type: ignore[attr-defined]

    # -----------------------------------------------------------------------
    # homeassistant.helpers.device_registry
    # -----------------------------------------------------------------------
    class DeviceInfo(dict):
        """Minimal DeviceInfo stub — behaves like a dict."""

        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)

    class _DeviceRegistryStub:
        """Minimal device registry stub."""

        def __init__(self) -> None:
            self._devices: dict = {}

        def async_get_or_create(self, **kwargs: Any) -> Any:
            key = str(kwargs.get("identifiers"))
            if key not in self._devices:
                self._devices[key] = kwargs
            return self._devices[key]

    _device_registry_instance = _DeviceRegistryStub()

    def async_get(hass: Any) -> _DeviceRegistryStub:
        return _device_registry_instance

    ha_dr = _make_module(
        "homeassistant.helpers.device_registry",
        DeviceInfo=DeviceInfo,
        async_get=async_get,
    )
    sys.modules["homeassistant.helpers.device_registry"] = ha_dr
    ha_helpers.device_registry = ha_dr  # type: ignore[attr-defined]

    # -----------------------------------------------------------------------
    # homeassistant.helpers.entity_platform
    # -----------------------------------------------------------------------
    ha_ep = _make_module(
        "homeassistant.helpers.entity_platform",
        AddEntitiesCallback=Any,
    )
    sys.modules["homeassistant.helpers.entity_platform"] = ha_ep
    ha_helpers.entity_platform = ha_ep  # type: ignore[attr-defined]

    # -----------------------------------------------------------------------
    # homeassistant.helpers.update_coordinator
    # -----------------------------------------------------------------------
    class CoordinatorEntity:
        """Minimal CoordinatorEntity stub that supports generic subscript."""

        def __class_getitem__(cls, item: Any) -> Any:
            return cls

        def __init__(self, coordinator: Any) -> None:
            self.coordinator = coordinator

        @property
        def unique_id(self) -> str | None:
            return getattr(self, "_attr_unique_id", None)

        @property
        def device_info(self) -> Any:
            return getattr(self, "_attr_device_info", None)

        def _handle_coordinator_update(self) -> None:
            """Default no-op coordinator update handler."""

    class DataUpdateCoordinator:
        """Minimal DataUpdateCoordinator stub that supports generic subscript."""

        def __class_getitem__(cls, item: Any) -> Any:
            return cls

        def __init__(
            self,
            hass: Any = None,
            logger: Any = None,
            *,
            name: str = "",
            config_entry: Any = None,
            update_interval: Any = None,
            **kwargs: Any,
        ) -> None:
            self.hass = hass
            self.logger = logger
            self.name = name
            self.config_entry = config_entry
            self.update_interval = update_interval
            self.data: Any = None
            self.last_update_success: bool = True

        async def _async_update_data(self) -> Any:
            """Override in subclasses."""
            return None

        async def _async_refresh(self) -> None:
            """Override in subclasses to add back-off logic."""
            try:
                self.data = await self._async_update_data()
                self.last_update_success = True
            except Exception:
                self.last_update_success = False
                raise

    ha_uc = _make_module(
        "homeassistant.helpers.update_coordinator",
        CoordinatorEntity=CoordinatorEntity,
        DataUpdateCoordinator=DataUpdateCoordinator,
        UpdateFailed=Exception,
    )
    sys.modules["homeassistant.helpers.update_coordinator"] = ha_uc
    ha_helpers.update_coordinator = ha_uc  # type: ignore[attr-defined]

    # -----------------------------------------------------------------------
    # homeassistant.helpers.entity
    # -----------------------------------------------------------------------
    ha_entity = _make_module("homeassistant.helpers.entity", Entity=object)
    sys.modules["homeassistant.helpers.entity"] = ha_entity
    ha_helpers.entity = ha_entity  # type: ignore[attr-defined]

    # -----------------------------------------------------------------------
    # homeassistant.components (parent package — must be registered first)
    # -----------------------------------------------------------------------
    ha_components = _make_module("homeassistant.components")
    sys.modules["homeassistant.components"] = ha_components

    # -----------------------------------------------------------------------
    # homeassistant.components.sensor
    # -----------------------------------------------------------------------
    class SensorDeviceClass(str, Enum):
        BATTERY = "battery"
        DISTANCE = "distance"
        DURATION = "duration"
        ENERGY = "energy"
        POWER = "power"
        SPEED = "speed"
        TIMESTAMP = "timestamp"

    class SensorStateClass(str, Enum):
        MEASUREMENT = "measurement"
        TOTAL = "total"
        TOTAL_INCREASING = "total_increasing"

    from dataclasses import dataclass as _dataclass

    @_dataclass(frozen=True)
    class SensorEntityDescription:
        """Minimal SensorEntityDescription stub (mirrors HA's frozen dataclass)."""

        key: str = ""
        name: str | None = None
        translation_key: str | None = None
        device_class: Any = None
        state_class: Any = None
        native_unit_of_measurement: str | None = None

    class SensorEntity:
        """Minimal SensorEntity stub."""

        entity_description: Any = None
        _attr_has_entity_name: bool = False

        @property
        def native_value(self) -> Any:
            return None

        @property
        def native_unit_of_measurement(self) -> str | None:
            return None

        @property
        def extra_state_attributes(self) -> dict:
            return {}

    ha_sensor = _make_module(
        "homeassistant.components.sensor",
        SensorDeviceClass=SensorDeviceClass,
        SensorStateClass=SensorStateClass,
        SensorEntityDescription=SensorEntityDescription,
        SensorEntity=SensorEntity,
    )
    sys.modules["homeassistant.components.sensor"] = ha_sensor
    ha_components.sensor = ha_sensor  # type: ignore[attr-defined]

    # -----------------------------------------------------------------------
    # homeassistant.components.binary_sensor
    # -----------------------------------------------------------------------
    class BinarySensorDeviceClass(str, Enum):
        TAMPER = "tamper"
        SAFETY = "safety"
        MOTION = "motion"
        DOOR = "door"

    class BinarySensorEntity:
        """Minimal BinarySensorEntity stub."""

        _attr_device_class: Any = None
        _attr_has_entity_name: bool = False

        @property
        def is_on(self) -> bool | None:
            return None

        @property
        def extra_state_attributes(self) -> dict:
            return {}

        def _handle_coordinator_update(self) -> None:
            pass

    ha_bs = _make_module(
        "homeassistant.components.binary_sensor",
        BinarySensorDeviceClass=BinarySensorDeviceClass,
        BinarySensorEntity=BinarySensorEntity,
    )
    sys.modules["homeassistant.components.binary_sensor"] = ha_bs
    ha_components.binary_sensor = ha_bs  # type: ignore[attr-defined]

    # -----------------------------------------------------------------------
    # homeassistant.components.device_tracker
    # -----------------------------------------------------------------------
    class SourceType(str, Enum):
        GPS = "gps"
        ROUTER = "router"
        BLUETOOTH = "bluetooth"
        BLUETOOTH_LE = "bluetooth_le"

    class TrackerEntity:
        """Minimal TrackerEntity stub."""

        _attr_has_entity_name: bool = False
        _attr_name: str | None = None

        @property
        def source_type(self) -> "SourceType":
            return SourceType.GPS

        @property
        def latitude(self) -> float | None:
            return None

        @property
        def longitude(self) -> float | None:
            return None

        @property
        def location_accuracy(self) -> int:
            return 0

        @property
        def state(self) -> str:
            return "not_home"

        @property
        def extra_state_attributes(self) -> dict:
            return {}

        def _handle_coordinator_update(self) -> None:
            pass

    ha_dt = _make_module(
        "homeassistant.components.device_tracker",
        SourceType=SourceType,
        TrackerEntity=TrackerEntity,
    )
    sys.modules["homeassistant.components.device_tracker"] = ha_dt
    ha_components.device_tracker = ha_dt  # type: ignore[attr-defined]

    # -----------------------------------------------------------------------
    # homeassistant.components.application_credentials
    # -----------------------------------------------------------------------
    class AuthorizationServer:
        """Minimal AuthorizationServer stub."""

        def __init__(self, authorize_url: str, token_url: str) -> None:
            self.authorize_url = authorize_url
            self.token_url = token_url

    async def async_get_application_credentials(hass: Any) -> list:
        return []

    ha_app_creds = _make_module(
        "homeassistant.components.application_credentials",
        AuthorizationServer=AuthorizationServer,
        async_get_application_credentials=async_get_application_credentials,
    )
    sys.modules["homeassistant.components.application_credentials"] = ha_app_creds
    ha_components.application_credentials = ha_app_creds  # type: ignore[attr-defined]

    # -----------------------------------------------------------------------
    # homeassistant.helpers.config_entry_oauth2_flow (top-level helper)
    # -----------------------------------------------------------------------
    class AbstractOAuth2FlowHandler:
        """Minimal AbstractOAuth2FlowHandler stub."""

        DOMAIN: str = ""
        VERSION: int = 1

        def __init_subclass__(cls, domain: str = "", **kwargs: Any) -> None:
            super().__init_subclass__(**kwargs)
            if domain:
                cls.DOMAIN = domain

        def __init__(self) -> None:
            pass

        @property
        def logger(self):
            import logging
            return logging.getLogger(__name__)

        def async_abort(self, reason: str, description_placeholders: dict | None = None) -> dict:
            """Return an abort result dict."""
            return {"type": "abort", "reason": reason}

        def async_show_form(
            self,
            step_id: str = "",
            data_schema: Any = None,
            errors: dict | None = None,
            description_placeholders: dict | None = None,
        ) -> dict:
            """Return a form result dict."""
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": errors or {},
            }

        def async_create_entry(
            self,
            title: str = "",
            data: dict | None = None,
            options: dict | None = None,
        ) -> dict:
            """Return a create_entry result dict."""
            return {
                "type": "create_entry",
                "title": title,
                "data": data or {},
                "options": options or {},
            }

        async def async_step_user(self, user_input: Any = None) -> dict:
            """Default user step — subclasses override this."""
            return self.async_show_form(step_id="user")

    ha_oauth2_flow = _make_module(
        "homeassistant.helpers.config_entry_oauth2_flow",
        AbstractOAuth2FlowHandler=AbstractOAuth2FlowHandler,
        OAuth2Session=OAuth2Session,
        FlowResult=dict,
    )
    # Already registered above; update it with the extra class
    existing = sys.modules.get("homeassistant.helpers.config_entry_oauth2_flow")
    if existing is not None:
        existing.AbstractOAuth2FlowHandler = AbstractOAuth2FlowHandler  # type: ignore[attr-defined]
        existing.FlowResult = dict  # type: ignore[attr-defined]
