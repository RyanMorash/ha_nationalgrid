"""Tests for the National Grid coordinator."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed

from custom_components.nationalgrid.api import (
    NationalGridApiClientAuthenticationError,
    NationalGridApiClientError,
)
from custom_components.nationalgrid.const import (
    CONF_SELECTED_ACCOUNTS,
    DOMAIN,
    LOGGER,
)
from custom_components.nationalgrid.coordinator import (
    NationalGridDataUpdateCoordinator,
)

from .conftest import (
    MOCK_ACCOUNT_ID,
    _mock_ami_usages,
    _mock_billing_account,
    _mock_costs,
    _mock_interval_reads,
    _mock_usages,
)


def _make_coordinator(
    hass: HomeAssistant, client: AsyncMock
) -> NationalGridDataUpdateCoordinator:
    """Create a coordinator with a mock client and config entry."""
    coordinator = NationalGridDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,
        name=DOMAIN,
        update_interval=timedelta(hours=1),
        client=client,
    )
    mock_entry = MagicMock()
    mock_entry.data = {CONF_SELECTED_ACCOUNTS: [MOCK_ACCOUNT_ID]}
    coordinator.config_entry = mock_entry
    return coordinator


def _make_client() -> AsyncMock:
    """Create a mock API client."""
    client = AsyncMock()
    client.async_get_billing_account = AsyncMock(return_value=_mock_billing_account())
    client.async_get_energy_usages = AsyncMock(return_value=_mock_usages())
    client.async_get_energy_usage_costs = AsyncMock(return_value=_mock_costs())
    client.async_get_ami_energy_usages = AsyncMock(return_value=_mock_ami_usages())
    client.async_get_interval_reads = AsyncMock(return_value=_mock_interval_reads())
    client.close = AsyncMock()
    return client


async def test_coordinator_fetches_data(hass: HomeAssistant) -> None:
    """Test coordinator fetches and structures data correctly."""
    client = _make_client()
    coordinator = _make_coordinator(hass, client)

    data = await coordinator._async_update_data()

    assert MOCK_ACCOUNT_ID in data.accounts
    assert len(data.meters) == 2
    assert MOCK_ACCOUNT_ID in data.usages
    assert MOCK_ACCOUNT_ID in data.costs


async def test_coordinator_auth_error_raises(hass: HomeAssistant) -> None:
    """Test coordinator raises ConfigEntryAuthFailed on auth error."""
    client = _make_client()
    client.async_get_billing_account = AsyncMock(
        side_effect=NationalGridApiClientAuthenticationError("Bad creds"),
    )
    coordinator = _make_coordinator(hass, client)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_coordinator_api_error_per_account(hass: HomeAssistant) -> None:
    """Test coordinator handles per-account API errors gracefully."""
    client = _make_client()
    client.async_get_billing_account = AsyncMock(
        side_effect=NationalGridApiClientError("Server error"),
    )
    coordinator = _make_coordinator(hass, client)

    # Per-account errors are caught and the account is skipped
    data = await coordinator._async_update_data()
    assert len(data.accounts) == 0
    assert len(data.meters) == 0


async def test_get_latest_usage(hass: HomeAssistant) -> None:
    """Test get_latest_usage filters by fuel type and returns most recent."""
    client = _make_client()
    coordinator = _make_coordinator(hass, client)

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
    client = _make_client()
    coordinator = _make_coordinator(hass, client)

    coordinator.data = await coordinator._async_update_data()

    cost = coordinator.get_latest_cost(MOCK_ACCOUNT_ID, fuel_type="Electric")
    assert cost is not None
    assert cost["fuelType"] == "ELECTRIC"

    cost = coordinator.get_latest_cost(MOCK_ACCOUNT_ID, fuel_type="Gas")
    assert cost is not None
    assert cost["fuelType"] == "GAS"
