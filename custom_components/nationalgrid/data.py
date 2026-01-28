"""Custom types for nationalgrid."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .api import NationalGridApiClient
    from .coordinator import NationalGridDataUpdateCoordinator


type NationalGridConfigEntry = ConfigEntry[NationalGridData]


@dataclass
class NationalGridData:
    """Data for the National Grid integration."""

    client: NationalGridApiClient
    coordinator: NationalGridDataUpdateCoordinator
