from homeassistant import config_entries
import voluptuous as vol
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

class MyEnergyTrackerConfigFlow(config_entries.ConfigFlow, domain="my_energy_tracker"):
    VERSION = 1
    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            return self.async_create_entry(title="Configure My Energy Tracker", data=user_input)
        fields = {
            vol.Required("electricity_price_sensor"): cv.entity_id,
            vol.Required("power_sensor"): cv.entity_id
        }
        return self.async_show_form(step_id="user", data_schema=vol.Schema(fields), errors=errors)
