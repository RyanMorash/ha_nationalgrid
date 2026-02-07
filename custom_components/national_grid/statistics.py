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

# StatisticMeanType was added in HA 2025.11 - use it if available for forward compatibility
try:
    from homeassistant.components.recorder.models import StatisticMeanType
    HAS_MEAN_TYPE = True
except ImportError:
    HAS_MEAN_TYPE = False

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import NationalGridDataUpdateCoordinator


def _get_interval_statistic_ids(service_point: str) -> list[str]:
    """Get the interval statistic IDs for a service point."""
    return [
        f"{DOMAIN}:{service_point}_electric_interval_usage",
        f"{DOMAIN}:{service_point}_electric_interval_return_usage",
    ]


async def async_import_all_statistics(
    hass: HomeAssistant,
    coordinator: NationalGridDataUpdateCoordinator,
) -> None:
    """Import energy usage statistics based on available data.

    Strategy:
    - First refresh (or force refresh): Import ALL hourly data
    - Midnight refresh: Force full hourly import (fills gaps from newly available data)
    - Subsequent refreshes: Only import data newer than last recorded statistic
    - Interval stats: Always cleared and reimported (last 2 days only)
    
    This ensures:
    1. Complete historical data on initial setup
    2. Gap filling when force_full_refresh is used
    3. Midnight refresh captures newly available hourly data
    4. Interval stats always have accurate data (cleared and reimported each time)
    5. No overlap between Hourly and Interval stats
    """
    data = coordinator.data
    if data is None:
        _LOGGER.info("No data available to import statistics")
        return

    # Determine if we should force import all hourly data
    # This happens on: first refresh, force refresh, OR midnight refresh
    is_first_refresh = data.is_first_refresh
    is_midnight_refresh = data.is_midnight_refresh
    force_hourly_import = is_first_refresh or is_midnight_refresh
    
    # Determine mode for logging
    if is_first_refresh:
        mode = "first_refresh"
    elif is_midnight_refresh:
        mode = "midnight_refresh"
    else:
        mode = "incremental"
    
    _LOGGER.info(
        "Importing statistics: %s AMI meters, %s interval meters, mode=%s",
        len(data.ami_usages),
        len(data.interval_reads),
        mode,
    )

    # Import AMI data for all meters
    for sp, ami_readings in data.ami_usages.items():
        meter_data = data.meters.get(sp)
        if meter_data is None:
            continue
        fuel_type = str(meter_data.meter.get("fuelType", ""))
        is_gas = fuel_type == "Gas"

        # Import hourly AMI stats
        # On first/midnight refresh: import all data (fills gaps)
        # On incremental: only import new data
        if is_gas:
            await _import_hourly_stats(
                hass, 
                sp, 
                ami_readings, 
                is_gas=True,
                force_import_all=force_hourly_import,
            )
        else:
            # Electric: separate consumption (positive) and return (negative)
            await _import_hourly_stats_electric(
                hass,
                sp,
                ami_readings,
                force_import_all=force_hourly_import,
            )

    # Import interval read stats (electric only)
    # These fill the gap between the latest Hourly data and now
    # Each import now clears and reimports to ensure accuracy with partial hour data
    for sp, reads in data.interval_reads.items():
        await _import_interval_stats_electric(hass, sp, reads)
    
    _LOGGER.info("Statistics import complete")


async def _import_hourly_stats_electric(
    hass: HomeAssistant,
    service_point: str,
    readings: list,
    *,
    force_import_all: bool = False,
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
        force_import_all: If True, import all data regardless of last_ts (fills gaps)
    """
    # Import consumption (positive values)
    await _import_hourly_stats(
        hass,
        service_point,
        readings,
        is_gas=False,
        consumption_only=True,
        force_import_all=force_import_all,
    )
    
    # Import return (negative values) if any exist
    has_negative = any(float(r.get("quantity", 0)) < 0 for r in readings)
    if has_negative:
        await _import_hourly_stats(
            hass,
            service_point,
            readings,
            is_gas=False,
            return_only=True,
            force_import_all=force_import_all,
        )


async def _import_hourly_stats(
    hass: HomeAssistant,
    service_point: str,
    readings: list,
    *,
    is_gas: bool,
    consumption_only: bool = False,
    return_only: bool = False,
    force_import_all: bool = False,
) -> None:
    """Import hourly AMI usage statistics.

    Imports AMI readings based on mode:
    - Normal mode: Only import readings newer than last recorded timestamp
    - Force mode (force_import_all=True): Import ALL readings, filling gaps
    
    When force_import_all is True, we recalculate the sum from scratch to ensure
    consistency when filling gaps in historical data.
    
    For electric meters, can separate consumption (positive) and return (negative).
    
    Args:
        hass: Home Assistant instance
        service_point: Service point identifier
        readings: List of AMI readings
        is_gas: Whether this is a gas meter
        consumption_only: Only import positive values (consumption)
        return_only: Only import negative values (return to grid)
        force_import_all: If True, import all data regardless of existing stats
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

    # Get last imported sum to continue cumulative total (only if not forcing full import)
    last_sum = 0.0
    last_ts = 0.0
    
    if not force_import_all:
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
        if last.get(statistic_id):
            row = last[statistic_id][0]
            last_sum = row.get("sum") or 0.0
            last_ts = row.get("start") or 0.0
    else:
        _LOGGER.info(
            "Force import mode for %s - will import all %d readings (fills gaps)",
            statistic_id,
            len(readings),
        )

    # Sort readings by date
    sorted_readings = sorted(readings, key=lambda r: str(r.get("date", "")))
    stats: list[StatisticData] = []
    running_sum = last_sum
    skipped_already_imported = 0
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

        # Parse date string from energyusage-cu-uwp-gql API.
        # The API returns timestamps like "2026-01-31T23:00:00.000Z"
        # These are in UTC (the Z suffix is correct).
        try:
            # Remove milliseconds and handle Z suffix
            clean_date = date_str.replace(".000", "")
            if clean_date.endswith("Z"):
                clean_date = clean_date[:-1] + "+00:00"
            dt = datetime.fromisoformat(clean_date)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            # Truncate to top of hour for HA statistics.
            dt = dt.replace(minute=0, second=0, microsecond=0)
        except ValueError:
            _LOGGER.debug("Could not parse AMI date: %s", date_str)
            continue

        # Skip if already imported (prevents duplicates)
        if dt.timestamp() <= last_ts:
            skipped_already_imported += 1
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

    if skipped_already_imported > 0:
        _LOGGER.debug(
            "Skipped %s AMI readings already imported for %s",
            skipped_already_imported,
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
        _LOGGER.info("Hourly %s: no new stats to import for %s", fuel, service_point)
        return

    # Set appropriate name for the statistic
    if return_only:
        stat_name = f"{service_point} Electric Return Hourly Usage"
    elif is_gas:
        stat_name = f"{service_point} Gas Hourly Usage"
    else:
        stat_name = f"{service_point} Electric Hourly Usage"

    # Build metadata with mean_type for HA 2025.11+ compatibility
    if HAS_MEAN_TYPE:
        metadata = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            mean_type=StatisticMeanType.NONE,
            name=stat_name,
            source=DOMAIN,
            statistic_id=statistic_id,
            unit_of_measurement=unit,
        )
    else:
        metadata = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name=stat_name,
            source=DOMAIN,
            statistic_id=statistic_id,
            unit_of_measurement=unit,
        )

    async_add_external_statistics(hass, metadata, stats)
    
    _LOGGER.info(
        "Imported %s hourly AMI stats for %s (sum=%.3f)",
        len(stats),
        statistic_id,
        running_sum,
    )


async def _import_interval_stats_electric(
    hass: HomeAssistant,
    service_point: str,
    reads: list,
) -> None:
    """Import interval read statistics for electric meters with consumption/return separation.
    
    Interval stats only cover the last 2 days (from midnight) - this matches the
    Hourly Usage API's ~2 day delay, ensuring no overlap between the two.
    
    Always clears and reimports to ensure accuracy with partial hour data.
    
    Creates two separate statistics:
    - Consumption (positive values): Energy used from grid
    - Return (negative values): Energy returned to grid (solar)
    
    Args:
        hass: Home Assistant instance
        service_point: Service point identifier
        reads: List of interval reads
    """
    # Import consumption (positive values)
    await _import_interval_stats(
        hass,
        service_point,
        reads,
        consumption_only=True,
    )
    
    # Import return (negative values) if any exist
    has_negative = any(float(r.get("value", 0)) < 0 for r in reads)
    if has_negative:
        await _import_interval_stats(
            hass,
            service_point,
            reads,
            return_only=True,
        )


async def _import_interval_stats(
    hass: HomeAssistant,
    service_point: str,
    reads: list,
    *,
    consumption_only: bool = False,
    return_only: bool = False,
) -> None:
    """Import 15-minute interval read statistics for electric meters.

    Interval reads only cover the last 2 days (from midnight UTC).
    This matches the Hourly Usage API's ~2 day delay, ensuring no overlap.
    
    Always clears and reimports all interval data within the 2-day window
    to ensure accuracy (handles partial hour data being updated).
    
    Args:
        hass: Home Assistant instance
        service_point: Service point identifier  
        reads: List of interval reads
        consumption_only: Only import positive values (consumption)
        return_only: Only import negative values (return to grid)
    """
    # Calculate cutoff: only keep the last 2 calendar days
    # On Feb 3, we want Feb 2 and Feb 3 only (exclude Feb 1 and earlier)
    # Cutoff = yesterday's midnight = midnight_today - 1 day
    now = datetime.now(tz=UTC)
    midnight_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_midnight = midnight_today - timedelta(days=1)  # Yesterday midnight
    cutoff_ts = cutoff_midnight.timestamp()
    
    # Determine statistic ID based on type
    if return_only:
        statistic_id = f"{DOMAIN}:{service_point}_electric_interval_return_usage"
        stat_name = f"{service_point} Electric Interval Return Usage"
        stat_type = "return"
    else:
        statistic_id = f"{DOMAIN}:{service_point}_electric_interval_usage"
        stat_name = f"{service_point} Electric Interval Usage"
        stat_type = "consumption"
    
    _LOGGER.info(
        "Interval %s: cutoff=%s, reimporting all data within window",
        stat_type,
        cutoff_midnight.strftime("%Y-%m-%d %H:%M UTC"),
    )

    # Clear existing interval stats before reimporting
    # This ensures we always have accurate data (handles partial hours being updated)
    recorder = get_instance(hass)
    recorder.async_clear_statistics([statistic_id])
    # Brief pause to let recorder process the clear
    import asyncio
    await asyncio.sleep(0.1)

    # Bucket interval reads by hour (HA requires top-of-hour timestamps).
    # Filter by consumption_only or return_only during bucketing.
    hourly_buckets: dict[datetime, float] = {}
    skipped_filtered = 0
    skipped_too_old = 0
    
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
        
        # Skip if older than cutoff (before yesterday midnight)
        if hour_start.timestamp() < cutoff_ts:
            skipped_too_old += 1
            continue
            
        hourly_buckets[hour_start] = hourly_buckets.get(hour_start, 0.0) + value

    if skipped_filtered > 0:
        filter_type = "consumption" if consumption_only else "return"
        _LOGGER.debug(
            "Filtered %s interval readings for %s statistic (keeping %s only)",
            skipped_filtered,
            filter_type,
            filter_type,
        )
    
    if skipped_too_old > 0:
        _LOGGER.info(
            "Interval %s: skipped %s readings older than cutoff",
            stat_type,
            skipped_too_old,
        )

    stats: list[StatisticData] = []
    running_sum = 0.0  # Always start fresh since we clear before import

    for hour_start in sorted(hourly_buckets):
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
        _LOGGER.info("Interval %s: no data within 2-day window to import", stat_type)
        return

    # Build metadata with mean_type for HA 2025.11+ compatibility
    if HAS_MEAN_TYPE:
        metadata = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            mean_type=StatisticMeanType.NONE,
            name=stat_name,
            source=DOMAIN,
            statistic_id=statistic_id,
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        )
    else:
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
            "Imported %s interval return stats for %s (sum=%.3f, last 2 days only)",
            len(stats),
            service_point,
            running_sum,
        )
    else:
        _LOGGER.info(
            "Imported %s interval stats for %s (sum=%.3f, last 2 days only)",
            len(stats),
            service_point,
            running_sum,
        )
