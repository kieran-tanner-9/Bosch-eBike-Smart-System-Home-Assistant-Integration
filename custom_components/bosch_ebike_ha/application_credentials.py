"""Application credentials for Bosch eBike (Smart System) integration."""

from homeassistant.components.application_credentials import AuthorizationServer
from homeassistant.core import HomeAssistant

from .const import BOSCH_AUTH_URL, BOSCH_TOKEN_URL


async def async_get_authorization_server(hass: HomeAssistant) -> AuthorizationServer:
    """Return the Bosch SingleKey ID OAuth2 authorization server."""
    return AuthorizationServer(
        authorize_url=BOSCH_AUTH_URL,
        token_url=BOSCH_TOKEN_URL,
    )
