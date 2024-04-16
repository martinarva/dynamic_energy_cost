
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, discovery
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN

import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Dynamic Energy Cost component from configuration.yaml."""
    # Handle configuration from YAML here if needed
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Dynamic Energy Cost from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # If your integration creates any async tasks, store their references here,
    # so they can be cancelled in async_unload_entry.

    # Forward the setup to the sensor platform.
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, 'sensor')
    )
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a Dynamic Energy Cost config entry."""
    # Optionally handle the unloading of entries, if needed
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, 'sensor')
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
