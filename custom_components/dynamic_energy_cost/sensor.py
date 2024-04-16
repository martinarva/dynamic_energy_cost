
import logging
from homeassistant.helpers.entity import Entity
from .const import DOMAIN, ELECTRICITY_PRICE_SENSOR, POWER_SENSOR

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the sensor based on a configuration entry."""
    config = config_entry.data
    electricity_sensor = config[ELECTRICITY_PRICE_SENSOR]
    power_sensor = config[POWER_SENSOR]

    async_add_entities([DynamicEnergyCostSensor(hass, electricity_sensor, power_sensor)], True)

class DynamicEnergyCostSensor(Entity):
    """Representation of a Sensor that calculates dynamic energy costs."""

    def __init__(self, hass, electricity_sensor, power_sensor):
        """Initialize the sensor."""
        self._hass = hass
        self._electricity_sensor = electricity_sensor
        self._power_sensor = power_sensor
        self._state = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'Dynamic Energy Cost'

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return 'EUR'

    async def async_update(self):
        """Fetch new state data for the sensor."""
        electricity_price = float(self._hass.states.get(self._electricity_sensor).state)
        power = float(self._hass.states.get(self._power_sensor).state)
        self._state = round((electricity_price * power) / 1000, 2)  # assuming power is in watts
