"""Tests for the config and options flow."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.dynamic_energy_cost.config_flow import (
    _entity_selector,
    _filtered_entity_selector,
    _schema,
)
from custom_components.dynamic_energy_cost.const import (
    DOMAIN,
    QUARTERLY,
    HOURLY,
    DAILY,
    WEEKLY,
    MONTHLY,
    YEARLY,
    MANUAL,
    REAL_TIME,
    SELECTED_SENSORS,
)

ALL_INTERVALS = [QUARTERLY, HOURLY, DAILY, WEEKLY, MONTHLY, YEARLY, MANUAL]
# real_time is no longer a selectable option — it's always auto-included for power path
ALL_SELECTABLE = sorted(ALL_INTERVALS)
# After normalization, power path results include REAL_TIME
ALL_POWER_NORMALIZED = sorted([*ALL_INTERVALS, REAL_TIME])


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


def test_filtered_entity_selector_uses_filter_syntax() -> None:
    """Filtered selectors should use the modern filter schema."""
    selector_config = _filtered_entity_selector(
        domains=["sensor"],
        device_class="power",
    ).serialize()

    assert selector_config == {
        "selector": {
            "entity": {
                "domain": ["sensor"],
                "filter": [{"device_class": ["power"], "domain": ["sensor"]}],
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


def test_options_schema_keeps_optional_selector_filters() -> None:
    """The options schema keeps proper power/energy filtering."""
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
                "filter": [{"device_class": ["power"], "domain": ["sensor"]}],
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
    # Step 1: change from power to energy sensor
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "integration_description": "Boiler",
            "electricity_price_sensor": "sensor.electricity_price",
            "power_sensor": None,
            "energy_sensor": "sensor.switch_0_energy",
        },
    )

    # Now at sensors step
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sensors"

    # Step 2: accept default sensor selection
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={SELECTED_SENSORS: ALL_SELECTABLE},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][SELECTED_SENSORS] == ALL_SELECTABLE
    assert result["data"]["energy_sensor"] == "sensor.switch_0_energy"
    assert result["data"]["power_sensor"] is None


async def test_user_flow_creates_entry_with_power_sensor(hass):
    """The user flow accepts a valid power-sensor configuration."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )

    # Step 1: configure sensors
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        _base_user_input(),
    )

    # Should be at sensors step now
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sensors"

    # Step 2: select all sensors
    with patch(
        "custom_components.dynamic_energy_cost.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {SELECTED_SENSORS: ALL_SELECTABLE},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Dynamic Energy Cost - Heat Pump"
    assert result["data"]["energy_sensor"] is None
    assert result["data"]["power_sensor"] == "sensor.heat_pump_power"
    assert result["data"][SELECTED_SENSORS] == ALL_POWER_NORMALIZED


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
    # Step 1: switch to energy sensor
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "integration_description": "Heat Pump",
            "electricity_price_sensor": "sensor.new_electricity_price",
            "power_sensor": None,
            "energy_sensor": "sensor.heat_pump_energy",
        },
    )

    # Now at sensors step
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sensors"

    # Step 2: select sensors
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={SELECTED_SENSORS: ALL_SELECTABLE},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["electricity_price_sensor"] == "sensor.new_electricity_price"
    assert result["data"]["power_sensor"] is None
    assert result["data"]["energy_sensor"] == "sensor.heat_pump_energy"
    assert result["data"][SELECTED_SENSORS] == ALL_SELECTABLE


# --- New tests for sensor selection feature ---


async def test_config_flow_power_path_defaults_exclude_real_time(hass):
    """Power path defaults only show interval sensors (real_time is auto-included)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        _base_user_input(),
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sensors"

    # real_time is NOT a selectable option — it's auto-included for power path
    schema = result["data_schema"].schema
    selected_key = next(
        key for key in schema if getattr(key, "schema", None) == SELECTED_SENSORS
    )
    default_value = (
        selected_key.default()
        if callable(selected_key.default)
        else selected_key.default
    )
    assert REAL_TIME not in default_value
    assert set(default_value) == set(ALL_SELECTABLE)


async def test_config_flow_energy_path_excludes_real_time_option(hass):
    """Energy path sensors step does not include real_time option."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        _base_user_input(power_sensor=None, energy_sensor="sensor.energy"),
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sensors"

    schema = result["data_schema"].schema
    selected_key = next(
        key for key in schema if getattr(key, "schema", None) == SELECTED_SENSORS
    )
    default_value = (
        selected_key.default()
        if callable(selected_key.default)
        else selected_key.default
    )
    assert REAL_TIME not in default_value


async def test_power_path_normalization_auto_includes_real_time(hass):
    """Selecting power intervals auto-includes real_time in the result."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        _base_user_input(),
    )

    # Select only daily — real_time should be auto-added
    with patch(
        "custom_components.dynamic_energy_cost.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {SELECTED_SENSORS: [DAILY]},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert REAL_TIME in result["data"][SELECTED_SENSORS]
    assert DAILY in result["data"][SELECTED_SENSORS]


async def test_power_path_single_interval_includes_real_time(hass):
    """Selecting a single interval on power path auto-includes real_time."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        _base_user_input(),
    )

    with patch(
        "custom_components.dynamic_energy_cost.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {SELECTED_SENSORS: [MONTHLY]},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert set(result["data"][SELECTED_SENSORS]) == {MONTHLY, REAL_TIME}


async def test_sensors_step_rejects_empty_selection(hass):
    """The sensors step shows an error when no sensors are selected."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        _base_user_input(),
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {SELECTED_SENSORS: []},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_sensors_selected"}


async def test_options_flow_shows_current_selection_as_defaults(hass):
    """Options flow pre-selects the current sensor selection."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Dynamic Energy Cost - Heat Pump",
        data=_base_user_input(),
        options={SELECTED_SENSORS: [REAL_TIME, DAILY, MONTHLY]},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    # Step 1: keep same config
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=_base_user_input(),
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sensors"

    schema = result["data_schema"].schema
    selected_key = next(
        key for key in schema if getattr(key, "schema", None) == SELECTED_SENSORS
    )
    # Defaults should match the current selection minus real_time (not selectable)
    default_value = (
        selected_key.default()
        if callable(selected_key.default)
        else selected_key.default
    )
    assert set(default_value) == {DAILY, MONTHLY}
