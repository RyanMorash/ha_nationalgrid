"""Custom integration to integrate National Grid with Home Assistant.

For more details about this integration, please refer to
https://github.com/ryanmorash/ha_nationalgrid
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform

from .const import _LOGGER, DOMAIN
from .coordinator import NationalGridDataUpdateCoordinator
from .statistics import async_import_all_statistics

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import NationalGridConfigEntry

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NationalGridConfigEntry,
) -> bool:
    """Set up this integration using UI."""
    coordinator = NationalGridDataUpdateCoordinator(
        hass=hass,
        logger=_LOGGER,
        name=DOMAIN,
        update_interval=timedelta(hours=1),
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
    )
    coordinator.config_entry = entry

    entry.runtime_data = coordinator

    await coordinator.async_config_entry_first_refresh()
    await async_import_all_statistics(hass, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Re-import statistics on each coordinator update.
    def _on_update() -> None:
        hass.async_create_task(async_import_all_statistics(hass, coordinator))

    entry.async_on_unload(coordinator.async_add_listener(_on_update))
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: NationalGridConfigEntry,
) -> bool:
    """Handle removal of an entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(
    hass: HomeAssistant,
    entry: NationalGridConfigEntry,
) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
