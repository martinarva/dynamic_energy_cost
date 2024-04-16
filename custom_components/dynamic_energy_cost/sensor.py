from datetime import datetime, timedelta
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import CONF_NAME, ENERGY_KILO_WATT_HOUR, EVENT_HOMEASSISTANT_START
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, ELECTRICITY_PRICE_SENSOR, POWER_SENSOR

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Setup sensor platform."""
    config = config_entry.data
    electricity_price_sensor = config[ELECTRICITY_PRICE_SENSOR]
    power_sensor = config[POWER_SENSOR]

    async_add_entities([
        DynamicCostSensor(hass, 'Dynamic Energy Cost', electricity_price_sensor, power_sensor),
        CumulativeCostSensor(hass, 'Cumulative Energy Cost', 'sensor.dynamic_energy_cost_right_now')
    ], True)

class DynamicCostSensor(Entity):
    """Dynamic Cost Sensor that calculates cost in real-time based on power usage and current electricity price."""

    def __init__(self, hass, name, electricity_price_sensor_id, power_sensor_id):
        """Initialize the sensor."""
        self.hass = hass
        self._name = name
        self._electricity_price_sensor_id = electricity_price_sensor_id
        self._power_sensor_id = power_sensor_id
        self._state = 0

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self._name} Cost Right Now"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return 'EUR'

    def update(self):
        """Update the sensor state."""
        electricity_price = float(self.hass.states.get(self._electricity_price_sensor_id).state)
        power = float(self.hass.states.get(self._power_sensor_id).state)
        self._state = round((electricity_price * power / 1000), 2)  # assuming power is in watts

class CumulativeCostSensor(RestoreEntity, SensorEntity):
    """Sensor to accumulate energy costs over time."""

    def __init__(self, hass, name, source_sensor):
        """Initialize the cumulative cost sensor."""
        self.hass = hass
        self._name = name
        self._source_sensor = source_sensor
        self._state = 0.0
        self._last_updated = datetime.now()

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return 'EUR'

    async def async_added_to_hass(self):
        """Handle entity which will be added to Home Assistant."""
        await super().async_added_to_hass()

        @callback
        def update_cost(entity, old_state, new_state):
            """Handle the sensor state changes."""
            if new_state is None:
                return
            current_cost = float(new_state.state)
            now = datetime.now()
            if self._last_updated is not None:
                time_diff = now - self._last_updated
                incremental_cost = current_cost * (time_diff.total_seconds() / 3600)
                self._state += incremental_cost
            self._last_updated = now
            self.async_write_ha_state()

        async_track_state_change_event(self.hass, self._source_sensor, update_cost)
