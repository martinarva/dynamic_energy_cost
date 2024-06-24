import logging
from .energy_based_sensors import (BaseEnergyCostSensor, DailyEnergyCostSensor, WeeklyEnergyCostSensor, MonthlyEnergyCostSensor,
                                   YearlyEnergyCostSensor)
from .power_based_sensors import RealTimeCostSensor, UtilityMeterSensor
from homeassistant.helpers import entity_platform
from .const import DOMAIN, ELECTRICITY_PRICE_SENSOR, ENERGY_SENSOR, POWER_SENSOR, SERVICE_RESET_COST

_LOGGER = logging.getLogger(__name__)

async def register_entity_services(hass):
    """Register custom services for energy cost sensors."""
    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_RESET_COST,
        {},  # No parameters for the service
        "async_reset"
    )

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Setup sensor platform based on user configuration."""
    data = config_entry.data
    electricity_price_sensor = data[ELECTRICITY_PRICE_SENSOR]
    sensors = []

    if POWER_SENSOR in data and data[POWER_SENSOR]:
        # Setup power-based sensors
        power_sensor = data[POWER_SENSOR]
        real_time_cost_sensor = RealTimeCostSensor(
            hass, config_entry, electricity_price_sensor, power_sensor, 'Real Time Energy Cost'
        )
        sensors.append(real_time_cost_sensor)
        intervals = ['daily', 'monthly', 'yearly']
        utility_sensors = [UtilityMeterSensor(hass, real_time_cost_sensor, interval) for interval in intervals]
        sensors.extend(utility_sensors)

    if ENERGY_SENSOR in data and data[ENERGY_SENSOR]:
        # Setup energy-based sensors
        energy_sensor = data[ENERGY_SENSOR]
        sensors.append(DailyEnergyCostSensor(hass, energy_sensor, electricity_price_sensor))
        sensors.append(WeeklyEnergyCostSensor(hass, energy_sensor, electricity_price_sensor))
        sensors.append(MonthlyEnergyCostSensor(hass, energy_sensor, electricity_price_sensor))
        sensors.append(YearlyEnergyCostSensor(hass, energy_sensor, electricity_price_sensor))

    if sensors:
        async_add_entities(sensors, True)
    else:
        _LOGGER.error("No sensors configured. Check your configuration.")
    
    await register_entity_services(hass)

