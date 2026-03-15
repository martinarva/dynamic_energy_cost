"""Home Assistant support for Dynamic Energy Costs."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DAILY, HOURLY, MANUAL, MONTHLY, QUARTERLY, WEEKLY, YEARLY

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]
INTERVALS = (QUARTERLY, HOURLY, DAILY, WEEKLY, MONTHLY, YEARLY, MANUAL)

async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Dynamic Energy Cost from a config entry."""
    _LOGGER.info(
        "Starting setup of Dynamic Energy Cost component, entry.data: %s", entry.data
    )

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    try:
        _LOGGER.debug(
            "Attempting to forward Dynamic Energy Cost entry setup to the sensor platform"
        )
        setup_result = await hass.config_entries.async_forward_entry_setups(
            entry, PLATFORMS
        )
        _LOGGER.debug("Forwarding to sensor setup was successful: %s", setup_result)
    except Exception as e:
        _LOGGER.error("Failed to set up sensor platform, error: %s", str(e))
        return False

    _LOGGER.info("Dynamic Energy Cost setup completed successfully")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a Dynamic Energy Cost config entry."""

    _LOGGER.debug("Attempting to unload the Dynamic Energy Cost component")
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate DEC entities to stable unique IDs."""
    if entry.version >= 2:
        return True

    entity_registry = er.async_get(hass)

    power_sensor = entry.data.get("power_sensor")
    energy_sensor = entry.data.get("energy_sensor")
    price_sensor = entry.data.get("electricity_price_sensor")

    for entity_entry in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        new_unique_id = None

        if power_sensor:
            old_realtime_uid = f"{entry.entry_id}_{power_sensor}_real_time_cost"
            if entity_entry.unique_id == old_realtime_uid:
                new_unique_id = f"{entry.entry_id}_real_time_cost"

            for interval in INTERVALS:
                old_power_uid = f"{old_realtime_uid}_{interval}"
                if entity_entry.unique_id == old_power_uid:
                    new_unique_id = f"{entry.entry_id}_{interval}_power_cost"
                    break

        if energy_sensor and price_sensor:
            for interval in INTERVALS:
                old_energy_uid = f"{price_sensor}_{energy_sensor}_{interval}_cost"
                if entity_entry.unique_id == old_energy_uid:
                    new_unique_id = f"{entry.entry_id}_{interval}_energy_cost"
                    break

        if new_unique_id and entity_entry.unique_id != new_unique_id:
            _LOGGER.info(
                "Migrating entity %s unique_id from %s to %s",
                entity_entry.entity_id,
                entity_entry.unique_id,
                new_unique_id,
            )
            entity_registry.async_update_entity(
                entity_entry.entity_id,
                new_unique_id=new_unique_id,
            )

    hass.config_entries.async_update_entry(entry, version=2)
    return True