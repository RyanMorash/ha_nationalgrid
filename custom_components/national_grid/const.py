"""Constants for national_grid."""

from logging import Logger, getLogger

_LOGGER: Logger = getLogger(__package__)

DOMAIN = "national_grid"
ATTRIBUTION = "Data provided by National Grid"

# Config entry data keys.
CONF_SELECTED_ACCOUNTS = "selected_accounts"

# Unit constants.
UNIT_CCF = "CCF"
UNIT_KWH = "kWh"
