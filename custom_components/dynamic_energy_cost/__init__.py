"""Home Assistant support for Dynamic Energy Costs."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    DAILY,
    DOMAIN,
    HOURLY,
    MANUAL,
    MONTHLY,
    QUARTERLY,
    REAL_TIME,
    SELECTED_SENSORS,
    WEEKLY,
    YEARLY,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]
MIGRATION_VERSION = 3
INTERVALS = [QUARTERLY, HOURLY, DAILY, WEEKLY, MONTHLY, YEARLY, MANUAL]


def get_entry_config(entry: ConfigEntry) -> dict[str, Any]:
    """Return merged config entry data and options."""
    return {**entry.data, **entry.options}


def get_selected_sensors(entry: ConfigEntry) -> set[str]:
    """Return the set of selected sensor keys.

    Reads from entry.options first, then entry.data, then defaults to all
    sensors for backward compatibility with existing installations.
    """
    selected = entry.options.get(SELECTED_SENSORS)
    if selected is None:
        selected = entry.data.get(SELECTED_SENSORS)

    if selected is None:
        config = get_entry_config(entry)
        if config.get("power_sensor"):
            return {REAL_TIME} | set(INTERVALS)
        return set(INTERVALS)

    return set(selected)


def get_realtime_unique_id(entry_id: str) -> str:
    """Return the stable realtime sensor unique ID."""
    return f"{entry_id}_real_time_cost"


def get_interval_cost_unique_id(entry_id: str, interval: str) -> str:
    """Return the stable shared interval sensor unique ID."""
    return f"{entry_id}_{interval}_cost"


def get_power_cost_unique_id(entry_id: str, interval: str) -> str:
    """Return the v2 power cost sensor unique ID."""
    return f"{entry_id}_{interval}_power_cost"


def get_energy_cost_unique_id(entry_id: str, interval: str) -> str:
    """Return the v2 energy cost sensor unique ID."""
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
                mappings[get_power_cost_unique_id(entry.entry_id, interval)] = (
                    get_interval_cost_unique_id(entry.entry_id, interval)
                )

        energy_sensor = config.get("energy_sensor")
        electricity_price_sensor = config.get("electricity_price_sensor")
        if energy_sensor and electricity_price_sensor:
            for interval in INTERVALS:
                mappings[
                    f"{electricity_price_sensor}_{energy_sensor}_{interval}_cost"
                ] = get_energy_cost_unique_id(entry.entry_id, interval)
                mappings[get_energy_cost_unique_id(entry.entry_id, interval)] = (
                    get_interval_cost_unique_id(entry.entry_id, interval)
                )

    return mappings


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options are updated."""
    config = get_entry_config(entry)
    title = f"Dynamic Energy Cost - {config.get('integration_description', 'Unnamed')}"
    if entry.title != title:
        hass.config_entries.async_update_entry(entry, title=title)

    entity_registry = er.async_get(hass)
    selected = get_selected_sensors(entry)

    # Build sensor_key -> unique_id map for all possible sensors.
    # Always include real_time — it may need cleanup when switching
    # from power to energy path.
    possible: dict[str, str] = {
        REAL_TIME: get_realtime_unique_id(entry.entry_id),
    }
    for interval in INTERVALS:
        possible[interval] = get_interval_cost_unique_id(entry.entry_id, interval)

    # Remove entities for deselected sensors
    for key, unique_id in possible.items():
        if key not in selected:
            entity_id = entity_registry.async_get_entity_id(
                "sensor", DOMAIN, unique_id
            )
            if entity_id is not None:
                entity_registry.async_remove(entity_id)

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

    _cleanup_orphaned_energy_device(hass, entry)
    return True


def _cleanup_orphaned_energy_device(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the orphaned device left by the v0.9.3 identifier change.

    In v0.9.3, EnergyCostSensor used (DOMAIN, energy_sensor_id) as the
    device identifier.  Current code uses (DOMAIN, entry_id) for all
    sensors, so the old device becomes an empty orphan after upgrade.

    Called from both async_migrate_entry (for fresh upgrades) and
    async_setup_entry (for installations that already migrated).
    """
    # Check both data and options: the user may have changed the energy
    # sensor via options, but the orphan was created with the original value.
    candidates: set[str] = set()
    for source in (entry.data, entry.options):
        sensor = source.get("energy_sensor") if source else None
        if sensor:
            candidates.add(sensor)

    if not candidates:
        return

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    for energy_sensor in candidates:
        old_device = device_registry.async_get_device(
            identifiers={(DOMAIN, energy_sensor)}
        )
        if old_device is None:
            continue

        if er.async_entries_for_device(entity_registry, old_device.id):
            _LOGGER.debug(
                "Skipping removal of device %s — it still has entities",
                old_device.id,
            )
            continue

        device_registry.async_remove_device(old_device.id)
        _LOGGER.info(
            "Removed orphaned device %s (old energy sensor identifier: %s)",
            old_device.id,
            energy_sensor,
        )


def _cleanup_legacy_helper_device(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the legacy (DOMAIN, entry_id) device if it has no entities.

    Before v0.10.0, all cost sensors lived under a helper-owned device
    identified by (DOMAIN, entry_id).  Now sensors attach directly to
    the source power/energy sensor's device via self.device_entry.
    The old device becomes an empty orphan after the first restart.
    """
    device_registry = dr.async_get(hass)
    old_device = device_registry.async_get_device(
        identifiers={(DOMAIN, entry.entry_id)}
    )
    if old_device is None:
        return

    entity_registry = er.async_get(hass)
    if er.async_entries_for_device(entity_registry, old_device.id):
        _LOGGER.debug(
            "Skipping removal of legacy device %s — it still has entities",
            old_device.id,
        )
        return

    device_registry.async_remove_device(old_device.id)
    _LOGGER.info(
        "Removed legacy helper device %s (entry_id: %s)",
        old_device.id,
        entry.entry_id,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Dynamic Energy Cost from a config entry."""
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    _cleanup_orphaned_energy_device(hass, entry)

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

    # Clean up old (DOMAIN, entry_id) device after sensor platform has
    # re-registered entities under the source device via device_entry.
    _cleanup_legacy_helper_device(hass, entry)

    _LOGGER.info("Dynamic Energy Cost setup completed successfully")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a Dynamic Energy Cost config entry."""

    _LOGGER.debug("Attempting to unload the Dynamic Energy Cost component")
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
