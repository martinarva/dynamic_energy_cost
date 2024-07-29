import logging
import voluptuous as vol
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import selector
from .const import DOMAIN, ELECTRICITY_PRICE_SENSOR, POWER_SENSOR, ENERGY_SENSOR

_LOGGER = logging.getLogger(__name__)

class DynamicEnergyCostConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dynamic Energy Cost."""
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def generate_friendly_name(self, sensor_id: str) -> str:
        """Generate a friendly name from the sensor ID."""
        # Remove common prefix like 'sensor.'
        if sensor_id.startswith('sensor.'):
            sensor_id = sensor_id[len('sensor.'):]
        # Replace underscores and dots with spaces
        name = sensor_id.replace('_', ' ').replace('.', ' ')
        # Capitalize first letter of each word, except small common words
        name = ' '.join(word.capitalize() if word.lower() not in ['a', 'an', 'the', 'and', 'of', 'in'] else word for word in name.split())
        return name

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        _LOGGER.debug("Initiating config flow for user.")
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
                if not user_input.get("power_sensor") and not user_input.get("energy_sensor"):
                    _LOGGER.warning("Neither power nor energy sensor was provided.")
                    raise vol.Invalid("Please enter either a power sensor or an energy sensor.")
                if user_input.get("power_sensor") and user_input.get("energy_sensor"):
                    _LOGGER.warning("Both power and energy sensors were provided.")
                    raise vol.Invalid("Please enter only one type of sensor (power or energy).")

                # Generate a friendly name
                sensor_id = user_input.get("power_sensor") or user_input.get("energy_sensor")
                title = f"Cost for {self.generate_friendly_name(sensor_id)}"

                # Create the config dictionary
                config = {
                    "electricity_price_sensor": user_input["electricity_price_sensor"],
                    "power_sensor": user_input.get("power_sensor"),
                    "energy_sensor": user_input.get("energy_sensor"),
                }

                _LOGGER.info("Config entry created successfully with title: %s", title)
                return self.async_create_entry(title=title, data=config)
            except vol.Invalid as err:
                _LOGGER.error("Validation error: %s", err)
                errors["base"] = "invalid_entity"

        schema = vol.Schema({
            vol.Required("electricity_price_sensor"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", multiple=False)
            ),
            vol.Optional("power_sensor"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", multiple=False, device_class="power")
            ),
            vol.Optional("energy_sensor"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", multiple=False, device_class="energy")
            )
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "electricity_price_sensor": "Electricity Price Sensor",
                "power_sensor": "Power Usage Sensor",
                "energy_sensor": "Energy (kWh) Sensor",
            }
        )
