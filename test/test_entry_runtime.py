"""Tests for config entry runtime behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dynamic_energy_cost import async_reload_entry, async_setup_entry
from custom_components.dynamic_energy_cost.const import DOMAIN
from custom_components.dynamic_energy_cost.sensor import EnergyCostSensor, RealTimeCostSensor, async_setup_entry as sensor_async_setup_entry


def _entry_data(**overrides):
    data = {
        "integration_description": "Heat Pump",
        "electricity_price_sensor": "sensor.electricity_price",
        "power_sensor": "sensor.heat_pump_power",
        "energy_sensor": None,
    }
    data.update(overrides)
    return data


async def test_async_setup_entry_registers_reload_listener(hass):
    """Config entries reload after options updates."""
    entry = MockConfigEntry(domain=DOMAIN, data=_entry_data())
    entry.add_to_hass(hass)

    with patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        AsyncMock(return_value=True),
    ) as forward_entry_setups:
        assert await async_setup_entry(hass, entry) is True

    forward_entry_setups.assert_awaited_once_with(entry, ["sensor"])
    assert len(entry.update_listeners) == 1


async def test_reload_listener_reloads_entry(hass):
    """The registered update listener reloads the config entry."""
    entry = MockConfigEntry(domain=DOMAIN, data=_entry_data())

    with patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=True)) as reload_entry:
        await async_reload_entry(hass, entry)

    reload_entry.assert_awaited_once_with(entry.entry_id)


async def test_sensor_setup_uses_options_over_data(hass):
    """Runtime sensor setup prefers options over original config data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=_entry_data(),
        options={
            "electricity_price_sensor": "sensor.new_electricity_price",
            "power_sensor": None,
            "energy_sensor": "sensor.heat_pump_energy",
        },
    )

    async_add_entities = Mock()

    with patch(
        "custom_components.dynamic_energy_cost.sensor.register_entity_services",
        AsyncMock(),
    ):
        await sensor_async_setup_entry(hass, entry, async_add_entities)

    async_add_entities.assert_called_once()
    sensors = async_add_entities.call_args.args[0]

    assert sensors
    assert all(isinstance(sensor, EnergyCostSensor) for sensor in sensors)
    assert not any(isinstance(sensor, RealTimeCostSensor) for sensor in sensors)
    assert len(sensors) == 7
