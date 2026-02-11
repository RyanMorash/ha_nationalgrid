"""Tests for the National Grid constants module."""

from custom_components.national_grid.const import (
    DOMAIN,
    UNIT_CCF,
    UNIT_KWH,
)


def test_constants_exist() -> None:
    """Test that expected constants are defined."""
    assert DOMAIN == "national_grid"
    assert UNIT_KWH == "kWh"
    assert UNIT_CCF == "CCF"
