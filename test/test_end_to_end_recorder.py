"""End-to-end recorder test: what the rate limit leaves in the database (#242).

The recorder is set up the way Home Assistant sets it up, with a SQLite
database file like most installs use, rather than through the test plugin's recorder fixtures: on
Python 3.14 those fixtures autospec recorder functions whose annotations name
types imported only for type checking, and fail before the test starts.
"""

from __future__ import annotations

from pathlib import Path

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.components.recorder.history import state_changes_during_period
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.components.recorder import get_instance
from homeassistant.core import HomeAssistant
from homeassistant.helpers import recorder as recorder_helper
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
    do_adhoc_statistics,
)

from custom_components.dynamic_energy_cost.const import DAILY

from .test_end_to_end import (
    ENERGY,
    PRICE,
    VOLATILE_ATTRIBUTES,
    _advance,
    _entity_id,
    _entry,
    _local,
    _set,
    _setup,
    _value,
)


async def test_recorder_rows_and_statistics_across_midnight(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tmp_path: Path
) -> None:
    """Fewer rows, no per-update attributes, and statistics still add up.

    The long-term statistics behind the Energy dashboard must include the
    cost that was held back by the rate limit when the daily reset happened.
    """
    freezer.move_to(_local(2026, 11, 21, 23, 58, 0))
    # Bootstrap normally does this before the recorder is set up.
    recorder_helper.async_initialize_recorder(hass)
    assert await async_setup_component(
        hass,
        "recorder",
        {
            "recorder": {
                "db_url": f"sqlite:///{tmp_path / 'home-assistant_v2.db'}",
                "commit_interval": 0,
            }
        },
    )
    await async_wait_recording_done(hass)
    recorder = get_instance(hass)
    await _set(hass, PRICE, 0.20, "EUR/kWh")
    await _set(hass, ENERGY, 100.0, "kWh")
    entry = _entry("energy_sensor", ENERGY, [DAILY])
    await _setup(hass, entry)
    daily = _entity_id(hass, entry, DAILY)
    start = dt_util.utcnow()

    # A 10-second energy sensor: 1 kWh per update until 00:01:00.
    kwh = 100.0
    for _ in range(18):
        await _advance(hass, freezer, 10)
        kwh += 1
        await _set(hass, ENERGY, kwh, "kWh")
    await _advance(hass, freezer, 30)  # let the last held-back value out
    # 17 counted updates (the first sets the baseline): 10 before midnight
    # (2.0 EUR), and 7 from the one that arrives right after the reset at
    # 00:00:00 (1.4 EUR).
    assert _value(hass, daily) == pytest.approx(1.4)

    freezer.move_to(_local(2026, 11, 22, 0, 5, 30))
    await async_wait_recording_done(hass)

    states = (
        await recorder.async_add_executor_job(
            state_changes_during_period, hass, start, None, daily
        )
    )[daily]
    # 18 source updates would have been 18 rows; the rate limit leaves a few
    # plus the closing value and the zero at midnight.
    assert 5 <= len(states) <= 10
    for state in states:
        assert not VOLATILE_ATTRIBUTES & state.attributes.keys()
        assert state.attributes["source"] == ENERGY
        assert state.attributes["price_source"] == PRICE
        assert "last_reset" in state.attributes

    # Compile the two 5-minute statistics periods around midnight.
    for period in (_local(2026, 11, 21, 23, 55, 0), _local(2026, 11, 22, 0, 0, 0)):
        do_adhoc_statistics(hass, start=dt_util.as_utc(period))
        await async_wait_recording_done(hass)
    stats = await recorder.async_add_executor_job(
        statistics_during_period,
        hass,
        dt_util.as_utc(_local(2026, 11, 21, 23, 55, 0)),
        None,
        {daily},
        "5minute",
        None,
        {"state", "sum"},
    )
    last = stats[daily][-1]
    assert last["state"] == pytest.approx(1.4)
    # Every kWh is in the statistics, including the value that was held back
    # when the reset came: 2.0 EUR before midnight + 1.4 after.
    assert last["sum"] == pytest.approx(3.4)
