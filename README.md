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

This Home Assistant custom integration provides a sophisticated real-time and cumulative energy cost tracking solution, ideal for monitoring electricity expenses related to fluctuating prices and varying energy consumption levels. It's specifically crafted to handle dynamic electricity prices such as those from [Nord Pool](https://www.home-assistant.io/integrations/nordpool/), [Amber](https://www.home-assistant.io/integrations/amberelectric/), [Tibber](https://www.home-assistant.io/integrations/tibber), ...

## Project status

This project is actively maintained. Release `v1.0.0` marks a stable, feature-complete baseline.

Key improvements since the early releases:

- cost sensors now attach directly to the source device (e.g. your heat pump or EV charger) instead of creating a separate "Dynamic Energy Cost" device
- automatic unit conversion for both energy sensors (Wh/MWh to kWh) and price sensors (currency/MWh and currency/Wh to currency/kWh)
- customizable sensor selection — choose which cost sensors to create during setup or later via options flow
- config flow and options flow editing were stabilized
- entity identity and migration behavior were improved
- power-based cost tracking was hardened and made more precise
- statistics/reset metadata was improved for interval sensors
- currency is automatically picked up from your Home Assistant settings
- orphaned devices from earlier versions are cleaned up automatically

## Quick start

- Use a dynamic electricity price sensor that already represents the final price you want to track.
- Prefer an energy (`kWh`) sensor whenever one is available.
- Use a power (`W`) sensor only as a fallback.
- If you need tariffs, standing charges, VAT, gas conversion, or other custom business logic, build that into a separate template sensor first and feed the final result into this integration.

## Features

- **Real-Time Cost Sensor (only Power Based):** Calculates energy costs in real-time based on current power usage in watts (W) and electricity prices.
- **15-Minute, Hourly, Daily, Weekly, Monthly and Yearly Cost (Energy and Power Based):** Automatically generates interval-based accumulated cost sensors for detailed energy expense tracking.
- **Sensor without reset interval (Energy and Power Based)** Similar to the above, but does not reset automatically. It resets only when the service `dynamic_energy_cost.reset_cost` is called. Making it perfect for calculating specific costs, such as the expenses for individual charging sessions of an electric car.
- **Customizable sensor selection:** Choose which cost sensors to create during setup. All sensors are selected by default, but you can deselect any you don't need. The selection can be changed later via the options flow.
- **Enhanced Sensor Attributes:** Energy Based Sensors include attributes for total energy used (kWh) and the average energy price, aiding in energy usage optimization during cheaper hours.
- **Statistics-friendly reset metadata:** Interval cost sensors expose `last_reset`, and resetting cost sensors now behave better with Home Assistant statistics consumers.

## Best Practices

Calculating energy cost from an energy (kWh) sensor is the preferred and recommended method. If an energy sensor is available, use it instead of a power sensor whenever possible.

- **Use an energy sensor whenever you can.** A cumulative kWh sensor is more accurate, behaves more like the Home Assistant Energy Dashboard, and is less sensitive to restarts or sparse updates.
- **Use a power sensor only as a fallback.** Power-based cost tracking integrates instantaneous W readings over time, so the final accuracy depends on how often the source sensor reports and how cleanly it reports changes.
- **If you only have a power sensor, it is still supported.** The integration includes safeguards for spikes, restarts, and low-load precision, but it remains an approximation compared with kWh-based tracking.

**Note:** It is important that only one type of sensor (either power or energy) is configured for this integration. Both cannot be used simultaneously.

## Scope

Dynamic Energy Cost is intentionally focused on turning a price sensor and a consumption sensor into cost sensors.

It is not intended to be a full contract or utility billing engine. In particular, these are better handled outside the integration with template sensors, helpers, or automations:

- standing charges
- tariff blending / VAT / fixed margins
- gas unit conversion (`m3` -> `kWh`)
- solar self-consumption or export deduction logic
- plan comparison against a different fixed-price contract

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

## Configure Sensors

When setting up the integration, you will go through two steps:

**Step 1 — Source sensors:**
- **Electricity Price Sensor:** Sensor that provides the current electricity price (for example Nordpool, Ember, ... fixed price, day/night).
- **Power/Energy Usage Sensor:** Power sensors must measure in Watts (W). Energy sensors can use kWh, Wh, or MWh (converted automatically). Prefer the energy sensor option when both are available.

**Step 2 — Sensor selection:**
- Choose which cost sensors to create. All sensors are selected by default.
- For power sensors, the Real Time Cost sensor is automatically included when any interval sensor is selected.
- You can change this selection later via Settings → Devices & Services → Configure.

### Recommended setup

Best option:

- electricity price sensor (`EUR/kWh`, `EUR/MWh`, or `EUR/Wh` — converted automatically)
- cumulative energy sensor (`kWh`, `Wh`, or `MWh` — converted automatically)

Fallback option:

- electricity price sensor (`EUR/kWh`, `EUR/MWh`, or `EUR/Wh`)
- power sensor (`W`)

The integration automatically detects the `unit_of_measurement` on both the price and energy sensors and converts to per-kWh internally. Any currency prefix is supported (EUR, SEK, USD, etc.).

The fallback works well for many setups, but it remains approximation-based because it integrates instantaneous power readings over time.

## Updating

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?repository=dynamic_energy_cost&owner=martinarva&category=Integration)

<details>
<summary><b> Update manually </b></summary>

To update the integration to a newer version:

1. Download the [latest release of Dynamic Energy Cost](https://github.com/martinarva/dynamic_energy_cost/releases/latest) and extract its contents. 
2. Go to your'e Home Assistant instance.
3. Make sure to make a back up first.  
  <a href="https://my.home-assistant.io/redirect/backup/" target="_blank" rel="noreferrer noopener"><img src="https://my.home-assistant.io/badges/backup.svg" alt="Open your Home Assistant instance and show an overview of your backups." /></a>  
4. Overwrite the `dynamic_energy_cost` folder into the `custom_components` directory located typically at `/config/custom_components/`.  
5. Reboot Home Assistant.  
  <a href="https://my.home-assistant.io/redirect/developer_call_service/?service=homeassistant%2Erestart" target="_blank" rel="noreferrer noopener"><img src="https://my.home-assistant.io/badges/developer_call_service.svg" alt="Open your Home Assistant instance and show your service developer tools with a specific action selected." /></a>

</details>

## Resetting the cost sensors

Dynamic Energy Cost provides a service `dynamic_energy_cost.reset_cost` which you can call to reset energy sensors to 0. You can call this service from the GUI (Developer tools -> Services) or use this in automations.

```yaml
service: dynamic_energy_cost.reset_cost
target:
  entity_id: sensor.your_sensor_entity_id
```

## Calibrating the cost sensors

Dynamic Energy Cost provides a service `dynamic_energy_cost.calibrate` which you can call to change the value of a given sensor. You can call this service from the GUI (Developer tools -> Actions) or use this in automations.

```yaml
action: dynamic_energy_cost.calibrate
target:
  entity_id: sensor.your_sensor_entity_id
data:
  value: "100"
```

## Prerequisites

- **Electricity Price Sensor:** A sensor that provides the current electricity price. Supported units: `currency/kWh`, `currency/MWh`, `currency/Wh` (converted automatically). Currency is taken from your Home Assistant settings.
- **Power Usage Sensor (optional):** A sensor that monitors power usage in Watts (W).
- **Energy Usage Sensor (optional):** A sensor that monitors energy consumption. Supported units: `kWh`, `Wh`, `MWh` (converted automatically).
- **Virtual Energy Usage Sensor (optional):** Use a virtual energy sensor such as e.g. [Powercalc](https://docs.powercalc.nl/).

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
