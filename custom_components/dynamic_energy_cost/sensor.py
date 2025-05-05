"""Class representing a Dynamic Energy Costs sensors."""

from decimal import Decimal, InvalidOperation
import logging
import voluptuous as vol

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.template import is_number
from homeassistant.util.dt import now

from .const import (
    HOURLY,
    DAILY,
    DOMAIN,
    ELECTRICITY_PRICE_SENSOR,
    ENERGY_SENSOR,
    MANUAL,
    MONTHLY,
    POWER_SENSOR,
    SERVICE_RESET_COST,
    SERVICE_CALIBRATE,
    WEEKLY,
    YEARLY,
)
from .entity import BaseUtilitySensor

INTERVALS = [HOURLY, DAILY, WEEKLY, MONTHLY, YEARLY, MANUAL]

_LOGGER = logging.getLogger(__name__)


def validate_is_number(value):
    """Validate value is a number."""
    if is_number(value):
        return value
    raise vol.Invalid("Value is not a number")


async def register_entity_services():
    """Register custom services for energy cost sensors."""
    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_RESET_COST,
        {},  # No parameters for the service
        "async_reset",
    )

    platform.async_register_entity_service(
        SERVICE_CALIBRATE,
        {vol.Required("value"): validate_is_number},
        "async_calibrate",
    )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Sensor platform setup based on user configuration."""
    data = config_entry.data
    electricity_price_sensor = data[ELECTRICITY_PRICE_SENSOR]
    sensors = []

    if data[POWER_SENSOR]:
        # Setup power-based sensors
        power_sensor = data[POWER_SENSOR]
        real_time_cost_sensor = RealTimeCostSensor(
            hass,
            config_entry,
            electricity_price_sensor,
            power_sensor,
        )
        sensors.append(real_time_cost_sensor)

        utility_sensors = [
            PowerCostSensor(hass, real_time_cost_sensor, interval)
            for interval in INTERVALS
        ]
        sensors.extend(utility_sensors)

    if data[ENERGY_SENSOR]:
        # Setup energy-based sensors
        energy_sensor = data[ENERGY_SENSOR]
        utility_sensors = [
            EnergyCostSensor(hass, energy_sensor, electricity_price_sensor, interval)
            for interval in INTERVALS
        ]
        sensors.extend(utility_sensors)

    if sensors:
        async_add_entities(sensors, False)
    else:
        _LOGGER.error("No sensors configured. Check your configuration")

    await register_entity_services()


def get_currency(hass: HomeAssistant):
    """Get the Home Assistant default currency."""
    currency = hass.config.currency
    if currency:
        _LOGGER.debug("Using Home Assistant default currency '%s'", currency)
        return currency

    _LOGGER.warning("No default currency set in Home Assistant")
    return None  # No default currency


class RealTimeCostSensor(SensorEntity):
    """Sensor that calculates energy cost in real-time based on power usage and electricity price."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        electricity_price_sensor_id: SensorEntity,
        power_sensor_id: SensorEntity,
    ) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self._config_entry = config_entry
        self._electricity_price_sensor_id = electricity_price_sensor_id
        self._power_sensor_id = power_sensor_id
        self._state = Decimal(0)
        self._unit_of_measurement = None

        _LOGGER.debug(
            "Initialized Real Time Cost Sensor with price sensor: %s and power sensor: %s",
            electricity_price_sensor_id,
            power_sensor_id,
        )

        # Extract a friendly name from the power sensor's entity ID
        base_part = power_sensor_id.split(".")[
            -1
        ]  # Assuming entity_id format like 'sensor.heat_pump_power'
        friendly_name_parts = base_part.replace("_", " ").split()  # Split into words
        friendly_name_parts = [
            word for word in friendly_name_parts if word.lower() != "power"
        ]  # Remove the word "Power"
        friendly_name = " ".join(friendly_name_parts).title()  # Rejoin and title-case
        self._base_name = friendly_name + " Real Time Energy Cost"

        # Prepare a device name using the friendly base part
        self._device_name = friendly_name + " Dynamic Energy Cost"

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
            "manufacturer": "Custom Integration",
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
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @callback
    def async_reset(self):
        """Handle reset, dummy to accept reset on device level."""

    @callback
    def handle_state_change(self, event: Event):
        """Handle changes to the electricity price or power usage."""
        entity_id = event.data["entity_id"]
        new_state = event.data.get("new_state")

        if new_state is None or new_state.state in ["unknown", "unavailable"]:
            _LOGGER.warning(
                "State of %s is '%s', skipping update", entity_id, new_state.state
            )
            return

        electricity_price = self.hass.states.get(
            self._electricity_price_sensor_id
        ).state
        power_usage = self.hass.states.get(self._power_sensor_id).state

        if (
            not electricity_price
            or not power_usage
            or electricity_price in ["unknown", "unavailable"]
            or power_usage in ["unknown", "unavailable"]
        ):
            _LOGGER.warning(
                "One or more sensor values are unavailable, skipping update"
            )
            return

        try:
            electricity_price = float(electricity_price)
            power_usage = float(power_usage)
            calculated_cost = round(electricity_price * (power_usage / 1000), 2)
            if calculated_cost != self._state:
                self._state = Decimal(calculated_cost)
                self.async_write_ha_state()
                _LOGGER.debug(
                    "Updated Real Time Energy Cost: %s EUR/h", calculated_cost
                )
        except ValueError as e:
            _LOGGER.error("Error converting sensor data to float: %s", e)

    async def async_added_to_hass(self):
        """Register callbacks when added to hass."""
        self._unit_of_measurement = f"{get_currency(self.hass)}/h"
        async_track_state_change_event(
            self.hass,
            [self._electricity_price_sensor_id, self._power_sensor_id],
            self.handle_state_change,
        )
        _LOGGER.info(
            "Callbacks registered for %s and %s",
            self._electricity_price_sensor_id,
            self._power_sensor_id,
        )


# -----------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------
class EnergyCostSensor(RestoreEntity, BaseUtilitySensor):
    """Base sensor for handling energy cost data."""

    def __init__(
        self,
        hass: HomeAssistant,
        energy_sensor_id: SensorEntity,
        price_sensor_id: SensorEntity,
        interval: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(hass, interval)
        self._energy_sensor_id = energy_sensor_id
        self._price_sensor_id = price_sensor_id
        self._last_energy_reading = None
        self._cumulative_energy = 0.0
        self._cumulative_cost = None  # updated on price change events and used for more precise cost calculations

        _LOGGER.debug(
            "Sensor initialized with energy sensor ID %s and price sensor ID %s",
            energy_sensor_id,
            price_sensor_id,
        )

        # Generate friendly names based on the energy sensor's ID
        base_part = energy_sensor_id.split(".")[-1]
        friendly_name_parts = base_part.replace("_", " ").split()

        # Exclude words that are commonly not part of the main identifier
        friendly_name_parts = [
            word for word in friendly_name_parts if word.lower() != "energy"
        ]

        friendly_name = " ".join(friendly_name_parts).title()

        self._base_name = friendly_name
        self._name = f"{self._base_name} {self._interval.capitalize()} Energy Cost"
        self._device_name = friendly_name + " Dynamic Energy Cost"

    @property
    def unique_id(self):
        """Return a unique identifier for this sensor."""
        return f"{self._price_sensor_id}_{self._energy_sensor_id}_{self._interval}_cost"

    @property
    def device_info(self):
        """Return device information to link this sensor with the integration."""
        return {
            "identifiers": {(DOMAIN, self._energy_sensor_id)},
            "name": self._device_name,
            "manufacturer": "Custom Integration",
        }

    @property
    def state_class(self):
        """Return the state class of this device, from SensorStateClass."""
        return SensorStateClass.TOTAL

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the device."""
        attrs = super().extra_state_attributes or {}  # Ensure it's a dict
        attrs["cumulative_energy"] = self._cumulative_energy
        attrs["last_energy_reading"] = self._last_energy_reading
        attrs["cumulative_cost"] = self._cumulative_cost
        attrs["average_energy_cost"] = (
            self._state / self._cumulative_energy if self._cumulative_energy else 0.0
        )
        return attrs

    # -----------------------------------------------------------------------------------------------
    async def async_added_to_hass(self):
        """Load the last known state and subscribe to updates."""
        await super().async_added_to_hass()
        # Restore state if available
        self._unit_of_measurement = get_currency(self.hass)
        last_state = await self.async_get_last_state()

        if last_state and last_state.state not in ["unknown", "unavailable", None]:
            self._state = float(last_state.state)
            if last_state.attributes.get("last_energy_reading") is not None:
                self._last_energy_reading = float(
                    last_state.attributes.get("last_energy_reading")
                )
            if last_state.attributes.get("cumulative_energy") is not None:
                self._cumulative_energy = float(
                    last_state.attributes.get("cumulative_energy")
                )
            if last_state.attributes.get("cumulative_cost") is not None:
                self._cumulative_cost = float(
                    last_state.attributes.get("cumulative_cost")
                )
            else:
                # For backwards compatibility
                self._cumulative_cost = float(last_state.state)

        self.async_write_ha_state()
        # track energy sensor changes
        async_track_state_change_event(
            self.hass, self._energy_sensor_id, self._async_update_energy_event
        )
        # track also the price sensor changes for more accuracy
        async_track_state_change_event(
            self.hass, self._price_sensor_id, self._async_update_price_event
        )
        self.schedule_next_reset()

    # -----------------------------------------------------------------------------------------------
    # when there is a price change we recalculate the _cumulative_cost and sync the state to this clibrated value
    async def _async_update_price_event(self, event):
        """Handle price sensor state changes."""
        try:
            old_price_state = event.data.get("old_state")
            energy_state = self.hass.states.get(
                self._energy_sensor_id
            )  # current energy readings

            if (
                not energy_state
                or not old_price_state
                or energy_state.state in ["unknown", "unavailable"]
                or old_price_state.state in ["unknown", "unavailable"]
            ):
                _LOGGER.debug("One or more sensors are unavailable. Skipping update.")
                return

            current_energy = float(energy_state.state)
            price = float(old_price_state.state)

            if current_energy == 0:
                _LOGGER.debug(
                    "Current energy reading is a perfect zero; assume a reset occured of the energy sensor."
                )
            # allow for decreasing energy readings to support energy feed-in
            # and allow negative prices
            elif self._last_energy_reading is not None:
                energy_difference = current_energy - self._last_energy_reading
                cost_increment = energy_difference * price
                self._cumulative_cost += cost_increment
                self._state = self._cumulative_cost
                self._cumulative_energy += (
                    energy_difference  # Add to the running total of energy
                )
                _LOGGER.info(
                    f"Change in Energy price: cumulative cost {self._cumulative_cost} EUR and cumulative energy usage to {self._cumulative_energy} kWh"
                )

            else:
                _LOGGER.debug(
                    "No previous energy reading available; initializing with current reading."
                )

            self._last_energy_reading = current_energy  # Always update the last reading
            self.async_write_ha_state()

        except Exception as e:
            _LOGGER.error("Failed to update energy costs due to an error: %s", str(e))

    # -----------------------------------------------------------------------------------------------
    # when there is a new energy reading we update our state based on the last _cumulative_cost (which is set on each price event)
    async def _async_update_energy_event(self, event):
        """Handle energy sensor state changes."""
        """Update the energy costs using the latest sensor states, adding both incremental as decremental costs."""
        try:
            energy_state = event.data.get("new_state")
            price_state = self.hass.states.get(self._price_sensor_id)

            if (
                not energy_state
                or not price_state
                or energy_state.state in ["unknown", "unavailable"]
                or price_state.state in ["unknown", "unavailable"]
            ):
                _LOGGER.debug("One or more sensors are unavailable. Skipping update.")
                return

            current_energy = float(energy_state.state)
            price = float(price_state.state)

            if current_energy == 0 or self._last_energy_reading is None:
                _LOGGER.debug(
                    "No previous energy reading available or current reading is a perfect zero."
                )
                self._last_energy_reading = (
                    current_energy  # Initialize with current reading
                )
                return

            energy_difference = current_energy - self._last_energy_reading
            cost_increment = energy_difference * price
            self._state = (
                self._cumulative_cost + cost_increment
            )  # set state to the cumulative cost + increment since last energy reading
            _LOGGER.info(
                f"Energy cost incremented by {cost_increment} on top of {self._cumulative_cost}, total cost now {self._state} EUR"
            )

            self.async_write_ha_state()

        except Exception as e:
            _LOGGER.error("Failed to update energy costs due to an error: %s", str(e))


# -----------------------------------------------------------------------------------------------
class PowerCostSensor(BaseUtilitySensor, RestoreEntity):
    """Sensor that calculates cumulative energy costs over set intervals and resets accordingly."""

    def __init__(
        self,
        hass: HomeAssistant,
        real_time_cost_sensor: RealTimeCostSensor,
        interval: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(hass, interval)
        self._real_time_cost_sensor = real_time_cost_sensor
        base_name = real_time_cost_sensor.name.replace(
            " Real Time Energy Cost", ""
        ).strip()
        self._name = f"{base_name} {interval.title()} Energy Cost"

    async def async_added_to_hass(self):
        """Restore state and set up updates when added to Home Assistant."""
        await super().async_added_to_hass()
        # Restore state if available
        self._unit_of_measurement = get_currency(self.hass)
        last_state = await self.async_get_last_state()

        if last_state and last_state.state not in ("unknown", "unavailable"):
            try:
                self._state = Decimal(last_state.state)
            except InvalidOperation:
                _LOGGER.error(
                    "Invalid state value for restoration: %s", last_state.state
                )

        self.schedule_next_reset()
        _LOGGER.debug(
            "Registering state change event for: %s",
            self._real_time_cost_sensor.entity_id,
        )

        try:
            async_track_state_change_event(
                self.hass,
                [self._real_time_cost_sensor.entity_id],
                self._handle_real_time_cost_update,
            )
        except Exception as e:
            _LOGGER.error("Failed to track state change: %s", str(e))

    @callback
    def _handle_real_time_cost_update(self, event: Event):
        """Update cumulative cost based on the real-time cost sensor updates."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in ("unknown", "unavailable"):
            _LOGGER.debug("Skipping update due to unavailable state")
            return

        try:
            current_cost = Decimal(new_state.state)
            _LOGGER.debug(
                "Current cost retrieved from state: %s", current_cost
            )  # Log current cost

            time_difference = now() - self._last_update
            hours_passed = Decimal(time_difference.total_seconds()) / Decimal(
                3600
            )  # Convert time difference to hours as Decimal
            _LOGGER.debug(
                "Time difference calculated as: %s, which is %s hours",
                time_difference,
                hours_passed,
            )  # Log time difference in hours

            self._state += (current_cost * hours_passed).quantize(Decimal("0.0001"))
            self._last_update = now()
            self.async_write_ha_state()
            _LOGGER.debug(
                "Updated state to: %s using cost: %s over %s hours",
                self._state,
                current_cost,
                hours_passed,
            )
        except (InvalidOperation, TypeError) as e:
            _LOGGER.error("Error updating cumulative cost: %s", str(e))

    @property
    def unique_id(self):
        """Return a unique identifier for this sensor."""
        return f"{self._real_time_cost_sensor.unique_id}_{self._interval}"

    @property
    def device_info(self):
        """Link this sensor to the real-time cost sensor's device."""
        return self._real_time_cost_sensor.device_info

    @property
    def state_class(self):
        """Return the state class of this device, from SensorStateClass."""
        return SensorStateClass.MEASUREMENT

    @property
    def should_poll(self):
        """No need to poll. Will be updated by RealTimeCostSensor."""
        return False
