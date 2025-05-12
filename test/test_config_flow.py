"""Tests for the config flow."""

import pytest
from unittest.mock import patch
from homeassistant import config_entries, setup
from custom_components.dynamic_energy_cost.const import DOMAIN


@pytest.mark.asyncio
async def test_form(hass):
    """Test we get the form."""
    # Ensure the component is set up correctly
    await setup.async_setup_component(hass, "persistent_notification", {})

    with (
        patch(
            "custom_components.dynamic_energy_cost.async_setup", return_value=True
        ) as mock_setup,
        patch(
            "custom_components.dynamic_energy_cost.async_setup_entry", return_value=True
        ) as mock_setup_entry,
    ):
        # Initialize the flow
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == "form"
        assert result["errors"] == {}

        # Configure the flow
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"name": "new_simple_config"}
        )
        assert result2["type"] == "create_entry"
        assert result2["title"] == "new_simple_config"
        assert result2["data"] == {"name": "new_simple_config"}

    # Verify that setup entry functions were called
    await hass.async_block_till_done()
    assert mock_setup.called
    assert mock_setup_entry.called
