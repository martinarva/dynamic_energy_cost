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

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return DynamicEnergyCostOptionsFlow(config_entry)


class DynamicEnergyCostOptionsFlow(config_entries.OptionsFlow):
    """Handle an options flow for DynamicEnergyCost."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__()

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        return await self.async_step_user(user_input)

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        current_values = self.config_entry.options or self.config_entry.data

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema_dict = {
            vol.Required(
                "electricity_price_sensor",
                default=current_values.get("electricity_price_sensor"),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=[SENSOR_DOMAIN, NUMBER_DOMAIN, INPUT_NUMBER_DOMAIN],
                    multiple=False,
                )
            )
        }

        for key, device_class in (
            ("power_sensor", "power"),
            ("energy_sensor", "energy"),
        ):
            schema_dict[
                vol.Optional(key, default=current_values.get(key, vol.UNDEFINED))
            ] = selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=[SENSOR_DOMAIN],
                    multiple=False,
                    device_class=device_class,
                )
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )
