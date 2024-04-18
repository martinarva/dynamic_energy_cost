import logging
from decimal import Decimal, InvalidOperation
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval, async_call_later
from homeassistant.helpers import config_validation as cv
from homeassistant.util.dt import now
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.exceptions import PlatformNotReady
from datetime import timedelta, datetime
import async_timeout
from .const import DOMAIN, ELECTRICITY_PRICE_SENSOR, POWER_SENSOR

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Setup sensor platform from a config entry."""
    _LOGGER.debug("Initializing setup entry for sensors.")
    electricity_price_sensor = config_entry.data[ELECTRICITY_PRICE_SENSOR]
    power_sensor = config_entry.data[POWER_SENSOR]

    real_time_cost_sensor = RealTimeCostSensor(
        hass,
        config_entry,
        electricity_price_sensor,
        power_sensor,
        'Real Time Energy Cost'
    )
    async_add_entities([real_time_cost_sensor], True)

    cumulative_cost_sensor = CumulativeCostSensor(
        hass,
        real_time_cost_sensor
    )
    async_add_entities([cumulative_cost_sensor], True)
    
    intervals = ['daily', 'monthly', 'yearly']
    utility_sensors = [UtilityMeterSensor(hass, real_time_cost_sensor, interval) for interval in intervals]
    async_add_entities(utility_sensors, True)


    # Set up listeners for the entities
    async_track_state_change_event(hass, [electricity_price_sensor, power_sensor], real_time_cost_sensor.handle_state_change)
    _LOGGER.info("Dynamic Energy Cost sensors setup complete.")

class RealTimeCostSensor(SensorEntity):
    """Sensor that calculates energy cost in real-time based on power usage and electricity price."""
    def __init__(self, hass, config_entry, electricity_price_sensor_id, power_sensor_id, name):
        """Initialize the sensor."""
        self.hass = hass
        self._config_entry = config_entry
        self._electricity_price_sensor_id = electricity_price_sensor_id
        self._power_sensor_id = power_sensor_id
        self._state = Decimal(0)

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
        """Dynamically return the name of the sensor."""
        return self._base_name

    @property
    def state(self):
        """Return the current state of the sensor."""
        return float(self._state)

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return 'EUR/h'

    @callback
    def handle_state_change(self, event):
        """Handle changes to the electricity price or power usage."""
        entity_id = event.data['entity_id']
        new_state = event.data.get('new_state')

        if new_state is None or new_state.state in ['unknown', 'unavailable']:
            _LOGGER.warning(f"State of {entity_id} is '{new_state.state}', skipping update.")
            return

        try:
            if entity_id == self._electricity_price_sensor_id:
                electricity_price = float(new_state.state)
                power_usage = float(self.hass.states.get(self._power_sensor_id).state)
            elif entity_id == self._power_sensor_id:
                power_usage = float(new_state.state)
                electricity_price = float(self.hass.states.get(self._electricity_price_sensor_id).state)
            else:
                return

            # Update the state only if both values are valid
            if electricity_price is not None and power_usage is not None:
                self._state = round(electricity_price * (power_usage / 1000), 2)
                self.async_write_ha_state()
        except ValueError as e:
            _LOGGER.error(f"Error converting state to float for {entity_id}: {e}")

class CumulativeCostSensor(SensorEntity, RestoreEntity):
    """Sensor that calculates cumulative energy cost based on the real-time cost."""

    def __init__(self, hass, real_time_cost_sensor):
        """Initialize the sensor."""
        super().__init__()
        self.hass = hass
        self._real_time_cost_sensor = real_time_cost_sensor
        self._state = Decimal('0.00')
        self._last_update = now()

        base_name = real_time_cost_sensor.name.replace("Real Time Energy Cost", "").strip()
        self._name = f"{base_name} Cumulative Energy Cost"

    async def async_added_to_hass(self):
        """Restore state and set up updates when added to Home Assistant."""
        await super().async_added_to_hass()
        # Restore state if available
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ('unknown', 'unavailable'):
            try:
                self._state = Decimal(last_state.state)
            except InvalidOperation:
                _LOGGER.error("Invalid state value for restoration: %s", last_state.state)

        self.async_on_remove(async_track_state_change_event(self.hass, [self._real_time_cost_sensor.entity_id], self._handle_real_time_cost_update))

    @callback
    def _handle_real_time_cost_update(self, event):
        """Update cumulative cost based on the real-time cost sensor updates."""
        new_state = event.data.get('new_state')
        if new_state is None or new_state.state in ('unknown', 'unavailable'):
            _LOGGER.debug("Skipping update due to unavailable state")
            return

        try:
            current_cost = Decimal(new_state.state)
            time_difference = now() - self._last_update
            hours_passed = Decimal(time_difference.total_seconds()) / Decimal(3600)  # Convert time difference to hours as Decimal
            self._state += (current_cost * hours_passed).quantize(Decimal('0.01'))
            self._last_update = now()
            self.async_write_ha_state()
            _LOGGER.debug(f"Updated state to: {self._state} using cost: {current_cost} over {hours_passed} hours")
        except (InvalidOperation, TypeError) as e:
            _LOGGER.error(f"Error updating cumulative cost: {e}")

    @property
    def unique_id(self):
        """Return a unique identifier for this sensor."""
        return f"{self._real_time_cost_sensor.unique_id}_cumulative"

    @property
    def device_info(self):
        """Return device information to link this sensor with the integration."""
        return self._real_time_cost_sensor.device_info

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the current cumulative cost."""
        return float(self._state) if self._state.is_finite() else None

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return 'EUR'

    @property
    def should_poll(self):
        """No need to poll. Will be updated by RealTimeCostSensor."""
        return False

class UtilityMeterSensor(SensorEntity, RestoreEntity):
    """Sensor that calculates cumulative energy costs over set intervals and resets accordingly."""

    def __init__(self, hass, real_time_cost_sensor, interval):
        """Initialize the sensor."""
        super().__init__()
        self.hass = hass
        self._real_time_cost_sensor = real_time_cost_sensor
        self._interval = interval
        self._state = Decimal('0.00')
        self._last_update = now()
        base_name = real_time_cost_sensor.name.replace(" Real Time Energy Cost", "").strip()
        self._name = f"{base_name} {interval.title()} Energy Cost"

    async def async_added_to_hass(self):
        """Restore state and set up updates when added to Home Assistant."""
        await super().async_added_to_hass()
        # Restore state if available
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

    def schedule_next_reset(self):
        """Schedule the next reset based on the interval."""
        next_reset_time = self.calculate_next_reset_time()
        async_track_time_interval(self.hass, self._reset_meter, next_reset_time)
        _LOGGER.debug(f"Scheduled next reset for {self._name} at {next_reset_time}")

    def calculate_next_reset_time(self):
        """Determine the next time to reset the meter based on the interval."""
        current_time = now()
        if self._interval == "daily":
            next_reset = current_time.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        elif self._interval == "monthly":
            next_month = (current_time.replace(day=1) + timedelta(days=32)).replace(day=1)
            next_reset = next_month.replace(hour=0, minute=0, second=0, microsecond=0)
        elif self._interval == "yearly":
            next_reset = current_time.replace(year=current_time.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return next_reset - current_time

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
            time_difference = now() - self._last_update
            hours_passed = Decimal(time_difference.total_seconds()) / Decimal(3600)  # Convert time difference to hours as Decimal
            self._state += (current_cost * hours_passed).quantize(Decimal('0.01'))
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
        """Return the unit of measurement."""
        return 'EUR'

    @property
    def should_poll(self):
        """No need to poll. Will be updated by RealTimeCostSensor."""
        return False
