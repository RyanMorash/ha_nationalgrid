"""National Grid API Client wrapper around aionatgrid."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import TYPE_CHECKING

import aiohttp
from aionatgrid import NationalGridClient, NationalGridConfig, create_cookie_jar
from aionatgrid.exceptions import (
    CannotConnectError,
    InvalidAuthError,
    NationalGridError,
    RetryExhaustedError,
)

if TYPE_CHECKING:
    from datetime import date

    from aionatgrid.models import (
        AccountLink,
        AmiEnergyUsage,
        BillingAccount,
        EnergyUsage,
        EnergyUsageCost,
        IntervalRead,
    )


@dataclass(frozen=True)
class AmiMeterIdentifier:
    """Identify an AMI smart meter for data queries."""

    meter_number: str
    premise_number: str
    service_point_number: str
    meter_point_number: str


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
        # Pass a session with a cookie jar configured for Azure AD B2C.
        # The library's _ensure_session creates sessions without cookie jars,
        # but B2C auth requires quote_cookie=False for OIDC cookie handling.
        self._session = aiohttp.ClientSession(cookie_jar=create_cookie_jar())
        self._client = NationalGridClient(config=self._config, session=self._session)
        self._exit_stack = AsyncExitStack()
        self._context_entered = False
        self._init_lock = asyncio.Lock()

    async def async_init(self) -> None:
        """Initialize the client by entering the async context."""
        if not self._context_entered:
            async with self._init_lock:
                if not self._context_entered:
                    await self._exit_stack.enter_async_context(self._client)
                    self._context_entered = True

    async def async_get_linked_accounts(self) -> list[AccountLink]:
        """Get all linked billing accounts."""
        await self.async_init()
        try:
            return await self._client.get_linked_accounts()
        except InvalidAuthError as err:
            msg = "Invalid credentials"
            raise NationalGridApiClientAuthenticationError(msg) from err
        except (CannotConnectError, RetryExhaustedError) as err:
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
        except (CannotConnectError, RetryExhaustedError) as err:
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
        except (CannotConnectError, RetryExhaustedError) as err:
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
        except (CannotConnectError, RetryExhaustedError) as err:
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
        except (CannotConnectError, RetryExhaustedError) as err:
            msg = f"Unable to connect to National Grid: {err}"
            raise NationalGridApiClientCommunicationError(msg) from err
        except NationalGridError as err:
            msg = f"Error fetching interval reads: {err}"
            raise NationalGridApiClientError(msg) from err

    async def async_get_ami_energy_usages(
        self,
        meter: AmiMeterIdentifier,
        date_from: date,
        date_to: date,
    ) -> list[AmiEnergyUsage]:
        """Get AMI smart meter energy usages."""
        await self.async_init()
        try:
            return await self._client.get_ami_energy_usages(
                meter_number=meter.meter_number,
                premise_number=meter.premise_number,
                service_point_number=meter.service_point_number,
                meter_point_number=meter.meter_point_number,
                date_from=date_from,
                date_to=date_to,
            )
        except InvalidAuthError as err:
            msg = "Invalid credentials"
            raise NationalGridApiClientAuthenticationError(msg) from err
        except (CannotConnectError, RetryExhaustedError) as err:
            msg = f"Unable to connect to National Grid: {err}"
            raise NationalGridApiClientCommunicationError(msg) from err
        except NationalGridError as err:
            msg = f"Error fetching AMI energy usages: {err}"
            raise NationalGridApiClientError(msg) from err

    async def close(self) -> None:
        """Close the client session."""
        if self._context_entered:
            await self._exit_stack.aclose()
            self._context_entered = False
        if self._session and not self._session.closed:
            await self._session.close()
