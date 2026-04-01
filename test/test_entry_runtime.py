"""Tests for config entry runtime behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.dynamic_energy_cost import async_reload_entry, async_setup_entry
from custom_components.dynamic_energy_cost.const import DOMAIN
from custom_components.dynamic_energy_cost.sensor import (
    EnergyCostSensor,
    PowerCostSensor,
    RealTimeCostSensor,
    async_setup_entry as sensor_async_setup_entry,
)


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
    entry.add_to_hass(hass)

    with patch.object(
        hass.config_entries, "async_reload", AsyncMock(return_value=True)
    ) as reload_entry:
        await async_reload_entry(hass, entry)

    reload_entry.assert_awaited_once_with(entry.entry_id)


async def test_reload_listener_updates_title_from_latest_description(hass):
    """Reload updates the config entry title when the description changes."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Dynamic Energy Cost - Heat Pump",
        data=_entry_data(),
        options={"integration_description": "EV Charger"},
    )

    with (
        patch.object(
            hass.config_entries, "async_reload", AsyncMock(return_value=True)
        ) as reload_entry,
        patch.object(hass.config_entries, "async_update_entry") as update_entry,
    ):
        await async_reload_entry(hass, entry)

    update_entry.assert_called_once_with(
        entry, title="Dynamic Energy Cost - EV Charger"
    )
    reload_entry.assert_awaited_once_with(entry.entry_id)


async def test_reload_listener_removes_obsolete_realtime_entity_when_switching_to_energy(
    hass,
):
    """Switching away from power mode removes the old realtime entity."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Dynamic Energy Cost - Heat Pump",
        entry_id="entry-123",
        data=_entry_data(),
        options={"power_sensor": None, "energy_sensor": "sensor.heat_pump_energy"},
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    realtime = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "entry-123_real_time_cost",
        config_entry=entry,
        suggested_object_id="heat_pump_real_time_energy_cost",
    )

    with patch.object(
        hass.config_entries, "async_reload", AsyncMock(return_value=True)
    ) as reload_entry:
        await async_reload_entry(hass, entry)

    assert registry.async_get(realtime.entity_id) is None
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
    assert all(sensor.unique_id.endswith("_cost") for sensor in sensors)


async def test_sensor_setup_handles_entries_missing_optional_keys(hass):
    """Runtime setup tolerates older entries without explicit optional keys."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "integration_description": "Heat Pump",
            "electricity_price_sensor": "sensor.electricity_price",
            "power_sensor": "sensor.heat_pump_power",
        },
    )

    async_add_entities = Mock()

    with patch(
        "custom_components.dynamic_energy_cost.sensor.register_entity_services",
        AsyncMock(),
    ):
        await sensor_async_setup_entry(hass, entry, async_add_entities)

    sensors = async_add_entities.call_args.args[0]
    assert any(isinstance(sensor, RealTimeCostSensor) for sensor in sensors)


async def test_mode_switch_reuses_shared_interval_unique_ids(hass):
    """Power and energy modes use the same interval unique IDs."""
    power_entry = MockConfigEntry(
        domain=DOMAIN, entry_id="entry-123", data=_entry_data()
    )
    energy_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry-123",
        data=_entry_data(power_sensor=None, energy_sensor="sensor.heat_pump_energy"),
    )

    power_add = Mock()
    energy_add = Mock()

    with patch(
        "custom_components.dynamic_energy_cost.sensor.register_entity_services",
        AsyncMock(),
    ):
        await sensor_async_setup_entry(hass, power_entry, power_add)
        await sensor_async_setup_entry(hass, energy_entry, energy_add)

    power_sensors = power_add.call_args.args[0]
    energy_sensors = energy_add.call_args.args[0]
    power_interval_ids = {
        sensor.unique_id
        for sensor in power_sensors
        if not isinstance(sensor, RealTimeCostSensor)
    }
    energy_interval_ids = {sensor.unique_id for sensor in energy_sensors}

    assert power_interval_ids == energy_interval_ids


async def test_async_setup_entry_returns_false_when_forward_fails(hass):
    """Entry setup fails gracefully if platform forwarding raises."""
    entry = MockConfigEntry(domain=DOMAIN, data=_entry_data())
    entry.add_to_hass(hass)

    with patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        AsyncMock(side_effect=RuntimeError("boom")),
    ):
        assert await async_setup_entry(hass, entry) is False


async def test_async_unload_entry_unloads_sensor_platform(hass):
    """Entry unload forwards to Home Assistant platform unloading."""
    entry = MockConfigEntry(domain=DOMAIN, data=_entry_data())

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=True),
    ) as unload_platforms:
        from custom_components.dynamic_energy_cost import async_unload_entry

        assert await async_unload_entry(hass, entry) is True

    unload_platforms.assert_awaited_once_with(entry, ["sensor"])


async def test_setup_entry_removes_orphaned_energy_device(hass):
    """Setup cleans up orphaned devices from the v0.9.3 identifier change."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        data=_entry_data(power_sensor=None, energy_sensor="sensor.heat_pump_energy"),
        entry_id="entry-123",
    )
    entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    old_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "sensor.heat_pump_energy")},
        name="Heat Pump Dynamic Energy Cost",
        manufacturer="Custom Integration",
    )

    with patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        AsyncMock(return_value=True),
    ):
        assert await async_setup_entry(hass, entry) is True

    assert device_registry.async_get(old_device.id) is None


async def test_cost_sensors_link_to_source_device(hass):
    """Cost sensors attach to the source power sensor's device via device_entry."""
    entry = MockConfigEntry(domain=DOMAIN, data=_entry_data(), entry_id="entry-456")
    entry.add_to_hass(hass)

    # Create a source device that owns the power sensor
    device_registry = dr.async_get(hass)
    source_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("other_integration", "heat_pump_123")},
        name="Heat Pump",
    )
    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        "sensor",
        "other_integration",
        "heat_pump_power",
        suggested_object_id="heat_pump_power",
        device_id=source_device.id,
        config_entry=entry,
    )

    async_add_entities = Mock()
    with patch(
        "custom_components.dynamic_energy_cost.sensor.register_entity_services",
        AsyncMock(),
    ):
        await sensor_async_setup_entry(hass, entry, async_add_entities)

    sensors = async_add_entities.call_args.args[0]
    realtime = next(s for s in sensors if isinstance(s, RealTimeCostSensor))
    power_cost = next(s for s in sensors if isinstance(s, PowerCostSensor))

    assert realtime.device_entry is not None
    assert realtime.device_entry.id == source_device.id
    assert power_cost.device_entry is not None
    assert power_cost.device_entry.id == source_device.id
    # device_info returns None when device_entry is set
    assert realtime.device_info is None


async def test_cost_sensors_fallback_device_without_source_device(hass):
    """Cost sensors create a standalone device when source has no device."""
    entry = MockConfigEntry(domain=DOMAIN, data=_entry_data(), entry_id="entry-789")
    entry.add_to_hass(hass)
    # power sensor exists but has no device (e.g. template sensor)

    async_add_entities = Mock()
    with patch(
        "custom_components.dynamic_energy_cost.sensor.register_entity_services",
        AsyncMock(),
    ):
        await sensor_async_setup_entry(hass, entry, async_add_entities)

    sensors = async_add_entities.call_args.args[0]
    realtime = next(s for s in sensors if isinstance(s, RealTimeCostSensor))

    assert realtime.device_entry is None
    assert realtime.device_info is not None
    assert realtime.device_info["identifiers"] == {(DOMAIN, "entry-789")}

    # All PowerCostSensors must also get the same fallback device_info
    power_costs = [s for s in sensors if isinstance(s, PowerCostSensor)]
    assert len(power_costs) > 0
    for sensor in power_costs:
        assert sensor.device_entry is None
        assert sensor.device_info is not None
        assert sensor.device_info["identifiers"] == {(DOMAIN, "entry-789")}
        assert sensor.device_info["name"] == realtime.device_info["name"]


async def test_power_cost_device_info_independent_of_realtime_mutation(hass):
    """PowerCostSensor device_info must not break when HA mutates RealTimeCostSensor.device_entry."""
    entry = MockConfigEntry(domain=DOMAIN, data=_entry_data(), entry_id="entry-timing")
    entry.add_to_hass(hass)

    async_add_entities = Mock()
    with patch(
        "custom_components.dynamic_energy_cost.sensor.register_entity_services",
        AsyncMock(),
    ):
        await sensor_async_setup_entry(hass, entry, async_add_entities)

    sensors = async_add_entities.call_args.args[0]
    realtime = next(s for s in sensors if isinstance(s, RealTimeCostSensor))
    power_cost = next(s for s in sensors if isinstance(s, PowerCostSensor))

    # Both start with no device
    assert realtime.device_entry is None
    assert power_cost.device_entry is None
    assert power_cost.device_info is not None

    # Simulate HA setting device_entry on realtime after creating fallback device
    realtime.device_entry = Mock()

    # PowerCostSensor must still return fallback device_info
    assert power_cost.device_info is not None
    assert power_cost.device_info["identifiers"] == {(DOMAIN, "entry-timing")}


async def test_energy_sensors_link_to_source_device(hass):
    """Energy cost sensors attach to the source energy sensor's device."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=_entry_data(power_sensor=None, energy_sensor="sensor.heat_pump_energy"),
        entry_id="entry-energy",
    )
    entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    source_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("other_integration", "heat_pump_456")},
        name="Heat Pump",
    )
    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        "sensor",
        "other_integration",
        "heat_pump_energy",
        suggested_object_id="heat_pump_energy",
        device_id=source_device.id,
        config_entry=entry,
    )

    async_add_entities = Mock()
    with patch(
        "custom_components.dynamic_energy_cost.sensor.register_entity_services",
        AsyncMock(),
    ):
        await sensor_async_setup_entry(hass, entry, async_add_entities)

    sensors = async_add_entities.call_args.args[0]
    energy_cost = sensors[0]
    assert isinstance(energy_cost, EnergyCostSensor)
    assert energy_cost.device_entry is not None
    assert energy_cost.device_entry.id == source_device.id
    assert energy_cost.device_info is None


async def test_setup_removes_legacy_helper_device(hass):
    """Setup cleans up the old (DOMAIN, entry_id) helper device."""
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, data=_entry_data(), entry_id="entry-legacy"
    )
    entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    old_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "entry-legacy")},
        name="Heat Pump Dynamic Energy Cost",
        manufacturer="Custom Integration",
    )

    with patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        AsyncMock(return_value=True),
    ):
        assert await async_setup_entry(hass, entry) is True

    assert device_registry.async_get(old_device.id) is None


async def test_legacy_device_not_removed_if_entities_remain(hass):
    """Legacy device is kept if it still has entities attached."""
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, data=_entry_data(), entry_id="entry-keep"
    )
    entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    old_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "entry-keep")},
        name="Heat Pump Dynamic Energy Cost",
    )
    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "some_remaining_entity",
        device_id=old_device.id,
        config_entry=entry,
    )

    with patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        AsyncMock(return_value=True),
    ):
        assert await async_setup_entry(hass, entry) is True

    # Device should still exist because it has entities
    assert device_registry.async_get(old_device.id) is not None
