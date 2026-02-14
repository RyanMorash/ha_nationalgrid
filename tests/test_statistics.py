"""Tests for the National Grid statistics module."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

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
    is_first_refresh: bool = True,
) -> NationalGridCoordinatorData:
    """Build mock coordinator data.

    Args:
        ami_usages: AMI usage data by service point
        interval_reads: Interval read data by service point
        meters: Meter data by service point
        is_first_refresh: Whether this is the first refresh (imports all data)
                          or incremental (applies 48h cutoff)

    """
    return NationalGridCoordinatorData(
        accounts={"acct1": {"billingAccountId": "acct1"}},
        meters=meters or {},
        usages={},
        costs={},
        ami_usages=ami_usages or {},
        interval_reads=interval_reads or {},
        is_first_refresh=is_first_refresh,
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
    assert metadata["statistic_id"] == "national_grid:SP1_electric_hourly_usage"
    assert len(stats) == 2
    assert stats[0]["state"] == 5.0
    assert stats[1]["sum"] == 8.0


@patch("custom_components.national_grid.statistics.async_add_external_statistics")
@patch("custom_components.national_grid.statistics.get_instance")
async def test_import_hourly_stats_gas(mock_get_instance, mock_add_stats, hass) -> None:
    """Test gas usage values are imported directly as CCF."""
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
    assert stats[0]["state"] == 10.0


@patch("custom_components.national_grid.statistics.async_add_external_statistics")
@patch("custom_components.national_grid.statistics.get_instance")
async def test_import_interval_stats(mock_get_instance, mock_add_stats, hass) -> None:
    """Test interval reads are bucketed into hourly totals."""
    mock_recorder = MagicMock()
    mock_recorder.async_clear_statistics = MagicMock()
    mock_get_instance.return_value = mock_recorder

    # Use dates within the last 2 days so they pass the cutoff
    now = datetime.now(tz=UTC)
    base_time = (now - timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)

    reads = [
        {"startTime": base_time.isoformat(), "value": 0.25},
        {"startTime": (base_time + timedelta(minutes=15)).isoformat(), "value": 0.30},
        {"startTime": (base_time + timedelta(hours=1)).isoformat(), "value": 0.50},
    ]
    coordinator = MagicMock()
    coordinator.data = _make_coordinator_data(interval_reads={"SP1": reads})

    await async_import_all_statistics(hass, coordinator)
    assert mock_add_stats.called
    stats = mock_add_stats.call_args[0][2]
    # Two hourly buckets: base_time (0.25+0.30=0.55) and base_time+1h (0.50)
    assert len(stats) == 2
    assert abs(stats[0]["state"] - 0.55) < 0.01
    assert stats[1]["state"] == 0.50


@patch("custom_components.national_grid.statistics.async_add_external_statistics")
@patch("custom_components.national_grid.statistics.get_instance")
async def test_import_interval_stats_skips_empty(
    mock_get_instance, mock_add_stats, hass
) -> None:
    """Test no stats imported when reads list is empty."""
    mock_recorder = MagicMock()
    mock_recorder.async_clear_statistics = MagicMock()
    mock_get_instance.return_value = mock_recorder

    coordinator = MagicMock()
    coordinator.data = _make_coordinator_data(interval_reads={"SP1": []})

    await async_import_all_statistics(hass, coordinator)
    assert not mock_add_stats.called


@patch("custom_components.national_grid.statistics.async_add_external_statistics")
@patch("custom_components.national_grid.statistics.get_instance")
async def test_import_hourly_stats_with_existing_sum(
    mock_get_instance, mock_add_stats, hass
) -> None:
    """Test hourly stats continues from last imported sum on incremental updates."""
    # Return existing statistics with a sum and timestamp
    existing = {
        "national_grid:SP1_electric_hourly_usage": [
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
        is_first_refresh=False,  # Incremental update - use existing sum
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
async def test_import_interval_stats_always_reimports_fresh(
    mock_get_instance, mock_add_stats, hass
) -> None:
    """Test interval stats always clears and reimports fresh."""
    # Use dates within the last 2 days
    now = datetime.now(tz=UTC)
    base_time = (now - timedelta(hours=3)).replace(minute=0, second=0, microsecond=0)

    # Mock the recorder instance with async_clear_statistics
    mock_recorder = MagicMock()
    mock_recorder.async_clear_statistics = MagicMock()
    mock_get_instance.return_value = mock_recorder

    reads = [
        {"startTime": base_time.isoformat(), "value": 0.25},
        {"startTime": (base_time + timedelta(hours=1)).isoformat(), "value": 0.50},
    ]
    coordinator = MagicMock()
    coordinator.data = _make_coordinator_data(
        interval_reads={"SP1": reads},
        is_first_refresh=False,  # Interval stats always reimport fresh
    )

    await async_import_all_statistics(hass, coordinator)

    # Verify clear was called
    assert mock_recorder.async_clear_statistics.called

    # Verify stats were imported
    assert mock_add_stats.called
    stats = mock_add_stats.call_args[0][2]
    assert len(stats) == 2  # Both hours included
    # Sum starts from 0 (not continuing from previous)
    assert stats[0]["sum"] == 0.25
    assert stats[1]["sum"] == 0.75


@patch("custom_components.national_grid.statistics.async_add_external_statistics")
@patch("custom_components.national_grid.statistics.get_instance")
async def test_import_interval_stats_skips_bad_time(
    mock_get_instance, mock_add_stats, hass
) -> None:
    """Test interval reads with bad startTime are skipped."""
    mock_recorder = MagicMock()
    mock_recorder.async_clear_statistics = MagicMock()
    mock_get_instance.return_value = mock_recorder

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
    mock_recorder = MagicMock()
    mock_recorder.async_clear_statistics = MagicMock()
    mock_get_instance.return_value = mock_recorder

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


@patch("custom_components.national_grid.statistics.async_add_external_statistics")
@patch("custom_components.national_grid.statistics.get_instance")
async def test_import_hourly_stats_imports_all_new_data(
    mock_get_instance, mock_add_stats, hass
) -> None:
    """Test all new readings are imported regardless of age."""
    mock_get_instance.return_value.async_add_executor_job = AsyncMock(return_value={})

    # Both recent and old readings should be imported (no cutoff)
    now = datetime.now(tz=UTC)
    recent_time = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:00:00.000Z")
    old_time = (now - timedelta(hours=72)).strftime("%Y-%m-%dT%H:00:00.000Z")

    readings = [
        {"date": old_time, "quantity": 5.0},  # Should be included
        {"date": recent_time, "quantity": 3.0},  # Should be included
    ]
    coordinator = MagicMock()
    coordinator.data = _make_coordinator_data(
        ami_usages={"SP1": readings},
        meters={"SP1": _make_meter_data("Electric")},
        is_first_refresh=False,  # Even on incremental, all new data is imported
    )

    await async_import_all_statistics(hass, coordinator)

    # Both readings should be imported (no 48h cutoff)
    assert mock_add_stats.called
    stats = mock_add_stats.call_args[0][2]
    assert len(stats) == 2
    # Stats should be sorted by time, so old_time first, then recent_time
    assert stats[0]["state"] == 5.0  # Old reading
    assert stats[1]["state"] == 3.0  # Recent reading
    assert stats[1]["sum"] == 8.0  # Running sum


@patch("custom_components.national_grid.statistics.async_add_external_statistics")
@patch("custom_components.national_grid.statistics.get_instance")
async def test_import_interval_stats_with_return_values(
    mock_get_instance, mock_add_stats, hass
) -> None:
    """Test interval stats creates separate consumption and return stats."""
    mock_recorder = MagicMock()
    mock_recorder.async_clear_statistics = MagicMock()
    mock_get_instance.return_value = mock_recorder

    # Use dates within the last 2 days
    now = datetime.now(tz=UTC)
    base_time = (now - timedelta(hours=3)).replace(minute=0, second=0, microsecond=0)

    # Mix of positive (consumption) and negative (return/solar) values
    reads = [
        {"startTime": base_time.isoformat(), "value": 0.5},  # Consumption
        {
            "startTime": (base_time + timedelta(minutes=15)).isoformat(),
            "value": 0.3,
        },  # Consumption
        {
            "startTime": (base_time + timedelta(hours=1)).isoformat(),
            "value": -0.4,
        },  # Return (solar)
        {
            "startTime": (base_time + timedelta(hours=1, minutes=15)).isoformat(),
            "value": -0.2,
        },  # Return (solar)
        {
            "startTime": (base_time + timedelta(hours=2)).isoformat(),
            "value": 0.6,
        },  # Consumption
    ]
    coordinator = MagicMock()
    coordinator.data = _make_coordinator_data(
        interval_reads={"SP1": reads},
        is_first_refresh=True,
    )

    await async_import_all_statistics(hass, coordinator)

    # Should be called twice - once for consumption, once for return
    assert mock_add_stats.call_count == 2

    # Check that both statistics were created with correct IDs
    call_args = [call[0] for call in mock_add_stats.call_args_list]
    statistic_ids = [args[1]["statistic_id"] for args in call_args]

    assert "national_grid:SP1_electric_interval_usage" in statistic_ids
    assert "national_grid:SP1_electric_interval_return_usage" in statistic_ids


@patch("custom_components.national_grid.statistics.async_add_external_statistics")
@patch("custom_components.national_grid.statistics.get_instance")
async def test_import_interval_stats_no_return_when_no_negative(
    mock_get_instance, mock_add_stats, hass
) -> None:
    """Test only consumption stat is created when no negatives."""
    mock_recorder = MagicMock()
    mock_recorder.async_clear_statistics = MagicMock()
    mock_get_instance.return_value = mock_recorder

    # Use dates within the last 2 days
    now = datetime.now(tz=UTC)
    base_time = (now - timedelta(hours=3)).replace(minute=0, second=0, microsecond=0)

    # Create interval reads with only positive values (no solar)
    reads = [
        {"startTime": base_time.isoformat(), "value": 0.5},
        {"startTime": (base_time + timedelta(minutes=15)).isoformat(), "value": 0.3},
        {"startTime": (base_time + timedelta(hours=1)).isoformat(), "value": 0.4},
    ]
    coordinator = MagicMock()
    coordinator.data = _make_coordinator_data(
        interval_reads={"SP1": reads},
        is_first_refresh=True,
    )

    await async_import_all_statistics(hass, coordinator)

    # Should only be called once (consumption only, no return)
    assert mock_add_stats.call_count == 1

    # Verify it's the consumption statistic
    metadata = mock_add_stats.call_args[0][1]
    assert metadata["statistic_id"] == "national_grid:SP1_electric_interval_usage"
