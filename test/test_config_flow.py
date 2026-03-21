"""Tests for the config and options flow."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.dynamic_energy_cost.config_flow import _entity_selector, _schema
from custom_components.dynamic_energy_cost.const import DOMAIN


def _base_user_input(**overrides):
    data = {
        "integration_description": "Heat Pump",
        "electricity_price_sensor": "sensor.electricity_price",
        "power_sensor": "sensor.heat_pump_power",
    }
    data.update(overrides)
    return data


def test_entity_selector_omits_device_class_when_not_requested() -> None:
    """The generic selector should not serialize an empty device class filter."""
    selector_config = _entity_selector(
        domains=["sensor", "number", "input_number"],
    ).serialize()

    assert selector_config == {
        "selector": {
            "entity": {
                "domain": ["sensor", "number", "input_number"],
                "multiple": False,
                "reorder": False,
            }
        }
    }


def test_schema_uses_unfiltered_price_selector() -> None:
    """The price selector should not add an empty device class filter."""
    schema = _schema().schema
    price_selector = schema[
        next(
            key
            for key in schema
            if getattr(key, "schema", None) == "electricity_price_sensor"
        )
    ]
    serialized = price_selector.serialize()

    assert serialized == {
        "selector": {
            "entity": {
                "domain": ["sensor", "number", "input_number"],
                "multiple": False,
                "reorder": False,
            }
        }
    }


def test_options_schema_relaxes_optional_selector_filters_for_existing_entries() -> None:
    """The options schema does not enforce device class on existing optional fields."""
    schema = _schema(
        {
            "integration_description": "Heat Pump",
            "electricity_price_sensor": "sensor.electricity_price",
            "power_sensor": "sensor.boiler_switch_0_device_power",
        }
    ).schema
    power_selector = next(
        validator.validators[1]
        for key, validator in schema.items()
        if getattr(key, "schema", None) == "power_sensor"
    )

    assert power_selector.serialize() == {
        "selector": {
            "entity": {
                "domain": ["sensor"],
                "multiple": False,
                "reorder": False,
            }
        }
    }


async def test_options_flow_uses_suggested_values_instead_of_defaults(hass):
    """Existing sensor values stay editable instead of becoming hard defaults."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Dynamic Energy Cost - Boiler",
        data={
            "integration_description": "Boiler",
            "electricity_price_sensor": "sensor.electricity_price",
            "power_sensor": "sensor.boiler_switch_0_device_power",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    schema = result["data_schema"].schema
    power_key = next(
        key for key in schema if getattr(key, "schema", None) == "power_sensor"
    )

    assert power_key.default is vol.UNDEFINED
    assert power_key.description == {
        "suggested_value": "sensor.boiler_switch_0_device_power"
    }


async def test_options_flow_allows_switching_from_existing_power_sensor_to_energy_sensor(
    hass,
):
    """An existing power sensor can be cleared when switching to energy mode."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Dynamic Energy Cost - Boiler",
        data={
            "integration_description": "Boiler",
            "electricity_price_sensor": "sensor.electricity_price",
            "power_sensor": "sensor.boiler_switch_0_device_power",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "integration_description": "Boiler",
            "electricity_price_sensor": "sensor.electricity_price",
            "power_sensor": None,
            "energy_sensor": "sensor.switch_0_energy",
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "integration_description": "Boiler",
        "electricity_price_sensor": "sensor.electricity_price",
        "power_sensor": None,
        "energy_sensor": "sensor.switch_0_energy",
    }


async def test_user_flow_creates_entry_with_power_sensor(hass):
    """The user flow accepts a valid power-sensor configuration."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )

    with patch(
        "custom_components.dynamic_energy_cost.async_setup_entry", return_value=True
    ):
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
