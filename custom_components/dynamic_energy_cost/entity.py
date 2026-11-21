"""Class representing a Dynamic Energy Costs entity."""

from datetime import datetime, timedelta
from decimal import Decimal
import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import CALLBACK_TYPE, HassJob, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_point_in_time
from homeassistant.util import dt as dt_util
from homeassistant.util.dt import now

from .const import (
    ATTR_PRICE_SOURCE,
    ATTR_SOURCE,
    QUARTERLY,
    HOURLY,
    DAILY,
    MANUAL,
    MONTHLY,
    WEEKLY,
    YEARLY,
)

_LOGGER = logging.getLogger(__name__)

# Interval cost sensors publish their state at most this often. Cost is still
# accumulated on every source update; only the state writes are rate-limited,
# so a fast source sensor no longer adds a recorder row per update for every
# interval sensor (#242). 30 s is Home Assistant's default polling interval.
PUBLISH_INTERVAL = timedelta(seconds=30)


class BaseUtilitySensor(SensorEntity):
    """Base sensor for handling energy cost data."""

    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, interval: str) -> None:
        """Initialize the sensor."""
        super().__init__()
        self.hass = hass
        self._state = Decimal("0.00")
        self._unit_of_measurement = None
        self._interval = interval
        self.event_unsub: CALLBACK_TYPE | None = None
        self._last_update = now()
        self._last_reset = now()
        self._name = None
        self._last_publish: datetime | None = None
        self._publish_unsub: CALLBACK_TYPE | None = None
        # Set by subclasses: the consumption and price sensors this cost is
        # calculated from.
        self._source_entity_id: str | None = None
        self._price_entity_id: str | None = None

    def calculate_next_reset_time(self):
        """Determine the exact datetime for the next reset based on the interval."""
        current_time = now()

        if self._interval == QUARTERLY:
            current_time = current_time.replace(second=0, microsecond=0)

            next_quarter = ((current_time.minute // 15) + 1) * 15
            if next_quarter >= 60:
                return current_time.replace(minute=0) + timedelta(hours=1)
            return current_time.replace(minute=next_quarter)

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
    def _async_publish_state(self, *, force: bool = False) -> None:
        """Write the state, at most once per PUBLISH_INTERVAL unless forced.

        An update that arrives inside the interval is published at its end,
        so the latest value always reaches Home Assistant within
        PUBLISH_INTERVAL.
        """
        if not force and self._last_publish is not None:
            if self._publish_unsub is not None:
                return  # The pending write will publish the latest value.
            elapsed = now() - self._last_publish
            if timedelta(0) <= elapsed < PUBLISH_INTERVAL:
                self._publish_unsub = async_call_later(
                    self.hass,
                    PUBLISH_INTERVAL - elapsed,
                    HassJob(
                        self._async_publish_pending,
                        "dynamic_energy_cost publish",
                        cancel_on_shutdown=True,
                    ),
                )
                return

        self._cancel_pending_publish()
        self._last_publish = now()
        self.async_write_ha_state()

    @callback
    def _async_publish_pending(self, _now: datetime) -> None:
        """Publish the state held back by the rate limit."""
        self._publish_unsub = None
        self._async_publish_state(force=True)

    @callback
    def _cancel_pending_publish(self) -> None:
        """Cancel a pending rate-limited write."""
        if self._publish_unsub is not None:
            self._publish_unsub()
            self._publish_unsub = None

    @callback
    def async_reset(self, *args):
        """Reset the energy cost and cumulative energy kWh."""
        # Publish the closing value of the ended period first. Publishing is
        # rate-limited, so the latest cost may not have been written yet and
        # would otherwise be lost from both the old and the new period.
        self._async_publish_state(force=True)

        self._state = Decimal(0) if type(self._state) is Decimal else 0

        if hasattr(self, "_cumulative_energy"):
            self._cumulative_energy = 0  # pylint: disable=attribute-defined-outside-init
        if hasattr(self, "_cumulative_cost"):
            self._cumulative_cost = 0  # pylint: disable=attribute-defined-outside-init

        if hasattr(self, "_last_energy_reading"):
            self._last_energy_reading = None  # pylint: disable=attribute-defined-outside-init
        if hasattr(self, "_last_cost_rate"):
            self._last_cost_rate = None  # pylint: disable=attribute-defined-outside-init
        self._last_update = now()
        self._last_reset = now()
        self._async_publish_state(force=True)
        _LOGGER.debug("Meter reset for %s", self._name)

    @callback
    def async_calibrate(self, value):
        """Calibrate the state with a given value."""
        _LOGGER.debug("Calibrate %s = %s type(%s)", self._name, value, type(value))
        self._cumulative_cost = float(str(value))
        # Keep the state type: PowerCostSensor adds Decimals to it, and
        # float + Decimal raises TypeError.
        self._state = (
            Decimal(str(value))
            if isinstance(self._state, Decimal)
            else self._cumulative_cost
        )
        self._last_update = now()
        self._async_publish_state(force=True)

    async def async_will_remove_from_hass(self):
        """Remove the reset event and any pending write from the schedule."""
        if self.event_unsub:
            event_unsub = self.event_unsub
            self.event_unsub = None
            event_unsub()
        self._cancel_pending_publish()

        await super().async_will_remove_from_hass()

    @property
    def state(self):
        """Return the current cumulative cost."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Name the sensors this cost is calculated from (#247).

        Lets templates and cards match cost sensors to their source
        devices without a hand-kept mapping.
        """
        return {
            ATTR_SOURCE: self._source_entity_id,
            ATTR_PRICE_SOURCE: self._price_entity_id,
        }

    @property
    def device_class(self):
        """Return the class of this device, from SensorDeviceClass."""
        return SensorDeviceClass.MONETARY

    @property
    def suggested_display_precision(self):
        """Return how many decimals the frontend should show.

        Cost is accumulated with more decimals than this so that small loads
        are not lost to rounding; the extra precision is internal only.
        """
        return 4

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

    @property
    def last_reset(self):
        """Return the timestamp of the last reset for resetting total sensors."""
        if self._interval == MANUAL:
            return None

        if isinstance(self._last_reset, str):
            return dt_util.parse_datetime(self._last_reset)

        return self._last_reset
