"""Tests for the National Grid sensor platform."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.components.sensor import SensorDeviceClass

from custom_components.national_grid.const import UNIT_CCF, UNIT_KWH
from custom_components.national_grid.coordinator import MeterData
from custom_components.national_grid.sensor import (
    PARALLEL_UPDATES,
    _get_energy_cost,
    _get_energy_device_class,
    _get_energy_unit,
    _get_energy_usage,
)


def _make_meter_data(
    fuel_type: str = "Electric", account_id: str = "acct1"
) -> MeterData:
    """Create a MeterData with a given fuel type."""
    return MeterData(
        account_id=account_id,
        meter={
            "fuelType": fuel_type,
            "servicePointNumber": "SP1",
            "hasAmiSmartMeter": True,
        },
        billing_account={"billingAccountId": account_id},
    )


def test_parallel_updates() -> None:
    """Test PARALLEL_UPDATES is set to 1."""
    assert PARALLEL_UPDATES == 1


def test_energy_usage_electric() -> None:
    """Test usage value for electric meter."""
    meter_data = _make_meter_data("Electric")
    coordinator = MagicMock()
    coordinator.get_latest_usage.return_value = {
        "usage": 500.0,
        "usageType": "TOTAL_KWH",
    }
    result = _get_energy_usage(coordinator, meter_data)
    assert result == 500.0


def test_energy_usage_gas_returns_value_directly() -> None:
    """Test usage value for gas meter returns API value directly (already CCF)."""
    meter_data = _make_meter_data("Gas")
    coordinator = MagicMock()
    coordinator.get_latest_usage.return_value = {"usage": 10.0, "usageType": "CCF"}
    result = _get_energy_usage(coordinator, meter_data)

    assert result == 10.0


def test_energy_usage_none() -> None:
    """Test usage returns None when no data."""
    meter_data = _make_meter_data()
    coordinator = MagicMock()
    coordinator.get_latest_usage.return_value = None
    result = _get_energy_usage(coordinator, meter_data)
    assert result is None


def test_energy_cost() -> None:
    """Test cost value extraction."""
    meter_data = _make_meter_data()
    coordinator = MagicMock()
    coordinator.get_latest_cost.return_value = {"amount": 120.50}
    result = _get_energy_cost(coordinator, meter_data)
    assert result == 120.50


def test_energy_cost_none() -> None:
    """Test cost returns None when no data."""
    meter_data = _make_meter_data()
    coordinator = MagicMock()
    coordinator.get_latest_cost.return_value = None
    result = _get_energy_cost(coordinator, meter_data)
    assert result is None


def test_gas_meter_units() -> None:
    """Test gas meter returns CCF unit."""
    meter_data = _make_meter_data("Gas")
    assert _get_energy_unit(meter_data) == UNIT_CCF


def test_electric_meter_units() -> None:
    """Test electric meter returns kWh unit."""
    meter_data = _make_meter_data("Electric")
    assert _get_energy_unit(meter_data) == UNIT_KWH


def test_gas_device_class() -> None:
    """Test gas meter returns GAS device class."""
    meter_data = _make_meter_data("Gas")
    assert _get_energy_device_class(meter_data) == SensorDeviceClass.GAS


def test_electric_device_class() -> None:
    """Test electric meter returns ENERGY device class."""
    meter_data = _make_meter_data("Electric")
    assert _get_energy_device_class(meter_data) == SensorDeviceClass.ENERGY
