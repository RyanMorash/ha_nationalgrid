"""Import AMI energy data into Home Assistant long-term statistics."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import partial
from typing import TYPE_CHECKING

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    async_import_statistics,
    get_last_statistics,
)
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, LOGGER

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import NationalGridDataUpdateCoordinator


async def async_import_all_statistics(
    hass: HomeAssistant,
    coordinator: NationalGridDataUpdateCoordinator,
) -> None:
    """Import AMI hourly and interval read statistics."""
    data = coordinator.data
    if data is None:
        return

    registry = er.async_get(hass)

    for sp, ami_readings in data.ami_usages.items():
        meter_data = data.meters.get(sp)
        if meter_data is None:
            continue
        fuel_type = str(meter_data.meter.get("fuelType", ""))
        is_gas = fuel_type == "Gas"

        # Import hourly AMI stats into the sensor entity's statistics
        await _import_hourly_stats(hass, registry, sp, ami_readings, is_gas=is_gas)

    # Import interval read stats (electric only)
    for sp, reads in data.interval_reads.items():
        await _import_interval_stats(hass, sp, reads)


async def _import_hourly_stats(
    hass: HomeAssistant,
    registry: er.EntityRegistry,
    service_point: str,
    readings: list,
    *,
    is_gas: bool,
) -> None:
    """Import hourly AMI usage statistics into the sensor entity."""
    unique_id = f"{DOMAIN}_{service_point}_ami_latest_reading"
    entry = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
    if entry is None:
        LOGGER.debug(
            "No sensor entity found for unique_id %s, skipping hourly stats",
            unique_id,
        )
        return

    statistic_id = entry  # entity_id is the statistic_id for entity stats
    unit = UnitOfVolume.CUBIC_FEET if is_gas else UnitOfEnergy.KILO_WATT_HOUR

    # Get last imported sum to continue cumulative total
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

    # Sort readings by date and filter to new ones only
    sorted_readings = sorted(readings, key=lambda r: str(r.get("date", "")))
    stats: list[StatisticData] = []
    running_sum = last_sum

    for reading in sorted_readings:
        date_str = str(reading.get("date", ""))
        quantity = float(reading.get("quantity", 0))
        if not date_str:
            continue

        # Parse date string (ISO 8601 format, e.g. "2026-01-22T15:00:00.000Z")
        try:
            dt = datetime.fromisoformat(date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            # Truncate to top of hour for HA statistics
            dt = dt.replace(minute=0, second=0, microsecond=0)
        except ValueError:
            LOGGER.debug("Could not parse AMI date: %s", date_str)
            continue

        if dt.timestamp() <= last_ts:
            continue

        running_sum += quantity
        stats.append(
            StatisticData(
                start=dt,
                state=quantity,
                sum=running_sum,
            )
        )

    if not stats:
        return

    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=f"{service_point} Hourly Usage",
        source="recorder",
        statistic_id=statistic_id,
        unit_of_measurement=unit,
    )

    async_import_statistics(hass, metadata, stats)
    LOGGER.debug(
        "Imported %s hourly stats for %s (sum=%.3f)",
        len(stats),
        statistic_id,
        running_sum,
    )


async def _import_interval_stats(
    hass: HomeAssistant,
    service_point: str,
    reads: list,
) -> None:
    """Import 15-minute interval read statistics for a service point."""
    statistic_id = f"{DOMAIN}:{service_point}_interval_usage"

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

    # Bucket interval reads by hour (HA requires top-of-hour timestamps)
    hourly_buckets: dict[datetime, float] = {}
    for read in reads:
        start_str = str(read.get("startTime", ""))
        value = float(read.get("value", 0))
        if not start_str:
            continue

        try:
            dt = datetime.fromisoformat(start_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
        except ValueError:
            LOGGER.debug("Could not parse interval startTime: %s", start_str)
            continue

        hour_start = dt.replace(minute=0, second=0, microsecond=0)
        hourly_buckets[hour_start] = hourly_buckets.get(hour_start, 0.0) + value

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
        return

    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=f"{service_point} Interval Usage",
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    )

    async_add_external_statistics(hass, metadata, stats)
    LOGGER.debug(
        "Imported %s interval stats for %s (sum=%.3f)",
        len(stats),
        service_point,
        running_sum,
    )
