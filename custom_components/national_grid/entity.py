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

        meter_number = meter.get("meterNumber", "") or self._service_point_number
        fuel_type = meter.get("fuelType", "")
        name = (
            f"{fuel_type.title()} Meter"
            if fuel_type
            else f"Meter {self._service_point_number}"
        )

        return DeviceInfo(
            identifiers={(DOMAIN, self._service_point_number)},
            serial_number=meter_number,
            name=name,
            manufacturer="National Grid",
            configuration_url="https://myaccount.nationalgrid.com",
        )

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
