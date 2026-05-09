"""Config flow for Bosch eBike (Smart System) integration.

Implements:
- BoschEBikeConfigFlow  — OAuth2 setup flow with unit-system selection step
- BoschEBikeOptionsFlow — Options flow for changing unit system post-setup

Requirements: 1.1–1.7, 13.1, 13.2, 13.5, 13.6, 13.9
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.application_credentials import (
    async_get_application_credentials,
)
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ApiClientError, BoschEBikeApiClient
from .const import CONF_UNIT_SYSTEM, DOMAIN, UNIT_IMPERIAL, UNIT_METRIC

_LOGGER = logging.getLogger(__name__)

# The OAuth2 client ID is the integration domain, matching the application
# credentials component convention.
OAUTH2_CLIENT_ID = DOMAIN


class BoschEBikeConfigFlow(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler,
    domain=DOMAIN,
):
    """Handle the OAuth2 config flow for Bosch eBike (Smart System).

    Flow steps:
    1. async_step_user        — check application credentials exist
    2. (OAuth2 redirect)      — handled by AbstractOAuth2FlowHandler
    3. async_step_unit_system — choose metric / imperial
    4. async_oauth_create_entry — verify token, create config entry
    """

    DOMAIN = DOMAIN
    VERSION = 1

    def __init__(self) -> None:
        """Initialise the config flow."""
        super().__init__()
        # Stores the unit system chosen in async_step_unit_system.
        self._unit_system: str = UNIT_METRIC

    @property
    def logger(self) -> logging.Logger:
        """Return the logger used by AbstractOAuth2FlowHandler."""
        return _LOGGER

    # ------------------------------------------------------------------
    # Step 1: Validate that application credentials have been registered
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entry_oauth2_flow.FlowResult:
        """Check that application credentials exist before starting OAuth2.

        If no credentials are registered the user is redirected to the
        Application Credentials UI with a descriptive message (Req 1.6).
        """
        credentials = await async_get_application_credentials(self.hass)
        domain_credentials = [
            c for c in credentials if c.get("domain") == DOMAIN
        ]

        if not domain_credentials:
            # No credentials registered — send the user to the Application
            # Credentials UI so they can enter their Data Act Portal
            # client_id and client_secret.
            return self.async_abort(reason="missing_credentials")

        # Credentials exist — proceed with the standard OAuth2 redirect.
        return await super().async_step_user(user_input)

    # ------------------------------------------------------------------
    # Step 3: Unit system selection (called after OAuth2 completes)
    # ------------------------------------------------------------------

    async def async_step_unit_system(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entry_oauth2_flow.FlowResult:
        """Present a selector for metric vs imperial units (Req 13.1).

        This step is inserted between the OAuth2 callback and entry creation
        by overriding async_oauth_create_entry to call it first.
        """
        if user_input is not None:
            self._unit_system = user_input[CONF_UNIT_SYSTEM]
            # Proceed to create the config entry.
            return await self.async_oauth_create_entry(
                data=self._oauth_token_data  # type: ignore[attr-defined]
            )

        return self.async_show_form(
            step_id="unit_system",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UNIT_SYSTEM, default=UNIT_METRIC
                    ): vol.In([UNIT_METRIC, UNIT_IMPERIAL]),
                }
            ),
        )

    # ------------------------------------------------------------------
    # Step 4: Create the config entry after OAuth2 + unit selection
    # ------------------------------------------------------------------

    async def async_oauth_create_entry(
        self, data: dict[str, Any]
    ) -> config_entry_oauth2_flow.FlowResult:
        """Verify the token works and create the config entry (Req 1.7, 13.2).

        Called by AbstractOAuth2FlowHandler after the OAuth2 callback.
        We intercept it to:
        1. Route through the unit-system step first (if not yet done).
        2. Verify the token by calling fetch_bikes.
        3. Handle the "application not yet approved" 403 error.
        4. Write unit_system into options.
        """
        # If the unit system step hasn't been completed yet, store the token
        # data and redirect to that step.
        if not hasattr(self, "_oauth_token_data"):
            self._oauth_token_data = data  # type: ignore[attr-defined]
            return await self.async_step_unit_system()

        # Verify the token by fetching the bike list.
        session = async_get_clientsession(self.hass)
        oauth_session = config_entry_oauth2_flow.OAuth2Session(
            self.hass,
            # We pass a temporary config entry-like object; the real entry
            # doesn't exist yet, so we build a minimal token holder.
            _TokenHolder(data),
            self,
        )
        client = BoschEBikeApiClient(session, oauth_session)

        try:
            bikes = await client.fetch_bikes()
        except ApiClientError as err:
            if err.status == 403:
                # Bosch Data Act Portal application not yet approved (Req 1.7).
                _LOGGER.warning(
                    "Bosch Data Act Portal application not yet approved "
                    "(HTTP 403). The user should check their email for an "
                    "approval notification."
                )
                return self.async_abort(reason="application_not_approved")
            _LOGGER.error(
                "API error %s while verifying token during config flow",
                err.status,
            )
            return self.async_abort(reason="api_error")
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error while verifying token")
            return self.async_abort(reason="unknown")

        # Use the first bike's name as the config entry title, or fall back
        # to the domain name.
        title = bikes[0].name if bikes else DOMAIN

        return self.async_create_entry(
            title=title,
            data=data,
            options={CONF_UNIT_SYSTEM: self._unit_system},
        )

    # ------------------------------------------------------------------
    # Re-authentication
    # ------------------------------------------------------------------

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> config_entry_oauth2_flow.FlowResult:
        """Re-run the OAuth2 flow to refresh tokens (Req 1.5).

        Triggered by HA when ConfigEntryAuthFailed is raised.
        """
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entry_oauth2_flow.FlowResult:
        """Show a confirmation form before re-running OAuth2."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        # Re-run the OAuth2 flow from the user step.
        return await self.async_step_user(user_input={})

    # ------------------------------------------------------------------
    # Options flow
    # ------------------------------------------------------------------

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> BoschEBikeOptionsFlow:
        """Return the options flow handler."""
        return BoschEBikeOptionsFlow(config_entry)


# ---------------------------------------------------------------------------
# Options flow
# ---------------------------------------------------------------------------


class BoschEBikeOptionsFlow(OptionsFlow):
    """Options flow for changing the unit system preference (Req 13.5, 13.6).

    Presents a single step that lets the user switch between metric and
    imperial units.  Saving the new value triggers a config entry reload
    (handled by the update_listener registered in async_setup_entry).
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialise the options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entry_oauth2_flow.FlowResult:
        """Show the unit system selector pre-populated with the current value."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(CONF_UNIT_SYSTEM, UNIT_METRIC)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UNIT_SYSTEM, default=current
                    ): vol.In([UNIT_METRIC, UNIT_IMPERIAL]),
                }
            ),
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _TokenHolder:
    """Minimal stand-in for a ConfigEntry used to build an OAuth2Session.

    AbstractOAuth2FlowHandler's OAuth2Session constructor expects an object
    with a ``data`` attribute containing the token dict.  During the config
    flow the real ConfigEntry doesn't exist yet, so we use this shim.
    """

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
