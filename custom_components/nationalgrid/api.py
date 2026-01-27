"""National Grid API Client wrapper around aionatgrid."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aionatgrid import NationalGridClient, NationalGridConfig
from aionatgrid.exceptions import (
    CannotConnectError,
    InvalidAuthError,
    NationalGridError,
)

if TYPE_CHECKING:
    from datetime import date

    from aionatgrid.models import (
        AccountLink,
        BillingAccount,
        EnergyUsage,
        EnergyUsageCost,
        IntervalRead,
    )


class NationalGridApiClientError(Exception):
    """Exception to indicate a general API error."""


class NationalGridApiClientCommunicationError(NationalGridApiClientError):
    """Exception to indicate a communication error."""


class NationalGridApiClientAuthenticationError(NationalGridApiClientError):
    """Exception to indicate an authentication error."""


class NationalGridApiClient:
    """Wrapper around aionatgrid.NationalGridClient for Home Assistant."""

    def __init__(
        self,
        username: str,
        password: str,
    ) -> None:
        """Initialize the API client."""
        self._config = NationalGridConfig(username=username, password=password)
        # Don't pass a session - let the library create its own with proper
        # cookie jar configuration for Azure AD B2C authentication
        self._client = NationalGridClient(config=self._config)
        self._context_entered = False

    async def async_init(self) -> None:
        """Initialize the client by entering the async context."""
        if not self._context_entered:
            await self._client.__aenter__()
            self._context_entered = True

    async def async_get_linked_accounts(self) -> list[AccountLink]:
        """Get all linked billing accounts."""
        await self.async_init()
        try:
            return await self._client.get_linked_accounts()
        except InvalidAuthError as err:
            msg = "Invalid credentials"
            raise NationalGridApiClientAuthenticationError(msg) from err
        except CannotConnectError as err:
            msg = f"Unable to connect to National Grid: {err}"
            raise NationalGridApiClientCommunicationError(msg) from err
        except NationalGridError as err:
            msg = f"Error fetching linked accounts: {err}"
            raise NationalGridApiClientError(msg) from err

    async def async_get_billing_account(self, account_number: str) -> BillingAccount:
        """Get billing account information."""
        await self.async_init()
        try:
            return await self._client.get_billing_account(account_number)
        except InvalidAuthError as err:
            msg = "Invalid credentials"
            raise NationalGridApiClientAuthenticationError(msg) from err
        except CannotConnectError as err:
            msg = f"Unable to connect to National Grid: {err}"
            raise NationalGridApiClientCommunicationError(msg) from err
        except NationalGridError as err:
            msg = f"Error fetching billing account {account_number}: {err}"
            raise NationalGridApiClientError(msg) from err

    async def async_get_energy_usages(
        self,
        account_number: str,
        from_month: int,
        first: int = 12,
    ) -> list[EnergyUsage]:
        """Get historical energy usages."""
        await self.async_init()
        try:
            return await self._client.get_energy_usages(
                account_number=account_number,
                from_month=from_month,
                first=first,
            )
        except InvalidAuthError as err:
            msg = "Invalid credentials"
            raise NationalGridApiClientAuthenticationError(msg) from err
        except CannotConnectError as err:
            msg = f"Unable to connect to National Grid: {err}"
            raise NationalGridApiClientCommunicationError(msg) from err
        except NationalGridError as err:
            msg = f"Error fetching energy usages: {err}"
            raise NationalGridApiClientError(msg) from err

    async def async_get_energy_usage_costs(
        self,
        account_number: str,
        query_date: date | str,
        company_code: str,
    ) -> list[EnergyUsageCost]:
        """Get energy usage costs."""
        await self.async_init()
        try:
            return await self._client.get_energy_usage_costs(
                account_number=account_number,
                query_date=query_date,
                company_code=company_code,
            )
        except InvalidAuthError as err:
            msg = "Invalid credentials"
            raise NationalGridApiClientAuthenticationError(msg) from err
        except CannotConnectError as err:
            msg = f"Unable to connect to National Grid: {err}"
            raise NationalGridApiClientCommunicationError(msg) from err
        except (NationalGridError, ValueError) as err:
            msg = f"Error fetching energy usage costs: {err}"
            raise NationalGridApiClientError(msg) from err

    async def async_get_interval_reads(
        self,
        premise_number: str,
        service_point_number: str,
        start_datetime: str,
    ) -> list[IntervalRead]:
        """Get smart meter interval reads."""
        await self.async_init()
        try:
            return await self._client.get_interval_reads(
                premise_number=premise_number,
                service_point_number=service_point_number,
                start_datetime=start_datetime,
            )
        except InvalidAuthError as err:
            msg = "Invalid credentials"
            raise NationalGridApiClientAuthenticationError(msg) from err
        except CannotConnectError as err:
            msg = f"Unable to connect to National Grid: {err}"
            raise NationalGridApiClientCommunicationError(msg) from err
        except NationalGridError as err:
            msg = f"Error fetching interval reads: {err}"
            raise NationalGridApiClientError(msg) from err

    async def close(self) -> None:
        """Close the client session."""
        if self._context_entered:
            await self._client.__aexit__(None, None, None)
            self._context_entered = False
