<div align="center">
  <br>
  <img src="docs/source/img/DynamicEnergyCost_Icon100.png">
  <h1>Dynamic Energy Cost</h1>
  <strong>HACS integration for Home Assistant</strong>
</div>
<a href="https://gitlocalize.com/repo/10085?utm_source=badge"> <img src="https://gitlocalize.com/repo/10085/whole_project/badge.svg" /> </a>
<a href="https://github.com/martinarva/dynamic_energy_cost/releases/latest">
    <img alt="GitHub release (latest by date)" src="https://img.shields.io/github/v/release/martinarva/dynamic_energy_cost">
  </a>
<a style="text-decoration:none" href="https://github.com/martinarva/dynamic_energy_cost/blob/main/LICENSE">
    <img alt="GitHub" src="https://img.shields.io/github/license/martinarva/dynamic_energy_cost">
  </a>
<p align="center">
    <img src="https://skills.syvixor.com/api/icons?i=github,homeassistant,hacs,python,gitlocalize" />
  </a>
</p>

This Home Assistant custom integration provides a sophisticated real-time and cumulative energy cost tracking solution, ideal for monitoring electricity expenses related to fluctuating prices and varying energy consumption levels. It's specifically crafted to handle dynamic electricity prices such as those from [Nord Pool](https://www.home-assistant.io/integrations/nordpool/), [Amber](https://www.home-assistant.io/integrations/amberelectric/), ...

## Features

- **Real-Time Cost Sensor (only Power Based):** Calculates energy costs in real-time based on current power usage in watts (W) and electricity prices.
- **Hourly, Daily, Weekly, Monthly and Yearly Cost (Energy and Power Based):** Automatically generates daily, monthly, and yearly accumulations of costs, facilitating detailed and segmented analysis of energy expenses. These are based on actual energy usage in kilowatt-hours (kWh), providing precision aligned with the Home Assistant Energy Dashboard.
- **Sensor without reset interval (Energy and Power Based)** Similar to the above, but does not reset automatically. It resets only when the service `dynamic_energy_cost.reset_cost` is called. Making it perfect for calculating specific costs, such as the expenses for individual charging sessions of an electric car.
- **Enhanced Sensor Attributes:** Energy Based Sensors include attributes for total energy used (kWh) and the average energy price, aiding in energy usage optimization during cheaper hours.

## Best Practices

Calculating energy cost from an energy (kWh) sensor is the more precise and recommended method. If an energy sensor is available, it is advisable to use this option for accuracy comparable to the Home Assistant Energy Dashboard. If no kWh sensor is available, the integration can alternatively use a power (W) sensor.

**Note:** It is important that only one type of sensor (either power or energy) is configured for this integration. Both cannot be used simultaneously.

## Installation

### Install using HACS (recommended)
If you do not have HACS installed yet visit https://hacs.xyz for installation instructions.

To add the this repository to HACS in your Home Assistant instance, use this My button:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?repository=dynamic_energy_cost&owner=martinarva&category=Integration)

After installation, please restart Home Assistant. To add Dynamic Energy Cost to your Home Assistant instance, use this My button:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=dynamic_energy_cost)

<details>
<summary><b><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24"><path fill="currentColor" d="m13.75 10.19l.63.13l4.17 2.08c.7.23 1.16.92 1.1 1.66v.26l-.9 6.12c-.06.43-.25.83-.6 1.11c-.31.3-.72.45-1.15.45h-6.88c-.49 0-.94-.18-1.27-.53L2.86 15.5l.9-1c.24-.25.62-.39.98-.37h.29L9 15V4.5a2 2 0 0 1 2-2a2 2 0 0 1 2 2v5.69z"></path></svg> Manual configuration steps</b></summary>

### Semi-Manual Installation with HACS

1. Go HACS integrations section.
2. Click on the 3 dots in the top right corner.
3. Select "Custom repositories"
4. Add the URL (https://github.com/martinarva/dynamic_energy_cost) to the repository.
5. Select the integration category.
6. Click the "ADD" button.
7. Now you are able to download the integration

### Manual Installation

1. Access the GitHub repository for this integration.
2. Download the ZIP file of the repository and extract its contents.
3. Copy the `dynamic_energy_cost` folder into the `custom_components` directory located typically at `/config/custom_components/` in your Home Assistant directory.

### Restart Home Assistant

- Restart Home Assistant to recognize the newly added custom component.

### Add Integration

1. Navigate to Settings > Devices & Services.
2. Click Add Integration and search for "Dynamic Energy Cost".
3. Select the Dynamic Energy Cost integration to initiate setup.

</details>

## Configure Sensors

When setting up the integration, you will be prompted to provide the following:

- Input the entity IDs
  - **Electricity Price Sensor:** Sensor that provides the current electricity price (for example Nordpool, Ember, ... fixed price, day/night).
  - **Power/Energy Usage Sensor:** Ensure the sensor measures in Watts (W) for power or kilowatt-hours (kWh) for energy.
- Submit to complete the integration setup.

## Updating

To update the integration to a newer version:

1. Access the GitHub repository for this integration.
2. Download the latest ZIP file of the repository and extract its contents.
3. Overwrite the `dynamic_energy_cost` folder into the `custom_components` directory located typically at `/config/custom_components/` in your Home Assistant directory.

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

- **Electricity Price Sensor:** A sensor that provides the current electricity price in EUR/kWh.
- **Power Usage Sensor (optional):** A sensor that monitors power usage in Watts (W).
- **Energy Usage Sensor (optional):** A sensor that monitors energy consumption in kilowatt-hours (kWh).
- **Virtual Energy Usage Sensor (optional):** Use a virtual energy sensor such as e.g. [Powercalc](https://docs.powercalc.nl/).

## Contribute

If you want, you can help with the translation via [GitLocalize](https://gitlocalize.com/repo/10085).

## Support

For support, additional instructions visit Home Assitant Community  forum topic: [Dynamic Energy Cost](https://community.home-assistant.io/t/dynamic-energy-cost/726931)  
To report issues, please visit the [GitHub issues page associated with this repository.](https://github.com/martinarva/dynamic_energy_cost/issues)
