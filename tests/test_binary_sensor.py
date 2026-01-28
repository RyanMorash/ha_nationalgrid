"""Tests for the National Grid binary sensor platform."""

from __future__ import annotations

from custom_components.nationalgrid.binary_sensor import PARALLEL_UPDATES
from custom_components.nationalgrid.coordinator import MeterData
from custom_components.nationalgrid.binary_sensor import _has_smart_meter


def _make_meter_data(has_ami: bool) -> MeterData:
    """Create a MeterData with a given AMI status."""
    return MeterData(
        account_id="acct1",
        meter={"fuelType": "Electric", "servicePointNumber": "SP1", "hasAmiSmartMeter": has_ami},
        billing_account={"billingAccountId": "acct1"},
    )


def test_parallel_updates() -> None:
    """Test PARALLEL_UPDATES is set to 1."""
    assert PARALLEL_UPDATES == 1


def test_smart_meter_on() -> None:
    """Test smart meter returns True when hasAmiSmartMeter is True."""
    meter_data = _make_meter_data(True)
    assert _has_smart_meter(meter_data) is True


def test_smart_meter_off() -> None:
    """Test smart meter returns False when hasAmiSmartMeter is False."""
    meter_data = _make_meter_data(False)
    assert _has_smart_meter(meter_data) is False
