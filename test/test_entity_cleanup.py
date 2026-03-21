"""Tests for entity subscription cleanup."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

from custom_components.dynamic_energy_cost.const import HOURLY
from custom_components.dynamic_energy_cost.entity import BaseUtilitySensor
from custom_components.dynamic_energy_cost.sensor import EnergyCostSensor, PowerCostSensor, RealTimeCostSensor


class _TestUtilitySensor(BaseUtilitySensor):
    """Concrete utility sensor for cleanup tests."""

    @property
    def name(self):
        return "Test Utility Sensor"


async def test_base_utility_sensor_cleanup_calls_unsubscriber_once(hass):
    """Removing an entity calls the stored unsubscribe callback safely."""
    sensor = _TestUtilitySensor(hass, HOURLY)
    unsubscribe = Mock()
    sensor.event_unsub = unsubscribe

    await sensor.async_will_remove_from_hass()

    unsubscribe.assert_called_once_with()
    assert sensor.event_unsub is None


async def test_realtime_sensor_registers_state_listener_for_cleanup(hass):
    """Realtime sensor state subscriptions are registered for entity cleanup."""
    sensor = RealTimeCostSensor(
        hass,
        Mock(entry_id="entry-1"),
        "sensor.electricity_price",
        "sensor.heat_pump_power",
    )
    unsubscribe = Mock()
    sensor.async_on_remove = Mock()

    with patch(
        "custom_components.dynamic_energy_cost.sensor.async_track_state_change_event",
        return_value=unsubscribe,
    ):
        await sensor.async_added_to_hass()

    sensor.async_on_remove.assert_called_once_with(unsubscribe)


async def test_energy_sensor_registers_state_listeners_for_cleanup(hass):
    """Energy sensor subscriptions are registered for entity cleanup."""
    sensor = EnergyCostSensor(
        hass,
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    first_unsubscribe = Mock()
    second_unsubscribe = Mock()
    sensor.async_on_remove = Mock()
    sensor.async_get_last_state = AsyncMock(return_value=None)
    sensor.async_write_ha_state = Mock()
    sensor.schedule_next_reset = Mock()

    with patch(
        "custom_components.dynamic_energy_cost.sensor.async_track_state_change_event",
        side_effect=[first_unsubscribe, second_unsubscribe],
    ):
        await sensor.async_added_to_hass()

    assert sensor.async_on_remove.call_args_list[0].args == (first_unsubscribe,)
    assert sensor.async_on_remove.call_args_list[1].args == (second_unsubscribe,)


async def test_power_sensor_registers_state_listener_for_cleanup(hass):
    """Power sensor subscriptions are registered for entity cleanup."""
    realtime_sensor = Mock(entity_id="sensor.heat_pump_real_time_energy_cost")
    realtime_sensor.name = "Heat Pump Real Time Energy Cost"
    realtime_sensor.device_info = {"identifiers": {("dynamic_energy_cost", "entry-1")}}
    realtime_sensor.unique_id = "entry-1_real_time_cost"

    sensor = PowerCostSensor(hass, realtime_sensor, HOURLY)
    unsubscribe = Mock()
    sensor.async_on_remove = Mock()
    sensor.async_get_last_state = AsyncMock(return_value=None)
    sensor.schedule_next_reset = Mock()

    with patch(
        "custom_components.dynamic_energy_cost.sensor.async_track_state_change_event",
        return_value=unsubscribe,
    ):
        await sensor.async_added_to_hass()

    sensor.async_on_remove.assert_called_once_with(unsubscribe)
