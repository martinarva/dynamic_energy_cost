"""Class representing a Dynamic Energy Costs constants."""

DOMAIN = "dynamic_energy_cost"
ELECTRICITY_PRICE_SENSOR = "electricity_price_sensor"
POWER_SENSOR = "power_sensor"
ENERGY_SENSOR = "energy_sensor"
SERVICE_RESET_COST = "reset_cost"
SERVICE_CALIBRATE = "calibrate"

QUARTERLY = "quarterly"
HOURLY = "hourly"
DAILY = "daily"
WEEKLY = "weekly"
MONTHLY = "monthly"
YEARLY = "yearly"
MANUAL = "manual"

SELECTED_SENSORS = "selected_sensors"
REAL_TIME = "real_time"

SENSOR_LABELS = {
    REAL_TIME: "Real Time Cost (current cost per hour)",
    QUARTERLY: "15-Minute Cost",
    HOURLY: "Hourly Cost",
    DAILY: "Daily Cost",
    WEEKLY: "Weekly Cost",
    MONTHLY: "Monthly Cost",
    YEARLY: "Yearly Cost",
    MANUAL: "Manual Cost (no automatic reset)",
}
