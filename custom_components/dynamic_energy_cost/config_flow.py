"""Class representing a Dynamic Energy Costs config flow."""

import logging

from homeassistant import config_entries
from homeassistant.components.input_number import DOMAIN as INPUT_NUMBER_DOMAIN
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.schema_config_entry_flow import SchemaFlowError

import voluptuous as vol

from .const import DOMAIN


_LOGGER = logging.getLogger(__name__)


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
                # Validate the electricity price sensor
                cv.entity_id(user_input["electricity_price_sensor"])
                if user_input.get("power_sensor"):
                    cv.entity_id(user_input["power_sensor"])
                if user_input.get("energy_sensor"):
                    cv.entity_id(user_input["energy_sensor"])

                # Check that either power sensor or energy sensor is filled
                if not user_input.get("power_sensor") and not user_input.get(
                    "energy_sensor"
                ):
                    _LOGGER.warning("Neither power nor energy sensor was provided")
                    raise SchemaFlowError("invalid_config")
                if user_input.get("power_sensor") and user_input.get("energy_sensor"):
                    _LOGGER.warning("Both power and energy sensors were provided")
                    raise SchemaFlowError("missing_sensor")

                # Create the config dictionary
                config = {
                    "electricity_price_sensor": user_input["electricity_price_sensor"],
                    "power_sensor": user_input.get("power_sensor"),
                    "energy_sensor": user_input.get("energy_sensor"),
                    "integration_description": user_input.get(
                        "integration_description", "Unnamed"
                    ),
                }
                _LOGGER.info("Config entry created successfully")
                return self.async_create_entry(
                    title=f"Dynamic Energy Cost - {user_input.get('integration_description', 'Unnamed')}",
                    data=config,
                )
            except vol.Invalid as err:
                _LOGGER.error("Validation error: %s", err)
                errors["base"] = "invalid_entity"

        schema = vol.Schema(
            {
                vol.Required("integration_description"): selector.TextSelector(),
                vol.Required("electricity_price_sensor"): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=[SENSOR_DOMAIN, NUMBER_DOMAIN, INPUT_NUMBER_DOMAIN],
                        multiple=False,
                    )
                ),
                vol.Optional("power_sensor"): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=[SENSOR_DOMAIN], multiple=False, device_class="power"
                    )
                ),
                vol.Optional("energy_sensor"): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=[SENSOR_DOMAIN], multiple=False, device_class="energy"
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "integration_description": "Name to append the integration title",
                "electricity_price_sensor": "Electricity Price Sensor",
                "power_sensor": "Power Usage Sensor",
                "energy_sensor": "Energy (kWh) Sensor",
            },
        )

    # Change existing config added !!
    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return DynamicEnergyCostOptionsFlow()


# Change existing config added !!
class DynamicEnergyCostOptionsFlow(config_entries.OptionsFlow):
    """Handle an options flow for DynamicEnergyCost."""

    async def async_step_init(self, user_input=None):
        """Manage the options."""

        errors = {}

        if user_input is not None:
            _LOGGER.info("Received user input: %s", user_input)
            try:
                # Validate the electricity price sensor
                cv.entity_id(user_input["electricity_price_sensor"])

                # Create the config dictionary
                config = self.config_entry.data | user_input

                # write updated config entries
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=config, options=self.config_entry.options
                )

                # write empty options entries
                return self.async_create_entry(title=None, data=None)
            except vol.Invalid as err:
                _LOGGER.error("Validation error: %s", err)
                errors["base"] = "invalid_entity"

        schema = vol.Schema(
            {
                vol.Required(
                    "electricity_price_sensor",
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=[SENSOR_DOMAIN, NUMBER_DOMAIN, INPUT_NUMBER_DOMAIN],
                        multiple=False,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema, self.config_entry.data
            ),
            errors=errors,
        )
