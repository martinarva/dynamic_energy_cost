"""Tests for utility sensor interval reset timing."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from custom_components.dynamic_energy_cost.const import QUARTERLY
from custom_components.dynamic_energy_cost.entity import BaseUtilitySensor
from custom_components.dynamic_energy_cost.sensor import interval_display_name


class _TestUtilitySensor(BaseUtilitySensor):
    """Concrete utility sensor for interval timing tests."""

    @property
    def name(self):
        return "Test Utility Sensor"


def test_quarterly_interval_display_name_is_15_minute() -> None:
    """User-facing labels should describe the actual interval behavior."""
    assert interval_display_name(QUARTERLY) == "15-Minute"


def test_quarterly_interval_resets_at_next_15_minute_boundary(hass, monkeypatch):
    """Quarterly currently means quarter-hourly for pricing intervals."""
    sensor = _TestUtilitySensor(hass, QUARTERLY)
    local_time = datetime(2026, 2, 15, 10, 30, tzinfo=ZoneInfo("Europe/Tallinn"))

    monkeypatch.setattr(
        "custom_components.dynamic_energy_cost.entity.now",
        lambda: local_time,
    )

    assert sensor.calculate_next_reset_time() == datetime(
        2026,
        2,
        15,
        10,
        45,
        0,
        0,
        tzinfo=ZoneInfo("Europe/Tallinn"),
    )


def test_quarterly_interval_rolls_to_next_hour(hass, monkeypatch):
    """Quarter-hourly reset rolls to the next hour after xx:45."""
    sensor = _TestUtilitySensor(hass, QUARTERLY)
    local_time = datetime(2026, 12, 15, 22, 45, tzinfo=ZoneInfo("Europe/Tallinn"))

    monkeypatch.setattr(
        "custom_components.dynamic_energy_cost.entity.now",
        lambda: local_time,
    )

    assert sensor.calculate_next_reset_time() == datetime(
        2026,
        12,
        15,
        23,
        0,
        0,
        0,
        tzinfo=ZoneInfo("Europe/Tallinn"),
    )
