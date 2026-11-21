"""End-to-end tests: the integration running inside a real Home Assistant core.

The unit tests call the sensor handlers directly. These tests instead set the
integration up through a config entry, as the UI does, so the sensor platform,
the state machine, services, timers, state restore and the recorder are all the
real ones. They cover what users see: the values, when they are published,
resets, services, restarts, reloads and what ends up in the database.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, HassJob, HomeAssistant, State, callback
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    restore_state,
)
from homeassistant.helpers.service import async_get_all_descriptions
from homeassistant.util import dt as dt_util
from homeassistant.util.async_ import get_scheduled_timer_handles

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache,
    mock_restore_cache_with_extra_data,
)

from custom_components.dynamic_energy_cost.const import (
    DAILY,
    DOMAIN,
    MONTHLY,
    REAL_TIME,
    SELECTED_SENSORS,
)
from custom_components.dynamic_energy_cost.entity import BaseUtilitySensor
from custom_components.dynamic_energy_cost.sensor import RealTimeCostSensor

PRICE = "sensor.electricity_price"
FIXED_PRICE = "sensor.fixed_price"
ENERGY = "sensor.heat_pump_energy"
POWER = "sensor.heat_pump_power"

VOLATILE_ATTRIBUTES = {
    "cumulative_energy",
    "last_energy_reading",
    "cumulative_cost",
    "average_energy_cost",
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _local(*args: int) -> datetime:
    return datetime(*args, tzinfo=dt_util.get_default_time_zone())


def _entry(
    source_key: str,
    source: str,
    selected: list[str],
    *,
    price: str = PRICE,
    description: str = "Heat Pump",
) -> MockConfigEntry:
    """A config entry shaped like the ones the config flow creates."""
    return MockConfigEntry(
        domain=DOMAIN,
        version=3,
        title=f"Dynamic Energy Cost - {description}",
        data={
            "integration_description": description,
            "electricity_price_sensor": price,
            source_key: source,
            SELECTED_SENSORS: selected,
        },
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _entity_id(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str:
    suffix = "real_time_cost" if key == REAL_TIME else f"{key}_cost"
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_{suffix}"
    )
    assert entity_id is not None, f"no {key} entity"
    return entity_id


def _value(hass: HomeAssistant, entity_id: str) -> float:
    return float(hass.states.get(entity_id).state)


async def _settle(hass: HomeAssistant) -> None:
    """Run the event loop until chained state-change dispatches are done.

    Home Assistant delivers state-change events to listeners one loop turn
    later, and the power path has two hops (power -> realtime -> interval
    sensor), so a single async_block_till_done() can return before the second
    hop has run. In a running Home Assistant the loop keeps turning, so this
    only matters when a test moves the clock right after a change.
    """
    for _ in range(3):
        await hass.async_block_till_done()


async def _advance(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float
) -> None:
    """Move the clock forward and run the timers that are now due."""
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await _settle(hass)


async def _set(hass: HomeAssistant, entity_id: str, value: float, unit: str) -> None:
    attributes = {"unit_of_measurement": unit}
    if unit == "kWh":
        attributes |= {"device_class": "energy", "state_class": "total_increasing"}
    elif unit == "W":
        attributes |= {"device_class": "power", "state_class": "measurement"}
    hass.states.async_set(entity_id, str(value), attributes)
    await _settle(hass)


def _published(hass: HomeAssistant, entity_id: str) -> list[State]:
    """Collect every state the entity publishes from now on."""
    states: list[State] = []

    @callback
    def _listener(event: Event) -> None:
        if event.data["entity_id"] == entity_id:
            states.append(event.data["new_state"])

    hass.bus.async_listen(EVENT_STATE_CHANGED, _listener)
    return states


def _values(states: list[State]) -> list[float]:
    return [float(state.state) for state in states]


def _our_timers(hass: HomeAssistant) -> list:
    """Scheduled timers that would call back into this integration's sensors."""
    ours = []
    for handle in get_scheduled_timer_handles(hass.loop):
        if handle.cancelled():
            continue
        callback_ = handle._callback
        candidates = [*(handle._args or ()), callback_, getattr(callback_, "job", None)]
        for candidate in candidates:
            if isinstance(candidate, HassJob):
                owner = getattr(candidate.target, "__self__", None)
                if isinstance(owner, (BaseUtilitySensor, RealTimeCostSensor)):
                    ours.append(handle)
    return ours


# ---------------------------------------------------------------------------
# energy sensor path
# ---------------------------------------------------------------------------


async def test_energy_entry_full_cycle(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A 10-second energy sensor across a price change and the midnight reset.

    Every update is counted, the cost sensors publish at most every 30 s, a
    price change books the energy used so far at the old price, and the daily
    reset publishes the closing value of the day before starting at zero.
    """
    freezer.move_to(_local(2026, 11, 21, 23, 58, 0))
    await _set(hass, PRICE, 0.20, "EUR/kWh")
    await _set(hass, ENERGY, 100.0, "kWh")
    entry = _entry("energy_sensor", ENERGY, [DAILY, MONTHLY])
    await _setup(hass, entry)
    daily = _entity_id(hass, entry, DAILY)
    monthly = _entity_id(hass, entry, MONTHLY)
    daily_states = _published(hass, daily)

    state = hass.states.get(daily)
    assert state.attributes["source"] == ENERGY
    assert state.attributes["price_source"] == PRICE
    assert state.attributes["unit_of_measurement"] == hass.config.currency
    first_last_reset = state.attributes["last_reset"]

    async def energy(seconds: float, kwh: float) -> None:
        await _advance(hass, freezer, seconds)
        await _set(hass, ENERGY, kwh, "kWh")

    await energy(10, 101.0)  # 23:58:10 first reading after setup: baseline only
    assert _value(hass, daily) == 0
    await energy(10, 102.0)  # 23:58:20 +1 kWh, published at once
    assert _value(hass, daily) == pytest.approx(0.2)
    await energy(10, 103.0)  # 23:58:30 held back
    await energy(10, 104.0)  # 23:58:40 held back
    assert _value(hass, daily) == pytest.approx(0.2)
    await _advance(hass, freezer, 10)  # 23:58:50 the held-back value goes out
    assert _value(hass, daily) == pytest.approx(0.6)

    await _advance(hass, freezer, 10)  # 23:59:00 price rises
    await _set(hass, PRICE, 0.30, "EUR/kWh")
    await energy(10, 105.0)  # 23:59:10 charged at the new price
    await _advance(hass, freezer, 10)  # 23:59:20
    assert _value(hass, daily) == pytest.approx(0.9)

    await energy(10, 106.0)  # 23:59:30
    await energy(10, 107.0)  # 23:59:40
    await _advance(hass, freezer, 10)  # 23:59:50
    assert _value(hass, daily) == pytest.approx(1.5)
    await energy(5, 108.0)  # 23:59:55 held back when midnight comes
    assert _value(hass, daily) == pytest.approx(1.5)

    await _advance(hass, freezer, 5)  # 00:00:00 daily reset
    assert _value(hass, daily) == 0
    await energy(10, 109.0)  # 00:00:10
    await _advance(hass, freezer, 20)  # 00:00:30

    assert _values(daily_states) == pytest.approx([0.2, 0.6, 0.9, 1.5, 1.8, 0.0, 0.3])
    closing, zero = daily_states[4], daily_states[5]
    # The closing value still belongs to the old day, the zero to the new one.
    assert closing.attributes["last_reset"] == first_last_reset
    assert dt_util.parse_datetime(zero.attributes["last_reset"]) == _local(
        2026, 11, 22, 0, 0, 0
    )
    # Monthly is not reset at midnight and has every kWh: 4 x 0.20 + 4 x 0.30.
    assert _value(hass, monthly) == pytest.approx(2.1)
    attributes = hass.states.get(monthly).attributes
    assert attributes["cumulative_energy"] == pytest.approx(8.0)
    assert attributes["average_energy_cost"] == pytest.approx(2.1 / 8.0)


async def test_energy_cost_is_restored_after_restart(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """State saved by the previous version is restored and counting continues."""
    freezer.move_to(_local(2026, 11, 21, 10, 0, 0))
    entry = _entry("energy_sensor", ENERGY, [DAILY])
    entry.add_to_hass(hass)
    daily = (
        er.async_get(hass)
        .async_get_or_create(
            "sensor",
            DOMAIN,
            f"{entry.entry_id}_daily_cost",
            suggested_object_id="heat_pump_daily_energy_cost",
            config_entry=entry,
        )
        .entity_id
    )
    last_reset = "2026-11-21T00:00:00-08:00"
    # Exactly the attributes v1.2.4 writes.
    mock_restore_cache(
        hass,
        [
            State(
                daily,
                "1.23",
                {
                    "state_class": "total",
                    "last_reset": last_reset,
                    "cumulative_energy": 6.15,
                    "last_energy_reading": 200.0,
                    "cumulative_cost": 1.23,
                    "average_energy_cost": 0.2,
                    "unit_of_measurement": "EUR",
                    "device_class": "monetary",
                    "icon": "mdi:cash",
                    "friendly_name": "Heat Pump Daily Energy Cost",
                },
            )
        ],
    )
    await _set(hass, PRICE, 0.20, "EUR/kWh")
    await _set(hass, ENERGY, 200.0, "kWh")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(daily)
    assert float(state.state) == pytest.approx(1.23)
    assert dt_util.parse_datetime(state.attributes["last_reset"]) == (
        dt_util.parse_datetime(last_reset)
    )

    # The restored reading is the baseline, so the first kWh is not lost.
    await _advance(hass, freezer, 10)
    await _set(hass, ENERGY, 201.0, "kWh")
    assert _value(hass, daily) == pytest.approx(1.43)
    assert hass.states.get(daily).attributes["cumulative_energy"] == pytest.approx(7.15)


# ---------------------------------------------------------------------------
# power sensor path
# ---------------------------------------------------------------------------


async def test_power_entry_full_cycle(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Cost from a power sensor, through calibrate and a reset (#246, #249)."""
    freezer.move_to(_local(2026, 11, 21, 10, 0, 0))
    await _set(hass, PRICE, 0.20, "EUR/kWh")
    await _set(hass, POWER, 0, "W")
    entry = _entry("power_sensor", POWER, [REAL_TIME, DAILY])
    await _setup(hass, entry)
    realtime = _entity_id(hass, entry, REAL_TIME)
    daily = _entity_id(hass, entry, DAILY)

    for entity_id in (realtime, daily):
        attributes = hass.states.get(entity_id).attributes
        assert attributes["source"] == POWER
        assert attributes["price_source"] == PRICE

    await _set(hass, POWER, 1000, "W")
    assert _value(hass, realtime) == pytest.approx(0.2)  # 1 kW at 0.20 EUR/kWh

    await _advance(hass, freezer, 3600)  # one hour at 1 kW
    await _set(hass, POWER, 2000, "W")
    assert _value(hass, realtime) == pytest.approx(0.4)
    assert _value(hass, daily) == pytest.approx(0.2)

    # Calibrating to a decimal amount must not stop accumulation (#246).
    await hass.services.async_call(
        DOMAIN, "calibrate", {"value": 5.25}, target={"entity_id": daily}, blocking=True
    )
    assert _value(hass, daily) == pytest.approx(5.25)

    await _advance(hass, freezer, 1800)  # half an hour at 2 kW
    await _set(hass, POWER, 1000, "W")
    assert _value(hass, daily) == pytest.approx(5.45)

    # 15 minutes at 1 kW pass without any update, then the user resets.
    daily_states = _published(hass, daily)
    await _advance(hass, freezer, 900)
    await hass.services.async_call(
        DOMAIN, "reset_cost", {}, target={"entity_id": daily}, blocking=True
    )
    # Those 15 minutes are booked into the closing value before zeroing (#249).
    assert _values(daily_states) == pytest.approx([5.5, 0.0])

    # Integration resumes from the reset with the kept rate.
    await _advance(hass, freezer, 3600)
    await _set(hass, POWER, 0, "W")
    assert _value(hass, daily) == pytest.approx(0.2)


async def test_power_cost_is_restored_after_restart(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A power-based cost sensor keeps its value over a restart."""
    freezer.move_to(_local(2026, 11, 21, 10, 0, 0))
    entry = _entry("power_sensor", POWER, [REAL_TIME, DAILY])
    entry.add_to_hass(hass)
    daily = (
        er.async_get(hass)
        .async_get_or_create(
            "sensor",
            DOMAIN,
            f"{entry.entry_id}_daily_cost",
            suggested_object_id="heat_pump_daily_energy_cost",
            config_entry=entry,
        )
        .entity_id
    )
    mock_restore_cache(
        hass,
        [
            State(
                daily,
                "4.5",
                {"state_class": "total", "last_reset": "2026-11-21T00:00:00-08:00"},
            )
        ],
    )
    await _set(hass, PRICE, 0.20, "EUR/kWh")
    await _set(hass, POWER, 1000, "W")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert _value(hass, daily) == pytest.approx(4.5)

    await _set(hass, POWER, 1200, "W")  # realtime rate becomes 0.24 EUR/h
    await _advance(hass, freezer, 3600)
    await _set(hass, POWER, 1000, "W")
    assert _value(hass, daily) == pytest.approx(4.74)


async def test_steady_load_is_charged_from_startup(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A load that doesn't change is charged from the moment the entry starts.

    Before, the realtime rate stayed 0 until the power or price changed, so
    after a restart a steady load cost nothing until then.
    """
    freezer.move_to(_local(2026, 11, 21, 10, 0, 0))
    await _set(hass, PRICE, 0.20, "EUR/kWh")
    await _set(hass, POWER, 1000, "W")  # already reporting, and stays put
    entry = _entry("power_sensor", POWER, [REAL_TIME, DAILY])
    await _setup(hass, entry)
    realtime = _entity_id(hass, entry, REAL_TIME)
    daily = _entity_id(hass, entry, DAILY)

    assert _value(hass, realtime) == pytest.approx(0.2)

    await _advance(hass, freezer, 3600)  # an hour without any change
    await _set(hass, PRICE, 0.30, "EUR/kWh")  # the next change books that hour
    assert _value(hass, daily) == pytest.approx(0.2)


async def test_steady_load_is_charged_across_a_reload(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Changing the options reloads the entry without losing a steady load's cost."""
    freezer.move_to(_local(2026, 11, 21, 10, 0, 0))
    await _set(hass, PRICE, 0.20, "EUR/kWh")
    await _set(hass, POWER, 1000, "W")
    entry = _entry("power_sensor", POWER, [REAL_TIME, DAILY, MONTHLY])
    await _setup(hass, entry)
    daily = _entity_id(hass, entry, DAILY)

    await _advance(hass, freezer, 1800)  # half an hour, nothing booked yet
    hass.config_entries.async_update_entry(
        entry, options={**entry.data, SELECTED_SENSORS: [REAL_TIME, DAILY]}
    )
    await _settle(hass)
    # The half hour before the reload is kept...
    assert _value(hass, daily) == pytest.approx(0.1)

    await _advance(hass, freezer, 3600)
    await _set(hass, PRICE, 0.30, "EUR/kWh")
    # ...and the hour after it is charged at the restarted rate.
    assert _value(hass, daily) == pytest.approx(0.3)


async def test_power_cost_saved_at_shutdown_includes_unpublished_cost(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """What Home Assistant saves for a restart includes cost not yet published.

    The published state can be up to 30 s behind, and the cost since the
    last rate change is only added on the next change. Both must be saved,
    or every restart would drop them.
    """
    freezer.move_to(_local(2026, 11, 21, 10, 0, 0))
    await _set(hass, PRICE, 0.20, "EUR/kWh")
    await _set(hass, POWER, 0, "W")
    entry = _entry("power_sensor", POWER, [REAL_TIME, DAILY])
    await _setup(hass, entry)
    daily = _entity_id(hass, entry, DAILY)

    await _set(hass, POWER, 1800, "W")  # 0.36 EUR/h
    await _advance(hass, freezer, 600)
    await _set(hass, POWER, 3600, "W")  # 10 min at 0.36: 0.06, published
    await _advance(hass, freezer, 10)
    await _set(hass, POWER, 1800, "W")  # 10 s at 0.72: +0.002, held back
    await _advance(hass, freezer, 15)  # 15 s at 0.36: +0.0015, not booked yet

    assert _value(hass, daily) == pytest.approx(0.06)
    saved = {
        stored.state.entity_id: stored
        for stored in restore_state.async_get(hass).async_get_stored_states()
    }[daily]
    assert float(saved.state.state) == pytest.approx(0.06)
    assert float(saved.extra_data.as_dict()["accrued_cost"]) == pytest.approx(0.0635)


async def test_power_cost_restored_from_saved_total(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """After a restart the full saved total comes back, and counting goes on."""
    freezer.move_to(_local(2026, 11, 21, 10, 0, 0))
    entry = _entry("power_sensor", POWER, [REAL_TIME, DAILY])
    entry.add_to_hass(hass)
    daily = (
        er.async_get(hass)
        .async_get_or_create(
            "sensor",
            DOMAIN,
            f"{entry.entry_id}_daily_cost",
            suggested_object_id="heat_pump_daily_energy_cost",
            config_entry=entry,
        )
        .entity_id
    )
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(
                    daily,
                    "0.06",
                    {"state_class": "total", "last_reset": "2026-11-21T00:00:00-08:00"},
                ),
                {"accrued_cost": "0.0635"},
            )
        ],
    )
    await _set(hass, PRICE, 0.20, "EUR/kWh")
    await _set(hass, POWER, 1800, "W")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert _value(hass, daily) == pytest.approx(0.0635)

    await _set(hass, POWER, 3600, "W")  # realtime rate 0.72 EUR/h
    await _advance(hass, freezer, 600)
    await _set(hass, POWER, 1800, "W")  # 10 min at 0.72: +0.12
    assert _value(hass, daily) == pytest.approx(0.1835)


# ---------------------------------------------------------------------------
# services, reloads, unloads, several entries
# ---------------------------------------------------------------------------


async def test_service_pickers_target_this_integration(hass: HomeAssistant) -> None:
    """services.yaml loads, and both actions only offer this integration's sensors."""
    await _set(hass, PRICE, 0.20, "EUR/kWh")
    await _set(hass, ENERGY, 100.0, "kWh")
    await _setup(hass, _entry("energy_sensor", ENERGY, [DAILY]))

    descriptions = (await async_get_all_descriptions(hass))[DOMAIN]

    for service in ("reset_cost", "calibrate"):
        entity_filter = descriptions[service]["target"]["entity"]
        filters = entity_filter if isinstance(entity_filter, list) else [entity_filter]
        assert [f["integration"] for f in filters] == [DOMAIN]
    number = descriptions["calibrate"]["fields"]["value"]["selector"]["number"]
    assert number["mode"] == "box"
    assert number["step"] == "any"


async def test_changing_selection_reloads_without_losing_cost(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Dropping an interval in the options reloads cleanly and keeps the cost.

    The reload happens while a value is held back by the rate limit; the
    energy behind it must still be counted afterwards.
    """
    freezer.move_to(_local(2026, 11, 21, 10, 0, 0))
    await _set(hass, PRICE, 0.20, "EUR/kWh")
    await _set(hass, ENERGY, 100.0, "kWh")
    entry = _entry("energy_sensor", ENERGY, [DAILY, MONTHLY])
    await _setup(hass, entry)
    daily = _entity_id(hass, entry, DAILY)

    for kwh in (101.0, 102.0, 103.0):  # baseline, published, held back
        await _advance(hass, freezer, 10)
        await _set(hass, ENERGY, kwh, "kWh")
    assert _value(hass, daily) == pytest.approx(0.2)

    hass.config_entries.async_update_entry(
        entry, options={**entry.data, SELECTED_SENSORS: [DAILY]}
    )
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_monthly_cost")
        is None
    )
    assert _entity_id(hass, entry, DAILY) == daily
    assert _value(hass, daily) == pytest.approx(0.2)

    await _advance(hass, freezer, 10)
    await _set(hass, ENERGY, 104.0, "kWh")
    # 103 and 104 kWh are both counted: 0.2 + 2 x 0.2.
    assert _value(hass, daily) == pytest.approx(0.6)


async def test_unloading_leaves_no_timers_behind(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Unloading an entry cancels its resets and any held-back write."""
    freezer.move_to(_local(2026, 11, 21, 10, 0, 0))
    await _set(hass, PRICE, 0.20, "EUR/kWh")
    await _set(hass, ENERGY, 100.0, "kWh")
    entry = _entry("energy_sensor", ENERGY, [DAILY, MONTHLY])
    await _setup(hass, entry)
    for kwh in (101.0, 102.0, 103.0):
        await _advance(hass, freezer, 10)
        await _set(hass, ENERGY, kwh, "kWh")
    assert _our_timers(hass)  # resets and a held-back write are scheduled

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert _our_timers(hass) == []


async def test_two_entries_on_one_sensor_stay_apart(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The dynamic-versus-fixed comparison: one energy sensor, two prices."""
    freezer.move_to(_local(2026, 11, 21, 10, 0, 0))
    await _set(hass, PRICE, 0.20, "EUR/kWh")
    await _set(hass, FIXED_PRICE, 0.15, "EUR/kWh")
    await _set(hass, ENERGY, 100.0, "kWh")
    dynamic = _entry("energy_sensor", ENERGY, [DAILY], description="Dynamic")
    fixed = _entry(
        "energy_sensor", ENERGY, [DAILY], price=FIXED_PRICE, description="Fixed"
    )
    await _setup(hass, dynamic)
    await _setup(hass, fixed)
    dynamic_daily = _entity_id(hass, dynamic, DAILY)
    fixed_daily = _entity_id(hass, fixed, DAILY)
    assert dynamic_daily != fixed_daily

    for kwh in (101.0, 103.0):  # baseline, then 2 kWh
        await _advance(hass, freezer, 10)
        await _set(hass, ENERGY, kwh, "kWh")

    assert _value(hass, dynamic_daily) == pytest.approx(0.4)
    assert _value(hass, fixed_daily) == pytest.approx(0.3)
    assert hass.states.get(dynamic_daily).attributes["price_source"] == PRICE
    assert hass.states.get(fixed_daily).attributes["price_source"] == FIXED_PRICE


# ---------------------------------------------------------------------------
# devices (#14)
# ---------------------------------------------------------------------------


async def test_cost_sensors_join_the_source_device(hass: HomeAssistant) -> None:
    """Cost sensors show up on the source sensor's device, without taking it over.

    Since Home Assistant 2026.8 a device belongs to a single config entry, and
    helpers must link their entities to another integration's device rather
    than add their config entry to it.
    """
    meter = MockConfigEntry(domain="test_meter")
    meter.add_to_hass(hass)
    devices = dr.async_get(hass)
    device = devices.async_get_or_create(
        config_entry_id=meter.entry_id,
        identifiers={("test_meter", "heat-pump-1")},
        name="Heat pump",
    )
    er.async_get(hass).async_get_or_create(
        "sensor",
        "test_meter",
        "heat-pump-energy",
        suggested_object_id="heat_pump_energy",
        config_entry=meter,
        device_id=device.id,
    )
    await _set(hass, PRICE, 0.20, "EUR/kWh")
    await _set(hass, ENERGY, 100.0, "kWh")
    entry = _entry("energy_sensor", ENERGY, [DAILY, MONTHLY])
    await _setup(hass, entry)

    registry = er.async_get(hass)
    for key in (DAILY, MONTHLY):
        assert registry.async_get(_entity_id(hass, entry, key)).device_id == device.id

    # Linked, not joined: the device still belongs to the meter integration.
    device = devices.async_get(device.id)
    owner = getattr(device, "config_entry_id", None)
    if owner is None:  # Home Assistant before 2026.8
        assert entry.entry_id not in device.config_entries
    else:
        assert owner == meter.entry_id
    # And no device of our own was created.
    assert not dr.async_entries_for_config_entry(devices, entry.entry_id)


async def test_cost_sensors_get_their_own_device_without_a_source_device(
    hass: HomeAssistant,
) -> None:
    """A source sensor without a device gets one Dynamic Energy Cost device."""
    await _set(hass, PRICE, 0.20, "EUR/kWh")
    await _set(hass, ENERGY, 100.0, "kWh")
    entry = _entry("energy_sensor", ENERGY, [DAILY, MONTHLY])
    await _setup(hass, entry)

    own = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert len(own) == 1
    assert own[0].identifiers == {(DOMAIN, entry.entry_id)}
    registry = er.async_get(hass)
    for key in (DAILY, MONTHLY):
        assert registry.async_get(_entity_id(hass, entry, key)).device_id == own[0].id
