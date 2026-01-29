"""DataUpdateCoordinator for national_grid."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

from aionatgrid import NationalGridClient, NationalGridConfig, create_cookie_jar
from aionatgrid.exceptions import (
    CannotConnectError,
    InvalidAuthError,
    NationalGridError,
    RetryExhaustedError,
)
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import _LOGGER, CONF_SELECTED_ACCOUNTS

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


@dataclass(frozen=True)
class AmiMeterIdentifier:
    """Identify an AMI smart meter for data queries."""

    meter_number: str
    premise_number: str
    service_point_number: str
    meter_point_number: str


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
    ami_usages: dict[str, list[AmiEnergyUsage]] = field(default_factory=dict)
    costs: dict[str, list[EnergyUsageCost]] = field(default_factory=dict)
    interval_reads: dict[str, list[IntervalRead]] = field(default_factory=dict)
    meters: dict[str, MeterData] = field(default_factory=dict)
    usages: dict[str, list[EnergyUsage]] = field(default_factory=dict)


class NationalGridDataUpdateCoordinator(
    DataUpdateCoordinator[NationalGridCoordinatorData]
):
    """Class to manage fetching data from the API."""

    config_entry: NationalGridConfigEntry

    def __init__(  # noqa: PLR0913
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        name: str,
        update_interval: timedelta,
        username: str,
        password: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(hass, logger, name=name, update_interval=update_interval)
        session = async_create_clientsession(hass, cookie_jar=create_cookie_jar())
        self.api = NationalGridClient(
            config=NationalGridConfig(username=username, password=password),
            session=session,
        )
        self._last_update_success = True

    async def _async_update_data(self) -> NationalGridCoordinatorData:
        """Update data via library."""
        try:
            data = await self._fetch_all_data()
        except InvalidAuthError as exception:
            raise ConfigEntryAuthFailed(exception) from exception
        except (
            CannotConnectError,
            RetryExhaustedError,
            NationalGridError,
        ) as exception:
            if self._last_update_success:
                _LOGGER.warning("National Grid service unavailable: %s", exception)
            self._last_update_success = False
            raise UpdateFailed(exception) from exception

        if not self._last_update_success:
            _LOGGER.info("National Grid service recovered")
        self._last_update_success = True
        return data

    async def _fetch_all_data(self) -> NationalGridCoordinatorData:
        """Fetch all data from the API."""
        selected_accounts: list[str] = self.config_entry.data.get(
            CONF_SELECTED_ACCOUNTS, []
        )
        _LOGGER.debug("Fetching data for accounts: %s", selected_accounts)

        # Seed from previous data to preserve stale data on per-account errors.
        data = self._seed_from_previous()

        # Calculate from_month for usage query (12 months back).
        today = datetime.now(tz=UTC).date()
        from_month = (today.year - 1) * 100 + today.month
        _LOGGER.debug("Fetching usages from month: %s", from_month)

        for account_id in selected_accounts:
            try:
                await self._fetch_account_data(account_id, today, from_month, data)
            except InvalidAuthError:
                # Re-raise auth errors to trigger reauth flow.
                raise
            except (
                CannotConnectError,
                RetryExhaustedError,
                NationalGridError,
            ) as err:
                _LOGGER.warning(
                    "Error fetching data for account %s: %s", account_id, err
                )
                continue

        _LOGGER.debug(
            "Fetch complete: %s accounts, %s meters, %s usage records, "
            "%s cost records, %s AMI usage records, %s interval reads",
            len(data.accounts),
            len(data.meters),
            sum(len(u) for u in data.usages.values()),
            sum(len(c) for c in data.costs.values()),
            sum(len(a) for a in data.ami_usages.values()),
            sum(len(r) for r in data.interval_reads.values()),
        )

        return data

    def _seed_from_previous(self) -> NationalGridCoordinatorData:
        """Create coordinator data seeded from previous fetch results."""
        prev = self.data
        if prev is None:
            return NationalGridCoordinatorData(accounts={})
        return NationalGridCoordinatorData(
            accounts=dict(prev.accounts),
            ami_usages=dict(prev.ami_usages),
            costs=dict(prev.costs),
            interval_reads=dict(prev.interval_reads),
            meters=dict(prev.meters),
            usages=dict(prev.usages),
        )

    async def _fetch_account_data(
        self,
        account_id: str,
        today: date,
        from_month: int,
        data: NationalGridCoordinatorData,
    ) -> None:
        """Fetch billing, usage, cost, and AMI data for a single account."""
        # Fetch billing account info.
        _LOGGER.debug("Fetching billing account: %s", account_id)
        billing_account = await self.api.get_billing_account(account_id)
        data.accounts[account_id] = billing_account
        _LOGGER.debug(
            "Billing account %s: region=%s, meters=%s",
            account_id,
            billing_account.get("region"),
            len(billing_account.get("meter", {}).get("nodes", [])),
        )

        # Extract meters from the billing account.
        meter_nodes = billing_account.get("meter", {}).get("nodes", [])
        for meter in meter_nodes:
            service_point = str(meter.get("servicePointNumber", ""))
            if service_point:
                data.meters[service_point] = MeterData(
                    meter=meter,
                    account_id=account_id,
                    billing_account=billing_account,
                )
                _LOGGER.debug(
                    "Found meter: service_point=%s, fuel_type=%s",
                    service_point,
                    meter.get("fuelType"),
                )

        # Fetch energy usages.
        data.usages[account_id] = await self._fetch_usages(account_id, from_month)

        # Fetch energy costs (company_code is the region from billing account).
        data.costs[account_id] = await self._fetch_costs(
            account_id, today, billing_account
        )

        # Fetch AMI energy usages for AMI-capable meters.
        await self._fetch_ami_data(
            billing_account,
            meter_nodes,
            today,
            data.ami_usages,
            data.interval_reads,
        )

    async def _fetch_usages(
        self, account_id: str, from_month: int
    ) -> list[EnergyUsage]:
        """Fetch energy usages for an account, returning empty list on error."""
        try:
            account_usages = await self.api.get_energy_usages(
                account_number=account_id,
                from_month=from_month,
                first=12,
            )
            _LOGGER.debug(
                "Fetched %s usage records for account %s, types: %s",
                len(account_usages),
                account_id,
                {u.get("usageType") for u in account_usages},
            )
        except (
            CannotConnectError,
            RetryExhaustedError,
            NationalGridError,
        ) as err:
            _LOGGER.debug(
                "Could not fetch energy usages for account %s: %s",
                account_id,
                err,
            )
            return []
        else:
            return account_usages

    async def _fetch_costs(
        self,
        account_id: str,
        today: date,
        billing_account: BillingAccount,
    ) -> list[EnergyUsageCost]:
        """Fetch energy costs for an account, returning empty list on error."""
        try:
            region = billing_account.get("region", "")
            if not region:
                _LOGGER.debug("No region for account %s, skipping costs", account_id)
                return []
            account_costs = await self.api.get_energy_usage_costs(
                account_number=account_id,
                query_date=today,
                company_code=region,
            )
            _LOGGER.debug(
                "Fetched %s cost records for account %s",
                len(account_costs),
                account_id,
            )
        except (
            CannotConnectError,
            RetryExhaustedError,
            NationalGridError,
            ValueError,
        ) as err:
            _LOGGER.debug(
                "Could not fetch energy costs for account %s: %s",
                account_id,
                err,
            )
            return []
        else:
            return account_costs

    async def _fetch_ami_data(
        self,
        billing_account: BillingAccount,
        meter_nodes: list[Meter],
        today: date,
        ami_usages: dict[str, list[AmiEnergyUsage]],
        interval_reads: dict[str, list[IntervalRead]],
    ) -> None:
        """Fetch AMI energy usages for AMI-capable meters."""
        premise_number = billing_account.get("premiseNumber", "")
        for meter in meter_nodes:
            if not meter.get("hasAmiSmartMeter"):
                continue
            sp = str(meter.get("servicePointNumber", ""))
            if not sp:
                continue
            try:
                # Fetch last 10 days of AMI data ending today.
                # AMI data has up to 72-hour delay, so recent days may be empty,
                # but this ensures we capture new data as it becomes available.
                # Statistics import will deduplicate based on last imported timestamp.
                date_to = today
                date_from = today - timedelta(days=10)
                ami_meter = AmiMeterIdentifier(
                    meter_number=str(meter.get("meterNumber", "")),
                    premise_number=premise_number,
                    service_point_number=sp,
                    meter_point_number=str(meter.get("meterPointNumber", "")),
                )
                ami_data = await self.api.get_ami_energy_usages(
                    meter_number=ami_meter.meter_number,
                    premise_number=ami_meter.premise_number,
                    service_point_number=ami_meter.service_point_number,
                    meter_point_number=ami_meter.meter_point_number,
                    date_from=date_from,
                    date_to=date_to,
                )
                ami_usages[sp] = ami_data
                _LOGGER.debug(
                    "Fetched %s AMI usage records for meter %s",
                    len(ami_data),
                    sp,
                )
            except (
                CannotConnectError,
                RetryExhaustedError,
                NationalGridError,
            ) as err:
                _LOGGER.debug(
                    "Could not fetch AMI usages for meter %s: %s",
                    sp,
                    err,
                )

            # Fetch interval reads for electric meters only.
            fuel_type = str(meter.get("fuelType", ""))
            if fuel_type == "Gas":
                continue
            try:
                # Fetch last 36 hours of interval reads (24h available + 12h buffer).
                # Interval data is only available for the last 24 hours.
                # Statistics import will deduplicate based on last imported timestamp.
                now = datetime.now(tz=UTC)
                start_dt = now - timedelta(hours=36)
                reads = await self.api.get_interval_reads(
                    premise_number=premise_number,
                    service_point_number=sp,
                    start_datetime=start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                )
                interval_reads[sp] = reads
                _LOGGER.debug(
                    "Fetched %s interval reads for meter %s",
                    len(reads),
                    sp,
                )
            except (
                CannotConnectError,
                RetryExhaustedError,
                NationalGridError,
            ) as err:
                _LOGGER.debug(
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

        # Filter by fuel type if specified.
        # Map meter fuel type to usage type: Electric->KWH, Gas->THERMS.
        filtered = account_usages
        if fuel_type:
            usage_type_map = {
                "Electric": "TOTAL_KWH",
                "Gas": "THERMS",
            }
            usage_type = usage_type_map.get(fuel_type, fuel_type.upper())
            filtered = [u for u in account_usages if u.get("usageType") == usage_type]
            _LOGGER.debug(
                "Filtering usages: fuel_type=%s -> usage_type=%s, found %s matches",
                fuel_type,
                usage_type,
                len(filtered),
            )

        if not filtered:
            return None

        # Return most recent (highest usageYearMonth).
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

        # Filter by fuel type if specified.
        # Cost records use fuelType field which may be "ELECTRIC" or "GAS" (uppercase).
        filtered = account_costs
        if fuel_type:
            # Try exact match first, then uppercase match.
            filtered = [
                c
                for c in account_costs
                if c.get("fuelType") == fuel_type
                or c.get("fuelType") == fuel_type.upper()
            ]

        if not filtered:
            return None

        # Return most recent (highest month).
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

        # Filter by fuel type if specified.
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

        # Filter by fuel type if specified.
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
