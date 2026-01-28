"""Add config flow for nationalgrid."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import selector
from slugify import slugify

from .api import (
    NationalGridApiClient,
    NationalGridApiClientAuthenticationError,
    NationalGridApiClientCommunicationError,
    NationalGridApiClientError,
)
from .const import _LOGGER, CONF_SELECTED_ACCOUNTS, DOMAIN


class NationalGridFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for nationalgrid."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._username: str | None = None
        self._password: str | None = None
        self._accounts: list[dict[str, str]] = []

    async def async_step_user(
        self,
        user_input: dict | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle a flow initialized by the user."""
        _errors: dict[str, str] = {}
        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]

            try:
                self._accounts = await self._fetch_accounts(
                    username=self._username,
                    password=self._password,
                )
            except NationalGridApiClientAuthenticationError as exception:
                _LOGGER.warning(exception)
                _errors["base"] = "auth"
            except NationalGridApiClientCommunicationError as exception:
                _LOGGER.error(exception)
                _errors["base"] = "connection"
            except NationalGridApiClientError as exception:
                _LOGGER.exception(exception)
                _errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(slugify(self._username))
                self._abort_if_unique_id_configured()

                if len(self._accounts) == 1:
                    # Single account - skip selection and auto-select.
                    return self.async_create_entry(
                        title=self._username,
                        data={
                            CONF_USERNAME: self._username,
                            CONF_PASSWORD: self._password,
                            CONF_SELECTED_ACCOUNTS: [
                                self._accounts[0]["billingAccountId"]
                            ],
                        },
                    )
                # Multiple accounts - proceed to selection step.
                return await self.async_step_select_accounts()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=(user_input or {}).get(CONF_USERNAME, vol.UNDEFINED),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT,
                        ),
                    ),
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        ),
                    ),
                },
            ),
            errors=_errors,
        )

    async def async_step_select_accounts(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the account selection step."""
        if user_input is not None:
            selected = user_input.get(CONF_SELECTED_ACCOUNTS, [])
            if not selected:
                return self.async_show_form(
                    step_id="select_accounts",
                    data_schema=self._get_account_selection_schema(),
                    errors={"base": "no_accounts_selected"},
                )

            return self.async_create_entry(
                title=self._username,
                data={
                    CONF_USERNAME: self._username,
                    CONF_PASSWORD: self._password,
                    CONF_SELECTED_ACCOUNTS: selected,
                },
            )

        return self.async_show_form(
            step_id="select_accounts",
            data_schema=self._get_account_selection_schema(),
        )

    async def async_step_reauth(
        self,
        entry_data: dict[str, Any],
    ) -> config_entries.ConfigFlowResult:
        """Handle re-authentication."""
        self._username = entry_data.get(CONF_USERNAME)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle re-authentication confirmation."""
        _errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            try:
                await self._fetch_accounts(
                    username=username,
                    password=password,
                )
            except NationalGridApiClientAuthenticationError as exception:
                _LOGGER.warning(exception)
                _errors["base"] = "auth"
            except NationalGridApiClientCommunicationError as exception:
                _LOGGER.error(exception)
                _errors["base"] = "connection"
            except NationalGridApiClientError as exception:
                _LOGGER.exception(exception)
                _errors["base"] = "unknown"
            else:
                reauth_entry = self._get_reauth_entry()
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={
                        **reauth_entry.data,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=self._username or vol.UNDEFINED,
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT,
                        ),
                    ),
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        ),
                    ),
                },
            ),
            errors=_errors,
        )

    def _get_account_selection_schema(self) -> vol.Schema:
        """Get the schema for account selection."""
        account_options = [
            selector.SelectOptionDict(
                value=account["billingAccountId"],
                label=f"Account {account['billingAccountId']}",
            )
            for account in self._accounts
        ]

        return vol.Schema(
            {
                vol.Required(CONF_SELECTED_ACCOUNTS): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=account_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    ),
                ),
            }
        )

    async def _fetch_accounts(
        self, username: str, password: str
    ) -> list[dict[str, str]]:
        """Fetch linked accounts from the API."""
        client = NationalGridApiClient(
            username=username,
            password=password,
        )
        try:
            accounts = await client.async_get_linked_accounts()
            # Convert to plain dicts for storage.
            return [dict(account) for account in accounts]
        finally:
            await client.close()
