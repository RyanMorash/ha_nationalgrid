"""
Custom integration to integrate National Grid with Home Assistant.

For more details about this integration, please refer to
https://github.com/ryanmorash/ha_nationalgrid
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.loader import async_get_loaded_integration

from .api import NationalGridApiClient
from .const import DOMAIN, LOGGER
from .coordinator import NationalGridDataUpdateCoordinator
from .data import NationalGridData
from .statistics import async_import_statistics

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import NationalGridConfigEntry

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NationalGridConfigEntry,
) -> bool:
    """Set up this integration using UI."""
    client = NationalGridApiClient(
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
    )

    coordinator = NationalGridDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,
        name=DOMAIN,
        update_interval=timedelta(hours=1),
    )
    coordinator.config_entry = entry

    entry.runtime_data = NationalGridData(
        client=client,
        integration=async_get_loaded_integration(hass, entry.domain),
        coordinator=coordinator,
    )

    try:
        # Fetch initial data
        await coordinator.async_config_entry_first_refresh()

        # Import historical data into long-term statistics
        await async_import_statistics(hass, coordinator)
    except Exception:
        await client.close()
        raise

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: NationalGridConfigEntry,
) -> bool:
    """Handle removal of an entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.client.close()
    return unload_ok


async def async_reload_entry(
    hass: HomeAssistant,
    entry: NationalGridConfigEntry,
) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
