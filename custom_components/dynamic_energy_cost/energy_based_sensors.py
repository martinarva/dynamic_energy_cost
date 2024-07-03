import logging
from datetime import timedelta
from homeassistant.util.dt import now
from homeassistant.helpers.event import async_track_state_change_event, async_track_point_in_time
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers import entity_platform
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.core import callback
from .const import DOMAIN, ELECTRICITY_PRICE_SENSOR, ENERGY_SENSOR, SERVICE_RESET_COST

_LOGGER = logging.getLogger(__name__)

class BaseEnergyCostSensor(RestoreEntity, SensorEntity):
    """Base sensor for handling energy cost data."""

    def __init__(self, hass, energy_sensor_id, price_sensor_id, interval):
        super().__init__()
        self.hass = hass
        self._energy_sensor_id = energy_sensor_id
        self._price_sensor_id = price_sensor_id
        self._state = None
        self._unit_of_measurement = None  # Default to None, will update after entity addition
        self._interval = interval
        self._last_energy_reading = None
        self._cumulative_energy_kwh = 0
        self._last_reset_time = now()
        self.schedule_next_reset()
        _LOGGER.debug("Sensor initialized with energy sensor ID %s and price sensor ID %s.", energy_sensor_id, price_sensor_id)

        _LOGGER.debug(f"Initializing EnergyCostSensor with energy_sensor_id: {energy_sensor_id} and price_sensor_id: {price_sensor_id}")

        # Generate friendly names based on the energy sensor's ID
        base_part = energy_sensor_id.split('.')[-1]
        _LOGGER.debug(f"Base part extracted from energy_sensor_id: {base_part}")

        friendly_name_parts = base_part.replace('_', ' ').split()
        _LOGGER.debug(f"Parts after replacing underscores and splitting: {friendly_name_parts}")

        # Exclude words that are commonly not part of the main identifier
        friendly_name_parts = [word for word in friendly_name_parts if word.lower() != 'energy']
        _LOGGER.debug(f"Parts after removing 'energy': {friendly_name_parts}")

        friendly_name = ' '.join(friendly_name_parts).title()
        _LOGGER.debug(f"Final friendly name generated: {friendly_name}")

        self._base_name = friendly_name
        self._device_name = friendly_name + ' Dynamic Energy Cost'

        _LOGGER.debug(f"Sensor base name set to: {self._base_name}")
        _LOGGER.debug(f"Sensor device name set to: {self._device_name}")

    @callback
    def async_reset(self):
        """Reset the energy cost and cumulative energy kWh."""
        _LOGGER.debug(f"Resetting cost for {self.entity_id}")
        self._state = 0
        self._cumulative_energy_kwh = 0
        self.async_write_ha_state()

    @property
    def unique_id(self):
        return f"{self._price_sensor_id}_{self._energy_sensor_id}_{self._interval}_cost"

    @property
    def name(self):
        return f"{self._base_name} {self._interval.capitalize()} Energy Cost"
    @property
    def device_info(self):
        """Return device information to link this sensor with the integration."""
        return {
            "identifiers": {(DOMAIN, self._energy_sensor_id)},
            "name": self._device_name,
            "manufacturer": "Custom Integration"
        }

    @property
    def state(self):
        return self._state

    @property
    def unit_of_measurement(self):
        return self._unit_of_measurement

    @property
    def device_class(self):
        """Return the class of this device, from SensorDeviceClass."""
        return SensorDeviceClass.MONETARY

    @property
    def state_class(self):
        """Return the state class of this device, from SensorStateClass."""
        return SensorStateClass.TOTAL

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return "mdi:cash"

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the device."""
        attrs = super().extra_state_attributes or {}  # Ensure it's a dict
        attrs['cumulative_energy_kwh'] = self._cumulative_energy_kwh
        attrs['last_energy_reading'] = self._last_energy_reading
        attrs['average_energy_cost'] = self._state / self._cumulative_energy_kwh if self._cumulative_energy_kwh else 0
        return attrs
    
    async def async_added_to_hass(self):
        """Load the last known state and subscribe to updates."""
        await super().async_added_to_hass()
        self._unit_of_measurement = self.get_currency()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ['unknown', 'unavailable', None]:
            self._state = float(last_state.state)
            self._last_energy_reading = float(last_state.attributes.get('last_energy_reading'))
            self._cumulative_energy_kwh = float(last_state.attributes.get('cumulative_energy_kwh'))
        self.async_write_ha_state()
        async_track_state_change_event(self.hass, self._energy_sensor_id, self._async_update_energy_price_event)
        self.schedule_next_reset()

    def get_currency(self):
        """Get the Home Assistant default currency."""
        currency = self.hass.config.currency
        if currency:
            _LOGGER.debug(f"Using Home Assistant default currency '{currency}'.")
            return currency
        else:
            _LOGGER.warning("No default currency set in Home Assistant.")
            return None  # No default currency


    def calculate_next_reset_time(self):
        current_time = now()
        if self._interval == "daily":
            next_reset = current_time.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        elif self._interval == "weekly":
            # Calculate the date of the next Monday
            days_until_monday = (7 - current_time.weekday()) % 7
            next_monday = (current_time + timedelta(days=days_until_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
            # If today is Monday, set to next Monday
            if days_until_monday == 0:
                next_monday += timedelta(days=7)
            next_reset = next_monday
        elif self._interval == "monthly":
            next_month = (current_time.replace(day=1) + timedelta(days=32)).replace(day=1)
            next_reset = next_month.replace(hour=0, minute=0, second=0, microsecond=0)
        elif self._interval == "yearly":
            next_reset = current_time.replace(year=current_time.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return next_reset

    def schedule_next_reset(self):
        next_reset = self.calculate_next_reset_time()
        async_track_point_in_time(self.hass, self._reset_meter, next_reset)

    async def _reset_meter(self, _):
        self._state = 0  # Reset the cost to zero
        self._cumulative_energy_kwh = 0 # Reset the cumulative energy kWh count to zero
        self.async_write_ha_state() # Update the state in Home Assistant
        self.schedule_next_reset() # Reschedule the next reset
        _LOGGER.debug(f"Meter reset for {self.name} and cumulative energy reset to {self._cumulative_energy_kwh}. Next reset scheduled.")

    async def _async_update_energy_price_event(self, event):
        """Handle sensor state changes based on event data."""
        new_state = event.data.get('new_state')
        if new_state is None or new_state.state in ['unknown', 'unavailable']:
            _LOGGER.debug("New state is unknown or unavailable, skipping update.")
            return
        await self.async_update()

    async def async_update(self):
        """Update the energy costs using the latest sensor states, only adding incremental costs."""
        _LOGGER.debug("Attempting to update energy costs.")
        energy_state = self.hass.states.get(self._energy_sensor_id)
        price_state = self.hass.states.get(self._price_sensor_id)

        if not energy_state or not price_state or energy_state.state in ['unknown', 'unavailable'] or price_state.state in ['unknown', 'unavailable']:
            _LOGGER.warning("One or more sensors are unavailable. Skipping update.")
            return

        try:
            current_energy = float(energy_state.state)
            price = float(price_state.state)

            if self._last_energy_reading is not None and current_energy >= self._last_energy_reading:
                energy_difference = current_energy - self._last_energy_reading
                cost_increment = energy_difference * price
                self._state = (self._state if self._state is not None else 0) + cost_increment
                self._cumulative_energy_kwh += energy_difference  # Add to the running total of energy
                _LOGGER.info(f"Energy cost incremented by {cost_increment} EUR, total cost now {self._state} EUR")
                
            elif self._last_energy_reading is not None and current_energy < self._last_energy_reading:
                _LOGGER.debug("Possible meter reset or rollback detected; recalculating from new base.")
                # Optionally reset the cost if you determine it's a complete reset
                # self._state = 0  # Uncomment this if you need to reset the state
            else:
                _LOGGER.debug("No previous energy reading available; initializing with current reading.")

            self._last_energy_reading = current_energy  # Always update the last reading

            self.async_write_ha_state()

        except Exception as e:
            _LOGGER.error(f"Failed to update energy costs due to an error: {e}", exc_info=True)
        pass

# Define sensor classes for each interval
class DailyEnergyCostSensor(BaseEnergyCostSensor):
    def __init__(self, hass, energy_sensor_id, price_sensor_id):
        super().__init__(hass, energy_sensor_id, price_sensor_id, "daily")

class WeeklyEnergyCostSensor(BaseEnergyCostSensor):
    def __init__(self, hass, energy_sensor_id, price_sensor_id):
        super().__init__(hass, energy_sensor_id, price_sensor_id, "weekly")

class MonthlyEnergyCostSensor(BaseEnergyCostSensor):
    def __init__(self, hass, energy_sensor_id, price_sensor_id):
        super().__init__(hass, energy_sensor_id, price_sensor_id, "monthly")

class YearlyEnergyCostSensor(BaseEnergyCostSensor):
    def __init__(self, hass, energy_sensor_id, price_sensor_id):
        super().__init__(hass, energy_sensor_id, price_sensor_id, "yearly")

async def async_setup_entry(hass, config_entry, async_add_entities):
    energy_sensor_id = config_entry.data.get(ENERGY_SENSOR)
    price_sensor_id = config_entry.data.get(ELECTRICITY_PRICE_SENSOR)
    sensors = [
        DailyEnergyCostSensor(hass, energy_sensor_id, price_sensor_id),
        WeeklyEnergyCostSensor(hass, energy_sensor_id, price_sensor_id),
        MonthlyEnergyCostSensor(hass, energy_sensor_id, price_sensor_id),
        YearlyEnergyCostSensor(hass, energy_sensor_id, price_sensor_id)
    ]
    async_add_entities(sensors, True)
