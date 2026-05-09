"""Constants for the Bosch eBike (Smart System) integration."""

DOMAIN = "bosch_ebike_ha"
BASE_URL = "https://portal.bosch-ebike.com/data-act"
BOSCH_AUTH_URL = "https://p9.authz.bosch.com/auth/realms/obc/protocol/openid-connect/auth"
BOSCH_TOKEN_URL = "https://p9.authz.bosch.com/auth/realms/obc/protocol/openid-connect/token"
DEFAULT_POLL_INTERVAL_MINUTES = 30
BATTERY_POLL_INTERVAL_MINUTES = 15
MAX_RETRY_INTERVAL_MINUTES = 60
REQUEST_TIMEOUT_SECONDS = 30
CONF_UNIT_SYSTEM = "unit_system"
UNIT_METRIC = "metric"
UNIT_IMPERIAL = "imperial"
