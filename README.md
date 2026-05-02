<div align="center">
  <br>
  <img src="docs/source/img/DynamicEnergyCost_Icon100.png" alt="Dynamic Energy Cost icon" width="100">

  <h1>Dynamic Energy Cost</h1>
  <strong>HACS integration for Home Assistant</strong>

  <p>
    <a href="https://analytics.home-assistant.io/">
      <img alt="dynamic_energy_cost usage" src="https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.dynamic_energy_cost.total">
    </a>
    <a href="https://gitlocalize.com/repo/10085?utm_source=badge">
      <img alt="GitLocalize" src="https://gitlocalize.com/repo/10085/whole_project/badge.svg">
    </a>
    <a href="https://github.com/martinarva/dynamic_energy_cost/blob/main/LICENSE">
      <img alt="License" src="https://img.shields.io/github/license/martinarva/dynamic_energy_cost">
    </a>
    <a href="https://github.com/martinarva/dynamic_energy_cost/releases/latest">
      <img alt="Latest release" src="https://img.shields.io/github/v/release/martinarva/dynamic_energy_cost">
    </a>
  </p>
</div>

<p align="center">
  <img src="https://skills.syvixor.com/api/icons?i=github,homeassistant,hacs,python,gitlocalize" />
</p>

Track your real electricity costs in Home Assistant. Point this integration at a **price sensor** and a **power or energy sensor** and it creates cost sensors that follow your actual dynamic tariff — whether that comes from [Nord Pool](https://www.home-assistant.io/integrations/nordpool/), [Amber](https://www.home-assistant.io/integrations/amberelectric/), [Tibber](https://www.home-assistant.io/integrations/tibber), or any other source.

## What you get

- **Real-time cost** (power path) — see what you're paying right now, in currency per hour
- **Interval cost sensors** — 15-minute, hourly, daily, weekly, monthly, and yearly accumulated costs
- **Manual reset sensor** — never resets automatically; perfect for tracking a single EV charging session or appliance run
- **Automatic unit conversion** — price in EUR/MWh or EUR/Wh? Energy in Wh or MWh? Power in kW or MW? The integration detects and converts automatically
- **Customizable sensor selection** — choose which cost sensors to create during setup; change it later via the options flow
- **Source device integration** — cost sensors appear directly under your source device (heat pump, EV charger, etc.)

## What you need

| Sensor | Required | Supported units |
|---|---|---|
| Electricity price | Yes | `currency/kWh`, `currency/MWh`, `currency/Wh` (any currency) |
| Energy consumption | Recommended | `kWh`, `Wh`, `MWh` |
| Power consumption | Alternative | `W`, `kW`, `MW` |

Use an **energy sensor** whenever one is available — it is more accurate and works like the HA Energy Dashboard. A **power sensor** is supported as a fallback but remains an approximation since it integrates instantaneous readings over time.

Only one consumption sensor (energy or power) can be configured per entry.

## Installation

### Install using HACS (recommended)
If you do not have HACS installed yet visit https://hacs.xyz for installation instructions.

To add the this repository to HACS in your Home Assistant instance, use this My button:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?repository=dynamic_energy_cost&owner=martinarva&category=Integration)

After installation, please restart Home Assistant. To add Dynamic Energy Cost to your Home Assistant instance, use this My button:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=dynamic_energy_cost)

<details>
<summary><b> Manual configuration steps</b></summary>

### Semi-Manual Installation with HACS

1. In Home Assistant go to HACS integrations section.
2. Click on the 3 dots in the top right corner.
3. Select "Custom repositories".
4. Add the URL (https://github.com/martinarva/dynamic_energy_cost) to the repository.
5. Select the integration category.
6. Click the "ADD" button.
7. Now you are able to download the integration.

### Manual Installation

1. Download the [latest release of Dynamic Energy Cost](https://github.com/martinarva/dynamic_energy_cost/releases/latest) and extract its contents.
2. Copy the `dynamic_energy_cost` folder into the `custom_components` directory located typically at `/config/custom_components/` in your Home Assistant directory.
3. Restart Home Assistant to recognize the newly added custom component.
  <a href="https://my.home-assistant.io/redirect/developer_call_service/?service=homeassistant%2Erestart" target="_blank" rel="noreferrer noopener"><img src="https://my.home-assistant.io/badges/developer_call_service.svg" alt="Open your Home Assistant instance and show your service developer tools with a specific action selected." /></a>

### Add Integration

1. Navigate to Settings > Devices & Services.
2. Click Add Integration and search for "Dynamic Energy Cost".
3. Select the Dynamic Energy Cost integration to initiate setup.

</details>

## Configuration

When setting up the integration, you will go through two steps:

**Step 1 — Source sensors:**
- **Electricity Price Sensor:** Sensor that provides the current electricity price (for example Nordpool, Amber, ... fixed price, day/night).
- **Power/Energy Usage Sensor:** Power sensors can measure in W, kW, or MW (converted automatically). Energy sensors can use kWh, Wh, or MWh (converted automatically). Prefer the energy sensor option when both are available.

**Step 2 — Sensor selection:**
- Choose which cost sensors to create. All sensors are selected by default.
- For power sensors, the Real Time Cost sensor is automatically included when any interval sensor is selected.
- You can change this selection later via Settings → Devices & Services → Configure.

## Tips

- Use a price sensor that already represents the final price you want to track.
- If you need tariffs, standing charges, VAT, or other custom logic, build that into a template sensor first and feed the result into this integration.
- Energy-based sensors include attributes for total energy used (kWh) and average energy price, useful for optimizing usage during cheaper hours.
- Interval cost sensors expose `last_reset` for compatibility with HA statistics consumers.

## Services

### Reset cost

Reset an energy cost sensor to 0. Useful in automations or via Developer Tools → Services.

```yaml
service: dynamic_energy_cost.reset_cost
target:
  entity_id: sensor.your_sensor_entity_id
```

### Calibrate

Set the value of a cost sensor to a specific number.

```yaml
action: dynamic_energy_cost.calibrate
target:
  entity_id: sensor.your_sensor_entity_id
data:
  value: "100"
```

## Scope

Dynamic Energy Cost is intentionally focused on turning a price sensor and a consumption sensor into cost sensors.

It is not intended to be a full contract or utility billing engine. In particular, these are better handled outside the integration with template sensors, helpers, or automations:

- standing charges
- tariff blending / VAT / fixed margins
- gas unit conversion (`m3` -> `kWh`)
- solar self-consumption or export deduction logic
- plan comparison against a different fixed-price contract

## Updating

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?repository=dynamic_energy_cost&owner=martinarva&category=Integration)

<details>
<summary><b> Update manually </b></summary>

To update the integration to a newer version:

1. Download the [latest release of Dynamic Energy Cost](https://github.com/martinarva/dynamic_energy_cost/releases/latest) and extract its contents.
2. Go to your Home Assistant instance.
3. Make sure to make a backup first.
  <a href="https://my.home-assistant.io/redirect/backup/" target="_blank" rel="noreferrer noopener"><img src="https://my.home-assistant.io/badges/backup.svg" alt="Open your Home Assistant instance and show an overview of your backups." /></a>
4. Overwrite the `dynamic_energy_cost` folder into the `custom_components` directory located typically at `/config/custom_components/`.
5. Reboot Home Assistant.
  <a href="https://my.home-assistant.io/redirect/developer_call_service/?service=homeassistant%2Erestart" target="_blank" rel="noreferrer noopener"><img src="https://my.home-assistant.io/badges/developer_call_service.svg" alt="Open your Home Assistant instance and show your service developer tools with a specific action selected." /></a>

</details>

## Contribute

Contributions are welcome.

- Bug reports with exact sensor setup, screenshots, and logs are extremely helpful.
- If you use a `W` sensor path, please mention that explicitly when reporting issues.
- Translation help is welcome via [GitLocalize](https://gitlocalize.com/repo/10085).

Thanks to everyone who has reported bugs, tested edge cases, opened pull requests, and kept using the integration.

## Support

For setup help, usage questions, and general discussion, use the Home Assistant Community topic: [Dynamic Energy Cost](https://community.home-assistant.io/t/dynamic-energy-cost/726931)

Use GitHub issues for concrete bugs and actionable feature requests.

When opening a bug report, please include:

- integration version
- Home Assistant version
- whether you use a `kWh` sensor or a `W` sensor
- the source sensor entities involved
- screenshots or logs that show the current behavior

GitHub issues: [Dynamic Energy Cost issues](https://github.com/martinarva/dynamic_energy_cost/issues)
