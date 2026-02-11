"""NationalGridEntity class."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import NationalGridDataUpdateCoordinator

if TYPE_CHECKING:
    from aionatgrid.models import BillingAccount, Meter


class NationalGridEntity(CoordinatorEntity[NationalGridDataUpdateCoordinator]):
    """Base entity class for National Grid integration."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NationalGridDataUpdateCoordinator,
        service_point_number: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._service_point_number = service_point_number
        self._attr_device_info = self._build_device_info()

    def _build_device_info(self) -> DeviceInfo:
        """Build device info for this meter."""
        meter_data = self.coordinator.get_meter_data(self._service_point_number)

        if meter_data is None:
            return DeviceInfo(
                identifiers={(DOMAIN, self._service_point_number)},
                serial_number=self._service_point_number,
                name=f"Meter {self._service_point_number}",
                manufacturer="National Grid",
            )

        meter: Meter = meter_data.meter
        billing_account: BillingAccount = meter_data.billing_account

        meter_number = str(meter.get("meterNumber", "")) or self._service_point_number
        fuel_type = str(meter.get("fuelType", ""))
        has_ami = bool(meter.get("hasAmiSmartMeter", False))
        is_smart = bool(meter.get("isSmartMeter", False))
        meter_point_number = str(meter.get("meterPointNumber", ""))

        # Build device name
        name = (
            f"{fuel_type.title()} Meter"
            if fuel_type
            else f"Meter {self._service_point_number}"
        )

        # Determine model based on meter capabilities
        if has_ami:
            model = "AMI Smart Meter"
        elif is_smart:
            model = "Smart Meter"
        else:
            model = "Standard Meter"

        # Add fuel type to model if available
        if fuel_type:
            model = f"{fuel_type.title()} {model}"

        # Extract address and account info from billing account
        service_address = ""
        if billing_account:
            addr_info = billing_account.get("serviceAddress", {})
            service_address = str(addr_info.get("serviceAddressCompressed", ""))

        premise_number = (
            billing_account.get("premiseNumber") if billing_account else None
        )

        # Build configuration URL with account info if available
        config_url = "https://myaccount.nationalgrid.com"

        # Build device info
        device_info = DeviceInfo(
            identifiers={(DOMAIN, self._service_point_number)},
            serial_number=meter_number,
            name=name,
            manufacturer="National Grid",
            model=model,
            configuration_url=config_url,
        )

        # Add suggested area based on service address (first part before comma)
        if service_address:
            # Try to extract a reasonable area name from the address
            parts = service_address.split(",")
            if len(parts) >= 2:
                # Use city or first meaningful part
                device_info["suggested_area"] = parts[0].strip().title()

        # Add hardware version with meter identifiers
        hw_parts = []
        hw_parts.append(f"SP: {self._service_point_number}")
        if meter_point_number:
            hw_parts.append(f"MP: {meter_point_number}")
        if premise_number:
            hw_parts.append(f"Premise: {premise_number}")

        if hw_parts:
            device_info["hw_version"] = " | ".join(hw_parts)

        return device_info

    @property
    def account_id(self) -> str | None:
        """Return the account ID for this meter."""
        meter_data = self.coordinator.get_meter_data(self._service_point_number)
        return meter_data.account_id if meter_data else None

    @property
    def meter(self) -> Meter | None:
        """Return the meter data."""
        meter_data = self.coordinator.get_meter_data(self._service_point_number)
        return meter_data.meter if meter_data else None

    @property
    def billing_account(self) -> BillingAccount | None:
        """Return the billing account data."""
        meter_data = self.coordinator.get_meter_data(self._service_point_number)
        return meter_data.billing_account if meter_data else None
