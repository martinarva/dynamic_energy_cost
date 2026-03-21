"""Tests for the config and options flow."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dynamic_energy_cost.const import DOMAIN


def _base_user_input(**overrides):
    data = {
        "integration_description": "Heat Pump",
        "electricity_price_sensor": "sensor.electricity_price",
        "power_sensor": "sensor.heat_pump_power",
    }
    data.update(overrides)
    return data


async def test_user_flow_creates_entry_with_power_sensor(hass):
    """The user flow accepts a valid power-sensor configuration."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )

    with patch("custom_components.dynamic_energy_cost.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            _base_user_input(),
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Dynamic Energy Cost - Heat Pump"
    assert result["data"] == {**_base_user_input(), "energy_sensor": None}


async def test_user_flow_requires_exactly_one_power_or_energy_sensor(hass):
    """The user flow rejects missing and duplicated source sensor input."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "integration_description": "Heat Pump",
            "electricity_price_sensor": "sensor.electricity_price",
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "missing_sensor"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        _base_user_input(energy_sensor="sensor.heat_pump_energy"),
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_config"}


async def test_options_flow_supports_entries_with_missing_optional_sensor(hass):
    """The options flow can open for entries that only use an energy sensor."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Dynamic Energy Cost - EV Charger",
        data=_base_user_input(
            integration_description="EV Charger",
            power_sensor=None,
            energy_sensor="sensor.ev_energy",
        ),
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_options_flow_validates_exactly_one_power_or_energy_sensor(hass):
    """The options flow enforces the same validation as the user flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Dynamic Energy Cost - Heat Pump",
        data=_base_user_input(),
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "integration_description": "Heat Pump",
            "electricity_price_sensor": "sensor.new_electricity_price",
            "power_sensor": None,
            "energy_sensor": None,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "missing_sensor"}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "integration_description": "Heat Pump",
            "electricity_price_sensor": "sensor.new_electricity_price",
            "power_sensor": "sensor.heat_pump_power",
            "energy_sensor": "sensor.heat_pump_energy",
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_config"}


async def test_options_flow_saves_updated_sensor_selection(hass):
    """The options flow stores valid sensor updates."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Dynamic Energy Cost - Heat Pump",
        data=_base_user_input(),
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "integration_description": "Heat Pump",
            "electricity_price_sensor": "sensor.new_electricity_price",
            "power_sensor": None,
            "energy_sensor": "sensor.heat_pump_energy",
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "integration_description": "Heat Pump",
        "electricity_price_sensor": "sensor.new_electricity_price",
        "power_sensor": None,
        "energy_sensor": "sensor.heat_pump_energy",
    }
