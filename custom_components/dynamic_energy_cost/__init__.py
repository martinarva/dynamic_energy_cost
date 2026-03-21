"""Home Assistant support for Dynamic Energy Costs."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


def get_entry_config(entry: ConfigEntry) -> dict[str, Any]:
    """Return merged config entry data and options."""
    return {**entry.data, **entry.options}


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


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
