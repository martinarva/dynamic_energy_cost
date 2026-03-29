"""Class representing a Dynamic Energy Costs config flow."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.components.input_number import DOMAIN as INPUT_NUMBER_DOMAIN
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.schema_config_entry_flow import SchemaFlowError

import voluptuous as vol

from .const import (
    DOMAIN,
    ELECTRICITY_PRICE_SENSOR,
    ENERGY_SENSOR,
    POWER_SENSOR,
    REAL_TIME,
    SELECTED_SENSORS,
    SENSOR_LABELS,
)
from . import get_selected_sensors, INTERVALS


_LOGGER = logging.getLogger(__name__)


def _entity_selector(*, domains: list[str]):
    """Create an entity selector for a single entity."""
    return selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain=domains,
            multiple=False,
        )
    )


def _filtered_entity_selector(*, domains: list[str], device_class: str):
    """Create an entity selector that uses the modern filter syntax."""
    return selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain=domains,
            multiple=False,
            filter=[{"domain": domains, "device_class": [device_class]}],
        )
    )


def _clean_optional_value(value: Any) -> Any:
    """Normalize empty optional selector values."""
    if value in (None, ""):
        return None
    return value


def _normalize_user_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize selector payloads for validation and storage."""
    cleaned = dict(user_input)
    cleaned[POWER_SENSOR] = _clean_optional_value(cleaned.get(POWER_SENSOR))
    cleaned[ENERGY_SENSOR] = _clean_optional_value(cleaned.get(ENERGY_SENSOR))
    cleaned["integration_description"] = cleaned.get(
        "integration_description", "Unnamed"
    )
    return cleaned


def _validate_config(user_input: dict[str, Any]) -> dict[str, Any]:
    """Validate config flow input and return normalized config data."""
    config = _normalize_user_input(user_input)

    cv.entity_id(config[ELECTRICITY_PRICE_SENSOR])

    if config.get(POWER_SENSOR):
        cv.entity_id(config[POWER_SENSOR])

    if config.get(ENERGY_SENSOR):
        cv.entity_id(config[ENERGY_SENSOR])

    if not config.get(POWER_SENSOR) and not config.get(ENERGY_SENSOR):
        raise SchemaFlowError("missing_sensor")

    if config.get(POWER_SENSOR) and config.get(ENERGY_SENSOR):
        raise SchemaFlowError("invalid_config")

    return config


def _schema(
    defaults: dict[str, Any] | None = None,
    *,
    use_defaults: bool = True,
    use_filtered_optional_selectors: bool = True,
) -> vol.Schema:
    """Build the shared config and options schema."""
    defaults = defaults or {}
    schema_dict = {
        vol.Required(
            "integration_description",
            default=defaults.get("integration_description", "Unnamed")
            if use_defaults
            else vol.UNDEFINED,
        ): selector.TextSelector(),
        vol.Required(
            ELECTRICITY_PRICE_SENSOR,
            default=defaults.get(ELECTRICITY_PRICE_SENSOR)
            if use_defaults
            else vol.UNDEFINED,
        ): _entity_selector(
            domains=[SENSOR_DOMAIN, NUMBER_DOMAIN, INPUT_NUMBER_DOMAIN]
        ),
    }

    for key, device_class in ((POWER_SENSOR, "power"), (ENERGY_SENSOR, "energy")):
        default = _clean_optional_value(defaults.get(key, vol.UNDEFINED))
        marker = vol.Optional(
            key,
            default=default
            if use_defaults and default is not vol.UNDEFINED
            else vol.UNDEFINED,
        )
        schema_dict[marker] = vol.Any(
            None,
            _filtered_entity_selector(
                domains=[SENSOR_DOMAIN], device_class=device_class
            )
            if use_filtered_optional_selectors
            else _entity_selector(domains=[SENSOR_DOMAIN]),
        )

    return vol.Schema(schema_dict)


def _sensor_options(is_power: bool) -> list[selector.SelectOptionDict]:
    """Return the available sensor options based on sensor type.

    Real Time Cost is not shown as a selectable option for power sensors —
    it is always created automatically. Only interval sensors are selectable.
    """
    keys = list(INTERVALS)
    return [
        selector.SelectOptionDict(value=key, label=SENSOR_LABELS[key])
        for key in keys
    ]


def _sensor_selection_schema(
    is_power: bool,
    defaults: list[str] | None = None,
) -> vol.Schema:
    """Build the sensor selection schema."""
    options = _sensor_options(is_power)
    all_values = [opt["value"] for opt in options]
    # Filter out real_time from defaults — it's not a selectable option
    if defaults is not None:
        defaults = [d for d in defaults if d != REAL_TIME]
    return vol.Schema(
        {
            vol.Required(
                SELECTED_SENSORS,
                default=defaults if defaults is not None else all_values,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                )
            )
        }
    )


def _normalize_sensor_selection(
    selected: list[str], is_power: bool
) -> list[str]:
    """Normalize sensor selection.

    For power path, auto-include real_time when any interval is selected.
    """
    result = set(selected)
    if is_power and any(i in result for i in INTERVALS):
        result.add(REAL_TIME)
    return sorted(result)


class DynamicEnergyCostConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dynamic Energy Cost."""

    VERSION = 3
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self) -> None:
        """Initialize config flow."""
        super().__init__()
        self._user_input: dict[str, Any] | None = None

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        _LOGGER.debug("Initiating config flow for user")
        errors = {}

        if user_input is not None:
            _LOGGER.info("Received user input: %s", user_input)
            try:
                config = _validate_config(user_input)
                self._user_input = config
                return await self.async_step_sensors()
            except SchemaFlowError as err:
                _LOGGER.warning("Config flow validation error: %s", err)
                errors["base"] = str(err)
            except vol.Invalid as err:
                _LOGGER.error("Validation error: %s", err)
                errors["base"] = "invalid_entity"

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(_schema(), user_input),
            errors=errors,
            last_step=False,
            description_placeholders={
                "integration_description": "Name to append the integration title",
                "electricity_price_sensor": "Electricity Price Sensor",
                "power_sensor": "Power Usage Sensor",
                "energy_sensor": "Energy (kWh) Sensor",
            },
        )

    async def async_step_sensors(self, user_input=None):
        """Handle the sensor selection step."""
        assert self._user_input is not None
        is_power = bool(self._user_input.get(POWER_SENSOR))
        errors = {}

        if user_input is not None:
            selected = user_input.get(SELECTED_SENSORS, [])
            if not selected:
                errors["base"] = "no_sensors_selected"
            else:
                normalized = _normalize_sensor_selection(selected, is_power)
                self._user_input[SELECTED_SENSORS] = normalized
                _LOGGER.info("Config entry created successfully")
                return self.async_create_entry(
                    title=f"Dynamic Energy Cost - {self._user_input['integration_description']}",
                    data=self._user_input,
                )

        return self.async_show_form(
            step_id="sensors",
            data_schema=_sensor_selection_schema(is_power),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return DynamicEnergyCostOptionsFlow(config_entry)


class DynamicEnergyCostOptionsFlow(config_entries.OptionsFlow):
    """Handle an options flow for DynamicEnergyCost."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__()
        self._config_entry = config_entry
        self._user_input: dict[str, Any] | None = None

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        return await self.async_step_user(user_input)

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        current_values = {**self._config_entry.data, **self._config_entry.options}

        if user_input is not None:
            try:
                config = _validate_config(user_input)
            except SchemaFlowError as err:
                errors["base"] = str(err)
            except vol.Invalid:
                errors["base"] = "invalid_entity"
            else:
                self._user_input = config
                return await self.async_step_sensors()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _schema(current_values, use_defaults=False),
                user_input or current_values,
            ),
            errors=errors,
            last_step=False,
        )

    async def async_step_sensors(self, user_input=None):
        """Handle the sensor selection step."""
        assert self._user_input is not None
        is_power = bool(self._user_input.get(POWER_SENSOR))
        errors = {}

        if user_input is not None:
            selected = user_input.get(SELECTED_SENSORS, [])
            if not selected:
                errors["base"] = "no_sensors_selected"
            else:
                normalized = _normalize_sensor_selection(selected, is_power)
                self._user_input[SELECTED_SENSORS] = normalized
                return self.async_create_entry(title="", data=self._user_input)

        current_selected = list(get_selected_sensors(self._config_entry))
        return self.async_show_form(
            step_id="sensors",
            data_schema=_sensor_selection_schema(is_power, defaults=current_selected),
            errors=errors,
        )
