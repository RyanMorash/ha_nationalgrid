"""DataUpdateCoordinator for nationalgrid."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    NationalGridApiClientAuthenticationError,
    NationalGridApiClientError,
)
from .const import CONF_SELECTED_ACCOUNTS, LOGGER

if TYPE_CHECKING:
    from aionatgrid.models import (
        BillingAccount,
        EnergyUsage,
        EnergyUsageCost,
        Meter,
    )

    from .data import NationalGridConfigEntry


@dataclass
class MeterData:
    """Data for a single meter."""

    meter: Meter
    account_id: str
    billing_account: BillingAccount


@dataclass
class NationalGridCoordinatorData:
    """Data returned by the coordinator."""

    accounts: dict[str, BillingAccount]
    meters: dict[str, MeterData]
    usages: dict[str, list[EnergyUsage]]
    costs: dict[str, list[EnergyUsageCost]]


class NationalGridDataUpdateCoordinator(
    DataUpdateCoordinator[NationalGridCoordinatorData]
):
    """Class to manage fetching data from the API."""

    config_entry: NationalGridConfigEntry

    async def _async_update_data(self) -> NationalGridCoordinatorData:
        """Update data via library."""
        try:
            return await self._fetch_all_data()
        except NationalGridApiClientAuthenticationError as exception:
            raise ConfigEntryAuthFailed(exception) from exception
        except NationalGridApiClientError as exception:
            raise UpdateFailed(exception) from exception

    async def _fetch_all_data(self) -> NationalGridCoordinatorData:
        """Fetch all data from the API."""
        client = self.config_entry.runtime_data.client
        selected_accounts: list[str] = self.config_entry.data.get(
            CONF_SELECTED_ACCOUNTS, []
        )

        accounts: dict[str, BillingAccount] = {}
        meters: dict[str, MeterData] = {}
        usages: dict[str, list[EnergyUsage]] = {}
        costs: dict[str, list[EnergyUsageCost]] = {}

        # Calculate from_month for usage query (12 months back)
        today = datetime.now(tz=UTC).date()
        from_month = (today.year - 1) * 100 + today.month

        for account_id in selected_accounts:
            try:
                # Fetch billing account info
                billing_account = await client.async_get_billing_account(account_id)
                accounts[account_id] = billing_account

                # Extract meters from the billing account
                meter_nodes = billing_account.get("meter", {}).get("nodes", [])
                for meter in meter_nodes:
                    service_point = str(meter.get("servicePointNumber", ""))
                    if service_point:
                        meters[service_point] = MeterData(
                            meter=meter,
                            account_id=account_id,
                            billing_account=billing_account,
                        )

                # Fetch energy usages
                try:
                    account_usages = await client.async_get_energy_usages(
                        account_number=account_id,
                        from_month=from_month,
                        first=12,
                    )
                    usages[account_id] = account_usages
                except NationalGridApiClientError:
                    LOGGER.debug(
                        "Could not fetch energy usages for account %s", account_id
                    )
                    usages[account_id] = []

                # Fetch energy costs (company_code is the region from billing account)
                try:
                    region = billing_account.get("region", "")
                    if region:
                        account_costs = await client.async_get_energy_usage_costs(
                            account_number=account_id,
                            query_date=today,
                            company_code=region,
                        )
                        costs[account_id] = account_costs
                    else:
                        LOGGER.debug(
                            "No region for account %s, skipping costs", account_id
                        )
                        costs[account_id] = []
                except NationalGridApiClientError as err:
                    LOGGER.debug(
                        "Could not fetch energy costs for account %s: %s",
                        account_id,
                        err,
                    )
                    costs[account_id] = []

            except NationalGridApiClientAuthenticationError:
                # Re-raise auth errors to trigger reauth flow
                raise
            except NationalGridApiClientError as err:
                LOGGER.warning(
                    "Error fetching data for account %s: %s", account_id, err
                )
                continue

        return NationalGridCoordinatorData(
            accounts=accounts,
            meters=meters,
            usages=usages,
            costs=costs,
        )

    def get_meter_data(self, service_point_number: str) -> MeterData | None:
        """Get meter data by service point number."""
        if self.data is None:
            return None
        return self.data.meters.get(service_point_number)

    def get_latest_usage(
        self, account_id: str, fuel_type: str | None = None
    ) -> EnergyUsage | None:
        """Get the most recent energy usage for an account."""
        if self.data is None:
            return None
        account_usages = self.data.usages.get(account_id, [])
        if not account_usages:
            return None

        # Filter by fuel type if specified
        filtered = account_usages
        if fuel_type:
            filtered = [u for u in account_usages if u.get("usageType") == fuel_type]

        if not filtered:
            return None

        # Return most recent (highest usageYearMonth)
        return max(filtered, key=lambda u: u.get("usageYearMonth", 0))

    def get_latest_cost(
        self, account_id: str, fuel_type: str | None = None
    ) -> EnergyUsageCost | None:
        """Get the most recent energy cost for an account."""
        if self.data is None:
            return None
        account_costs = self.data.costs.get(account_id, [])
        if not account_costs:
            return None

        # Filter by fuel type if specified
        filtered = account_costs
        if fuel_type:
            filtered = [c for c in account_costs if c.get("fuelType") == fuel_type]

        if not filtered:
            return None

        # Return most recent (highest month)
        return max(filtered, key=lambda c: c.get("month", 0))
