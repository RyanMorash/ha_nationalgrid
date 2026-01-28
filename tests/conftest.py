"""Fixtures for National Grid tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from custom_components.nationalgrid.const import CONF_SELECTED_ACCOUNTS, DOMAIN

MOCK_USERNAME = "testuser@example.com"
MOCK_PASSWORD = "testpassword123"
MOCK_ACCOUNT_ID = "1234567890"
MOCK_ACCOUNT_ID_2 = "0987654321"
MOCK_SERVICE_POINT = "SP001"
MOCK_SERVICE_POINT_2 = "SP002"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    recorder_mock: None,  # noqa: ARG001
    enable_custom_integrations: None,  # noqa: ARG001
) -> None:
    """Enable custom integrations and recorder in Home Assistant."""


@pytest.fixture
def mock_config_entry():
    """Return a mock config entry."""
    from unittest.mock import MagicMock

    entry = MagicMock()
    entry.domain = DOMAIN
    entry.entry_id = "test_entry_id"
    entry.unique_id = "testuser-example-com"
    entry.data = {
        CONF_USERNAME: MOCK_USERNAME,
        CONF_PASSWORD: MOCK_PASSWORD,
        CONF_SELECTED_ACCOUNTS: [MOCK_ACCOUNT_ID],
    }
    entry.runtime_data = None
    return entry


def _mock_billing_account(account_id: str = MOCK_ACCOUNT_ID) -> dict:
    """Return a mock billing account."""
    return {
        "billingAccountId": account_id,
        "region": "KEDNY",
        "premiseNumber": "PREM001",
        "meter": {
            "nodes": [
                {
                    "servicePointNumber": MOCK_SERVICE_POINT,
                    "meterNumber": "MTR001",
                    "meterPointNumber": "MPT001",
                    "fuelType": "Electric",
                    "hasAmiSmartMeter": True,
                },
                {
                    "servicePointNumber": MOCK_SERVICE_POINT_2,
                    "meterNumber": "MTR002",
                    "meterPointNumber": "MPT002",
                    "fuelType": "Gas",
                    "hasAmiSmartMeter": False,
                },
            ],
        },
    }


def _mock_usages() -> list[dict]:
    """Return mock energy usages."""
    return [
        {
            "usageType": "TOTAL_KWH",
            "usageYearMonth": 202501,
            "usage": 500.0,
        },
        {
            "usageType": "TOTAL_KWH",
            "usageYearMonth": 202412,
            "usage": 450.0,
        },
        {
            "usageType": "THERMS",
            "usageYearMonth": 202501,
            "usage": 30.0,
        },
    ]


def _mock_costs() -> list[dict]:
    """Return mock energy costs."""
    return [
        {
            "fuelType": "ELECTRIC",
            "month": 202501,
            "totalCost": 120.50,
        },
        {
            "fuelType": "GAS",
            "month": 202501,
            "totalCost": 45.00,
        },
    ]


def _mock_ami_usages() -> list[dict]:
    """Return mock AMI usages."""
    return [
        {
            "date": "2025-01-15",
            "usage": 18.5,
        },
    ]


def _mock_interval_reads() -> list[dict]:
    """Return mock interval reads."""
    return [
        {
            "startDateTime": "2025-01-15T00:00:00",
            "endDateTime": "2025-01-15T00:15:00",
            "value": 0.25,
        },
    ]


@pytest.fixture
def mock_api_client():
    """Patch the NationalGridApiClient with mock return data."""
    with patch(
        "custom_components.nationalgrid.api.NationalGridApiClient",
        autospec=True,
    ) as mock_cls:
        client = mock_cls.return_value
        client.async_init = AsyncMock()
        client.async_get_linked_accounts = AsyncMock(
            return_value=[{"billingAccountId": MOCK_ACCOUNT_ID}],
        )
        client.async_get_billing_account = AsyncMock(
            return_value=_mock_billing_account(),
        )
        client.async_get_energy_usages = AsyncMock(
            return_value=_mock_usages(),
        )
        client.async_get_energy_usage_costs = AsyncMock(
            return_value=_mock_costs(),
        )
        client.async_get_interval_reads = AsyncMock(
            return_value=_mock_interval_reads(),
        )
        client.async_get_ami_energy_usages = AsyncMock(
            return_value=_mock_ami_usages(),
        )
        client.close = AsyncMock()
        yield client
