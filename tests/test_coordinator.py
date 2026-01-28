"""Tests for the National Grid coordinator."""

from __future__ import annotations

import logging
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aionatgrid.exceptions import (
    InvalidAuthError,
    NationalGridError,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.nationalgrid.const import (
    _LOGGER,
    CONF_SELECTED_ACCOUNTS,
    DOMAIN,
)
from custom_components.nationalgrid.coordinator import (
    NationalGridDataUpdateCoordinator,
)

from .conftest import (
    MOCK_ACCOUNT_ID,
    MOCK_SERVICE_POINT,
    _mock_ami_usages,
    _mock_billing_account,
    _mock_costs,
    _mock_interval_reads,
    _mock_usages,
)


def _make_coordinator(
    hass: HomeAssistant, api_mock: AsyncMock
) -> NationalGridDataUpdateCoordinator:
    """Create a coordinator with a mock API client and config entry."""
    with (
        patch(
            "custom_components.nationalgrid.coordinator.async_create_clientsession",
        ),
        patch(
            "custom_components.nationalgrid.coordinator.NationalGridClient",
            return_value=api_mock,
        ),
    ):
        coordinator = NationalGridDataUpdateCoordinator(
            hass=hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=1),
            username="test@example.com",
            password="password",
        )
    mock_entry = MagicMock()
    mock_entry.data = {CONF_SELECTED_ACCOUNTS: [MOCK_ACCOUNT_ID]}
    coordinator.config_entry = mock_entry
    return coordinator


def _make_api() -> AsyncMock:
    """Create a mock aionatgrid client."""
    api = AsyncMock()
    api.get_billing_account = AsyncMock(return_value=_mock_billing_account())
    api.get_energy_usages = AsyncMock(return_value=_mock_usages())
    api.get_energy_usage_costs = AsyncMock(return_value=_mock_costs())
    api.get_ami_energy_usages = AsyncMock(return_value=_mock_ami_usages())
    api.get_interval_reads = AsyncMock(return_value=_mock_interval_reads())
    return api


async def test_coordinator_fetches_data(hass: HomeAssistant) -> None:
    """Test coordinator fetches and structures data correctly."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)

    data = await coordinator._async_update_data()

    assert MOCK_ACCOUNT_ID in data.accounts
    assert len(data.meters) == 2
    assert MOCK_ACCOUNT_ID in data.usages
    assert MOCK_ACCOUNT_ID in data.costs


async def test_coordinator_auth_error_raises(hass: HomeAssistant) -> None:
    """Test coordinator raises ConfigEntryAuthFailed on auth error."""
    api = _make_api()
    api.get_billing_account = AsyncMock(
        side_effect=InvalidAuthError("Bad creds"),
    )
    coordinator = _make_coordinator(hass, api)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_coordinator_api_error_per_account(hass: HomeAssistant) -> None:
    """Test coordinator handles per-account API errors gracefully."""
    api = _make_api()
    api.get_billing_account = AsyncMock(
        side_effect=NationalGridError("Server error"),
    )
    coordinator = _make_coordinator(hass, api)

    # Per-account errors are caught and the account is skipped
    data = await coordinator._async_update_data()
    assert len(data.accounts) == 0
    assert len(data.meters) == 0


async def test_get_latest_usage(hass: HomeAssistant) -> None:
    """Test get_latest_usage filters by fuel type and returns most recent."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)

    # Populate coordinator data
    coordinator.data = await coordinator._async_update_data()

    # Electric usage (TOTAL_KWH)
    usage = coordinator.get_latest_usage(MOCK_ACCOUNT_ID, fuel_type="Electric")
    assert usage is not None
    assert usage["usageType"] == "TOTAL_KWH"
    assert usage["usageYearMonth"] == 202501

    # Gas usage (THERMS)
    usage = coordinator.get_latest_usage(MOCK_ACCOUNT_ID, fuel_type="Gas")
    assert usage is not None
    assert usage["usageType"] == "THERMS"

    # No filter
    usage = coordinator.get_latest_usage(MOCK_ACCOUNT_ID)
    assert usage is not None
    assert usage["usageYearMonth"] == 202501


async def test_get_latest_cost(hass: HomeAssistant) -> None:
    """Test get_latest_cost filters by fuel type."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)

    coordinator.data = await coordinator._async_update_data()

    cost = coordinator.get_latest_cost(MOCK_ACCOUNT_ID, fuel_type="Electric")
    assert cost is not None
    assert cost["fuelType"] == "ELECTRIC"

    cost = coordinator.get_latest_cost(MOCK_ACCOUNT_ID, fuel_type="Gas")
    assert cost is not None
    assert cost["fuelType"] == "GAS"


async def test_coordinator_logs_unavailable_on_failure(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test WARNING logged on first failure."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)
    # _fetch_all_data catches per-account errors, so we need to make
    # the coordinator's _fetch_all_data itself raise.
    coordinator._fetch_all_data = AsyncMock(
        side_effect=NationalGridError("Server down"),
    )

    with caplog.at_level(logging.WARNING), pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    assert "National Grid service unavailable" in caplog.text
    assert coordinator._last_update_success is False


async def test_coordinator_logs_recovery(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test INFO logged on recovery after failure."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)
    # Simulate previous failure
    coordinator._last_update_success = False

    with caplog.at_level(logging.INFO):
        await coordinator._async_update_data()

    assert "National Grid service recovered" in caplog.text
    assert coordinator._last_update_success is True


async def test_coordinator_no_duplicate_unavailable_log(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test consecutive failures only log WARNING once."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)
    coordinator._fetch_all_data = AsyncMock(
        side_effect=NationalGridError("Server down"),
    )

    # First failure
    with caplog.at_level(logging.WARNING), pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    first_count = caplog.text.count("National Grid service unavailable")

    # Second failure
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    second_count = caplog.text.count("National Grid service unavailable")

    assert first_count == 1
    assert second_count == 1  # No additional log


async def test_get_all_usages(hass: HomeAssistant) -> None:
    """Test get_all_usages returns usages for account."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)
    coordinator.data = await coordinator._async_update_data()

    usages = coordinator.get_all_usages(MOCK_ACCOUNT_ID)
    assert usages is not None
    assert len(usages) > 0


async def test_get_all_costs(hass: HomeAssistant) -> None:
    """Test get_all_costs returns costs for account."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)
    coordinator.data = await coordinator._async_update_data()

    costs = coordinator.get_all_costs(MOCK_ACCOUNT_ID)
    assert costs is not None
    assert len(costs) > 0


async def test_get_latest_ami_usage(hass: HomeAssistant) -> None:
    """Test get_latest_ami_usage returns AMI data for service point."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)
    coordinator.data = await coordinator._async_update_data()

    ami = coordinator.get_latest_ami_usage(MOCK_SERVICE_POINT)
    assert ami is not None


async def test_fetch_usages_error_graceful(hass: HomeAssistant) -> None:
    """Test _fetch_all_data handles usages error gracefully."""
    api = _make_api()
    api.get_energy_usages = AsyncMock(
        side_effect=NationalGridError("usage fail"),
    )
    coordinator = _make_coordinator(hass, api)
    data = await coordinator._async_update_data()
    # Usages should be empty list for that account
    assert data.usages[MOCK_ACCOUNT_ID] == []


async def test_fetch_costs_error_graceful(hass: HomeAssistant) -> None:
    """Test _fetch_all_data handles costs error gracefully."""
    api = _make_api()
    api.get_energy_usage_costs = AsyncMock(
        side_effect=NationalGridError("cost fail"),
    )
    coordinator = _make_coordinator(hass, api)
    data = await coordinator._async_update_data()
    assert data.costs[MOCK_ACCOUNT_ID] == []


async def test_fetch_costs_no_region(hass: HomeAssistant) -> None:
    """Test _fetch_all_data handles missing region gracefully."""
    api = _make_api()
    billing = _mock_billing_account()
    billing["region"] = ""
    api.get_billing_account = AsyncMock(return_value=billing)
    coordinator = _make_coordinator(hass, api)
    data = await coordinator._async_update_data()
    assert data.costs[MOCK_ACCOUNT_ID] == []


async def test_fetch_ami_error_graceful(hass: HomeAssistant) -> None:
    """Test _fetch_all_data handles AMI error gracefully."""
    api = _make_api()
    api.get_ami_energy_usages = AsyncMock(
        side_effect=NationalGridError("ami fail"),
    )
    coordinator = _make_coordinator(hass, api)
    data = await coordinator._async_update_data()
    # AMI usages should not contain the service point that failed
    assert MOCK_SERVICE_POINT not in data.ami_usages


async def test_fetch_interval_reads_error_graceful(hass: HomeAssistant) -> None:
    """Test _fetch_all_data handles interval reads error gracefully."""
    api = _make_api()
    api.get_interval_reads = AsyncMock(
        side_effect=NationalGridError("interval fail"),
    )
    coordinator = _make_coordinator(hass, api)
    data = await coordinator._async_update_data()
    # Interval reads should not contain the service point that failed
    assert MOCK_SERVICE_POINT not in data.interval_reads


async def test_get_meter_data_none_when_no_data(hass: HomeAssistant) -> None:
    """Test get_meter_data returns None when data is None."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)
    coordinator.data = None
    assert coordinator.get_meter_data("SP001") is None


async def test_get_latest_usage_none_when_no_data(hass: HomeAssistant) -> None:
    """Test get_latest_usage returns None when data is None."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)
    coordinator.data = None
    assert coordinator.get_latest_usage("acct1") is None


async def test_get_latest_usage_none_when_no_usages(hass: HomeAssistant) -> None:
    """Test get_latest_usage returns None when account has no usages."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)
    coordinator.data = await coordinator._async_update_data()
    assert coordinator.get_latest_usage("nonexistent_account") is None


async def test_get_latest_usage_filtered_empty(hass: HomeAssistant) -> None:
    """Test get_latest_usage returns None when fuel type filter matches nothing."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)
    coordinator.data = await coordinator._async_update_data()
    assert coordinator.get_latest_usage(MOCK_ACCOUNT_ID, fuel_type="Solar") is None


async def test_get_latest_cost_none_when_no_data(hass: HomeAssistant) -> None:
    """Test get_latest_cost returns None when data is None."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)
    coordinator.data = None
    assert coordinator.get_latest_cost("acct1") is None


async def test_get_latest_cost_none_when_no_costs(hass: HomeAssistant) -> None:
    """Test get_latest_cost returns None when account has no costs."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)
    coordinator.data = await coordinator._async_update_data()
    assert coordinator.get_latest_cost("nonexistent_account") is None


async def test_get_latest_cost_filtered_empty(hass: HomeAssistant) -> None:
    """Test get_latest_cost returns None when fuel type filter matches nothing."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)
    coordinator.data = await coordinator._async_update_data()
    assert coordinator.get_latest_cost(MOCK_ACCOUNT_ID, fuel_type="Solar") is None


async def test_get_all_usages_none_data(hass: HomeAssistant) -> None:
    """Test get_all_usages returns empty when data is None."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)
    coordinator.data = None
    assert coordinator.get_all_usages("acct1") == []


async def test_get_all_usages_no_account(hass: HomeAssistant) -> None:
    """Test get_all_usages returns empty for unknown account."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)
    coordinator.data = await coordinator._async_update_data()
    assert coordinator.get_all_usages("nonexistent") == []


async def test_get_all_usages_with_fuel_filter(hass: HomeAssistant) -> None:
    """Test get_all_usages filters by fuel type."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)
    coordinator.data = await coordinator._async_update_data()
    gas_usages = coordinator.get_all_usages(MOCK_ACCOUNT_ID, fuel_type="Gas")
    assert all(u.get("usageType") == "THERMS" for u in gas_usages)


async def test_get_all_costs_none_data(hass: HomeAssistant) -> None:
    """Test get_all_costs returns empty when data is None."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)
    coordinator.data = None
    assert coordinator.get_all_costs("acct1") == []


async def test_get_all_costs_no_account(hass: HomeAssistant) -> None:
    """Test get_all_costs returns empty for unknown account."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)
    coordinator.data = await coordinator._async_update_data()
    assert coordinator.get_all_costs("nonexistent") == []


async def test_get_all_costs_with_fuel_filter(hass: HomeAssistant) -> None:
    """Test get_all_costs filters by fuel type."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)
    coordinator.data = await coordinator._async_update_data()
    electric_costs = coordinator.get_all_costs(MOCK_ACCOUNT_ID, fuel_type="Electric")
    assert all(c.get("fuelType") == "ELECTRIC" for c in electric_costs)


async def test_get_latest_ami_usage_none_data(hass: HomeAssistant) -> None:
    """Test get_latest_ami_usage returns None when data is None."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)
    coordinator.data = None
    assert coordinator.get_latest_ami_usage("SP001") is None


async def test_get_latest_ami_usage_no_readings(hass: HomeAssistant) -> None:
    """Test get_latest_ami_usage returns None when no readings exist."""
    api = _make_api()
    coordinator = _make_coordinator(hass, api)
    coordinator.data = await coordinator._async_update_data()
    assert coordinator.get_latest_ami_usage("NONEXISTENT_SP") is None
