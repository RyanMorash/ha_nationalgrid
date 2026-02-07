"""Custom integration to integrate National Grid with Home Assistant.

For more details about this integration, please refer to
https://github.com/ryanmorash/ha_nationalgrid
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_change

from .const import _LOGGER, DOMAIN
from .coordinator import NationalGridDataUpdateCoordinator
from .statistics import async_import_all_statistics

if TYPE_CHECKING:
    from datetime import datetime

    from homeassistant.core import HomeAssistant, ServiceCall

    from .data import NationalGridConfigEntry

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
]

# Service names
SERVICE_FORCE_REFRESH = "force_full_refresh"

# Service schemas
SERVICE_FORCE_REFRESH_SCHEMA = vol.Schema({
    vol.Optional("entry_id"): cv.string,
    vol.Optional("clear_interval_stats", default=False): cv.boolean,
})


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NationalGridConfigEntry,
) -> bool:
    """Set up this integration using UI."""
    coordinator = NationalGridDataUpdateCoordinator(
        hass=hass,
        logger=_LOGGER,
        name=DOMAIN,
        update_interval=None,  # We use time-based scheduling instead
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

    # Schedule updates at the 18th minute of every hour
    # - At 00:18 (midnight): Full refresh + clear interval stats to sync with new Hourly data
    # - All other hours: Interval-only refresh (just interval reads)
    def _scheduled_refresh(now: datetime) -> None:
        """Refresh data at scheduled time."""
        if now.hour == 0:
            _LOGGER.info("Midnight refresh triggered at %s - fetching Hourly + clearing/reimporting Interval data", now)
            hass.add_job(coordinator.async_refresh_full_with_clear)
        else:
            _LOGGER.info("Hourly refresh triggered at %s - fetching Interval data only", now)
            hass.add_job(coordinator.async_refresh_interval_only)

    cancel_scheduled = async_track_time_change(
        hass,
        _scheduled_refresh,
        minute=18,
        second=0,
    )
    entry.async_on_unload(cancel_scheduled)

    # Register services (only once, when first entry is set up)
    await _async_setup_services(hass)

    return True


async def _async_setup_services(hass: HomeAssistant) -> None:
    """Set up National Grid services."""
    
    async def handle_force_refresh(call: ServiceCall) -> None:
        """Handle the force_full_refresh service call."""
        entry_id = call.data.get("entry_id")
        # Note: clear_interval_stats is now effectively always True since interval
        # stats are always cleared and reimported. Kept for backwards compatibility.
        clear_interval = call.data.get("clear_interval_stats", False)
        
        # Get all National Grid config entries
        entries = hass.config_entries.async_entries(DOMAIN)
        
        if not entries:
            _LOGGER.warning("No National Grid integrations configured")
            return
        
        # Filter to specific entry if provided
        if entry_id:
            entries = [e for e in entries if e.entry_id == entry_id]
            if not entries:
                _LOGGER.warning("No National Grid integration found with entry_id: %s", entry_id)
                return
        
        for entry in entries:
            coordinator: NationalGridDataUpdateCoordinator = entry.runtime_data
            _LOGGER.info(
                "Force full refresh triggered for account: %s",
                entry.title,
            )
            
            # Reset to first refresh mode to get full historical data
            coordinator.reset_to_first_refresh()
            
            try:
                # Trigger an immediate refresh
                await coordinator.async_refresh()
                
                # Import statistics after refresh
                await async_import_all_statistics(hass, coordinator)
            finally:
                pass  # No flags to reset - first_refresh auto-resets after refresh
            
            _LOGGER.info(
                "Force full refresh completed for account: %s",
                entry.title,
            )
    
    # Only register if not already registered
    if not hass.services.has_service(DOMAIN, SERVICE_FORCE_REFRESH):
        hass.services.async_register(
            DOMAIN,
            SERVICE_FORCE_REFRESH,
            handle_force_refresh,
            schema=SERVICE_FORCE_REFRESH_SCHEMA,
        )


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
