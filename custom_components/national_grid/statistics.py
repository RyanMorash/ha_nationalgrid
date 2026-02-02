"""Import AMI energy data into Home Assistant long-term statistics.

Creates external statistic series for energy usage:

For electric meters:
- On first setup: Imports all historical data from energy_usages (up to 465 days)
- On updates: 
  * AMI hourly usage for last ~48 hours (near real-time)
  * Interval reads for validated data older than 48 hours
  
For gas meters:
- AMI hourly usage statistics only (no interval data available)

Time window strategy:
- AMI data: Only import readings from last 48 hours to avoid overlap
- Interval data: Only import after initial setup, provides validated historical data
- Historical: On first setup, import all available energy_usages data

This prevents double-counting in the Energy dashboard by ensuring AMI and interval
data don't overlap.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import partial
from typing import TYPE_CHECKING

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.const import UnitOfEnergy

from .const import _LOGGER, DOMAIN, therms_to_ccf

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import NationalGridDataUpdateCoordinator


async def async_import_all_statistics(
    hass: HomeAssistant,
    coordinator: NationalGridDataUpdateCoordinator,
) -> None:
    """Import energy usage statistics based on available data.

    Strategy:
    - First refresh: Import AMI data without 48h cutoff (get all historical)
    - Subsequent refreshes:
      * AMI hourly data for last 48 hours only (near real-time)
      * Interval reads for validated recent data (electric only)
    
    This ensures:
    1. Complete historical data on initial setup
    2. No double-counting between AMI and interval data
    3. Clean statistics with proper time windows
    """
    data = coordinator.data
    if data is None:
        return

    is_first_refresh = data.is_first_refresh

    # Import AMI data for all meters
    for sp, ami_readings in data.ami_usages.items():
        meter_data = data.meters.get(sp)
        if meter_data is None:
            continue
        fuel_type = str(meter_data.meter.get("fuelType", ""))
        is_gas = fuel_type == "Gas"

        # Import hourly AMI stats
        # First refresh: import all data (no cutoff)
        # Subsequent: only last 48 hours (with cutoff)
        # For electric: create separate stats for consumption and return
        if is_gas:
            await _import_hourly_stats(
                hass, 
                sp, 
                ami_readings, 
                is_gas=True,
                is_first_refresh=is_first_refresh
            )
        else:
            # Electric: separate consumption (positive) and return (negative)
            await _import_hourly_stats_electric(
                hass,
                sp,
                ami_readings,
                is_first_refresh=is_first_refresh
            )

    # Import interval read stats (electric only)
    # Separate consumption and return like we do for AMI hourly
    for sp, reads in data.interval_reads.items():
        await _import_interval_stats_electric(hass, sp, reads, is_first_refresh=is_first_refresh)


async def _import_hourly_stats_electric(
    hass: HomeAssistant,
    service_point: str,
    readings: list,
    *,
    is_first_refresh: bool = False,
) -> None:
    """Import hourly AMI usage statistics for electric meters.
    
    Creates two separate statistics:
    - Consumption (positive values): Energy used from grid
    - Return (negative values): Energy returned to grid (solar)
    
    This matches OPower behavior and allows proper display in Energy Dashboard.
    
    Args:
        hass: Home Assistant instance
        service_point: Service point identifier
        readings: List of AMI readings
        is_first_refresh: Whether this is the first data import
    """
    # Import consumption (positive values)
    await _import_hourly_stats(
        hass,
        service_point,
        readings,
        is_gas=False,
        is_first_refresh=is_first_refresh,
        consumption_only=True,
    )
    
    # Import return (negative values) if any exist
    has_negative = any(float(r.get("quantity", 0)) < 0 for r in readings)
    if has_negative:
        await _import_hourly_stats(
            hass,
            service_point,
            readings,
            is_gas=False,
            is_first_refresh=is_first_refresh,
            return_only=True,
        )


async def _import_hourly_stats(
    hass: HomeAssistant,
    service_point: str,
    readings: list,
    *,
    is_gas: bool,
    is_first_refresh: bool = False,
    consumption_only: bool = False,
    return_only: bool = False,
) -> None:
    """Import hourly AMI usage statistics with optional 48-hour time window.

    On first refresh: Imports all available AMI data to establish baseline
    On subsequent refreshes: Only imports readings from the last 48 hours to 
    prevent overlap with interval data.
    
    For electric meters, can separate consumption (positive) and return (negative).
    
    Args:
        hass: Home Assistant instance
        service_point: Service point identifier
        readings: List of AMI readings
        is_gas: Whether this is a gas meter
        is_first_refresh: Whether this is the first data import
        consumption_only: Only import positive values (consumption)
        return_only: Only import negative values (return to grid)
    """
    # Determine statistic ID based on type
    if is_gas:
        fuel = "gas"
        statistic_id = f"{DOMAIN}:{service_point}_{fuel}_hourly_usage"
        unit = "CCF"
    elif return_only:
        fuel = "electric"
        statistic_id = f"{DOMAIN}:{service_point}_{fuel}_return_hourly_usage"
        unit = UnitOfEnergy.KILO_WATT_HOUR
    else:
        fuel = "electric"
        statistic_id = f"{DOMAIN}:{service_point}_{fuel}_hourly_usage"
        unit = UnitOfEnergy.KILO_WATT_HOUR

    # Calculate cutoff: only keep readings from last 48 hours (except on first refresh)
    cutoff_ts = 0.0
    if not is_first_refresh:
        now = datetime.now(tz=UTC)
        cutoff_time = now - timedelta(hours=48)
        cutoff_ts = cutoff_time.timestamp()

    # Get last imported sum to continue cumulative total.
    last = await get_instance(hass).async_add_executor_job(
        partial(
            get_last_statistics,
            hass,
            1,
            statistic_id,
            convert_units=True,
            types={"sum"},
        )
    )
    last_sum = 0.0
    last_ts = 0.0
    if last.get(statistic_id):
        row = last[statistic_id][0]
        last_sum = row.get("sum") or 0.0
        last_ts = row.get("start") or 0.0

    # Sort readings by date and filter based on cutoff
    sorted_readings = sorted(readings, key=lambda r: str(r.get("date", "")))
    stats: list[StatisticData] = []
    running_sum = last_sum
    skipped_old = 0
    skipped_filtered = 0

    for reading in sorted_readings:
        date_str = str(reading.get("date", ""))
        quantity = float(reading.get("quantity", 0))
        if not date_str:
            continue

        # Filter based on consumption_only or return_only
        if consumption_only and quantity < 0:
            skipped_filtered += 1
            continue
        if return_only and quantity >= 0:
            skipped_filtered += 1
            continue
        
        # For return values, use absolute value for sum
        if return_only:
            quantity = abs(quantity)

        # Parse date string (ISO 8601 format, e.g. "2026-01-22T15:00:00.000Z").
        try:
            dt = datetime.fromisoformat(date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            # Truncate to top of hour for HA statistics.
            dt = dt.replace(minute=0, second=0, microsecond=0)
        except ValueError:
            _LOGGER.debug("Could not parse AMI date: %s", date_str)
            continue

        # Skip if already imported
        if dt.timestamp() <= last_ts:
            continue

        # Apply 48-hour cutoff only on incremental updates (not first refresh)
        if not is_first_refresh and dt.timestamp() < cutoff_ts:
            skipped_old += 1
            continue

        value = therms_to_ccf(quantity) if is_gas else quantity
        running_sum += value
        stats.append(
            StatisticData(
                start=dt,
                state=value,
                sum=running_sum,
            )
        )

    if skipped_old > 0:
        _LOGGER.debug(
            "Skipped %s AMI readings older than 48 hours for %s (prevents overlap)",
            skipped_old,
            statistic_id,
        )
    
    if skipped_filtered > 0:
        filter_type = "consumption" if consumption_only else "return"
        _LOGGER.debug(
            "Filtered %s readings for %s statistic (keeping %s only)",
            skipped_filtered,
            filter_type,
            filter_type,
        )

    if not stats:
        _LOGGER.debug("No new AMI hourly stats to import for %s", statistic_id)
        return

    # Set appropriate name for the statistic
    if return_only:
        stat_name = f"{service_point} Electric Return Hourly Usage"
    elif is_gas:
        stat_name = f"{service_point} Gas Hourly Usage"
    else:
        stat_name = f"{service_point} Electric Hourly Usage"

    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=stat_name,
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_of_measurement=unit,
    )

    async_add_external_statistics(hass, metadata, stats)
    
    if is_first_refresh:
        _LOGGER.info(
            "Imported %s hourly AMI stats for %s (sum=%.3f, first refresh - all data)",
            len(stats),
            statistic_id,
            running_sum,
        )
    else:
        _LOGGER.info(
            "Imported %s hourly AMI stats for %s (sum=%.3f, window=last 48h)",
            len(stats),
            statistic_id,
            running_sum,
        )


async def _import_interval_stats_electric(
    hass: HomeAssistant,
    service_point: str,
    reads: list,
    *,
    is_first_refresh: bool = False,
) -> None:
    """Import interval read statistics for electric meters with consumption/return separation.
    
    Creates two separate statistics:
    - Consumption (positive values): Energy used from grid
    - Return (negative values): Energy returned to grid (solar)
    
    This matches the behavior of AMI hourly stats and allows proper display in Energy Dashboard.
    
    Args:
        hass: Home Assistant instance
        service_point: Service point identifier
        reads: List of interval reads
        is_first_refresh: Whether this is the first data import
    """
    # Import consumption (positive values)
    await _import_interval_stats(
        hass,
        service_point,
        reads,
        is_first_refresh=is_first_refresh,
        consumption_only=True,
    )
    
    # Import return (negative values) if any exist
    has_negative = any(float(r.get("value", 0)) < 0 for r in reads)
    if has_negative:
        await _import_interval_stats(
            hass,
            service_point,
            reads,
            is_first_refresh=is_first_refresh,
            return_only=True,
        )


async def _import_interval_stats(
    hass: HomeAssistant,
    service_point: str,
    reads: list,
    *,
    is_first_refresh: bool = False,
    consumption_only: bool = False,
    return_only: bool = False,
) -> None:
    """Import 15-minute interval read statistics for electric meters.

    Interval reads provide validated usage data at 15-minute granularity.
    They are aggregated into hourly buckets for Home Assistant statistics.
    
    This data represents validated historical usage and should not overlap
    with AMI hourly data (which only covers last 48 hours on incremental updates).
    
    Args:
        hass: Home Assistant instance
        service_point: Service point identifier  
        reads: List of interval reads
        is_first_refresh: Whether this is the first data import
        consumption_only: Only import positive values (consumption)
        return_only: Only import negative values (return to grid)
    """
    # Determine statistic ID based on type
    if return_only:
        statistic_id = f"{DOMAIN}:{service_point}_electric_interval_return_usage"
        stat_name = f"{service_point} Electric Interval Return Usage"
    else:
        statistic_id = f"{DOMAIN}:{service_point}_electric_interval_usage"
        stat_name = f"{service_point} Electric Interval Usage"

    last = await get_instance(hass).async_add_executor_job(
        partial(
            get_last_statistics,
            hass,
            1,
            statistic_id,
            convert_units=True,
            types={"sum"},
        )
    )
    last_sum = 0.0
    last_ts = 0.0
    if last.get(statistic_id):
        row = last[statistic_id][0]
        last_sum = row.get("sum") or 0.0
        last_ts = row.get("start") or 0.0

    # Bucket interval reads by hour (HA requires top-of-hour timestamps).
    # Filter by consumption_only or return_only during bucketing.
    hourly_buckets: dict[datetime, float] = {}
    skipped_filtered = 0
    
    for read in reads:
        start_str = str(read.get("startTime", ""))
        value = float(read.get("value", 0))
        if not start_str:
            continue

        # Filter based on consumption_only or return_only
        if consumption_only and value < 0:
            skipped_filtered += 1
            continue
        if return_only and value >= 0:
            skipped_filtered += 1
            continue
        
        # For return values, use absolute value for sum
        if return_only:
            value = abs(value)

        try:
            dt = datetime.fromisoformat(start_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
        except ValueError:
            _LOGGER.debug("Could not parse interval startTime: %s", start_str)
            continue

        hour_start = dt.replace(minute=0, second=0, microsecond=0)
        hourly_buckets[hour_start] = hourly_buckets.get(hour_start, 0.0) + value

    if skipped_filtered > 0:
        filter_type = "consumption" if consumption_only else "return"
        _LOGGER.debug(
            "Filtered %s interval readings for %s statistic (keeping %s only)",
            skipped_filtered,
            filter_type,
            filter_type,
        )

    stats: list[StatisticData] = []
    running_sum = last_sum

    for hour_start in sorted(hourly_buckets):
        if hour_start.timestamp() <= last_ts:
            continue

        hour_total = hourly_buckets[hour_start]
        running_sum += hour_total
        stats.append(
            StatisticData(
                start=hour_start,
                state=hour_total,
                sum=running_sum,
            )
        )

    if not stats:
        _LOGGER.debug("No new interval stats to import for %s", statistic_id)
        return

    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=stat_name,
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    )

    async_add_external_statistics(hass, metadata, stats)
    
    if return_only:
        _LOGGER.info(
            "Imported %s interval return stats for %s (sum=%.3f)",
            len(stats),
            service_point,
            running_sum,
        )
    else:
        _LOGGER.info(
            "Imported %s interval stats for %s (sum=%.3f)",
            len(stats),
            service_point,
            running_sum,
        )
