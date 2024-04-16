import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN  # Ensure you have a const.py that defines DOMAIN

class DynamicEnergyCostConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dynamic Energy Cost."""
    
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Optional: Add additional validation of the user input here
            # Example: Check if the selected sensors actually exist or are valid
            # This would typically involve checking the state of the sensors
            # in Home Assistant's entity registry.

            return self.async_create_entry(title="Dynamic Energy Cost", data=user_input)

        fields = {
            vol.Required("electricity_price_sensor"): cv.entity_id,
            vol.Required("power_sensor"): cv.entity_id
        }

        return self.async_show_form(
            step_id="user", 
            data_schema=vol.Schema(fields), 
            errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handles options flow for the integration."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}

        if user_input is not None:
            # Here, you could add checks before saving the options,
            # such as validating the new sensor selections
            return self.async_create_entry(title="", data=user_input)

        fields = {
            vol.Required("electricity_price_sensor", default=self.config_entry.options.get("electricity_price_sensor", self.config_entry.data.get("electricity_price_sensor"))): cv.entity_id,
            vol.Required("power_sensor", default=self.config_entry.options.get("power_sensor", self.config_entry.data.get("power_sensor"))): cv.entity_id
        }

        return self.async_show_form(
            step_id="init", 
            data_schema=vol.Schema(fields), 
            errors=errors
        )
