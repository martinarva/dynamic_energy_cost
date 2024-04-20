# Dynamic Energy Cost Integration for Home Assistant

This Home Assistant custom integration provides a sophisticated real-time and cumulative energy cost tracking solution, ideal for monitoring electricity expenses related to fluctuating prices and varying energy consumption levels. It's specifically crafted to handle dynamic electricity prices such as those from Nordpool.

## Features

- **Real-Time Cost Sensor (Power Based):** Calculates energy costs in real-time based on current power usage in watts (W) and electricity prices. This sensor updates dynamically, making it especially useful with frequently changing electricity price sensors.
- **Utility Meters (Energy Based):** Automatically generates daily, monthly, and yearly accumulations of costs, facilitating detailed and segmented analysis of energy expenses. These are based on actual energy usage in kilowatt-hours (kWh), providing precision aligned with the Home Assistant Energy Dashboard.
- **Enhanced Sensor Attributes:** Sensors now include attributes for total energy used (kWh) and the average energy price, aiding in energy usage optimization during cheaper hours.

## Best Practices

Calculating energy cost from an energy (kWh) sensor is the more precise and recommended method. If an energy sensor is available, it is advisable to use this option for accuracy comparable to the Home Assistant Energy Dashboard. If no kWh sensor is available, the integration can alternatively use a power (W) sensor.

**Note:** It is important that only one type of sensor (either power or energy) is configured for this integration. Both cannot be used simultaneously.

## Prerequisites

- **Electricity Price Sensor:** A sensor that provides the current electricity price in EUR/kWh.
- **Power Usage Sensor (optional):** A sensor that monitors power usage in Watts (W).
- **Energy Usage Sensor (optional):** A sensor that monitors energy consumption in kilowatt-hours (kWh).

## Installation

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
