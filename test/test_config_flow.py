"""Tests for the config flow."""
from unittest import mock
from unittest.mock import AsyncMock, patch

from gidgethub import BadRequest
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_NAME, CONF_PATH
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.github_custom import config_flow
from custom_components.github_custom.const import CONF_REPOS, DOMAIN


@pytest.mark.asyncio
@patch("custom_components.github_custom.config_flow.GitHubAPI")
async def test_validate_path_valid(m_github, hass):
    """Test no exception is raised for a valid path."""
    m_instance = AsyncMock()
    m_instance.getitem = AsyncMock()
    m_github.return_value = m_instance
    await config_flow.validate_path("home-assistant/core", "access-token", hass)


@pytest.mark.asyncio
async def test_validate_path_invalid(hass):
    """Test a ValueError is raised when the path is not valid."""
    for bad_path in ("home-assistant", "home-assistant/core/foo"):
        with pytest.raises(ValueError):
            await config_flow.validate_path(bad_path, "access-token", hass)


@pytest.mark.asyncio
@patch("custom_components.github_custom.config_flow.GitHubAPI")
async def test_validate_auth_valid(m_github, hass):
    """Test no exception is raised for valid auth."""
    m_instance = AsyncMock()
    m_instance.getitem = AsyncMock()
    m_github.return_value = m_instance
    await config_flow.validate_auth("token", hass)


@pytest.mark.asyncio
@patch("custom_components.github_custom.config_flow.GitHubAPI")
async def test_validate_auth_invalid(m_github, hass):
    """Test ValueError is raised when auth is invalid."""
    m_instance = AsyncMock()
    m_instance.getitem = AsyncMock(side_effect=BadRequest(AsyncMock()))
    m_github.return_value = m_instance
    with pytest.raises(ValueError):
        await config_flow.validate_auth("token", hass)


@pytest.mark.asyncio
async def test_flow_user_init(hass):
    """Test the initialization of the form in the first step of the config flow."""
    result = await hass.config_entries.flow.async_init(
        config_flow.DOMAIN, context={"source": "user"}
    )
    expected = {
        "data_schema": config_flow.AUTH_SCHEMA,
        "description_placeholders": None,
        "errors": {},
        "flow_id": mock.ANY,
        "handler": "github_custom",
        "last_step": None,
        "step_id": "user",
        "type": "form",
    }
    assert expected == result


@pytest.mark.asyncio
@patch("custom_components.github_custom.config_flow.validate_auth")
async def test_flow_user_init_invalid_auth_token(m_validate_auth, hass):
    """Test errors populated when auth token is invalid."""
    m_validate_auth.side_effect = ValueError
    _result = await hass.config_entries.flow.async_init(
        config_flow.DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        _result["flow_id"], user_input={CONF_ACCESS_TOKEN: "bad"}
    )
    assert {"base": "auth"} == result["errors"]


@pytest.mark.asyncio
@patch("custom_components.github_custom.config_flow.validate_auth")
async def test_flow_user_init_data_valid(m_validate_auth, hass):
    """Test we advance to the next step when data is valid."""
    _result = await hass.config_entries.flow.async_init(
        config_flow.DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        _result["flow_id"], user_input={CONF_ACCESS_TOKEN: "bad"}
    )
    assert "repo" == result["step_id"]
    assert "form" == result["type"]


@pytest.mark.asyncio
async def test_flow_repo_init_form(hass):
    """Test the initialization of the form in the second step of the config flow."""
    result = await hass.config_entries.flow.async_init(
        config_flow.DOMAIN, context={"source": "repo"}
    )
    expected = {
        "data_schema": config_flow.REPO_SCHEMA,
        "description_placeholders": None,
        "errors": {},
        "flow_id": mock.ANY,
        "handler": "github_custom",
        "step_id": "repo",
        "last_step": None,
        "type": "form",
    }
    assert expected == result


@pytest.mark.asyncio
async def test_flow_repo_path_invalid(hass):
    """Test errors populated when path is invalid."""
    config_flow.GithubCustomConfigFlow.data = {
        CONF_ACCESS_TOKEN: "token",
    }
    _result = await hass.config_entries.flow.async_init(
        config_flow.DOMAIN, context={"source": "repo"}
    )
    result = await hass.config_entries.flow.async_configure(
        _result["flow_id"], user_input={CONF_NAME: "bad", CONF_PATH: "bad"}
    )
    assert {"base": "invalid_path"} == result["errors"]


@pytest.mark.asyncio
@patch("custom_components.github_custom.config_flow.GitHubAPI")
async def test_flow_repo_add_another(github, hass):
    """Test we show the repo flow again if the add_another box was checked."""
    instance = AsyncMock()
    instance.getitem = AsyncMock()
    github.return_value = instance

    config_flow.GithubCustomConfigFlow.data = {
        CONF_ACCESS_TOKEN: "token",
        CONF_REPOS: [],
    }
    _result = await hass.config_entries.flow.async_init(
        config_flow.DOMAIN, context={"source": "repo"}
    )
    result = await hass.config_entries.flow.async_configure(
        _result["flow_id"],
        user_input={CONF_PATH: "home-assistant/core", "add_another": True},
    )
    assert "repo" == result["step_id"]
    assert "form" == result["type"]


@pytest.mark.asyncio
@patch("custom_components.github_custom.config_flow.GitHubAPI")
async def test_flow_repo_creates_config_entry(m_github, hass):
    """Test the config entry is successfully created."""
    m_instance = AsyncMock()
    m_instance.getitem = AsyncMock()
    m_github.return_value = m_instance
    config_flow.GithubCustomConfigFlow.data = {
        CONF_ACCESS_TOKEN: "token",
        CONF_REPOS: [],
    }
    with patch("custom_components.github_custom.async_setup_entry", return_value=True):
        _result = await hass.config_entries.flow.async_init(
            config_flow.DOMAIN, context={"source": "repo"}
        )
        await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_configure(
        _result["flow_id"],
        user_input={CONF_PATH: "home-assistant/core"},
    )
    expected = {
        "context": {"source": "repo"},
        "version": 1,
        "type": "create_entry",
        "flow_id": mock.ANY,
        "handler": "github_custom",
        "title": "GitHub Custom",
        "data": {
            "access_token": "token",
            "repositories": [
                {"path": "home-assistant/core", "name": "home-assistant/core"}
            ],
        },
        "description": None,
        "description_placeholders": None,
        "options": {},
        "result": mock.ANY,
    }
    assert expected == result


@pytest.mark.asyncio
@patch("custom_components.github_custom.sensor.GitHubAPI")
async def test_options_flow_init(m_github, hass):
    """Test config flow options."""
    m_instance = AsyncMock()
    m_instance.getitem = AsyncMock()
    m_github.return_value = m_instance

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="kodi_recently_added_media",
        data={
            CONF_ACCESS_TOKEN: "access-token",
            CONF_REPOS: [{"path": "home-assistant/core", "name": "HA Core"}],
        },
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # show initial form
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert "form" == result["type"]
    assert "init" == result["step_id"]
    assert {} == result["errors"]
    # Verify multi-select options populated with configured repos.
    assert {"sensor.ha_core": "HA Core"} == result["data_schema"].schema[
        "repos"
    ].options
