"""Sensor platform for national_grid."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)

from .const import _LOGGER, DOMAIN, UNIT_CCF, UNIT_KWH
from .entity import NationalGridEntity

PARALLEL_UPDATES = 1

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import MeterData, NationalGridDataUpdateCoordinator
    from .data import NationalGridConfigEntry


@dataclass(frozen=True, kw_only=True)
class NationalGridSensorEntityDescription(SensorEntityDescription):
    """Describe National Grid sensor entity."""

    value_fn: Callable[[NationalGridDataUpdateCoordinator, MeterData], Any]
    unit_fn: Callable[[MeterData], str | None] | None = None
    device_class_fn: Callable[[MeterData], SensorDeviceClass | None] | None = None
    available_fn: Callable[[MeterData], bool] = lambda _: True


def _get_energy_usage(
    coordinator: NationalGridDataUpdateCoordinator, meter_data: MeterData
) -> float | None:
    """Get the latest energy usage for a meter."""
    fuel_type = meter_data.meter.get("fuelType")
    usage = coordinator.get_latest_usage(meter_data.account_id, fuel_type)
    _LOGGER.debug(
        "Getting usage for account=%s, fuel_type=%s: %s",
        meter_data.account_id,
        fuel_type,
        usage,
    )
    if usage:
        return usage.get("usage")
    return None


def _get_energy_cost(
    coordinator: NationalGridDataUpdateCoordinator, meter_data: MeterData
) -> float | None:
    """Get the latest energy cost for a meter."""
    fuel_type = meter_data.meter.get("fuelType")
    cost = coordinator.get_latest_cost(meter_data.account_id, fuel_type)
    if cost:
        return cost.get("amount")
    return None


def _get_energy_unit(meter_data: MeterData) -> str:
    """Get the appropriate energy unit based on fuel type."""
    fuel_type = meter_data.meter.get("fuelType", "").upper()
    if fuel_type == "GAS":
        return UNIT_CCF
    return UNIT_KWH


def _get_energy_device_class(meter_data: MeterData) -> SensorDeviceClass | None:
    """Get the device class based on fuel type."""
    fuel_type = meter_data.meter.get("fuelType", "").upper()
    if fuel_type == "GAS":
        return SensorDeviceClass.GAS
    return SensorDeviceClass.ENERGY


SENSOR_DESCRIPTIONS: tuple[NationalGridSensorEntityDescription, ...] = (
    NationalGridSensorEntityDescription(
        key="energy_cost",
        translation_key="energy_cost",
        native_unit_of_measurement="$",
        device_class=SensorDeviceClass.MONETARY,
        value_fn=_get_energy_cost,
    ),
    NationalGridSensorEntityDescription(
        key="energy_usage",
        translation_key="energy_usage",
        value_fn=_get_energy_usage,
        unit_fn=_get_energy_unit,
        device_class_fn=_get_energy_device_class,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: NationalGridConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = entry.runtime_data

    entities: list[NationalGridSensor] = []

    # Create sensors for each meter.
    if coordinator.data:
        for service_point_number, meter_data in coordinator.data.meters.items():
            entities.extend(
                NationalGridSensor(
                    coordinator=coordinator,
                    service_point_number=service_point_number,
                    entity_description=description,
                    meter_data=meter_data,
                )
                for description in SENSOR_DESCRIPTIONS
                if description.available_fn(meter_data)
            )

    async_add_entities(entities)


class NationalGridSensor(NationalGridEntity, SensorEntity):
    """National Grid sensor entity."""

    entity_description: NationalGridSensorEntityDescription

    def __init__(
        self,
        coordinator: NationalGridDataUpdateCoordinator,
        service_point_number: str,
        entity_description: NationalGridSensorEntityDescription,
        meter_data: MeterData,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, service_point_number)
        self.entity_description = entity_description
        self._attr_unique_id = (
            f"{DOMAIN}_{service_point_number}_{entity_description.key}"
        )
        # Set dynamic unit based on meter type.
        if entity_description.unit_fn:
            self._attr_native_unit_of_measurement = entity_description.unit_fn(
                meter_data
            )
        # Set dynamic device class based on meter type.
        if entity_description.device_class_fn:
            self._attr_device_class = entity_description.device_class_fn(meter_data)

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        meter_data = self.coordinator.get_meter_data(self._service_point_number)
        if meter_data is None:
            return None
        return self.entity_description.value_fn(self.coordinator, meter_data)
