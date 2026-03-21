"""Tests for config entry migration and stable unique IDs."""

from __future__ import annotations

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dynamic_energy_cost import async_migrate_entry
from custom_components.dynamic_energy_cost.const import DOMAIN, HOURLY
from custom_components.dynamic_energy_cost.sensor import (
    EnergyCostSensor,
    PowerCostSensor,
    RealTimeCostSensor,
)


def _entry_data(**overrides):
    data = {
        "integration_description": "Heat Pump",
        "electricity_price_sensor": "sensor.electricity_price",
        "power_sensor": "sensor.heat_pump_power",
        "energy_sensor": "sensor.heat_pump_energy",
    }
    data.update(overrides)
    return data


async def test_migrate_entry_updates_legacy_unique_ids(hass):
    """Migration keeps existing entity IDs while moving to stable unique IDs."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        data=_entry_data(energy_sensor=None),
        entry_id="entry-123",
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)

    realtime = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_sensor.heat_pump_power_real_time_cost",
        config_entry=entry,
        suggested_object_id="heat_pump_real_time_energy_cost",
    )
    power = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_sensor.heat_pump_power_real_time_cost_{HOURLY}",
        config_entry=entry,
        suggested_object_id="heat_pump_hourly_energy_cost",
    )
    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 3
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, "entry-123_real_time_cost")
        == realtime.entity_id
    )
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, "entry-123_hourly_cost")
        == power.entity_id
    )


async def test_sensors_use_entry_based_unique_ids(hass):
    """New sensors derive unique IDs only from the config entry."""
    entry = MockConfigEntry(domain=DOMAIN, data=_entry_data(), entry_id="entry-123")

    realtime_sensor = RealTimeCostSensor(
        hass,
        entry,
        "sensor.electricity_price",
        "sensor.heat_pump_power",
    )
    energy_sensor = EnergyCostSensor(
        hass,
        entry,
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    power_sensor = PowerCostSensor(hass, realtime_sensor, HOURLY)

    assert realtime_sensor.unique_id == "entry-123_real_time_cost"
    assert energy_sensor.unique_id == "entry-123_hourly_cost"
    assert power_sensor.unique_id == "entry-123_hourly_cost"


async def test_migrate_entry_skips_collision_without_breaking_existing_entity(hass):
    """Migration leaves the legacy entity in place if the target unique ID already exists."""
    entry = MockConfigEntry(
        domain=DOMAIN, version=1, data=_entry_data(), entry_id="entry-123"
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)

    legacy = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_sensor.heat_pump_power_real_time_cost",
        config_entry=entry,
        suggested_object_id="legacy_heat_pump_real_time_energy_cost",
    )
    stable = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "entry-123_real_time_cost",
        config_entry=entry,
        suggested_object_id="stable_heat_pump_real_time_energy_cost",
    )

    assert await async_migrate_entry(hass, entry) is True

    assert (
        registry.async_get_entity_id("sensor", DOMAIN, "entry-123_real_time_cost")
        == stable.entity_id
    )
    assert (
        registry.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_sensor.heat_pump_power_real_time_cost"
        )
        == legacy.entity_id
    )
    assert entry.version == 1


async def test_migrate_entry_includes_legacy_ids_from_original_data_when_options_changed(
    hass,
):
    """Migration still finds legacy entities created from entry.data after options edits."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        entry_id="entry-123",
        data=_entry_data(power_sensor="sensor.old_power", energy_sensor=None),
        options={
            "power_sensor": None,
            "energy_sensor": "sensor.new_energy",
            "electricity_price_sensor": "sensor.new_price",
        },
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)

    legacy = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "entry-123_sensor.old_power_real_time_cost",
        config_entry=entry,
        suggested_object_id="old_power_real_time_energy_cost",
    )

    assert await async_migrate_entry(hass, entry) is True
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, "entry-123_real_time_cost")
        == legacy.entity_id
    )


async def test_migrate_entry_includes_legacy_energy_ids_from_original_data_when_options_changed(
    hass,
):
    """Migration still finds legacy energy entities created from entry.data after options edits."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        entry_id="entry-123",
        data=_entry_data(
            electricity_price_sensor="sensor.old_price",
            power_sensor=None,
            energy_sensor="sensor.old_energy",
        ),
        options={
            "power_sensor": "sensor.new_power",
            "energy_sensor": None,
            "electricity_price_sensor": "sensor.new_price",
        },
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)

    legacy = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "sensor.old_price_sensor.old_energy_hourly_cost",
        config_entry=entry,
        suggested_object_id="old_energy_hourly_cost",
    )

    assert await async_migrate_entry(hass, entry) is True
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, "entry-123_hourly_cost")
        == legacy.entity_id
    )


async def test_migrate_entry_updates_v2_interval_unique_ids_to_shared_ids(hass):
    """Migration upgrades v2 mode-specific interval IDs to shared IDs."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        data=_entry_data(power_sensor="sensor.heat_pump_power", energy_sensor=None),
        entry_id="entry-123",
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)

    power = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "entry-123_hourly_power_cost",
        config_entry=entry,
        suggested_object_id="heat_pump_hourly_energy_cost",
    )

    assert await async_migrate_entry(hass, entry) is True
    assert entry.version == 3
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, "entry-123_hourly_cost")
        == power.entity_id
    )
