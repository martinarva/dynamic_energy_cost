"""Tests for the config flow."""

from unittest import mock
from unittest.mock import AsyncMock, patch

import pytest
import logging
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Enable debug logging for tests
logging.basicConfig(level=logging.DEBUG)
_LOGGER = logging.getLogger(__name__)

