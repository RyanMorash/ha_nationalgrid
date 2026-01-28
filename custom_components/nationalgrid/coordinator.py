"""DataUpdateCoordinator for nationalgrid."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    NationalGridApiClient,
    NationalGridApiClientAuthenticationError,
    NationalGridApiClientError,
)
from .const import CONF_SELECTED_ACCOUNTS, LOGGER

if TYPE_CHECKING:
    import logging

    from aionatgrid.models import (
        AmiEnergyUsage,
        BillingAccount,
        EnergyUsage,
        EnergyUsageCost,
        IntervalRead,
        Meter,
    )
    from homeassistant.core import HomeAssistant

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
    ami_usages: dict[str, list[AmiEnergyUsage]] = field(default_factory=dict)
    interval_reads: dict[str, list[IntervalRead]] = field(default_factory=dict)


class NationalGridDataUpdateCoordinator(
    DataUpdateCoordinator[NationalGridCoordinatorData]
):
    """Class to manage fetching data from the API."""

    config_entry: NationalGridConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        name: str,
        update_interval: timedelta,
        client: NationalGridApiClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(hass, logger, name=name, update_interval=update_interval)
        self.client = client

    async def _async_update_data(self) -> NationalGridCoordinatorData:
        """Update data via library."""
        try:
            data = await self._fetch_all_data()
        except NationalGridApiClientAuthenticationError as exception:
            raise ConfigEntryAuthFailed(exception) from exception
        except NationalGridApiClientError as exception:
            raise UpdateFailed(exception) from exception

        return data

    async def _fetch_all_data(self) -> NationalGridCoordinatorData:  # noqa: PLR0915
        """Fetch all data from the API."""
        client = self.client
        selected_accounts: list[str] = self.config_entry.data.get(
            CONF_SELECTED_ACCOUNTS, []
        )

        LOGGER.debug("Fetching data for accounts: %s", selected_accounts)

        # Seed from previous data to preserve stale data on per-account errors
        prev = self.data
        accounts: dict[str, BillingAccount] = dict(prev.accounts) if prev else {}
        meters: dict[str, MeterData] = dict(prev.meters) if prev else {}
        usages: dict[str, list[EnergyUsage]] = dict(prev.usages) if prev else {}
        costs: dict[str, list[EnergyUsageCost]] = dict(prev.costs) if prev else {}
        ami_usages: dict[str, list[AmiEnergyUsage]] = (
            dict(prev.ami_usages) if prev else {}
        )
        interval_reads: dict[str, list[IntervalRead]] = (
            dict(prev.interval_reads) if prev else {}
        )

        # Calculate from_month for usage query (12 months back)
        today = datetime.now(tz=UTC).date()
        from_month = (today.year - 1) * 100 + today.month
        LOGGER.debug("Fetching usages from month: %s", from_month)

        for account_id in selected_accounts:
            try:
                # Fetch billing account info
                LOGGER.debug("Fetching billing account: %s", account_id)
                billing_account = await client.async_get_billing_account(account_id)
                accounts[account_id] = billing_account
                LOGGER.debug(
                    "Billing account %s: region=%s, meters=%s",
                    account_id,
                    billing_account.get("region"),
                    len(billing_account.get("meter", {}).get("nodes", [])),
                )

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
                        LOGGER.debug(
                            "Found meter: service_point=%s, fuel_type=%s",
                            service_point,
                            meter.get("fuelType"),
                        )

                # Fetch energy usages
                try:
                    account_usages = await client.async_get_energy_usages(
                        account_number=account_id,
                        from_month=from_month,
                        first=12,
                    )
                    usages[account_id] = account_usages
                    LOGGER.debug(
                        "Fetched %s usage records for account %s, types: %s",
                        len(account_usages),
                        account_id,
                        {u.get("usageType") for u in account_usages},
                    )
                except NationalGridApiClientError as err:
                    LOGGER.debug(
                        "Could not fetch energy usages for account %s: %s",
                        account_id,
                        err,
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
                        LOGGER.debug(
                            "Fetched %s cost records for account %s",
                            len(account_costs),
                            account_id,
                        )
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

                # Fetch AMI energy usages for AMI-capable meters
                await self._fetch_ami_data(
                    billing_account,
                    meter_nodes,
                    today,
                    ami_usages,
                    interval_reads,
                )

            except NationalGridApiClientAuthenticationError:
                # Re-raise auth errors to trigger reauth flow
                raise
            except NationalGridApiClientError as err:
                LOGGER.warning(
                    "Error fetching data for account %s: %s", account_id, err
                )
                continue

        LOGGER.debug(
            "Fetch complete: %s accounts, %s meters, %s usage records, "
            "%s cost records, %s AMI usage records, %s interval reads",
            len(accounts),
            len(meters),
            sum(len(u) for u in usages.values()),
            sum(len(c) for c in costs.values()),
            sum(len(a) for a in ami_usages.values()),
            sum(len(r) for r in interval_reads.values()),
        )

        return NationalGridCoordinatorData(
            accounts=accounts,
            meters=meters,
            usages=usages,
            costs=costs,
            ami_usages=ami_usages,
            interval_reads=interval_reads,
        )

    async def _fetch_ami_data(
        self,
        billing_account: BillingAccount,
        meter_nodes: list[Meter],
        today: date,
        ami_usages: dict[str, list[AmiEnergyUsage]],
        interval_reads: dict[str, list[IntervalRead]],
    ) -> None:
        """Fetch AMI energy usages for AMI-capable meters."""
        client = self.client
        premise_number = billing_account.get("premiseNumber", "")
        for meter in meter_nodes:
            if not meter.get("hasAmiSmartMeter"):
                continue
            sp = str(meter.get("servicePointNumber", ""))
            if not sp:
                continue
            try:
                date_to = today - timedelta(days=3)
                date_from = today - timedelta(days=10)
                ami_data = await client.async_get_ami_energy_usages(
                    meter_number=str(meter.get("meterNumber", "")),
                    premise_number=premise_number,
                    service_point_number=sp,
                    meter_point_number=str(meter.get("meterPointNumber", "")),
                    date_from=date_from,
                    date_to=date_to,
                )
                ami_usages[sp] = ami_data
                LOGGER.debug(
                    "Fetched %s AMI usage records for meter %s",
                    len(ami_data),
                    sp,
                )
            except NationalGridApiClientError as err:
                LOGGER.debug(
                    "Could not fetch AMI usages for meter %s: %s",
                    sp,
                    err,
                )

            # Fetch interval reads for electric meters only
            fuel_type = str(meter.get("fuelType", ""))
            if fuel_type == "Gas":
                continue
            try:
                now = datetime.now(tz=UTC)
                start_dt = now - timedelta(hours=24)
                reads = await client.async_get_interval_reads(
                    premise_number=premise_number,
                    service_point_number=sp,
                    start_datetime=start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                )
                interval_reads[sp] = reads
                LOGGER.debug(
                    "Fetched %s interval reads for meter %s",
                    len(reads),
                    sp,
                )
            except NationalGridApiClientError as err:
                LOGGER.debug(
                    "Could not fetch interval reads for meter %s: %s",
                    sp,
                    err,
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
        # Map meter fuel type to usage type: Electric->KWH, Gas->THERMS
        filtered = account_usages
        if fuel_type:
            usage_type_map = {
                "Electric": "TOTAL_KWH",
                "Gas": "THERMS",
            }
            usage_type = usage_type_map.get(fuel_type, fuel_type.upper())
            filtered = [u for u in account_usages if u.get("usageType") == usage_type]
            LOGGER.debug(
                "Filtering usages: fuel_type=%s -> usage_type=%s, found %s matches",
                fuel_type,
                usage_type,
                len(filtered),
            )

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
        # Cost records use fuelType field which may be "ELECTRIC" or "GAS" (uppercase)
        filtered = account_costs
        if fuel_type:
            # Try exact match first, then uppercase match
            filtered = [
                c
                for c in account_costs
                if c.get("fuelType") == fuel_type
                or c.get("fuelType") == fuel_type.upper()
            ]

        if not filtered:
            return None

        # Return most recent (highest month)
        return max(filtered, key=lambda c: c.get("month", 0))

    def get_all_usages(
        self, account_id: str, fuel_type: str | None = None
    ) -> list[EnergyUsage]:
        """Get all energy usages for an account, filtered by fuel type."""
        if self.data is None:
            return []
        account_usages = self.data.usages.get(account_id, [])
        if not account_usages:
            return []

        # Filter by fuel type if specified
        if fuel_type:
            usage_type_map = {
                "Electric": "TOTAL_KWH",
                "Gas": "THERMS",
            }
            usage_type = usage_type_map.get(fuel_type, fuel_type.upper())
            return [u for u in account_usages if u.get("usageType") == usage_type]

        return list(account_usages)

    def get_all_costs(
        self, account_id: str, fuel_type: str | None = None
    ) -> list[EnergyUsageCost]:
        """Get all energy costs for an account, filtered by fuel type."""
        if self.data is None:
            return []
        account_costs = self.data.costs.get(account_id, [])
        if not account_costs:
            return []

        # Filter by fuel type if specified
        if fuel_type:
            return [
                c
                for c in account_costs
                if c.get("fuelType") == fuel_type
                or c.get("fuelType") == fuel_type.upper()
            ]

        return list(account_costs)

    def get_latest_ami_usage(self, service_point_number: str) -> AmiEnergyUsage | None:
        """Get the most recent AMI usage reading for a service point."""
        if self.data is None:
            return None
        readings = self.data.ami_usages.get(service_point_number, [])
        if not readings:
            return None
        return max(readings, key=lambda r: r.get("date", ""))
