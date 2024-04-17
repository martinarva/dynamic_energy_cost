import logging
import voluptuous as vol
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from .const import DOMAIN, ELECTRICITY_PRICE_SENSOR, POWER_SENSOR

_LOGGER = logging.getLogger(__name__)

class DynamicEnergyCostConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dynamic Energy Cost."""
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                # Direct validation of entity IDs
                cv.entity_id(user_input["electricity_price_sensor"])
                cv.entity_id(user_input["power_sensor"])
                
                # Create the config dictionary
                config = {
                    "electricity_price_sensor": user_input["electricity_price_sensor"],
                    "power_sensor": user_input["power_sensor"]
                }
                return self.async_create_entry(title="Dynamic Energy Cost", data=config)
            except vol.Invalid as err:
                _LOGGER.error("Validation error: %s", err)
                errors["base"] = "invalid_entity"  # Use a fixed error key with a translation path in the frontend

        schema = vol.Schema({
            vol.Required("electricity_price_sensor"): str,
            vol.Required("power_sensor"): str
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors, 
            description_placeholders={
                "electricity_price_sensor": "Electricity Price Sensor",
                "power_sensor": "Power Usage Sensor",
            }  
        )

    # @staticmethod
    # @callback
    # def async_get_options_flow(config_entry):
    #     """Define the options flow for this integration."""
    #     return OptionsFlowHandler(config_entry)
