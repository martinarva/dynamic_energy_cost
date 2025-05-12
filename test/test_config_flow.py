"""Tests for the config flow."""

from unittest.mock import patch

from homeassistant import config_entries, setup
from custom_components.dynamic_energy_cost.const import DOMAIN

# Enable debug logging for tests
logging.basicConfig(level=logging.DEBUG)
_LOGGER = logging.getLogger(__name__)

async def test_form(hass):
    """Test we get the form."""
    await setup.async_setup_component(hass, "persistent_notification", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["errors"] == {}

    with patch(
        "custom_components.simple_integration.async_setup", return_value=True
    ) as mock_setup, patch(
        "custom_components.simple_integration.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "name": "new_simple_config"
            },
        )

    assert result2["type"] == "create_entry"
    assert result2["title"] == "new_simple_config"
    assert result2["data"] == {
        "name": "new_simple_config",
    }
    await hass.async_block_till_done()
    assert len(mock_setup.mock_calls) == 1
    assert len(mock_setup_entry.mock_calls) == 1
