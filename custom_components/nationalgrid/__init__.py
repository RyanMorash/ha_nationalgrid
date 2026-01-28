"""
Custom integration to integrate National Grid with Home Assistant.

For more details about this integration, please refer to
https://github.com/ryanmorash/ha_nationalgrid
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.components.recorder.statistics import clear_statistics
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform

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
        client=client,
    )
    coordinator.config_entry = entry

    entry.runtime_data = NationalGridData(
        client=client,
        coordinator=coordinator,
    )

    try:
        # Fetch initial data
        await coordinator.async_config_entry_first_refresh()

        # Import historical data into long-term statistics
        await async_import_statistics(hass, coordinator)

        # Re-import statistics after each successful coordinator update
        async def _on_coordinator_update() -> None:
            if coordinator.data is not None:
                await async_import_statistics(hass, coordinator)

        entry.async_on_unload(coordinator.async_add_listener(_on_coordinator_update))

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    except Exception:
        await client.close()
        raise

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: NationalGridConfigEntry,
) -> bool:
    """Handle removal of an entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    await entry.runtime_data.client.close()
    return unload_ok


async def async_remove_entry(
    hass: HomeAssistant,
    entry: NationalGridConfigEntry,
) -> None:
    """Handle removal of a config entry — clean up external statistics."""
    statistic_ids: list[str] = []
    # Build statistic IDs from coordinator data if available
    if entry.runtime_data and entry.runtime_data.coordinator.data:
        for sp in entry.runtime_data.coordinator.data.meters:
            statistic_ids.append(f"{DOMAIN}:{sp}_energy_usage")
            statistic_ids.append(f"{DOMAIN}:{sp}_energy_cost")

    if statistic_ids:
        LOGGER.debug("Clearing statistics: %s", statistic_ids)
        clear_statistics(hass, statistic_ids)


async def async_reload_entry(
    hass: HomeAssistant,
    entry: NationalGridConfigEntry,
) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
