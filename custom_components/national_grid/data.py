"""Custom types for national_grid."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .coordinator import NationalGridDataUpdateCoordinator


type NationalGridConfigEntry = ConfigEntry[NationalGridDataUpdateCoordinator]
