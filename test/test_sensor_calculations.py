"""Regression tests for sensor calculation edge cases."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import Mock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dynamic_energy_cost.const import DOMAIN, HOURLY
from custom_components.dynamic_energy_cost.sensor import EnergyCostSensor, PowerCostSensor, RealTimeCostSensor


def _event(*, entity_id: str, new_state=None, old_state=None):
    return Mock(data={"entity_id": entity_id, "new_state": new_state, "old_state": old_state})


def _state(value: str):
    return Mock(state=value)


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry-123",
        data={
            "integration_description": "Heat Pump",
            "electricity_price_sensor": "sensor.electricity_price",
            "power_sensor": "sensor.heat_pump_power",
            "energy_sensor": "sensor.heat_pump_energy",
        },
    )


def test_realtime_sensor_ignores_missing_source_state(hass):
    """Realtime cost updates are skipped if source states are missing."""
    sensor = RealTimeCostSensor(
        hass,
        _entry(),
        "sensor.electricity_price",
        "sensor.heat_pump_power",
    )
    sensor.async_write_ha_state = Mock()

    hass.states.async_remove("sensor.electricity_price")
    hass.states.async_remove("sensor.heat_pump_power")

    sensor.handle_state_change(
        _event(entity_id="sensor.heat_pump_power", new_state=_state("500"))
    )

    assert sensor.state == 0.0
    sensor.async_write_ha_state.assert_not_called()


async def test_energy_sensor_zero_price_and_follow_up_increment(hass):
    """Energy sensor handles zero price and later increments correctly."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 10.0
    sensor._cumulative_cost = 0.0

    hass.states.async_set("sensor.electricity_price", "0")
    await sensor._async_update_energy_event(
        _event(entity_id="sensor.heat_pump_energy", new_state=_state("11"))
    )

    assert sensor.state == 0.0
    assert sensor._cumulative_cost == 0.0
    assert sensor._last_energy_reading == 11.0

    hass.states.async_set("sensor.electricity_price", "2")
    await sensor._async_update_energy_event(
        _event(entity_id="sensor.heat_pump_energy", new_state=_state("12"))
    )

    assert sensor.state == 2.0
    assert sensor._cumulative_cost == 2.0
    assert sensor._last_energy_reading == 12.0


async def test_energy_sensor_reset_to_zero_reinitializes_baseline(hass):
    """Energy sensor does not generate a negative jump on source reset."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 15.0
    sensor._cumulative_cost = 7.5
    sensor._state = 7.5

    hass.states.async_set("sensor.electricity_price", "3")
    await sensor._async_update_energy_event(
        _event(entity_id="sensor.heat_pump_energy", new_state=_state("0"))
    )

    assert sensor.state == 7.5
    assert sensor._cumulative_cost == 7.5
    assert sensor._last_energy_reading == 0.0

    await sensor._async_update_energy_event(
        _event(entity_id="sensor.heat_pump_energy", new_state=_state("1"))
    )

    assert sensor.state == 10.5
    assert sensor._cumulative_cost == 10.5
    assert sensor._last_energy_reading == 1.0


async def test_energy_sensor_calibrate_updates_internal_baseline(hass):
    """Calibration affects the next increment instead of being overwritten."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 5.0

    sensor.async_calibrate("4.5")
    hass.states.async_set("sensor.electricity_price", "2")
    await sensor._async_update_energy_event(
        _event(entity_id="sensor.heat_pump_energy", new_state=_state("6"))
    )

    assert sensor.state == 6.5
    assert sensor._cumulative_cost == 6.5
    assert sensor._last_energy_reading == 6.0


def test_power_sensor_first_update_only_sets_baseline(hass):
    """Power cost sensor avoids a large jump when no prior update timestamp exists."""
    realtime_sensor = Mock(entity_id="sensor.heat_pump_real_time_energy_cost")
    realtime_sensor.name = "Heat Pump Real Time Energy Cost"
    realtime_sensor.device_info = {"identifiers": {(DOMAIN, "entry-123")}}
    realtime_sensor.unique_id = "entry-123_real_time_cost"
    realtime_sensor._config_entry = _entry()

    sensor = PowerCostSensor(hass, realtime_sensor, HOURLY)
    sensor.async_write_ha_state = Mock()
    sensor._state = Decimal("1.5000")
    sensor._last_update = None

    sensor._handle_real_time_cost_update(
        _event(entity_id=realtime_sensor.entity_id, new_state=_state("2.5"))
    )

    assert sensor.state == Decimal("1.5000")
    assert sensor._last_update is not None
    sensor.async_write_ha_state.assert_not_called()
