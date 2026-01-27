"""Statistics import for National Grid historical data."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)

from .const import DOMAIN, LOGGER
from .sensor import THERM_TO_CCF, UNIT_CCF, UNIT_KWH

if TYPE_CHECKING:
    from typing import Any

    from homeassistant.core import HomeAssistant

    from .coordinator import NationalGridDataUpdateCoordinator


def _get_last_stats(hass: HomeAssistant, statistic_id: str) -> dict[str, Any]:
    """Get last statistics for a statistic_id."""
    return get_last_statistics(hass, 1, statistic_id, convert_units=True, types={"sum"})


async def async_import_statistics(
    hass: HomeAssistant,
    coordinator: NationalGridDataUpdateCoordinator,
) -> None:
    """Import historical usage and cost data into long-term statistics."""
    if coordinator.data is None:
        LOGGER.debug("No coordinator data available for statistics import")
        return

    for service_point_number, meter_data in coordinator.data.meters.items():
        account_id = meter_data.account_id
        fuel_type = meter_data.meter.get("fuelType", "")

        # Import energy usage statistics
        await _import_usage_statistics(
            hass=hass,
            coordinator=coordinator,
            service_point_number=service_point_number,
            account_id=account_id,
            fuel_type=fuel_type,
        )

        # Import energy cost statistics
        await _import_cost_statistics(
            hass=hass,
            coordinator=coordinator,
            service_point_number=service_point_number,
            account_id=account_id,
            fuel_type=fuel_type,
        )


async def _import_usage_statistics(
    hass: HomeAssistant,
    coordinator: NationalGridDataUpdateCoordinator,
    service_point_number: str,
    account_id: str,
    fuel_type: str,
) -> None:
    """Import historical usage statistics for a meter."""
    statistic_id = f"{DOMAIN}:{service_point_number}_energy_usage"
    is_gas = fuel_type.upper() == "GAS"
    unit = UNIT_CCF if is_gas else UNIT_KWH

    # Get existing statistics to find last imported timestamp
    last_stats = await hass.async_add_executor_job(_get_last_stats, hass, statistic_id)
    last_imported_sum = 0.0
    last_imported_time: datetime | None = None

    if last_stats.get(statistic_id):
        last_stat = last_stats[statistic_id][0]
        last_imported_sum = last_stat.get("sum", 0.0) or 0.0
        last_imported_time = datetime.fromtimestamp(last_stat["start"], tz=UTC)
        LOGGER.debug(
            "Last imported statistic for %s: sum=%s, time=%s",
            statistic_id,
            last_imported_sum,
            last_imported_time,
        )

    # Get all usage records for this meter
    all_usages = coordinator.get_all_usages(account_id, fuel_type)
    if not all_usages:
        LOGGER.debug("No usage records found for %s", statistic_id)
        return

    # Sort by year-month
    sorted_usages = sorted(all_usages, key=lambda u: u.get("usageYearMonth", 0))

    # Build statistics data
    statistics: list[StatisticData] = []
    running_sum = last_imported_sum

    for usage in sorted_usages:
        year_month = usage.get("usageYearMonth", 0)
        if not year_month:
            continue

        year = year_month // 100
        month = year_month % 100

        # Create timestamp for start of month
        start_time = datetime(year, month, 1, tzinfo=UTC)

        # Skip if already imported
        if last_imported_time and start_time <= last_imported_time:
            continue

        value = usage.get("usage", 0) or 0
        if is_gas:
            # Convert therms to CCF
            value = round(value * THERM_TO_CCF, 2)

        running_sum += value

        statistics.append(
            StatisticData(
                start=start_time,
                state=value,
                sum=running_sum,
            )
        )

    if not statistics:
        LOGGER.debug("No new statistics to import for %s", statistic_id)
        return

    # Create metadata
    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=f"National Grid {fuel_type} Usage",
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_of_measurement=unit,
    )

    LOGGER.info(
        "Importing %s usage statistics for %s (sum: %.2f %s)",
        len(statistics),
        statistic_id,
        running_sum,
        unit,
    )

    async_add_external_statistics(hass, metadata, statistics)


async def _import_cost_statistics(
    hass: HomeAssistant,
    coordinator: NationalGridDataUpdateCoordinator,
    service_point_number: str,
    account_id: str,
    fuel_type: str,
) -> None:
    """Import historical cost statistics for a meter."""
    statistic_id = f"{DOMAIN}:{service_point_number}_energy_cost"

    # Get existing statistics to find last imported timestamp
    last_stats = await hass.async_add_executor_job(_get_last_stats, hass, statistic_id)
    last_imported_sum = 0.0
    last_imported_time: datetime | None = None

    if last_stats.get(statistic_id):
        last_stat = last_stats[statistic_id][0]
        last_imported_sum = last_stat.get("sum", 0.0) or 0.0
        last_imported_time = datetime.fromtimestamp(last_stat["start"], tz=UTC)
        LOGGER.debug(
            "Last imported cost statistic for %s: sum=%s, time=%s",
            statistic_id,
            last_imported_sum,
            last_imported_time,
        )

    # Get all cost records for this meter
    all_costs = coordinator.get_all_costs(account_id, fuel_type)
    if not all_costs:
        LOGGER.debug("No cost records found for %s", statistic_id)
        return

    # Sort by month
    sorted_costs = sorted(all_costs, key=lambda c: c.get("month", 0))

    # Build statistics data
    statistics: list[StatisticData] = []
    running_sum = last_imported_sum

    for cost in sorted_costs:
        month_val = cost.get("month", 0)
        if not month_val:
            continue

        year = month_val // 100
        month = month_val % 100

        # Create timestamp for start of month
        start_time = datetime(year, month, 1, tzinfo=UTC)

        # Skip if already imported
        if last_imported_time and start_time <= last_imported_time:
            continue

        value = cost.get("amount", 0) or 0
        running_sum += value

        statistics.append(
            StatisticData(
                start=start_time,
                state=value,
                sum=running_sum,
            )
        )

    if not statistics:
        LOGGER.debug("No new cost statistics to import for %s", statistic_id)
        return

    # Create metadata
    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=f"National Grid {fuel_type} Cost",
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_of_measurement="$",
    )

    LOGGER.info(
        "Importing %s cost statistics for %s (sum: $%.2f)",
        len(statistics),
        statistic_id,
        running_sum,
    )

    async_add_external_statistics(hass, metadata, statistics)
