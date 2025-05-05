"""Class representing a Dynamic Energy Costs entity."""

from datetime import timedelta
from decimal import Decimal
import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util.dt import now

from .const import HOURLY, DAILY, MANUAL, MONTHLY, WEEKLY, YEARLY

_LOGGER = logging.getLogger(__name__)


class BaseUtilitySensor(SensorEntity):
    """Base sensor for handling energy cost data."""

    def __init__(self, hass: HomeAssistant, interval: str) -> None:
        """Initialize the sensor."""
        super().__init__()
        self.hass = hass
        self._state = Decimal("0.00")
        self._unit_of_measurement = None
        self._interval = interval
        self.event_unsub: CALLBACK_TYPE | None = None
        self._last_update = now()
        self._name = None

    def calculate_next_reset_time(self):
        """Determine the exact datetime for the next reset based on the interval."""
        current_time = now()

        if self._interval == HOURLY:
            # Only activate for testing purpose:
            # return current_time + timedelta(seconds=30)

            return current_time.replace(minute=0, second=0, microsecond=0) + timedelta(
                hours=1
            )

        if self._interval == DAILY:
            # Only activate for testing purpose:
            # return current_time + timedelta(seconds=30)

            return current_time.replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)

        if self._interval == WEEKLY:
            # Calculate the date of the next Monday
            days_until_monday = (7 - current_time.weekday()) % 7
            next_monday = (current_time + timedelta(days=days_until_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            # If today is Monday, set to next Monday
            if days_until_monday == 0:
                next_monday += timedelta(days=7)
            return next_monday

        if self._interval == MONTHLY:
            next_month = (current_time.replace(day=1) + timedelta(days=32)).replace(
                day=1
            )
            return next_month.replace(hour=0, minute=0, second=0, microsecond=0)

        if self._interval == YEARLY:
            return current_time.replace(
                year=current_time.year + 1,
                month=1,
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )

        return None

    def schedule_next_reset(self):
        """Schedule the next reset based on the interval, cancelling any previous schedules."""
        # The Manual sensor has no reset time
        if self._interval == MANUAL:
            return

        next_reset = self.calculate_next_reset_time()

        # Log the scheduling of the next reset
        _LOGGER.debug("Scheduling next reset for %s at %s", self.name, next_reset)

        # Schedule the next reset
        self.event_unsub = async_track_point_in_time(
            self.hass, self._async_reset_meter, next_reset
        )
        _LOGGER.debug("Next reset scheduled successfully")

    @callback
    def _async_reset_meter(self, *args) -> None:
        """Reset the meter at the specified interval or from the reset event."""
        self.async_reset()
        self.schedule_next_reset()

    @callback
    def async_reset(self, *args):
        """Reset the energy cost and cumulative energy kWh."""
        self._state = Decimal(0) if type(self._state) is Decimal else 0

        if hasattr(self, "_cumulative_energy"):
            self._cumulative_energy = 0  # pylint: disable=attribute-defined-outside-init
        if hasattr(self, "_cumulative_cost"):
            self._cumulative_cost = 0  # pylint: disable=attribute-defined-outside-init

        if hasattr(self, "_last_energy_reading"):
            self._last_energy_reading = None  # pylint: disable=attribute-defined-outside-init
        self._last_update = now()
        self.async_write_ha_state()
        _LOGGER.debug("Meter reset for %s", self._name)

    @callback
    def async_calibrate(self, value):
        """Calibrate the state with a given value."""
        _LOGGER.debug("Calibrate %s = %s type(%s)", self._name, value, type(value))
        self._cumulative_cost = float(str(value))
        self._state = self._cumulative_cost
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self):
        """Remove the reset event from the schedule."""
        if self.event_unsub:
            await self.hass.async_add_executor_job(self.event_unsub())

    @property
    def state(self):
        """Return the current cumulative cost."""
        return self._state

    @property
    def device_class(self):
        """Return the class of this device, from SensorDeviceClass."""
        return SensorDeviceClass.MONETARY

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return "mdi:cash"

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement
