"""Tests for the National Grid statistics module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.national_grid.const import therms_to_ccf
from custom_components.national_grid.coordinator import (
    MeterData,
    NationalGridCoordinatorData,
)
from custom_components.national_grid.statistics import async_import_all_statistics


def _make_coordinator_data(
    *,
    ami_usages: dict | None = None,
    interval_reads: dict | None = None,
    meters: dict | None = None,
) -> NationalGridCoordinatorData:
    """Build mock coordinator data."""
    return NationalGridCoordinatorData(
        accounts={"acct1": {"billingAccountId": "acct1"}},
        meters=meters or {},
        usages={},
        costs={},
        ami_usages=ami_usages or {},
        interval_reads=interval_reads or {},
    )


def _make_meter_data(fuel_type: str = "Electric") -> MeterData:
    return MeterData(
        account_id="acct1",
        meter={"fuelType": fuel_type, "servicePointNumber": "SP1"},
        billing_account={"billingAccountId": "acct1"},
    )


async def test_import_all_statistics_no_data(hass) -> None:
    """Test no error when coordinator data is None."""
    coordinator = MagicMock()
    coordinator.data = None
    await async_import_all_statistics(hass, coordinator)


@patch("custom_components.national_grid.statistics.async_add_external_statistics")
@patch("custom_components.national_grid.statistics.get_instance")
async def test_import_hourly_stats(mock_get_instance, mock_add_stats, hass) -> None:
    """Test hourly stats import for electric meter."""
    mock_get_instance.return_value.async_add_executor_job = AsyncMock(return_value={})

    readings = [
        {"date": "2025-01-15T10:00:00.000Z", "quantity": 5.0},
        {"date": "2025-01-15T11:00:00.000Z", "quantity": 3.0},
    ]
    coordinator = MagicMock()
    coordinator.data = _make_coordinator_data(
        ami_usages={"SP1": readings},
        meters={"SP1": _make_meter_data("Electric")},
    )

    await async_import_all_statistics(hass, coordinator)
    assert mock_add_stats.called
    metadata = mock_add_stats.call_args[0][1]
    stats = mock_add_stats.call_args[0][2]
    assert metadata["statistic_id"] == "national_grid:SP1_hourly_usage"
    assert len(stats) == 2
    assert stats[0]["state"] == 5.0
    assert stats[1]["sum"] == 8.0


@patch("custom_components.national_grid.statistics.async_add_external_statistics")
@patch("custom_components.national_grid.statistics.get_instance")
async def test_import_hourly_stats_gas_converts_therms(
    mock_get_instance, mock_add_stats, hass
) -> None:
    """Test gas therms are converted to CCF."""
    mock_get_instance.return_value.async_add_executor_job = AsyncMock(return_value={})

    readings = [{"date": "2025-01-15T10:00:00.000Z", "quantity": 10.0}]
    coordinator = MagicMock()
    coordinator.data = _make_coordinator_data(
        ami_usages={"SP1": readings},
        meters={"SP1": _make_meter_data("Gas")},
    )

    await async_import_all_statistics(hass, coordinator)
    assert mock_add_stats.called
    stats = mock_add_stats.call_args[0][2]
    assert stats[0]["state"] == therms_to_ccf(10.0)


@patch("custom_components.national_grid.statistics.async_add_external_statistics")
@patch("custom_components.national_grid.statistics.get_instance")
async def test_import_interval_stats(mock_get_instance, mock_add_stats, hass) -> None:
    """Test interval reads are bucketed into hourly totals."""
    mock_get_instance.return_value.async_add_executor_job = AsyncMock(return_value={})

    reads = [
        {"startTime": "2025-01-15T10:00:00", "value": 0.25},
        {"startTime": "2025-01-15T10:15:00", "value": 0.30},
        {"startTime": "2025-01-15T11:00:00", "value": 0.50},
    ]
    coordinator = MagicMock()
    coordinator.data = _make_coordinator_data(interval_reads={"SP1": reads})

    await async_import_all_statistics(hass, coordinator)
    assert mock_add_stats.called
    stats = mock_add_stats.call_args[0][2]
    # Two hourly buckets: 10:00 (0.25+0.30=0.55) and 11:00 (0.50)
    assert len(stats) == 2
    assert abs(stats[0]["state"] - 0.55) < 0.01
    assert stats[1]["state"] == 0.50


@patch("custom_components.national_grid.statistics.async_add_external_statistics")
@patch("custom_components.national_grid.statistics.get_instance")
async def test_import_interval_stats_skips_empty(
    mock_get_instance, mock_add_stats, hass
) -> None:
    """Test no stats imported when reads list is empty."""
    mock_get_instance.return_value.async_add_executor_job = AsyncMock(return_value={})

    coordinator = MagicMock()
    coordinator.data = _make_coordinator_data(interval_reads={"SP1": []})

    await async_import_all_statistics(hass, coordinator)
    assert not mock_add_stats.called


@patch("custom_components.national_grid.statistics.async_add_external_statistics")
@patch("custom_components.national_grid.statistics.get_instance")
async def test_import_hourly_stats_with_existing_sum(
    mock_get_instance, mock_add_stats, hass
) -> None:
    """Test hourly stats continues from last imported sum."""
    # Return existing statistics with a sum and timestamp
    existing = {
        "national_grid:SP1_hourly_usage": [
            {"sum": 10.0, "start": 1736935200.0}  # 2025-01-15T10:00:00 UTC
        ]
    }
    mock_get_instance.return_value.async_add_executor_job = AsyncMock(
        return_value=existing
    )

    readings = [
        {"date": "2025-01-15T10:00:00.000Z", "quantity": 5.0},  # should be skipped
        {"date": "2025-01-15T11:00:00.000Z", "quantity": 3.0},  # should be included
    ]
    coordinator = MagicMock()
    coordinator.data = _make_coordinator_data(
        ami_usages={"SP1": readings},
        meters={"SP1": _make_meter_data("Electric")},
    )

    await async_import_all_statistics(hass, coordinator)
    assert mock_add_stats.called
    stats = mock_add_stats.call_args[0][2]
    assert len(stats) == 1
    assert stats[0]["sum"] == 13.0  # 10.0 + 3.0


@patch("custom_components.national_grid.statistics.async_add_external_statistics")
@patch("custom_components.national_grid.statistics.get_instance")
async def test_import_hourly_stats_skips_empty_date(
    mock_get_instance, mock_add_stats, hass
) -> None:
    """Test readings with empty date are skipped."""
    mock_get_instance.return_value.async_add_executor_job = AsyncMock(return_value={})

    readings = [{"date": "", "quantity": 5.0}]
    coordinator = MagicMock()
    coordinator.data = _make_coordinator_data(
        ami_usages={"SP1": readings},
        meters={"SP1": _make_meter_data("Electric")},
    )

    await async_import_all_statistics(hass, coordinator)
    assert not mock_add_stats.called


@patch("custom_components.national_grid.statistics.async_add_external_statistics")
@patch("custom_components.national_grid.statistics.get_instance")
async def test_import_hourly_stats_skips_bad_date(
    mock_get_instance, mock_add_stats, hass
) -> None:
    """Test readings with unparseable date are skipped."""
    mock_get_instance.return_value.async_add_executor_job = AsyncMock(return_value={})

    readings = [{"date": "not-a-date", "quantity": 5.0}]
    coordinator = MagicMock()
    coordinator.data = _make_coordinator_data(
        ami_usages={"SP1": readings},
        meters={"SP1": _make_meter_data("Electric")},
    )

    await async_import_all_statistics(hass, coordinator)
    assert not mock_add_stats.called


@patch("custom_components.national_grid.statistics.async_add_external_statistics")
@patch("custom_components.national_grid.statistics.get_instance")
async def test_import_interval_stats_with_existing_sum(
    mock_get_instance, mock_add_stats, hass
) -> None:
    """Test interval stats continues from last imported sum."""
    existing = {
        "national_grid:SP1_interval_usage": [
            {"sum": 5.0, "start": 1736935200.0}  # 2025-01-15T10:00:00 UTC
        ]
    }
    mock_get_instance.return_value.async_add_executor_job = AsyncMock(
        return_value=existing
    )

    reads = [
        {"startTime": "2025-01-15T10:00:00", "value": 0.25},  # skipped
        {"startTime": "2025-01-15T11:00:00", "value": 0.50},  # included
    ]
    coordinator = MagicMock()
    coordinator.data = _make_coordinator_data(interval_reads={"SP1": reads})

    await async_import_all_statistics(hass, coordinator)
    assert mock_add_stats.called
    stats = mock_add_stats.call_args[0][2]
    assert len(stats) == 1
    assert stats[0]["sum"] == 5.5


@patch("custom_components.national_grid.statistics.async_add_external_statistics")
@patch("custom_components.national_grid.statistics.get_instance")
async def test_import_interval_stats_skips_bad_time(
    mock_get_instance, mock_add_stats, hass
) -> None:
    """Test interval reads with bad startTime are skipped."""
    mock_get_instance.return_value.async_add_executor_job = AsyncMock(return_value={})

    reads = [{"startTime": "not-a-time", "value": 0.25}]
    coordinator = MagicMock()
    coordinator.data = _make_coordinator_data(interval_reads={"SP1": reads})

    await async_import_all_statistics(hass, coordinator)
    assert not mock_add_stats.called


@patch("custom_components.national_grid.statistics.async_add_external_statistics")
@patch("custom_components.national_grid.statistics.get_instance")
async def test_import_interval_stats_skips_empty_starttime(
    mock_get_instance, mock_add_stats, hass
) -> None:
    """Test interval reads with empty startTime are skipped."""
    mock_get_instance.return_value.async_add_executor_job = AsyncMock(return_value={})

    reads = [{"startTime": "", "value": 0.25}]
    coordinator = MagicMock()
    coordinator.data = _make_coordinator_data(interval_reads={"SP1": reads})

    await async_import_all_statistics(hass, coordinator)
    assert not mock_add_stats.called


async def test_import_all_statistics_skips_missing_meter(hass) -> None:
    """Test AMI usages for unknown service points are skipped."""
    coordinator = MagicMock()
    coordinator.data = _make_coordinator_data(
        ami_usages={
            "SP_UNKNOWN": [{"date": "2025-01-15T10:00:00.000Z", "quantity": 5.0}]
        },
        meters={},  # no meters
    )
    # Should not raise
    await async_import_all_statistics(hass, coordinator)
