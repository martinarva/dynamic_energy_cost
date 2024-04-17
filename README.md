# Dynamic Energy Cost Integration for Home Assistant

This Home Assistant custom integration provides a real-time and cumulative energy cost tracking solution, ideal for monitoring electricity expenses as they relate to fluctuating prices and power consumption. It's specifically designed to work with frequently updating electricity prices, such as those provided by Nordpool.

## Features

- **Real-Time Cost Sensor**: Calculates energy costs in real-time, based on current power usage and electricity prices. This feature is particularly useful with electricity price sensors that update frequently.
- **Cumulative Cost Sensor**: Accumulates the total cost over time, maintaining a running total even through Home Assistant restarts.
- **Utility Meters**: Automatically generates daily, monthly, and yearly accumulations of costs, allowing for detailed and segmented analysis of energy expenses.

## Prerequisites

Before installing, ensure you have a functional Home Assistant setup on a suitable device like a Raspberry Pi or within a Docker container if running on other hardware.

## Installation

### Manual Installation

1. **Download and Prepare**:
   - Access the GitHub repository for this integration.
   - Download the ZIP file of the repository and extract its contents.
   - Copy the `dynamic_energy_cost` folder into the `custom_components` directory located typically at `/config/custom_components/` in your Home Assistant directory.

2. **Restart Home Assistant**:
   - Restart Home Assistant to recognize the newly added custom component.

### Configuration via UI

1. **Add Integration**:
   - Navigate to **Settings** > **Devices & Services**.
   - Click **Add Integration** and search for "Dynamic Energy Cost".
   - Select the Dynamic Energy Cost integration to initiate setup.

2. **Configure Sensors**:
   - Input the entity IDs for your:
     - **Electricity Price Sensor**: Sensor that provides the current electricity price.
     - **Power Usage Sensor**: Sensor that monitors the power usage in watts.
   - Submit to complete the integration setup.

## Support

For support, additional instructions, or to report issues, please visit the GitHub issues page associated with this repository.
