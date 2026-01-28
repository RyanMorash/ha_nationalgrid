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

# Conversion factor: 1 therm = 1.038 CCF.
THERM_TO_CCF = 1.038


def therms_to_ccf(therms: float) -> float:
    """Convert therms to CCF (hundred cubic feet)."""
    return round(therms * THERM_TO_CCF, 2)
