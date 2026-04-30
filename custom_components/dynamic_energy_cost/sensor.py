"""Class representing a Dynamic Energy Costs sensors."""

from decimal import Decimal, InvalidOperation
import logging
import math
import voluptuous as vol

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import (
    device_registry as dr,
    entity_platform,
    entity_registry as er,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util.dt import now

try:
    from homeassistant.helpers.device import async_entity_id_to_device
except ImportError:
    async_entity_id_to_device = None

from .const import (
    QUARTERLY,
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
from . import (
    get_entry_config,
    get_interval_cost_unique_id,
    get_realtime_unique_id,
    get_selected_sensors,
)
from .entity import BaseUtilitySensor

INTERVALS = [QUARTERLY, HOURLY, DAILY, WEEKLY, MONTHLY, YEARLY, MANUAL]

_LOGGER = logging.getLogger(__name__)
REALTIME_COST_PRECISION = Decimal("0.0001")


def _resolve_source_device(hass: HomeAssistant, source_entity_id: str):
    """Return the DeviceEntry for a source entity, or None."""
    if not source_entity_id:
        return None
    if async_entity_id_to_device is not None:
        return async_entity_id_to_device(hass, source_entity_id)
    # HA < 2025.8 fallback
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get(source_entity_id)
    if entry and entry.device_id:
        dev_reg = dr.async_get(hass)
        return dev_reg.async_get(entry.device_id)
    return None


def _fallback_device_info(config_entry, device_name, device_entry):
    """Return fallback device info when source sensor has no device.

    Each sensor class must call this with its *own* device_entry to
    avoid coupling to another entity's mutable runtime state.
    """
    if device_entry is not None:
        return None
    return {
        "identifiers": {(DOMAIN, config_entry.entry_id)},
        "name": device_name,
        "manufacturer": "Custom Integration",
    }


def interval_display_name(interval: str) -> str:
    """Return a user-facing label for an interval."""
    if interval == QUARTERLY:
        return "15-Minute"

    return interval.replace("_", " ").title()


def _is_finite_number(value) -> bool:
    """Return True when value coerces to a finite float.

    Local replacement for ``homeassistant.helpers.template.is_number``,
    which was relocated into a Jinja2 extension in HA 2026.5 (PR #167280)
    and is no longer importable.  Mirrors the original behaviour
    (rejects ``inf``/``nan`` and unparseable values).
    """
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def validate_is_number(value):
    """Validate value is a number."""
    if _is_finite_number(value):
        return value
    raise vol.Invalid("Value is not a number")


_ENERGY_UNIT_TO_KWH: dict[str, float] = {
    "Wh": 0.001,
    "kWh": 1.0,
    "MWh": 1000.0,
}


def _energy_unit_conversion_factor(state) -> float:
    """Return the factor to convert the energy sensor's unit to kWh.

    Defaults to 1.0 (kWh) when the unit is missing or unrecognised.
    """
    if state is None:
        return 1.0
    unit = state.attributes.get("unit_of_measurement", "kWh")
    return _ENERGY_UNIT_TO_KWH.get(unit, 1.0)


_PRICE_UNIT_TO_PER_KWH: dict[str, float] = {
    "wh": 1000.0,
    "kwh": 1.0,
    "mwh": 0.001,
}


def _price_unit_conversion_factor(state) -> float:
    """Return the factor to convert a price sensor's value to currency/kWh.

    Parses unit_of_measurement (e.g. ``EUR/MWh``) and extracts the energy
    denominator after the last ``/``.  Supports Wh, kWh and MWh in any
    case.  Defaults to 1.0 when the unit is missing, has no slash, or
    the energy part is unrecognised.
    """
    if state is None:
        return 1.0
    unit = state.attributes.get("unit_of_measurement", "")
    if "/" not in unit:
        return 1.0
    energy_part = unit.rsplit("/", 1)[-1].strip().lower()
    return _PRICE_UNIT_TO_PER_KWH.get(energy_part, 1.0)


def _state_to_float(state) -> float | None:
    """Convert a Home Assistant state object to float if usable."""
    if state is None or state.state in (None, "unknown", "unavailable"):
        return None

    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


def _last_reset_changed(old_state, new_state) -> bool:
    """Detect a source-sensor reset via the ``last_reset`` attribute.

    Canonical signal for ``state_class=total`` resetting sensors (e.g. HA's
    ``utility_meter`` helper). Returns True when ``new_state.last_reset`` is
    set and differs from ``old_state.last_reset``.
    """
    if old_state is None or new_state is None:
        return False
    old_lr = old_state.attributes.get("last_reset")
    new_lr = new_state.attributes.get("last_reset")
    return new_lr is not None and old_lr != new_lr


def _source_decremented_total_increasing(
    current_state, last_known: float | None
) -> bool:
    """Detect a source-sensor reset via decrement on a ``total_increasing`` sensor.

    Per HA convention any decrease on a ``total_increasing`` sensor is a reset.
    Covers ESPHome ``total_daily_energy`` and most polling integrations that
    skip the explicit ``0`` reading (e.g. Deye Modbus).
    """
    if current_state is None or last_known is None:
        return False
    if current_state.attributes.get("state_class") != "total_increasing":
        return False
    try:
        return float(current_state.state) < last_known
    except (TypeError, ValueError):
        return False


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
    data = get_entry_config(config_entry)
    electricity_price_sensor = data[ELECTRICITY_PRICE_SENSOR]
    selected = get_selected_sensors(config_entry)
    sensors = []

    if data.get(POWER_SENSOR):
        # Setup power-based sensors
        power_sensor = data[POWER_SENSOR]
        real_time_cost_sensor = RealTimeCostSensor(
            hass,
            config_entry,
            electricity_price_sensor,
            power_sensor,
        )
        # Always add RealTimeCostSensor — normalization ensures it's in
        # selected whenever any power interval is selected.
        sensors.append(real_time_cost_sensor)

        selected_intervals = [i for i in INTERVALS if i in selected]
        utility_sensors = [
            PowerCostSensor(hass, real_time_cost_sensor, interval)
            for interval in selected_intervals
        ]
        sensors.extend(utility_sensors)

    if data.get(ENERGY_SENSOR):
        # Setup energy-based sensors
        energy_sensor = data[ENERGY_SENSOR]
        selected_intervals = [i for i in INTERVALS if i in selected]
        utility_sensors = [
            EnergyCostSensor(
                hass,
                config_entry,
                energy_sensor,
                electricity_price_sensor,
                interval,
            )
            for interval in selected_intervals
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

        # Link to the source power sensor's device when available
        self.device_entry = _resolve_source_device(hass, power_sensor_id)

    @property
    def unique_id(self):
        """Return a unique identifier for this sensor."""
        return get_realtime_unique_id(self._config_entry.entry_id)

    @property
    def device_info(self):
        """Fallback device info when source sensor has no device."""
        return _fallback_device_info(
            self._config_entry, self._device_name, self.device_entry
        )

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

        if new_state is None:
            _LOGGER.warning("State of %s is missing, skipping update", entity_id)
            return

        if new_state.state in ["unknown", "unavailable"]:
            _LOGGER.warning(
                "State of %s is '%s', skipping update", entity_id, new_state.state
            )
            return

        price_state = self.hass.states.get(self._electricity_price_sensor_id)
        electricity_price = _state_to_float(price_state)
        power_usage = _state_to_float(self.hass.states.get(self._power_sensor_id))

        if electricity_price is None or power_usage is None:
            _LOGGER.warning(
                "One or more sensor values are unavailable, skipping update"
            )
            return

        price_to_kwh = _price_unit_conversion_factor(price_state)
        try:
            calculated_cost = (
                Decimal(str(electricity_price))
                * Decimal(str(price_to_kwh))
                * (Decimal(str(power_usage)) / Decimal("1000"))
            ).quantize(REALTIME_COST_PRECISION)
            if calculated_cost != self._state:
                self._state = calculated_cost
                self.async_write_ha_state()
                _LOGGER.debug(
                    "Updated Real Time Energy Cost: %s EUR/h", calculated_cost
                )
        except ValueError as e:
            _LOGGER.error("Error converting sensor data to float: %s", e)

    async def async_added_to_hass(self):
        """Register callbacks when added to hass."""
        self._unit_of_measurement = f"{get_currency(self.hass)}/h"
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._electricity_price_sensor_id, self._power_sensor_id],
                self.handle_state_change,
            )
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
        config_entry: ConfigEntry,
        energy_sensor_id: SensorEntity,
        price_sensor_id: SensorEntity,
        interval: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(hass, interval)
        self._config_entry = config_entry
        self._energy_sensor_id = energy_sensor_id
        self._price_sensor_id = price_sensor_id
        self._last_energy_reading = None
        self._cumulative_energy = 0.0
        self._cumulative_cost = None  # updated on price change events and used for more precise cost calculations
        self._energy_to_kwh = (
            1.0  # resolved in async_added_to_hass from unit_of_measurement
        )

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
        self._name = (
            f"{self._base_name} {interval_display_name(self._interval)} Energy Cost"
        )
        self._device_name = friendly_name + " Dynamic Energy Cost"

        # Link to the source energy sensor's device when available
        self.device_entry = _resolve_source_device(hass, energy_sensor_id)

    @property
    def unique_id(self):
        """Return a unique identifier for this sensor."""
        return get_interval_cost_unique_id(self._config_entry.entry_id, self._interval)

    @property
    def device_info(self):
        """Fallback device info when source sensor has no device."""
        return _fallback_device_info(
            self._config_entry, self._device_name, self.device_entry
        )

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
            if last_state.attributes.get("last_reset") is not None:
                self._last_reset = last_state.attributes.get("last_reset")
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

        # Resolve unit conversion factor from the source energy sensor
        self._energy_to_kwh = _energy_unit_conversion_factor(
            self.hass.states.get(self._energy_sensor_id)
        )

        self.async_write_ha_state()
        # track energy sensor changes
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._energy_sensor_id, self._async_update_energy_event
            )
        )
        # track also the price sensor changes for more accuracy
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._price_sensor_id, self._async_update_price_event
            )
        )
        self.schedule_next_reset()

    # -----------------------------------------------------------------------------------------------
    # when there is a price change we recalculate the _cumulative_cost and sync the state to this clibrated value
    async def _async_update_price_event(self, event):
        """Handle price sensor state changes."""
        try:
            old_price_state = event.data.get("old_state")
            energy_state = self.hass.states.get(self._energy_sensor_id)
            current_energy = _state_to_float(energy_state)
            price = _state_to_float(old_price_state)

            if current_energy is None or price is None:
                _LOGGER.debug("One or more sensors are unavailable. Skipping update.")
                return

            if self._cumulative_cost is None:
                self._cumulative_cost = float(self._state)

            if self._last_energy_reading is None:
                _LOGGER.debug(
                    "Initializing energy baseline from current reading during price update."
                )
                self._last_energy_reading = current_energy
            elif _source_decremented_total_increasing(
                energy_state, self._last_energy_reading
            ):
                _LOGGER.debug(
                    "Source sensor reset detected during price update. "
                    "Re-initialising baseline to %s.",
                    current_energy,
                )
                self._last_energy_reading = current_energy
            else:
                energy_difference = current_energy - self._last_energy_reading
                energy_difference_kwh = energy_difference * self._energy_to_kwh
                price_to_kwh = _price_unit_conversion_factor(old_price_state)
                cost_increment = energy_difference_kwh * price * price_to_kwh
                self._cumulative_cost += cost_increment
                self._state = self._cumulative_cost
                self._cumulative_energy += energy_difference_kwh
                _LOGGER.debug(
                    f"Change in Energy price: cumulative cost {self._cumulative_cost} EUR and cumulative energy usage to {self._cumulative_energy} kWh"
                )
                self._last_energy_reading = current_energy
            self.async_write_ha_state()

        except Exception as e:
            _LOGGER.error("Failed to update energy costs due to an error: %s", str(e))

    # -----------------------------------------------------------------------------------------------
    # when there is a new energy reading we update our state based on the last _cumulative_cost (which is set on each price event)
    async def _async_update_energy_event(self, event):
        """Handle energy sensor state changes."""
        """Update the energy costs using the latest sensor states, adding both incremental as decremental costs."""
        try:
            new_state = event.data.get("new_state")
            old_state = event.data.get("old_state")
            current_energy = _state_to_float(new_state)
            price_state = self.hass.states.get(self._price_sensor_id)
            price = _state_to_float(price_state)
            # Re-resolve unit in case the sensor was unavailable at startup
            if self._energy_to_kwh == 1.0:
                self._energy_to_kwh = _energy_unit_conversion_factor(new_state)

            if current_energy is None or price is None:
                _LOGGER.debug("One or more sensors are unavailable. Skipping update.")
                return

            if self._cumulative_cost is None:
                self._cumulative_cost = float(self._state)

            source_was_reset = (
                current_energy == 0
                or _last_reset_changed(old_state, new_state)
                or _source_decremented_total_increasing(
                    new_state, self._last_energy_reading
                )
            )
            if source_was_reset or self._last_energy_reading is None:
                _LOGGER.debug(
                    "Source sensor reset detected or baseline missing. "
                    "Re-initialising baseline to %s.",
                    current_energy,
                )
                self._last_energy_reading = current_energy
                return

            energy_difference = current_energy - self._last_energy_reading
            energy_difference_kwh = energy_difference * self._energy_to_kwh
            price_to_kwh = _price_unit_conversion_factor(price_state)
            cost_increment = energy_difference_kwh * price * price_to_kwh
            self._cumulative_cost += cost_increment
            self._cumulative_energy += energy_difference_kwh
            self._state = self._cumulative_cost
            self._last_energy_reading = current_energy
            _LOGGER.debug(
                f"Energy cost incremented by {cost_increment} on top of {self._cumulative_cost}, total cost now {self._state} EUR"
            )

            self.async_write_ha_state()

        except Exception as e:
            _LOGGER.error("Failed to update energy costs due to an error: %s", str(e))

    @callback
    def async_reset(self, *args):
        """Reset cost totals, preserving energy baseline from the current sensor state.

        Reading the current energy value before the base class clears
        _last_energy_reading ensures that cumulative sensors (which never reset)
        keep a correct baseline so the next delta is counted rather than swallowed.
        For daily-resetting sensors that are already at 0 when the cost resets, the
        baseline is set to 0 here; if they reset slightly after the cost reset the
        existing current_energy == 0 guard in _async_update_energy_event handles it.
        """
        # Snapshot the current reading before the base class wipes _last_energy_reading.
        current_energy: float | None = None
        if self.hass:
            current_state = self.hass.states.get(self._energy_sensor_id)
            current_energy = _state_to_float(current_state)

        super().async_reset(*args)

        # Restore the baseline so cumulative sensors produce a correct first delta.
        # If the sensor was unavailable, leave _last_energy_reading as None
        # (base class fallback: first event after reset will initialise the baseline).
        if current_energy is not None:
            self._last_energy_reading = current_energy


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
        self._last_cost_rate: Decimal | None = None
        # Power cost follows the same source device as realtime cost
        self.device_entry = real_time_cost_sensor.device_entry
        self._config_entry = real_time_cost_sensor._config_entry
        self._device_name = real_time_cost_sensor._device_name
        base_name = real_time_cost_sensor.name.replace(
            " Real Time Energy Cost", ""
        ).strip()
        self._name = f"{base_name} {interval_display_name(interval)} Energy Cost"

    async def async_added_to_hass(self):
        """Restore state and set up updates when added to Home Assistant."""
        await super().async_added_to_hass()
        # Restore state if available
        self._unit_of_measurement = get_currency(self.hass)
        last_state = await self.async_get_last_state()

        if last_state and last_state.state not in ("unknown", "unavailable"):
            try:
                self._state = Decimal(last_state.state)
                if last_state.attributes.get("last_reset") is not None:
                    self._last_reset = last_state.attributes.get("last_reset")
            except InvalidOperation:
                _LOGGER.error(
                    "Invalid state value for restoration: %s", last_state.state
                )

        current_rate_state = self.hass.states.get(self._real_time_cost_sensor.entity_id)
        if current_rate_state and current_rate_state.state not in (
            "unknown",
            "unavailable",
        ):
            try:
                self._last_cost_rate = Decimal(current_rate_state.state)
            except InvalidOperation:
                _LOGGER.error(
                    "Invalid realtime cost value for baseline: %s",
                    current_rate_state.state,
                )

        self._last_update = now()

        self.schedule_next_reset()
        _LOGGER.debug(
            "Registering state change event for: %s",
            self._real_time_cost_sensor.entity_id,
        )

        try:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    [self._real_time_cost_sensor.entity_id],
                    self._handle_real_time_cost_update,
                )
            )
        except Exception as e:
            _LOGGER.error("Failed to track state change: %s", str(e))

    @callback
    def _handle_real_time_cost_update(self, event: Event):
        """Update cumulative cost based on the real-time cost sensor updates."""
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in ("unknown", "unavailable"):
            _LOGGER.debug("Skipping update due to unavailable state")
            return

        try:
            current_cost = Decimal(new_state.state)
            previous_cost = self._last_cost_rate

            if old_state is not None and old_state.state not in (
                "unknown",
                "unavailable",
            ):
                previous_cost = Decimal(old_state.state)

            if self._last_update is None or previous_cost is None:
                self._last_cost_rate = current_cost
                self._last_update = now()
                return

            _LOGGER.debug(
                "Current cost retrieved from state: %s", current_cost
            )  # Log current cost

            time_difference = now() - self._last_update
            if time_difference.total_seconds() <= 0:
                self._last_update = now()
                return
            hours_passed = Decimal(time_difference.total_seconds()) / Decimal(
                3600
            )  # Convert time difference to hours as Decimal
            _LOGGER.debug(
                "Time difference calculated as: %s, which is %s hours",
                time_difference,
                hours_passed,
            )  # Log time difference in hours

            self._state += (previous_cost * hours_passed).quantize(Decimal("0.0001"))
            self._last_cost_rate = current_cost
            self._last_update = now()
            self.async_write_ha_state()
            _LOGGER.debug(
                "Updated state to: %s using previous cost: %s over %s hours",
                self._state,
                previous_cost,
                hours_passed,
            )
        except (InvalidOperation, TypeError) as e:
            _LOGGER.error("Error updating cumulative cost: %s", str(e))

    @property
    def unique_id(self):
        """Return a unique identifier for this sensor."""
        return get_interval_cost_unique_id(
            self._real_time_cost_sensor._config_entry.entry_id,
            self._interval,
        )

    @property
    def device_info(self):
        """Fallback device info when source sensor has no device."""
        return _fallback_device_info(
            self._config_entry, self._device_name, self.device_entry
        )

    @property
    def state_class(self):
        """Return the state class of this device, from SensorStateClass."""
        return SensorStateClass.TOTAL

    @property
    def should_poll(self):
        """No need to poll. Will be updated by RealTimeCostSensor."""
        return False
