# Dynamic Energy Cost Integration for Home Assistant

This Home Assistant custom integration provides a sophisticated real-time and cumulative energy cost tracking solution, ideal for monitoring electricity expenses related to fluctuating prices and varying energy consumption levels. It's specifically crafted to handle dynamic electricity prices such as those from Nordpool.

## Features

- **Real-Time Cost Sensor (only Power Based):** Calculates energy costs in real-time based on current power usage in watts (W) and electricity prices.
- **Daily, Monhtly and Yearly Cost (Energy and Power Based):** Automatically generates daily, monthly, and yearly accumulations of costs, facilitating detailed and segmented analysis of energy expenses. These are based on actual energy usage in kilowatt-hours (kWh), providing precision aligned with the Home Assistant Energy Dashboard.
- **Enhanced Sensor Attributes:** Energy Based Sensors include attributes for total energy used (kWh) and the average energy price, aiding in energy usage optimization during cheaper hours.

## Best Practices

Calculating energy cost from an energy (kWh) sensor is the more precise and recommended method. If an energy sensor is available, it is advisable to use this option for accuracy comparable to the Home Assistant Energy Dashboard. If no kWh sensor is available, the integration can alternatively use a power (W) sensor.

**Note:** It is important that only one type of sensor (either power or energy) is configured for this integration. Both cannot be used simultaneously.

## Resetting the cost sensors

Dynamic Energy Cost provides a service dynamic_energy_cost.reset_cost which you can call to reset energy sensors to 0. You can call this service from the GUI (Developer tools -> Services) or use this in automations.

```yaml
service: dynamic_energy_cost.reset_cost
target:
  entity_id: sensor.your_sensor_entity_id
```


## Prerequisites

- **Electricity Price Sensor:** A sensor that provides the current electricity price in EUR/kWh.
- **Power Usage Sensor (optional):** A sensor that monitors power usage in Watts (W).
- **Energy Usage Sensor (optional):** A sensor that monitors energy consumption in kilowatt-hours (kWh).

## Installation

### Semi-Manual Installation with HACS
1. Go HACS integrations secction.
2. Click on the 3 dots in the top right corner.
3. Select "Custom repositories"
4. Add the URL (https://github.com/martinarva/dynamic_energy_cost) to the repository.
5. Select the integration category.
6. Click the "ADD" button.
7. Now you are able to download the integration


### Manual Installation

#### Download and Prepare:

1. Access the GitHub repository for this integration.
2. Download the ZIP file of the repository and extract its contents.
3. Copy the `dynamic_energy_cost` folder into the `custom_components` directory located typically at `/config/custom_components/` in your Home Assistant directory.

#### Restart Home Assistant:

- Restart Home Assistant to recognize the newly added custom component.

### Configuration via UI

#### Add Integration:

1. Navigate to Settings > Devices & Services.
2. Click Add Integration and search for "Dynamic Energy Cost".
3. Select the Dynamic Energy Cost integration to initiate setup.

#### Configure Sensors:

- Input the entity IDs for your:
  - **Electricity Price Sensor:** Sensor that provides the current electricity price.
  - **Power/Energy Usage Sensor:** Ensure the sensor measures in Watts (W) for power or kilowatt-hours (kWh) for energy.
- Submit to complete the integration setup.

## Updating

To update the integration to a newer version:

1. Access the GitHub repository for this integration.
2. Download the latest ZIP file of the repository and extract its contents.
3. Overwrite the `dynamic_energy_cost` folder into the `custom_components` directory located typically at `/config/custom_components/` in your Home Assistant directory.

## Support

For support, additional instructions, or to report issues, please visit the GitHub issues page associated with this repository.
Home Assitant Community  topic: https://community.home-assistant.io/t/dynamic-energy-cost/726931

