"""Tests for the National Grid API client."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from aionatgrid.exceptions import (
    CannotConnectError,
    InvalidAuthError,
    NationalGridError,
)

from custom_components.nationalgrid.api import (
    NationalGridApiClient,
    NationalGridApiClientAuthenticationError,
    NationalGridApiClientCommunicationError,
    NationalGridApiClientError,
)


@pytest.fixture
def mock_ng_client():
    """Patch the underlying aionatgrid client."""
    with patch(
        "custom_components.nationalgrid.api.NationalGridClient",
        autospec=True,
    ) as mock_cls:
        instance = mock_cls.return_value
        # Make the async context manager work
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        yield instance


def _make_api_client() -> NationalGridApiClient:
    return NationalGridApiClient(username="user", password="pass")


async def test_async_get_linked_accounts(mock_ng_client) -> None:
    """Test happy path for getting linked accounts."""
    mock_ng_client.get_linked_accounts = AsyncMock(return_value=[{"id": "1"}])
    client = _make_api_client()
    result = await client.async_get_linked_accounts()
    assert result == [{"id": "1"}]


async def test_async_get_linked_accounts_auth_error(mock_ng_client) -> None:
    """Test InvalidAuthError maps to authentication error."""
    mock_ng_client.get_linked_accounts = AsyncMock(side_effect=InvalidAuthError("bad"))
    client = _make_api_client()
    with pytest.raises(NationalGridApiClientAuthenticationError):
        await client.async_get_linked_accounts()


async def test_async_get_linked_accounts_communication_error(mock_ng_client) -> None:
    """Test CannotConnectError maps to communication error."""
    mock_ng_client.get_linked_accounts = AsyncMock(
        side_effect=CannotConnectError("down")
    )
    client = _make_api_client()
    with pytest.raises(NationalGridApiClientCommunicationError):
        await client.async_get_linked_accounts()


async def test_async_get_linked_accounts_generic_error(mock_ng_client) -> None:
    """Test NationalGridError maps to generic API error."""
    mock_ng_client.get_linked_accounts = AsyncMock(
        side_effect=NationalGridError("oops")
    )
    client = _make_api_client()
    with pytest.raises(NationalGridApiClientError):
        await client.async_get_linked_accounts()


async def test_async_get_billing_account(mock_ng_client) -> None:
    """Test happy path for billing account."""
    mock_ng_client.get_billing_account = AsyncMock(return_value={"id": "acct1"})
    client = _make_api_client()
    result = await client.async_get_billing_account("acct1")
    assert result == {"id": "acct1"}


async def test_async_get_energy_usages(mock_ng_client) -> None:
    """Test happy path for energy usages."""
    mock_ng_client.get_energy_usages = AsyncMock(return_value=[{"usage": 100}])
    client = _make_api_client()
    result = await client.async_get_energy_usages("acct1", from_month=202501)
    assert result == [{"usage": 100}]


async def test_async_get_energy_usage_costs(mock_ng_client) -> None:
    """Test happy path for energy usage costs."""
    mock_ng_client.get_energy_usage_costs = AsyncMock(return_value=[{"cost": 50}])
    client = _make_api_client()
    result = await client.async_get_energy_usage_costs("acct1", "2025-01-01", "KEDNY")
    assert result == [{"cost": 50}]


async def test_async_get_interval_reads(mock_ng_client) -> None:
    """Test happy path for interval reads."""
    mock_ng_client.get_interval_reads = AsyncMock(return_value=[{"value": 0.5}])
    client = _make_api_client()
    result = await client.async_get_interval_reads("PREM1", "SP1", "2025-01-01T00:00")
    assert result == [{"value": 0.5}]


async def test_async_get_ami_energy_usages(mock_ng_client) -> None:
    """Test happy path for AMI energy usages."""
    mock_ng_client.get_ami_energy_usages = AsyncMock(return_value=[{"usage": 10}])
    client = _make_api_client()
    result = await client.async_get_ami_energy_usages(
        meter_number="MTR1",
        premise_number="PREM1",
        service_point_number="SP1",
        meter_point_number="MPT1",
        date_from=date(2025, 1, 1),
        date_to=date(2025, 1, 2),
    )
    assert result == [{"usage": 10}]


async def test_async_get_billing_account_auth_error(mock_ng_client) -> None:
    """Test billing account auth error."""
    mock_ng_client.get_billing_account = AsyncMock(side_effect=InvalidAuthError("bad"))
    client = _make_api_client()
    with pytest.raises(NationalGridApiClientAuthenticationError):
        await client.async_get_billing_account("acct1")


async def test_async_get_billing_account_communication_error(mock_ng_client) -> None:
    """Test billing account communication error."""
    mock_ng_client.get_billing_account = AsyncMock(
        side_effect=CannotConnectError("down")
    )
    client = _make_api_client()
    with pytest.raises(NationalGridApiClientCommunicationError):
        await client.async_get_billing_account("acct1")


async def test_async_get_billing_account_generic_error(mock_ng_client) -> None:
    """Test billing account generic error."""
    mock_ng_client.get_billing_account = AsyncMock(
        side_effect=NationalGridError("oops")
    )
    client = _make_api_client()
    with pytest.raises(NationalGridApiClientError):
        await client.async_get_billing_account("acct1")


async def test_async_get_energy_usages_auth_error(mock_ng_client) -> None:
    """Test energy usages auth error."""
    mock_ng_client.get_energy_usages = AsyncMock(side_effect=InvalidAuthError("bad"))
    client = _make_api_client()
    with pytest.raises(NationalGridApiClientAuthenticationError):
        await client.async_get_energy_usages("acct1", from_month=202501)


async def test_async_get_energy_usages_communication_error(mock_ng_client) -> None:
    """Test energy usages communication error."""
    mock_ng_client.get_energy_usages = AsyncMock(side_effect=CannotConnectError("down"))
    client = _make_api_client()
    with pytest.raises(NationalGridApiClientCommunicationError):
        await client.async_get_energy_usages("acct1", from_month=202501)


async def test_async_get_energy_usages_generic_error(mock_ng_client) -> None:
    """Test energy usages generic error."""
    mock_ng_client.get_energy_usages = AsyncMock(side_effect=NationalGridError("oops"))
    client = _make_api_client()
    with pytest.raises(NationalGridApiClientError):
        await client.async_get_energy_usages("acct1", from_month=202501)


async def test_async_get_energy_usage_costs_auth_error(mock_ng_client) -> None:
    """Test energy usage costs auth error."""
    mock_ng_client.get_energy_usage_costs = AsyncMock(
        side_effect=InvalidAuthError("bad")
    )
    client = _make_api_client()
    with pytest.raises(NationalGridApiClientAuthenticationError):
        await client.async_get_energy_usage_costs("acct1", "2025-01-01", "KEDNY")


async def test_async_get_energy_usage_costs_communication_error(mock_ng_client) -> None:
    """Test energy usage costs communication error."""
    mock_ng_client.get_energy_usage_costs = AsyncMock(
        side_effect=CannotConnectError("down")
    )
    client = _make_api_client()
    with pytest.raises(NationalGridApiClientCommunicationError):
        await client.async_get_energy_usage_costs("acct1", "2025-01-01", "KEDNY")


async def test_async_get_energy_usage_costs_generic_error(mock_ng_client) -> None:
    """Test energy usage costs generic error (includes ValueError)."""
    mock_ng_client.get_energy_usage_costs = AsyncMock(
        side_effect=NationalGridError("oops")
    )
    client = _make_api_client()
    with pytest.raises(NationalGridApiClientError):
        await client.async_get_energy_usage_costs("acct1", "2025-01-01", "KEDNY")


async def test_async_get_energy_usage_costs_value_error(mock_ng_client) -> None:
    """Test energy usage costs ValueError maps to generic error."""
    mock_ng_client.get_energy_usage_costs = AsyncMock(
        side_effect=ValueError("bad date")
    )
    client = _make_api_client()
    with pytest.raises(NationalGridApiClientError):
        await client.async_get_energy_usage_costs("acct1", "2025-01-01", "KEDNY")


async def test_async_get_interval_reads_auth_error(mock_ng_client) -> None:
    """Test interval reads auth error."""
    mock_ng_client.get_interval_reads = AsyncMock(side_effect=InvalidAuthError("bad"))
    client = _make_api_client()
    with pytest.raises(NationalGridApiClientAuthenticationError):
        await client.async_get_interval_reads("PREM1", "SP1", "2025-01-01T00:00")


async def test_async_get_interval_reads_communication_error(mock_ng_client) -> None:
    """Test interval reads communication error."""
    mock_ng_client.get_interval_reads = AsyncMock(
        side_effect=CannotConnectError("down")
    )
    client = _make_api_client()
    with pytest.raises(NationalGridApiClientCommunicationError):
        await client.async_get_interval_reads("PREM1", "SP1", "2025-01-01T00:00")


async def test_async_get_interval_reads_generic_error(mock_ng_client) -> None:
    """Test interval reads generic error."""
    mock_ng_client.get_interval_reads = AsyncMock(side_effect=NationalGridError("oops"))
    client = _make_api_client()
    with pytest.raises(NationalGridApiClientError):
        await client.async_get_interval_reads("PREM1", "SP1", "2025-01-01T00:00")


async def test_async_get_ami_energy_usages_auth_error(mock_ng_client) -> None:
    """Test AMI energy usages auth error."""
    mock_ng_client.get_ami_energy_usages = AsyncMock(
        side_effect=InvalidAuthError("bad")
    )
    client = _make_api_client()
    with pytest.raises(NationalGridApiClientAuthenticationError):
        await client.async_get_ami_energy_usages(
            meter_number="MTR1",
            premise_number="PREM1",
            service_point_number="SP1",
            meter_point_number="MPT1",
            date_from=date(2025, 1, 1),
            date_to=date(2025, 1, 2),
        )


async def test_async_get_ami_energy_usages_communication_error(mock_ng_client) -> None:
    """Test AMI energy usages communication error."""
    mock_ng_client.get_ami_energy_usages = AsyncMock(
        side_effect=CannotConnectError("down")
    )
    client = _make_api_client()
    with pytest.raises(NationalGridApiClientCommunicationError):
        await client.async_get_ami_energy_usages(
            meter_number="MTR1",
            premise_number="PREM1",
            service_point_number="SP1",
            meter_point_number="MPT1",
            date_from=date(2025, 1, 1),
            date_to=date(2025, 1, 2),
        )


async def test_async_get_ami_energy_usages_generic_error(mock_ng_client) -> None:
    """Test AMI energy usages generic error."""
    mock_ng_client.get_ami_energy_usages = AsyncMock(
        side_effect=NationalGridError("oops")
    )
    client = _make_api_client()
    with pytest.raises(NationalGridApiClientError):
        await client.async_get_ami_energy_usages(
            meter_number="MTR1",
            premise_number="PREM1",
            service_point_number="SP1",
            meter_point_number="MPT1",
            date_from=date(2025, 1, 1),
            date_to=date(2025, 1, 2),
        )


async def test_close(mock_ng_client) -> None:
    """Test close shuts down the exit stack."""
    client = _make_api_client()
    # Enter context first
    await client.async_init()
    await client.close()
    assert client._context_entered is False


async def test_close_when_not_entered(mock_ng_client) -> None:
    """Test close is safe when context was never entered."""
    client = _make_api_client()
    await client.close()
    assert client._context_entered is False


async def test_async_init_idempotent(mock_ng_client) -> None:
    """Test async_init only enters context once."""
    client = _make_api_client()
    await client.async_init()
    await client.async_init()
    # __aenter__ should only be called once
    assert mock_ng_client.__aenter__.call_count == 1
