import logging
from decimal import Decimal
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval, async_track_point_in_time
from homeassistant.util.dt import now
from datetime import timedelta
from .const import DOMAIN, ELECTRICITY_PRICE_SENSOR, ENERGY_SENSOR, POWER_SENSOR, SERVICE_RESET_COST
_LOGGER = logging.getLogger(__name__)

class RealTimeCostSensor(SensorEntity):
    """Sensor that calculates energy cost in real-time based on power usage and electricity price."""

    def __init__(self, hass, config_entry, electricity_price_sensor_id, power_sensor_id, name):
        """Initialize the sensor."""
        self.hass = hass
        self._config_entry = config_entry
        self._electricity_price_sensor_id = electricity_price_sensor_id
        self._power_sensor_id = power_sensor_id
        self._state = Decimal(0)
        self._unit_of_measurement = None  # Default to None, will update after entity addition

        _LOGGER.debug(f"Initialized Real Time Cost Sensor with price sensor: {electricity_price_sensor_id} and power sensor: {power_sensor_id}")

        # Extract a friendly name from the power sensor's entity ID
        base_part = power_sensor_id.split('.')[-1]  # Assuming entity_id format like 'sensor.heat_pump_power'
        friendly_name_parts = base_part.replace('_', ' ').split()  # Split into words
        friendly_name_parts = [word for word in friendly_name_parts if word.lower() != 'power']  # Remove the word "Power"
        friendly_name = ' '.join(friendly_name_parts).title()  # Rejoin and title-case
        self._base_name = friendly_name + ' Real Time Energy Cost'

        # Prepare a device name using the friendly base part
        self._device_name = friendly_name + ' Dynamic Energy Cost'

    @property
    def unique_id(self):
        """Return a unique identifier for this sensor."""
        return f"{self._config_entry.entry_id}_{self._power_sensor_id}_real_time_cost"

    @property
    def device_info(self):
        """Return device information to link this sensor with the integration."""
        return {
            "identifiers": {(DOMAIN, self._config_entry.entry_id)},
            "name": self._device_name,
            "manufacturer": "Custom Integration"
        }

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._base_name

    @property
    def state(self):
        """Return the current state of the sensor."""
        return float(self._state)

    @property
    def unit_of_measurement(self):
        return self._unit_of_measurement

    @callback
    def handle_state_change(self, event):
        """Handle changes to the electricity price or power usage."""
        entity_id = event.data['entity_id']
        new_state = event.data.get('new_state')

        if new_state is None or new_state.state in ['unknown', 'unavailable']:
            _LOGGER.warning(f"State of {entity_id} is '{new_state.state}', skipping update.")
            return

        electricity_price = self.hass.states.get(self._electricity_price_sensor_id).state
        power_usage = self.hass.states.get(self._power_sensor_id).state

        if not electricity_price or not power_usage or electricity_price in ['unknown', 'unavailable'] or power_usage in ['unknown', 'unavailable']:
            _LOGGER.warning("One or more sensor values are unavailable, skipping update.")
            return

        try:
            electricity_price = float(electricity_price)
            power_usage = float(power_usage)
            calculated_cost = round(electricity_price * (power_usage / 1000), 2)
            if calculated_cost != self._state:
                self._state = Decimal(calculated_cost)
                self.async_write_ha_state()
                _LOGGER.debug(f"Updated Real Time Energy Cost: {calculated_cost} EUR/h")
        except ValueError as e:
            _LOGGER.error(f"Error converting sensor data to float: {e}")

    async def async_added_to_hass(self):
        """Register callbacks when added to hass."""
        self._unit_of_measurement = self.get_currency()
        async_track_state_change_event(
            self.hass, [self._electricity_price_sensor_id, self._power_sensor_id], self.handle_state_change
        )
        _LOGGER.info(f"Callbacks registered for {self._electricity_price_sensor_id} and {self._power_sensor_id}")

    def get_currency(self):
        """Get the Home Assistant default currency."""
        currency = self.hass.config.currency
        if currency:
            currency_with_time = f"{currency}/h"
            _LOGGER.debug(f"Using Home Assistant default currency '{currency_with_time}'.")
            return currency_with_time
        else:
            _LOGGER.warning("No default currency set in Home Assistant.")
            return None  # No default currency

def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the sensor platform from a config entry."""
    electricity_price_sensor = config_entry.data.get('electricity_price_sensor')
    power_sensor = config_entry.data.get('power_sensor')
    real_time_cost_sensor = RealTimeCostSensor(hass, config_entry, electricity_price_sensor, power_sensor, 'Real Time Energy Cost')
    async_add_entities([real_time_cost_sensor])

    # Utility Meter Sensors setup
    intervals = ['daily', 'monthly', 'yearly']
    utility_sensors = [UtilityMeterSensor(hass, real_time_cost_sensor, interval) for interval in intervals]
    async_add_entities(utility_sensors)

class UtilityMeterSensor(SensorEntity, RestoreEntity):
    """Sensor that calculates cumulative energy costs over set intervals and resets accordingly."""

    def __init__(self, hass, real_time_cost_sensor, interval):
        """Initialize the sensor."""
        super().__init__()
        self.hass = hass
        self._real_time_cost_sensor = real_time_cost_sensor
        self._interval = interval
        self._state = Decimal('0.00')
        self._unit_of_measurement = None  # Default to None, will update after entity addition
        self._last_update = now()
        base_name = real_time_cost_sensor.name.replace(" Real Time Energy Cost", "").strip()
        self._name = f"{base_name} {interval.title()} Energy Cost"

    async def async_added_to_hass(self):
        """Restore state and set up updates when added to Home Assistant."""
        await super().async_added_to_hass()
        # Restore state if available
        self._unit_of_measurement = self.get_currency()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ('unknown', 'unavailable'):
            try:
                self._state = Decimal(last_state.state)
            except InvalidOperation:
                _LOGGER.error("Invalid state value for restoration: %s", last_state.state)
        self.schedule_next_reset()
        _LOGGER.debug("Registering state change event for: %s", self._real_time_cost_sensor.entity_id)
        try:
            async_track_state_change_event(self.hass, [self._real_time_cost_sensor.entity_id], self._handle_real_time_cost_update)
        except Exception as e:
            _LOGGER.error("Failed to track state change: %s", str(e))

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
        """Determine the exact datetime for the next reset based on the interval."""
        current_time = now()
        if self._interval == "daily":
            next_reset = (current_time + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif self._interval == "monthly":
            next_month = (current_time.replace(day=1) + timedelta(days=32)).replace(day=1)
            next_reset = next_month.replace(hour=0, minute=0, second=0, microsecond=0)
        elif self._interval == "yearly":
            next_reset = current_time.replace(year=current_time.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        
        _LOGGER.debug(f"Calculated next reset time for {self._interval} reset: {next_reset}")
        return next_reset

    @callback
    def async_reset(self):
        """Reset the energy cost and cumulative energy kWh."""
        _LOGGER.debug(f"Resetting cost for {self.entity_id}")
        self._state = 0
        self.async_write_ha_state()

    @callback
    def schedule_next_reset(self):
        """Schedule the next reset based on the interval, cancelling any previous schedules."""
        next_reset_time = self.calculate_next_reset_time()

        # Cancel existing scheduled reset if it exists
        if hasattr(self, '_reset_timer'):
            self.hass.async_create_task(self.hass.async_remove_job(self._reset_timer))

        # Log the scheduling of the next reset
        _LOGGER.debug(f"Scheduling next reset for {self._name} at {next_reset_time}")

        # Schedule the next reset
        self._reset_timer = async_track_point_in_time(self.hass, self._reset_meter, next_reset_time)
        _LOGGER.debug("Next reset scheduled successfully.")

    async def _reset_meter(self, _):
        """Reset the meter at the specified interval."""
        self._state = Decimal('0.00')
        self._last_update = now()
        self.async_write_ha_state()
        self.schedule_next_reset()
        _LOGGER.debug(f"Meter reset for {self._name}. Next reset scheduled.")

    @callback
    def _handle_real_time_cost_update(self, event):
        """Update cumulative cost based on the real-time cost sensor updates."""
        new_state = event.data.get('new_state')
        if new_state is None or new_state.state in ('unknown', 'unavailable'):
            _LOGGER.debug("Skipping update due to unavailable state")
            return

        try:
            current_cost = Decimal(new_state.state)
            _LOGGER.debug(f"Current cost retrieved from state: {current_cost}")  # Log current cost

            if current_cost <= 0:  # Skip updates if the new cost is not positive
                _LOGGER.debug(f"Skipping update as the calculated cost {current_cost} is not positive.")
                return

            time_difference = now() - self._last_update
            hours_passed = Decimal(time_difference.total_seconds()) / Decimal(3600)  # Convert time difference to hours as Decimal
            _LOGGER.debug(f"Time difference calculated as: {time_difference}, which is {hours_passed} hours.")  # Log time difference in hours

            self._state += (current_cost * hours_passed).quantize(Decimal('0.0001'))
            self._last_update = now()
            self.async_write_ha_state()
            _LOGGER.debug(f"Updated state to: {self._state} using cost: {current_cost} over {hours_passed} hours")
        except (InvalidOperation, TypeError) as e:
            _LOGGER.error(f"Error updating cumulative cost: {e}")

    @property
    def unique_id(self):
        """Return a unique identifier for this sensor."""
        return f"{self._real_time_cost_sensor.unique_id}_{self._interval}"

    @property
    def device_info(self):
        """Link this sensor to the real-time cost sensor's device."""
        return self._real_time_cost_sensor.device_info

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the current cumulative cost."""
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
    def should_poll(self):
        """No need to poll. Will be updated by RealTimeCostSensor."""
        return False
