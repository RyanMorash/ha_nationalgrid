"""Tests for the National Grid config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from aionatgrid.exceptions import (
    CannotConnectError,
    InvalidAuthError,
    NationalGridError,
)
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nationalgrid.const import CONF_SELECTED_ACCOUNTS, DOMAIN

from .conftest import (
    MOCK_ACCOUNT_ID,
    MOCK_ACCOUNT_ID_2,
    MOCK_PASSWORD,
    MOCK_USERNAME,
)

PATCH_CLIENT = "custom_components.nationalgrid.config_flow.NationalGridClient"


async def test_user_step_shows_form(hass: HomeAssistant) -> None:
    """Test that the user step shows a form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_step_single_account(hass: HomeAssistant) -> None:
    """Test user step with a single account creates entry directly."""
    with patch(PATCH_CLIENT) as mock_cls:
        client = mock_cls.return_value
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get_linked_accounts = AsyncMock(
            return_value=[{"billingAccountId": MOCK_ACCOUNT_ID}],
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_USERNAME: MOCK_USERNAME,
                CONF_PASSWORD: MOCK_PASSWORD,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == MOCK_USERNAME
    assert result["data"][CONF_USERNAME] == MOCK_USERNAME
    assert result["data"][CONF_PASSWORD] == MOCK_PASSWORD
    assert result["data"][CONF_SELECTED_ACCOUNTS] == [MOCK_ACCOUNT_ID]


async def test_user_step_multiple_accounts(hass: HomeAssistant) -> None:
    """Test user step with multiple accounts moves to select_accounts."""
    with patch(PATCH_CLIENT) as mock_cls:
        client = mock_cls.return_value
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get_linked_accounts = AsyncMock(
            return_value=[
                {"billingAccountId": MOCK_ACCOUNT_ID},
                {"billingAccountId": MOCK_ACCOUNT_ID_2},
            ],
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_USERNAME: MOCK_USERNAME,
                CONF_PASSWORD: MOCK_PASSWORD,
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "select_accounts"


async def test_user_step_auth_error(hass: HomeAssistant) -> None:
    """Test user step with authentication error."""
    with patch(PATCH_CLIENT) as mock_cls:
        client = mock_cls.return_value
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get_linked_accounts = AsyncMock(
            side_effect=InvalidAuthError("Bad creds"),
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_USERNAME: MOCK_USERNAME,
                CONF_PASSWORD: MOCK_PASSWORD,
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "auth"


async def test_user_step_communication_error(hass: HomeAssistant) -> None:
    """Test user step with communication error."""
    with patch(PATCH_CLIENT) as mock_cls:
        client = mock_cls.return_value
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get_linked_accounts = AsyncMock(
            side_effect=CannotConnectError("Timeout"),
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_USERNAME: MOCK_USERNAME,
                CONF_PASSWORD: MOCK_PASSWORD,
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "connection"


async def test_user_step_unknown_error(hass: HomeAssistant) -> None:
    """Test user step with unknown error."""
    with patch(PATCH_CLIENT) as mock_cls:
        client = mock_cls.return_value
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get_linked_accounts = AsyncMock(
            side_effect=NationalGridError("Something broke"),
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_USERNAME: MOCK_USERNAME,
                CONF_PASSWORD: MOCK_PASSWORD,
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "unknown"


async def test_select_accounts_step(hass: HomeAssistant) -> None:
    """Test selecting accounts creates entry."""
    with patch(PATCH_CLIENT) as mock_cls:
        client = mock_cls.return_value
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get_linked_accounts = AsyncMock(
            return_value=[
                {"billingAccountId": MOCK_ACCOUNT_ID},
                {"billingAccountId": MOCK_ACCOUNT_ID_2},
            ],
        )

        # First step: provide credentials
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_USERNAME: MOCK_USERNAME,
                CONF_PASSWORD: MOCK_PASSWORD,
            },
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "select_accounts"

        # Second step: select accounts
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_SELECTED_ACCOUNTS: [MOCK_ACCOUNT_ID]},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SELECTED_ACCOUNTS] == [MOCK_ACCOUNT_ID]


async def test_select_accounts_none_selected(hass: HomeAssistant) -> None:
    """Test selecting no accounts shows error."""
    with patch(PATCH_CLIENT) as mock_cls:
        client = mock_cls.return_value
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get_linked_accounts = AsyncMock(
            return_value=[
                {"billingAccountId": MOCK_ACCOUNT_ID},
                {"billingAccountId": MOCK_ACCOUNT_ID_2},
            ],
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_USERNAME: MOCK_USERNAME,
                CONF_PASSWORD: MOCK_PASSWORD,
            },
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_SELECTED_ACCOUNTS: []},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "no_accounts_selected"


async def test_reauth_flow(hass: HomeAssistant) -> None:
    """Test the reauthentication flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=MOCK_USERNAME,
        data={
            CONF_USERNAME: MOCK_USERNAME,
            CONF_PASSWORD: "old_password",
            CONF_SELECTED_ACCOUNTS: [MOCK_ACCOUNT_ID],
        },
        unique_id="testuser-example-com",
    )
    entry.add_to_hass(hass)

    with patch(PATCH_CLIENT) as mock_cls:
        client = mock_cls.return_value
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get_linked_accounts = AsyncMock(
            return_value=[{"billingAccountId": MOCK_ACCOUNT_ID}],
        )

        result = await entry.start_reauth_flow(hass)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: MOCK_USERNAME,
                CONF_PASSWORD: "new_password",
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new_password"


async def test_already_configured(hass: HomeAssistant) -> None:
    """Test that duplicate unique_id aborts."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=MOCK_USERNAME,
        data={
            CONF_USERNAME: MOCK_USERNAME,
            CONF_PASSWORD: MOCK_PASSWORD,
            CONF_SELECTED_ACCOUNTS: [MOCK_ACCOUNT_ID],
        },
        unique_id="testuser-example-com",
    )
    entry.add_to_hass(hass)

    with patch(PATCH_CLIENT) as mock_cls:
        client = mock_cls.return_value
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get_linked_accounts = AsyncMock(
            return_value=[{"billingAccountId": MOCK_ACCOUNT_ID}],
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_USERNAME: MOCK_USERNAME,
                CONF_PASSWORD: MOCK_PASSWORD,
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
