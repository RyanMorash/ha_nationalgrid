"""Binary sensor platform for national_grid."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory

from .const import DOMAIN
from .entity import NationalGridEntity

PARALLEL_UPDATES = 1

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import MeterData, NationalGridDataUpdateCoordinator
    from .data import NationalGridConfigEntry


@dataclass(frozen=True, kw_only=True)
class NationalGridBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describe National Grid binary sensor entity."""

    value_fn: Callable[[MeterData], bool | None]


def _has_smart_meter(meter_data: MeterData) -> bool | None:
    """Check if the meter has AMI smart meter capability."""
    meter = meter_data.meter
    return meter.get("hasAmiSmartMeter")


BINARY_SENSOR_DESCRIPTIONS: tuple[NationalGridBinarySensorEntityDescription, ...] = (
    NationalGridBinarySensorEntityDescription(
        key="has_smart_meter",
        translation_key="has_smart_meter",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_has_smart_meter,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: NationalGridConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary_sensor platform."""
    coordinator = entry.runtime_data

    entities: list[NationalGridBinarySensor] = []

    # Create binary sensors for each meter.
    if coordinator.data:
        for service_point_number in coordinator.data.meters:
            entities.extend(
                NationalGridBinarySensor(
                    coordinator=coordinator,
                    service_point_number=service_point_number,
                    entity_description=description,
                )
                for description in BINARY_SENSOR_DESCRIPTIONS
            )

    async_add_entities(entities)


class NationalGridBinarySensor(NationalGridEntity, BinarySensorEntity):
    """National Grid binary sensor entity."""

    entity_description: NationalGridBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: NationalGridDataUpdateCoordinator,
        service_point_number: str,
        entity_description: NationalGridBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, service_point_number)
        self.entity_description = entity_description
        self._attr_unique_id = (
            f"{DOMAIN}_{service_point_number}_{entity_description.key}"
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        meter_data = self.coordinator.get_meter_data(self._service_point_number)
        if meter_data is None:
            return None
        return self.entity_description.value_fn(meter_data)
