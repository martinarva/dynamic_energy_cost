import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

DOMAIN = "dynamic_energy_cost"

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Dynamic Energy Cost component."""
    _LOGGER.debug("Global setup of Dynamic Energy Cost component.")
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Dynamic Energy Cost from a config entry."""
    _LOGGER.debug("Setting up Dynamic Energy Cost component, entry.data: %s", entry.data)
    
    try:
        setup_result = await hass.config_entries.async_forward_entry_setup(entry, 'sensor')
        _LOGGER.debug("Forwarding to sensor setup was successful: %s", setup_result)
    except Exception as e:
        _LOGGER.error("Failed to set up sensor platform, error: %s", str(e))
        return False

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a Dynamic Energy Cost config entry."""
    _LOGGER.debug("Attempting to unload the Dynamic Energy Cost component.")
    try:
        unload_ok = await hass.config_entries.async_forward_entry_unload(entry, 'sensor')
        _LOGGER.debug("Unloading was successful: %s", unload_ok)
        return unload_ok
    except Exception as e:
        _LOGGER.error("Failed to unload sensor platform, error: %s", str(e))
        return False
