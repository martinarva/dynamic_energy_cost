"""Regression tests for sensor calculation edge cases."""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from homeassistant.components.sensor import SensorStateClass
from homeassistant.util import dt as dt_util

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dynamic_energy_cost.const import DAILY, DOMAIN, HOURLY
from custom_components.dynamic_energy_cost.sensor import (
    EnergyCostSensor,
    PowerCostSensor,
    RealTimeCostSensor,
    _price_unit_conversion_factor,
)


def _event(*, entity_id: str, new_state=None, old_state=None):
    return Mock(
        data={"entity_id": entity_id, "new_state": new_state, "old_state": old_state}
    )


def _state(value: str):
    return Mock(state=value, attributes={})


def _state_with_unit(value: str, unit: str):
    return Mock(state=value, attributes={"unit_of_measurement": unit})


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry-123",
        data={
            "integration_description": "Heat Pump",
            "electricity_price_sensor": "sensor.electricity_price",
            "power_sensor": "sensor.heat_pump_power",
            "energy_sensor": "sensor.heat_pump_energy",
        },
    )


def test_realtime_sensor_ignores_missing_source_state(hass):
    """Realtime cost updates are skipped if source states are missing."""
    sensor = RealTimeCostSensor(
        hass,
        _entry(),
        "sensor.electricity_price",
        "sensor.heat_pump_power",
    )
    sensor.async_write_ha_state = Mock()

    hass.states.async_remove("sensor.electricity_price")
    hass.states.async_remove("sensor.heat_pump_power")

    sensor.handle_state_change(
        _event(entity_id="sensor.heat_pump_power", new_state=_state("500"))
    )

    assert sensor.state == 0.0
    sensor.async_write_ha_state.assert_not_called()


def test_realtime_sensor_ignores_none_event_state(hass):
    """Realtime cost updates are skipped if the event has no new state."""
    sensor = RealTimeCostSensor(
        hass,
        _entry(),
        "sensor.electricity_price",
        "sensor.heat_pump_power",
    )
    sensor.async_write_ha_state = Mock()

    sensor.handle_state_change(
        _event(entity_id="sensor.heat_pump_power", new_state=None)
    )

    assert sensor.state == 0.0
    sensor.async_write_ha_state.assert_not_called()


def test_realtime_sensor_keeps_internal_precision_for_low_loads(hass):
    """Realtime cost keeps more than 2 decimals internally for power integration."""
    sensor = RealTimeCostSensor(
        hass,
        _entry(),
        "sensor.electricity_price",
        "sensor.heat_pump_power",
    )
    sensor.async_write_ha_state = Mock()

    hass.states.async_set("sensor.electricity_price", "0.9731")
    hass.states.async_set("sensor.heat_pump_power", "17")

    sensor.handle_state_change(
        _event(entity_id="sensor.heat_pump_power", new_state=_state("17"))
    )

    assert sensor._state == Decimal("0.0165")
    assert sensor.state == 0.0165
    sensor.async_write_ha_state.assert_called_once()


async def test_energy_sensor_zero_price_and_follow_up_increment(hass):
    """Energy sensor handles zero price and later increments correctly."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 10.0
    sensor._cumulative_cost = 0.0

    hass.states.async_set("sensor.electricity_price", "0")
    await sensor._async_update_energy_event(
        _event(entity_id="sensor.heat_pump_energy", new_state=_state("11"))
    )

    assert sensor.state == 0.0
    assert sensor._cumulative_cost == 0.0
    assert sensor._last_energy_reading == 11.0

    hass.states.async_set("sensor.electricity_price", "2")
    await sensor._async_update_energy_event(
        _event(entity_id="sensor.heat_pump_energy", new_state=_state("12"))
    )

    assert sensor.state == 2.0
    assert sensor._cumulative_cost == 2.0
    assert sensor._last_energy_reading == 12.0


async def test_energy_sensor_reset_to_zero_reinitializes_baseline(hass):
    """Energy sensor does not generate a negative jump on source reset."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 15.0
    sensor._cumulative_cost = 7.5
    sensor._state = 7.5

    hass.states.async_set("sensor.electricity_price", "3")
    await sensor._async_update_energy_event(
        _event(entity_id="sensor.heat_pump_energy", new_state=_state("0"))
    )

    assert sensor.state == 7.5
    assert sensor._cumulative_cost == 7.5
    assert sensor._last_energy_reading == 0.0

    await sensor._async_update_energy_event(
        _event(entity_id="sensor.heat_pump_energy", new_state=_state("1"))
    )

    assert sensor.state == 10.5
    assert sensor._cumulative_cost == 10.5
    assert sensor._last_energy_reading == 1.0


async def test_energy_cost_reset_reinitialises_baseline(hass):
    """After periodic reset, first reading sets baseline and second produces cost."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 100.0
    sensor._cumulative_cost = 50.0
    sensor._cumulative_energy = 20.0
    sensor._state = 50.0

    hass.states.async_set("sensor.electricity_price", "2")

    # Simulate periodic reset (daily/weekly/monthly)
    sensor.schedule_next_reset = Mock()
    sensor.async_reset()

    assert sensor.state == 0
    assert sensor._last_energy_reading is None

    # First energy reading after reset — sets baseline
    await sensor._async_update_energy_event(
        _event(entity_id="sensor.heat_pump_energy", new_state=_state("100"))
    )
    assert sensor._last_energy_reading == 100.0
    assert sensor.state == 0  # no cost yet, just baseline

    # Second energy reading — produces correct cost
    await sensor._async_update_energy_event(
        _event(entity_id="sensor.heat_pump_energy", new_state=_state("102"))
    )
    assert sensor._cumulative_cost == 4.0  # 2 kWh * €2
    assert sensor.state == 4.0
    assert sensor._last_energy_reading == 102.0


async def test_energy_sensor_daily_source_resets_with_daily_cost(hass):
    """Daily source sensor + daily cost sensor: both reset around midnight."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.daily_energy",
        "sensor.electricity_price",
        DAILY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 50.0
    sensor._cumulative_cost = 10.0
    sensor._cumulative_energy = 5.0
    sensor._state = 10.0

    hass.states.async_set("sensor.electricity_price", "0.20")

    # Cost sensor resets at midnight (clears _last_energy_reading)
    sensor.schedule_next_reset = Mock()
    sensor.async_reset()
    assert sensor._last_energy_reading is None
    assert sensor.state == 0

    # Source sensor also resets — first reading sets baseline
    await sensor._async_update_energy_event(
        _event(entity_id="sensor.daily_energy", new_state=_state("0.1"))
    )
    assert sensor._last_energy_reading == 0.1
    assert sensor.state == 0  # baseline only, no cost yet

    # Next reading produces correct positive cost
    await sensor._async_update_energy_event(
        _event(entity_id="sensor.daily_energy", new_state=_state("2.1"))
    )
    assert sensor._cumulative_cost == 0.4  # 2 kWh * €0.20
    assert sensor._last_energy_reading == 2.1


async def test_energy_sensor_cumulative_source_never_resets(hass):
    """Cumulative source sensor (total_increasing) works across cost resets."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.total_energy",
        "sensor.electricity_price",
        DAILY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 1000.0
    sensor._cumulative_cost = 5.0
    sensor._cumulative_energy = 10.0
    sensor._state = 5.0

    hass.states.async_set("sensor.electricity_price", "0.10")

    # Cost sensor daily reset at midnight
    sensor.schedule_next_reset = Mock()
    sensor.async_reset()

    assert sensor.state == 0
    assert sensor._last_energy_reading is None

    # Source sensor keeps incrementing (never resets)
    await sensor._async_update_energy_event(
        _event(entity_id="sensor.total_energy", new_state=_state("1002"))
    )
    # First reading after reset sets baseline
    assert sensor._last_energy_reading == 1002.0
    assert sensor.state == 0

    await sensor._async_update_energy_event(
        _event(entity_id="sensor.total_energy", new_state=_state("1005"))
    )
    # 3 kWh * €0.10 = €0.30
    from pytest import approx

    assert sensor._cumulative_cost == approx(0.3)
    assert sensor.state == approx(0.3)

    await sensor._async_update_energy_event(
        _event(entity_id="sensor.total_energy", new_state=_state("1010"))
    )
    # +5 kWh * €0.10 = €0.50, total €0.80
    assert sensor._cumulative_cost == approx(0.8)
    assert sensor.state == approx(0.8)


async def test_energy_sensor_calibrate_updates_internal_baseline(hass):
    """Calibration affects the next increment instead of being overwritten."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 5.0

    sensor.async_calibrate("4.5")
    hass.states.async_set("sensor.electricity_price", "2")
    await sensor._async_update_energy_event(
        _event(entity_id="sensor.heat_pump_energy", new_state=_state("6"))
    )

    assert sensor.state == 6.5
    assert sensor._cumulative_cost == 6.5
    assert sensor._last_energy_reading == 6.0


async def test_energy_sensor_price_change_uses_previous_price(hass):
    """Price-change updates finalize accrued cost using the old price."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 10.0
    sensor._cumulative_cost = 4.0
    sensor._state = 4.0

    hass.states.async_set("sensor.heat_pump_energy", "12")
    await sensor._async_update_price_event(
        _event(
            entity_id="sensor.electricity_price",
            old_state=_state("2"),
            new_state=_state("3"),
        )
    )

    assert sensor.state == 8.0
    assert sensor._cumulative_cost == 8.0
    assert sensor._cumulative_energy == 2.0
    assert sensor._last_energy_reading == 12.0


async def test_energy_sensor_supports_decreasing_readings_for_feed_in(hass):
    """Energy sensor preserves negative deltas for export/feed-in meters."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 12.0
    sensor._cumulative_cost = 10.0
    sensor._cumulative_energy = 4.0
    sensor._state = 10.0

    hass.states.async_set("sensor.electricity_price", "2")
    await sensor._async_update_energy_event(
        _event(entity_id="sensor.heat_pump_energy", new_state=_state("11"))
    )

    assert sensor.state == 8.0
    assert sensor._cumulative_cost == 8.0
    assert sensor._cumulative_energy == 3.0
    assert sensor._last_energy_reading == 11.0


async def test_energy_sensor_price_change_supports_decreasing_readings(hass):
    """Price-change path also preserves negative deltas for feed-in meters."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 12.0
    sensor._cumulative_cost = 10.0
    sensor._cumulative_energy = 4.0
    sensor._state = 10.0

    hass.states.async_set("sensor.heat_pump_energy", "11")
    await sensor._async_update_price_event(
        _event(entity_id="sensor.electricity_price", old_state=_state("2"))
    )

    assert sensor.state == 8.0
    assert sensor._cumulative_cost == 8.0
    assert sensor._cumulative_energy == 3.0
    assert sensor._last_energy_reading == 11.0


async def test_energy_sensor_restores_legacy_state_without_cumulative_cost_attribute(
    hass,
):
    """Restore falls back to last state value for older entities."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_get_last_state = AsyncMock(
        return_value=Mock(
            state="9.5",
            attributes={"last_energy_reading": 4.0, "cumulative_energy": 2.5},
        )
    )
    sensor.async_write_ha_state = Mock()
    sensor.schedule_next_reset = Mock()

    await sensor.async_added_to_hass()

    assert sensor.state == 9.5
    assert sensor._cumulative_cost == 9.5
    assert sensor._last_energy_reading == 4.0
    assert sensor._cumulative_energy == 2.5


async def test_energy_sensor_exposes_and_restores_last_reset(hass):
    """Energy cost sensors expose last_reset and restore it."""
    last_reset = datetime(2026, 3, 1, 0, 0, tzinfo=dt_util.UTC)
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_get_last_state = AsyncMock(
        return_value=Mock(
            state="9.5",
            attributes={
                "last_energy_reading": 4.0,
                "cumulative_energy": 2.5,
                "cumulative_cost": 9.5,
                "last_reset": last_reset.isoformat(),
            },
        )
    )
    sensor.async_write_ha_state = Mock()
    sensor.schedule_next_reset = Mock()

    await sensor.async_added_to_hass()

    assert sensor.state_class is SensorStateClass.TOTAL
    assert sensor.last_reset == last_reset

    previous_reset = sensor.last_reset
    sensor.async_reset()

    assert sensor.last_reset is not None
    assert sensor.last_reset >= previous_reset


def test_power_sensor_first_update_only_sets_baseline(hass):
    """Power cost sensor avoids a large jump when no prior update timestamp exists."""
    realtime_sensor = Mock(entity_id="sensor.heat_pump_real_time_energy_cost")
    realtime_sensor.name = "Heat Pump Real Time Energy Cost"
    realtime_sensor.device_info = {"identifiers": {(DOMAIN, "entry-123")}}
    realtime_sensor.unique_id = "entry-123_real_time_cost"
    realtime_sensor._config_entry = _entry()

    sensor = PowerCostSensor(hass, realtime_sensor, HOURLY)
    sensor.async_write_ha_state = Mock()
    sensor._state = Decimal("1.5000")
    sensor._last_update = None

    sensor._handle_real_time_cost_update(
        _event(entity_id=realtime_sensor.entity_id, new_state=_state("2.5"))
    )

    assert sensor.state == Decimal("1.5000")
    assert sensor._last_update is not None
    sensor.async_write_ha_state.assert_not_called()


def test_power_sensor_integrates_cost_over_elapsed_time(hass):
    """Power cost sensor integrates realtime cost over elapsed time."""
    realtime_sensor = Mock(entity_id="sensor.heat_pump_real_time_energy_cost")
    realtime_sensor.name = "Heat Pump Real Time Energy Cost"
    realtime_sensor.device_info = {"identifiers": {(DOMAIN, "entry-123")}}
    realtime_sensor.unique_id = "entry-123_real_time_cost"
    realtime_sensor._config_entry = _entry()

    sensor = PowerCostSensor(hass, realtime_sensor, HOURLY)
    sensor.async_write_ha_state = Mock()
    sensor._state = Decimal("1.0000")

    from datetime import timedelta
    from homeassistant.util.dt import now

    sensor._last_cost_rate = Decimal("1.5")
    sensor._last_update = now() - timedelta(hours=2)
    sensor._handle_real_time_cost_update(
        _event(entity_id=realtime_sensor.entity_id, new_state=_state("1.5"))
    )

    assert sensor.state == Decimal("4.0000")
    sensor.async_write_ha_state.assert_called_once()


def test_power_sensor_uses_previous_cost_rate_for_elapsed_time(hass):
    """Elapsed time is charged using the previous realtime cost rate."""
    realtime_sensor = Mock(entity_id="sensor.heat_pump_real_time_energy_cost")
    realtime_sensor.name = "Heat Pump Real Time Energy Cost"
    realtime_sensor.device_info = {"identifiers": {(DOMAIN, "entry-123")}}
    realtime_sensor.unique_id = "entry-123_real_time_cost"
    realtime_sensor._config_entry = _entry()

    sensor = PowerCostSensor(hass, realtime_sensor, HOURLY)
    sensor.async_write_ha_state = Mock()
    sensor._state = Decimal("1.0000")

    from datetime import timedelta
    from homeassistant.util.dt import now

    sensor._last_update = now() - timedelta(hours=2)
    sensor._handle_real_time_cost_update(
        _event(
            entity_id=realtime_sensor.entity_id,
            old_state=_state("0.5"),
            new_state=_state("1.5"),
        )
    )

    assert sensor.state == Decimal("2.0000")
    assert sensor._last_cost_rate == Decimal("1.5")
    sensor.async_write_ha_state.assert_called_once()


def test_power_sensor_uses_precise_rate_for_elapsed_time(hass):
    """Power integration uses the higher precision realtime rate baseline."""
    realtime_sensor = Mock(entity_id="sensor.heat_pump_real_time_energy_cost")
    realtime_sensor.name = "Heat Pump Real Time Energy Cost"
    realtime_sensor.device_info = {"identifiers": {(DOMAIN, "entry-123")}}
    realtime_sensor.unique_id = "entry-123_real_time_cost"
    realtime_sensor._config_entry = _entry()

    sensor = PowerCostSensor(hass, realtime_sensor, HOURLY)
    sensor.async_write_ha_state = Mock()
    sensor._state = Decimal("0.0000")

    from datetime import timedelta
    from homeassistant.util.dt import now

    sensor._last_cost_rate = Decimal("0.0165")
    sensor._last_update = now() - timedelta(hours=2)
    sensor._handle_real_time_cost_update(
        _event(
            entity_id=realtime_sensor.entity_id,
            old_state=_state("0.0165"),
            new_state=_state("0.0200"),
        )
    )

    assert sensor.state == Decimal("0.0330")


def test_power_sensor_does_not_backfill_idle_time_with_new_spike(hass):
    """A new spike after idle time does not charge the whole gap at the new rate."""
    realtime_sensor = Mock(entity_id="sensor.heat_pump_real_time_energy_cost")
    realtime_sensor.name = "Heat Pump Real Time Energy Cost"
    realtime_sensor.device_info = {"identifiers": {(DOMAIN, "entry-123")}}
    realtime_sensor.unique_id = "entry-123_real_time_cost"
    realtime_sensor._config_entry = _entry()

    sensor = PowerCostSensor(hass, realtime_sensor, HOURLY)
    sensor.async_write_ha_state = Mock()
    sensor._state = Decimal("0.0000")

    from datetime import timedelta
    from homeassistant.util.dt import now

    sensor._last_update = now() - timedelta(hours=3)
    sensor._handle_real_time_cost_update(
        _event(
            entity_id=realtime_sensor.entity_id,
            old_state=_state("0"),
            new_state=_state("7.5"),
        )
    )

    assert sensor.state == Decimal("0.0000")
    assert sensor._last_cost_rate == Decimal("7.5")


async def test_power_sensor_restore_uses_current_rate_as_baseline(hass):
    """Restore sets the current realtime rate as the baseline for later integration."""
    realtime_sensor = Mock(entity_id="sensor.heat_pump_real_time_energy_cost")
    realtime_sensor.name = "Heat Pump Real Time Energy Cost"
    realtime_sensor.device_info = {"identifiers": {(DOMAIN, "entry-123")}}
    realtime_sensor.unique_id = "entry-123_real_time_cost"
    realtime_sensor._config_entry = _entry()

    hass.states.async_set(realtime_sensor.entity_id, "2.5")

    sensor = PowerCostSensor(hass, realtime_sensor, HOURLY)
    sensor.async_get_last_state = AsyncMock(return_value=Mock(state="4.0"))
    sensor.schedule_next_reset = Mock()

    await sensor.async_added_to_hass()

    assert sensor.state == Decimal("4.0")
    assert sensor._last_cost_rate == Decimal("2.5")


async def test_power_sensor_exposes_total_state_class_and_last_reset(hass):
    """Power cost sensors behave like resetting TOTAL sensors."""
    realtime_sensor = Mock(entity_id="sensor.heat_pump_real_time_energy_cost")
    realtime_sensor.name = "Heat Pump Real Time Energy Cost"
    realtime_sensor.device_info = {"identifiers": {(DOMAIN, "entry-123")}}
    realtime_sensor.unique_id = "entry-123_real_time_cost"
    realtime_sensor._config_entry = _entry()

    last_reset = datetime(2026, 3, 1, 0, 0, tzinfo=dt_util.UTC)
    sensor = PowerCostSensor(hass, realtime_sensor, HOURLY)
    sensor.async_get_last_state = AsyncMock(
        return_value=Mock(
            state="4.0",
            attributes={"last_reset": last_reset.isoformat()},
        )
    )
    sensor.async_write_ha_state = Mock()
    sensor.schedule_next_reset = Mock()

    await sensor.async_added_to_hass()

    assert sensor.state_class is SensorStateClass.TOTAL
    assert sensor.last_reset == last_reset

    previous_reset = sensor.last_reset
    sensor.async_reset()

    assert sensor.last_reset is not None
    assert sensor.last_reset >= previous_reset


def test_energy_sensor_uses_entry_based_device_identifier(hass):
    """Energy sensors share the config-entry device identity with the integration."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )

    assert sensor.device_info["identifiers"] == {(DOMAIN, "entry-123")}


async def test_energy_sensor_wh_unit_converts_to_kwh(hass):
    """Energy sensor in Wh divides by 1000 before calculating cost."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 1000.0
    sensor._cumulative_cost = 0.0
    sensor._energy_to_kwh = 0.001  # Wh → kWh

    hass.states.async_set("sensor.electricity_price", "0.2")
    await sensor._async_update_energy_event(
        _event(
            entity_id="sensor.heat_pump_energy",
            new_state=_state_with_unit("2000", "Wh"),
        )
    )

    # delta = 1000 Wh = 1 kWh; cost = 1 kWh x 0.2 = 0.2
    assert sensor._cumulative_cost == pytest.approx(0.2)
    assert sensor._cumulative_energy == pytest.approx(1.0)


async def test_energy_sensor_mwh_unit_converts_to_kwh(hass):
    """Energy sensor in MWh multiplies by 1000 before calculating cost."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 1.0
    sensor._cumulative_cost = 0.0
    sensor._energy_to_kwh = 1000.0  # MWh → kWh

    hass.states.async_set("sensor.electricity_price", "0.1")
    await sensor._async_update_energy_event(
        _event(
            entity_id="sensor.heat_pump_energy",
            new_state=_state_with_unit("2", "MWh"),
        )
    )

    # delta = 1 MWh = 1000 kWh; cost = 1000 kWh x 0.1 = 100
    assert sensor._cumulative_cost == pytest.approx(100.0)
    assert sensor._cumulative_energy == pytest.approx(1000.0)


async def test_energy_sensor_kwh_unit_unchanged(hass):
    """Energy sensor in kWh uses factor 1.0 — behaviour unchanged."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 10.0
    sensor._cumulative_cost = 0.0
    sensor._energy_to_kwh = 1.0  # kWh, default

    hass.states.async_set("sensor.electricity_price", "0.3")
    await sensor._async_update_energy_event(
        _event(
            entity_id="sensor.heat_pump_energy",
            new_state=_state_with_unit("11", "kWh"),
        )
    )

    # delta = 1 kWh; cost = 1 x 0.3 = 0.3
    assert sensor._cumulative_cost == pytest.approx(0.3)
    assert sensor._cumulative_energy == pytest.approx(1.0)


async def test_energy_sensor_wh_unit_resolved_from_event(hass):
    """Unit is resolved from first energy event when sensor was unavailable at startup."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 1000.0
    sensor._cumulative_cost = 0.0
    # _energy_to_kwh stays at default 1.0 (sensor was unavailable at startup)
    assert sensor._energy_to_kwh == 1.0

    hass.states.async_set("sensor.electricity_price", "0.2")
    # First event carries Wh unit — should trigger re-resolution
    await sensor._async_update_energy_event(
        _event(
            entity_id="sensor.heat_pump_energy",
            new_state=_state_with_unit("2000", "Wh"),
        )
    )

    assert sensor._energy_to_kwh == pytest.approx(0.001)
    # delta = 1000 Wh = 1 kWh; cost = 1 x 0.2 = 0.2
    assert sensor._cumulative_cost == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# Price unit conversion helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "unit, expected",
    [
        ("EUR/MWh", 0.001),
        ("EUR/kWh", 1.0),
        ("EUR/Wh", 1000.0),
        ("SEK/kWh", 1.0),
        ("USD/MWh", 0.001),
        ("€/MWh", 0.001),
        ("EUR / MWh", 0.001),
        ("eur/mwh", 0.001),
        ("EUR/MWH", 0.001),
        ("EUR", 1.0),
        ("", 1.0),
        ("EUR/MW", 1.0),
    ],
)
def test_price_unit_conversion_factor(unit, expected):
    """Price unit helper correctly extracts energy denominator."""
    state = _state_with_unit("50", unit) if unit else _state("50")
    assert _price_unit_conversion_factor(state) == pytest.approx(expected)


def test_price_unit_conversion_factor_none():
    """Price unit helper returns 1.0 for None state."""
    assert _price_unit_conversion_factor(None) == 1.0


# ---------------------------------------------------------------------------
# Price unit conversion in RealTimeCostSensor
# ---------------------------------------------------------------------------


def test_realtime_sensor_converts_eur_per_mwh(hass):
    """Realtime cost correctly converts EUR/MWh price to EUR/kWh."""
    sensor = RealTimeCostSensor(
        hass,
        _entry(),
        "sensor.electricity_price",
        "sensor.heat_pump_power",
    )
    sensor.async_write_ha_state = Mock()

    hass.states.async_set(
        "sensor.electricity_price",
        "50",
        {"unit_of_measurement": "EUR/MWh"},
    )
    hass.states.async_set("sensor.heat_pump_power", "1000")

    sensor.handle_state_change(
        _event(entity_id="sensor.heat_pump_power", new_state=_state("1000"))
    )

    # 50 EUR/MWh = 0.05 EUR/kWh; 1000 W = 1 kW; cost = 0.05 EUR/h
    assert sensor._state == Decimal("0.0500")


def test_realtime_sensor_converts_eur_per_wh(hass):
    """Realtime cost correctly converts EUR/Wh price to EUR/kWh."""
    sensor = RealTimeCostSensor(
        hass,
        _entry(),
        "sensor.electricity_price",
        "sensor.heat_pump_power",
    )
    sensor.async_write_ha_state = Mock()

    hass.states.async_set(
        "sensor.electricity_price",
        "0.0002",
        {"unit_of_measurement": "EUR/Wh"},
    )
    hass.states.async_set("sensor.heat_pump_power", "1000")

    sensor.handle_state_change(
        _event(entity_id="sensor.heat_pump_power", new_state=_state("1000"))
    )

    # 0.0002 EUR/Wh = 0.2 EUR/kWh; 1000 W = 1 kW; cost = 0.2 EUR/h
    assert sensor._state == Decimal("0.2000")


def test_realtime_sensor_eur_per_kwh_unchanged(hass):
    """Realtime cost is unchanged when price is already in EUR/kWh."""
    sensor = RealTimeCostSensor(
        hass,
        _entry(),
        "sensor.electricity_price",
        "sensor.heat_pump_power",
    )
    sensor.async_write_ha_state = Mock()

    hass.states.async_set(
        "sensor.electricity_price",
        "0.25",
        {"unit_of_measurement": "EUR/kWh"},
    )
    hass.states.async_set("sensor.heat_pump_power", "2000")

    sensor.handle_state_change(
        _event(entity_id="sensor.heat_pump_power", new_state=_state("2000"))
    )

    # 0.25 EUR/kWh; 2000 W = 2 kW; cost = 0.5 EUR/h
    assert sensor._state == Decimal("0.5000")


# ---------------------------------------------------------------------------
# Price unit conversion in EnergyCostSensor
# ---------------------------------------------------------------------------


async def test_energy_sensor_converts_eur_per_mwh_on_energy_event(hass):
    """Energy sensor correctly converts EUR/MWh price on energy event."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 10.0
    sensor._cumulative_cost = 0.0

    hass.states.async_set(
        "sensor.electricity_price",
        "100",
        {"unit_of_measurement": "EUR/MWh"},
    )
    await sensor._async_update_energy_event(
        _event(
            entity_id="sensor.heat_pump_energy",
            new_state=_state_with_unit("11", "kWh"),
        )
    )

    # delta = 1 kWh; price = 100 EUR/MWh = 0.1 EUR/kWh; cost = 0.1
    assert sensor._cumulative_cost == pytest.approx(0.1)


async def test_energy_sensor_converts_eur_per_mwh_on_price_event(hass):
    """Energy sensor correctly converts EUR/MWh price on price change."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 10.0
    sensor._cumulative_cost = 0.0

    hass.states.async_set("sensor.heat_pump_energy", "11")
    await sensor._async_update_price_event(
        _event(
            entity_id="sensor.electricity_price",
            old_state=_state_with_unit("200", "EUR/MWh"),
            new_state=_state_with_unit("250", "EUR/MWh"),
        )
    )

    # delta = 1 kWh; old price = 200 EUR/MWh = 0.2 EUR/kWh; cost = 0.2
    assert sensor._cumulative_cost == pytest.approx(0.2)


async def test_energy_sensor_converts_eur_per_wh(hass):
    """Energy sensor correctly converts EUR/Wh price."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 10.0
    sensor._cumulative_cost = 0.0

    hass.states.async_set(
        "sensor.electricity_price",
        "0.0002",
        {"unit_of_measurement": "EUR/Wh"},
    )
    await sensor._async_update_energy_event(
        _event(
            entity_id="sensor.heat_pump_energy",
            new_state=_state_with_unit("11", "kWh"),
        )
    )

    # delta = 1 kWh; 0.0002 EUR/Wh = 0.2 EUR/kWh; cost = 0.2
    assert sensor._cumulative_cost == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# Backward compatibility: no unit_of_measurement on price sensor
# ---------------------------------------------------------------------------


def test_realtime_sensor_no_price_unit_backward_compat(hass):
    """Realtime cost works unchanged when price sensor has no unit_of_measurement."""
    sensor = RealTimeCostSensor(
        hass,
        _entry(),
        "sensor.electricity_price",
        "sensor.heat_pump_power",
    )
    sensor.async_write_ha_state = Mock()

    # No unit_of_measurement — most existing setups
    hass.states.async_set("sensor.electricity_price", "0.25")
    hass.states.async_set("sensor.heat_pump_power", "2000")

    sensor.handle_state_change(
        _event(entity_id="sensor.heat_pump_power", new_state=_state("2000"))
    )

    # 0.25 EUR/kWh (assumed); 2000 W = 2 kW; cost = 0.5 EUR/h
    assert sensor._state == Decimal("0.5000")


async def test_energy_sensor_no_price_unit_backward_compat(hass):
    """Energy sensor works unchanged when price sensor has no unit_of_measurement."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 10.0
    sensor._cumulative_cost = 0.0

    # No unit_of_measurement on price — most existing setups
    hass.states.async_set("sensor.electricity_price", "0.30")
    await sensor._async_update_energy_event(
        _event(
            entity_id="sensor.heat_pump_energy",
            new_state=_state_with_unit("12", "kWh"),
        )
    )

    # delta = 2 kWh; price = 0.30 (assumed EUR/kWh); cost = 0.60
    assert sensor._cumulative_cost == pytest.approx(0.6)


async def test_energy_sensor_price_change_no_unit_backward_compat(hass):
    """Energy sensor price-change path works unchanged when price has no unit."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 10.0
    sensor._cumulative_cost = 0.0

    hass.states.async_set("sensor.heat_pump_energy", "12")
    await sensor._async_update_price_event(
        _event(
            entity_id="sensor.electricity_price",
            old_state=_state("0.25"),
            new_state=_state("0.30"),
        )
    )

    # delta = 2 kWh; old price = 0.25 (no unit, assumed /kWh); cost = 0.50
    assert sensor._cumulative_cost == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Combined: energy unit + price unit conversion together
# ---------------------------------------------------------------------------


async def test_energy_sensor_mwh_energy_with_eur_per_mwh_price(hass):
    """Both energy (MWh) and price (EUR/MWh) conversions work together correctly."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 1.0
    sensor._cumulative_cost = 0.0
    sensor._energy_to_kwh = 1000.0  # MWh → kWh

    hass.states.async_set(
        "sensor.electricity_price",
        "50",
        {"unit_of_measurement": "EUR/MWh"},
    )
    await sensor._async_update_energy_event(
        _event(
            entity_id="sensor.heat_pump_energy",
            new_state=_state_with_unit("1.5", "MWh"),
        )
    )

    # delta = 0.5 MWh = 500 kWh; price = 50 EUR/MWh = 0.05 EUR/kWh
    # cost = 500 * 0.05 = 25.0 EUR
    assert sensor._cumulative_cost == pytest.approx(25.0)
    assert sensor._cumulative_energy == pytest.approx(500.0)


async def test_energy_sensor_wh_energy_with_eur_per_wh_price(hass):
    """Both energy (Wh) and price (EUR/Wh) conversions work together correctly."""
    sensor = EnergyCostSensor(
        hass,
        _entry(),
        "sensor.heat_pump_energy",
        "sensor.electricity_price",
        HOURLY,
    )
    sensor.async_write_ha_state = Mock()
    sensor._last_energy_reading = 1000.0
    sensor._cumulative_cost = 0.0
    sensor._energy_to_kwh = 0.001  # Wh → kWh

    hass.states.async_set(
        "sensor.electricity_price",
        "0.0003",
        {"unit_of_measurement": "EUR/Wh"},
    )
    await sensor._async_update_energy_event(
        _event(
            entity_id="sensor.heat_pump_energy",
            new_state=_state_with_unit("2000", "Wh"),
        )
    )

    # delta = 1000 Wh = 1 kWh; price = 0.0003 EUR/Wh = 0.3 EUR/kWh
    # cost = 1 * 0.3 = 0.3 EUR
    assert sensor._cumulative_cost == pytest.approx(0.3)
    assert sensor._cumulative_energy == pytest.approx(1.0)
