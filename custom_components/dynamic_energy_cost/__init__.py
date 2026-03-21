"""Home Assistant support for Dynamic Energy Costs."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DAILY, DOMAIN, HOURLY, MANUAL, MONTHLY, QUARTERLY, WEEKLY, YEARLY

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]
MIGRATION_VERSION = 2
INTERVALS = [QUARTERLY, HOURLY, DAILY, WEEKLY, MONTHLY, YEARLY, MANUAL]


def get_entry_config(entry: ConfigEntry) -> dict[str, Any]:
    """Return merged config entry data and options."""
    return {**entry.data, **entry.options}


def get_realtime_unique_id(entry_id: str) -> str:
    """Return the stable realtime sensor unique ID."""
    return f"{entry_id}_real_time_cost"


def get_power_cost_unique_id(entry_id: str, interval: str) -> str:
    """Return the stable power cost sensor unique ID."""
    return f"{entry_id}_{interval}_power_cost"


def get_energy_cost_unique_id(entry_id: str, interval: str) -> str:
    """Return the stable energy cost sensor unique ID."""
    return f"{entry_id}_{interval}_energy_cost"


def get_legacy_unique_id_mappings(entry: ConfigEntry) -> dict[str, str]:
    """Return legacy-to-stable unique ID mappings for the config entry."""
    mappings: dict[str, str] = {}

    configs = [entry.data, entry.options, get_entry_config(entry)]
    stable_realtime = get_realtime_unique_id(entry.entry_id)

    for config in configs:
        if not config:
            continue

        power_sensor = config.get("power_sensor")
        if power_sensor:
            legacy_realtime = f"{entry.entry_id}_{power_sensor}_real_time_cost"
            mappings[legacy_realtime] = stable_realtime
            for interval in INTERVALS:
                mappings[f"{legacy_realtime}_{interval}"] = get_power_cost_unique_id(
                    entry.entry_id, interval
                )

        energy_sensor = config.get("energy_sensor")
        electricity_price_sensor = config.get("electricity_price_sensor")
        if energy_sensor and electricity_price_sensor:
            for interval in INTERVALS:
                mappings[
                    f"{electricity_price_sensor}_{energy_sensor}_{interval}_cost"
                ] = get_energy_cost_unique_id(entry.entry_id, interval)

    return mappings


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options are updated."""
    config = get_entry_config(entry)
    title = f"Dynamic Energy Cost - {config.get('integration_description', 'Unnamed')}"
    if entry.title != title:
        hass.config_entries.async_update_entry(entry, title=title)

    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate existing entities to stable entry-based unique IDs."""
    if entry.version >= MIGRATION_VERSION:
        return True

    entity_registry = er.async_get(hass)
    skipped_migrations = False
    for old_unique_id, new_unique_id in get_legacy_unique_id_mappings(entry).items():
        entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, old_unique_id)
        if entity_id is None:
            continue

        if entity_registry.async_get_entity_id("sensor", DOMAIN, new_unique_id):
            _LOGGER.warning(
                "Skipping unique ID migration from %s to %s because target exists",
                old_unique_id,
                new_unique_id,
            )
            skipped_migrations = True
            continue

        entity_registry.async_update_entity(entity_id, new_unique_id=new_unique_id)

    if not skipped_migrations:
        hass.config_entries.async_update_entry(entry, version=MIGRATION_VERSION)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Dynamic Energy Cost from a config entry."""
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.info(
        "Starting setup of Dynamic Energy Cost component, entry config: %s",
        get_entry_config(entry),
    )

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
