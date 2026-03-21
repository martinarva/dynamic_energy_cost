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

from .const import DOMAIN, ELECTRICITY_PRICE_SENSOR, ENERGY_SENSOR, POWER_SENSOR


_LOGGER = logging.getLogger(__name__)


def _entity_selector(*, domains: list[str], device_class: str | None = None):
    """Create an entity selector for a single entity."""
    return selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain=domains,
            multiple=False,
            device_class=device_class,
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
    cleaned["integration_description"] = cleaned.get("integration_description", "Unnamed")
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


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Build the shared config and options schema."""
    defaults = defaults or {}

    schema_dict = {
        vol.Required(
            "integration_description",
            default=defaults.get("integration_description", "Unnamed"),
        ): selector.TextSelector(),
        vol.Required(
            ELECTRICITY_PRICE_SENSOR,
            default=defaults.get(ELECTRICITY_PRICE_SENSOR),
        ): _entity_selector(
            domains=[SENSOR_DOMAIN, NUMBER_DOMAIN, INPUT_NUMBER_DOMAIN]
        ),
    }

    for key, device_class in ((POWER_SENSOR, "power"), (ENERGY_SENSOR, "energy")):
        default = _clean_optional_value(defaults.get(key, vol.UNDEFINED))
        schema_dict[vol.Optional(key, default=default)] = vol.Any(
            None,
            _entity_selector(domains=[SENSOR_DOMAIN], device_class=device_class),
        )

    return vol.Schema(schema_dict)


class DynamicEnergyCostConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dynamic Energy Cost."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        _LOGGER.debug("Initiating config flow for user")
        errors = {}

        if user_input is not None:
            _LOGGER.info("Received user input: %s", user_input)
            try:
                config = _validate_config(user_input)
                _LOGGER.info("Config entry created successfully")
                return self.async_create_entry(
                    title=f"Dynamic Energy Cost - {config['integration_description']}",
                    data=config,
                )
            except SchemaFlowError as err:
                _LOGGER.warning("Config flow validation error: %s", err)
                errors["base"] = str(err)
            except vol.Invalid as err:
                _LOGGER.error("Validation error: %s", err)
                errors["base"] = "invalid_entity"

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(),
            errors=errors,
            description_placeholders={
                "integration_description": "Name to append the integration title",
                "electricity_price_sensor": "Electricity Price Sensor",
                "power_sensor": "Power Usage Sensor",
                "energy_sensor": "Energy (kWh) Sensor",
            },
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
                return self.async_create_entry(title="", data=config)

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(current_values),
            errors=errors,
        )
