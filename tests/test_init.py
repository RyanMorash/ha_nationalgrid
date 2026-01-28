"""Tests for the National Grid integration init."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nationalgrid.const import CONF_SELECTED_ACCOUNTS, DOMAIN

from .conftest import (
    MOCK_ACCOUNT_ID,
    MOCK_PASSWORD,
    MOCK_USERNAME,
    _mock_ami_usages,
    _mock_billing_account,
    _mock_costs,
    _mock_interval_reads,
    _mock_usages,
)


@pytest.fixture
def config_entry(hass: HomeAssistant):
    """Create and add a config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=MOCK_USERNAME,
        data={
            CONF_USERNAME: MOCK_USERNAME,
            CONF_PASSWORD: MOCK_PASSWORD,
            CONF_SELECTED_ACCOUNTS: [MOCK_ACCOUNT_ID],
        },
    )
    entry.add_to_hass(hass)
    return entry


async def test_setup_entry(hass: HomeAssistant, config_entry) -> None:
    """Test successful setup of a config entry."""
    with (
        patch(
            "custom_components.nationalgrid.NationalGridApiClient",
        ) as mock_cls,
        patch(
            "custom_components.nationalgrid.async_import_all_statistics",
            new_callable=AsyncMock,
        ),
    ):
        client = mock_cls.return_value
        client.async_init = AsyncMock()
        client.async_get_billing_account = AsyncMock(
            return_value=_mock_billing_account(),
        )
        client.async_get_energy_usages = AsyncMock(return_value=_mock_usages())
        client.async_get_energy_usage_costs = AsyncMock(return_value=_mock_costs())
        client.async_get_ami_energy_usages = AsyncMock(return_value=_mock_ami_usages())
        client.async_get_interval_reads = AsyncMock(
            return_value=_mock_interval_reads(),
        )
        client.close = AsyncMock()

        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert config_entry.runtime_data is not None


async def test_unload_entry(hass: HomeAssistant, config_entry) -> None:
    """Test unloading a config entry."""
    with (
        patch(
            "custom_components.nationalgrid.NationalGridApiClient",
        ) as mock_cls,
        patch(
            "custom_components.nationalgrid.async_import_all_statistics",
            new_callable=AsyncMock,
        ),
    ):
        client = mock_cls.return_value
        client.async_init = AsyncMock()
        client.async_get_billing_account = AsyncMock(
            return_value=_mock_billing_account(),
        )
        client.async_get_energy_usages = AsyncMock(return_value=_mock_usages())
        client.async_get_energy_usage_costs = AsyncMock(return_value=_mock_costs())
        client.async_get_ami_energy_usages = AsyncMock(return_value=_mock_ami_usages())
        client.async_get_interval_reads = AsyncMock(
            return_value=_mock_interval_reads(),
        )
        client.close = AsyncMock()

        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        assert config_entry.state is ConfigEntryState.LOADED

        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_entry_auth_error(hass: HomeAssistant, config_entry) -> None:
    """Test setup with auth error triggers reauth."""
    from custom_components.nationalgrid.api import (
        NationalGridApiClientAuthenticationError,
    )

    with (
        patch(
            "custom_components.nationalgrid.NationalGridApiClient",
        ) as mock_cls,
        patch(
            "custom_components.nationalgrid.async_import_all_statistics",
            new_callable=AsyncMock,
        ),
    ):
        client = mock_cls.return_value
        client.async_init = AsyncMock()
        client.async_get_billing_account = AsyncMock(
            side_effect=NationalGridApiClientAuthenticationError("Bad creds"),
        )
        client.close = AsyncMock()

        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
