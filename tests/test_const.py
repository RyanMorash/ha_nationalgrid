"""Tests for the National Grid constants module."""

from custom_components.nationalgrid.const import (
    DOMAIN,
    THERM_TO_CCF,
    UNIT_CCF,
    UNIT_KWH,
    therms_to_ccf,
)


def test_therms_to_ccf() -> None:
    """Test therms to CCF conversion."""
    assert therms_to_ccf(1.0) == round(1.0 * THERM_TO_CCF, 2)
    assert therms_to_ccf(0.0) == 0.0
    assert therms_to_ccf(10.0) == round(10.0 * THERM_TO_CCF, 2)


def test_constants_exist() -> None:
    """Test that expected constants are defined."""
    assert DOMAIN == "nationalgrid"
    assert UNIT_KWH == "kWh"
    assert UNIT_CCF == "CCF"
    assert THERM_TO_CCF == 1.038
