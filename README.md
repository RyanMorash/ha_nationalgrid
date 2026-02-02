# National Grid Integration for Home Assistant

A custom [Home Assistant](https://www.home-assistant.io/) integration that provides energy usage, cost, and meter data from [National Grid](https://www.nationalgridus.com/) utility accounts. It uses the [aionatgrid](https://github.com/ryanmorash/aionatgrid) library to communicate with National Grid's API.

This integration polls your National Grid account once per hour and creates sensor and binary sensor entities for each meter linked to your account, giving you visibility into your electricity and gas billing data directly in Home Assistant.

## Features

- **Energy Usage Sensors**: Track your monthly billing usage and costs
- **Smart Meter Detection**: Identify which meters have AMI (Advanced Metering Infrastructure) capabilities
- **Long-Term Statistics**: Import historical energy data for use in the Energy Dashboard
- **Solar/Return Support**: Separate statistics for grid consumption and energy returned to the grid (for solar users)
- **Historical Data Import**: On first setup, imports up to 5 years of historical data
- **Force Refresh Service**: Manually trigger a full historical data refresh when needed

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance.
2. Go to **Integrations** and select the three-dot menu in the top right corner.
3. Select **Custom repositories**.
4. Add the URL `https://github.com/ryanmorash/ha_nationalgrid` with category **Integration**.
5. Find **National Grid** in the HACS integration list and click **Download**.
6. Restart Home Assistant.

### Manual Installation

1. Download the `custom_components/national_grid` folder from this repository.
2. Copy the `national_grid` folder into your Home Assistant `config/custom_components/` directory.
3. Restart Home Assistant.

## Configuration

Configuration is done entirely through the Home Assistant UI.

1. Go to **Settings > Devices & Services > Add Integration**.
2. Search for **National Grid**.
3. Enter your National Grid account **username** and **password**.
4. If your account has multiple billing accounts linked, select which accounts to monitor. If only one account is linked, it is selected automatically.

### Configuration Parameters

| Parameter | Description |
|-----------|-------------|
| Username  | Your National Grid online account email or username |
| Password  | Your National Grid online account password |
| Selected Accounts | Which linked billing accounts to monitor (shown only if multiple accounts exist) |

## Removal

1. Go to **Settings > Devices & Services**.
2. Find the **National Grid** integration entry.
3. Click the three-dot menu and select **Delete**.
4. Optionally, remove the `custom_components/national_grid` folder and restart Home Assistant.

## Entities

The integration creates the following entities for each meter on your account:

### Sensors

| Entity | Description | Unit | Device Class |
|--------|-------------|------|--------------|
| Last Billing Usage | Most recent monthly billing usage | kWh (electric) / CCF (gas) | Energy / Gas |
| Last Billing Cost | Most recent monthly billing cost | $ | Monetary |

### Binary Sensors

| Entity | Description | Category |
|--------|-------------|----------|
| Smart Meter | Whether the meter is an AMI smart meter | Diagnostic |

### Device Information

Each meter device includes detailed information:

| Field | Description |
|-------|-------------|
| Name | Fuel type and meter designation (e.g., "Electric Meter") |
| Model | Meter type (AMI Smart Meter, Smart Meter, or Standard Meter) |
| Serial Number | Meter number |
| Hardware Version | Service Point, Meter Point, and Premise numbers |
| Software Version | Device code, Region, and Customer type |
| Suggested Area | Derived from service address |

## Data Updates

The integration polls National Grid's API **every hour**. Each update fetches:

- Billing account information and meter details
- Energy usage records for the last 12 months
- Energy cost records for the current billing period
- AMI (smart meter) energy usage data for meters that support it
- Interval reads (15-minute granularity) for electric smart meters

### First Setup vs. Incremental Updates

**On first setup**, the integration imports full historical data:
- Up to 5 years of AMI hourly usage data
- Up to 5 years of interval read data (if available from the API)
- 15 months of billing usage data

**On incremental updates** (after first setup):
- AMI data: Last 48 hours only (prevents overlap with interval data)
- Interval data: Last 24 hours
- Billing data: Last 12 months

## Long-Term Statistics

The integration imports external statistics into Home Assistant's recorder on every update. These statistics can be used in the **Energy dashboard** and for long-term trend analysis.

### Electric Meters

| Statistic ID | Description | Unit | Notes |
|--------------|-------------|------|-------|
| `national_grid:{sp}_electric_hourly_usage` | Electric hourly AMI consumption | kWh | Energy consumed from grid |
| `national_grid:{sp}_electric_return_hourly_usage` | Electric hourly AMI return | kWh | Energy returned to grid (solar users only) |
| `national_grid:{sp}_electric_interval_usage` | Electric interval consumption | kWh | 15-minute data aggregated hourly |
| `national_grid:{sp}_electric_interval_return_usage` | Electric interval return | kWh | Energy returned (solar users only) |

### Gas Meters

| Statistic ID | Description | Unit |
|--------------|-------------|------|
| `national_grid:{sp}_gas_hourly_usage` | Gas hourly AMI usage | CCF |

`{sp}` is replaced with your meter's service point identifier.

### Energy Dashboard Setup

To add these statistics to the Energy dashboard:

1. Go to **Settings > Dashboards > Energy**
2. Under **Electricity grid**:
   - Add `national_grid:{sp}_electric_hourly_usage` or `national_grid:{sp}_electric_interval_usage` as "Grid consumption"
   - If you have solar, add `national_grid:{sp}_electric_return_hourly_usage` or `national_grid:{sp}_electric_interval_return_usage` as "Return to grid"
3. Under **Gas consumption**:
   - Add `national_grid:{sp}_gas_hourly_usage`

**Note**: Choose either hourly OR interval statistics for each type - don't add both to avoid double-counting.

## Services

### `national_grid.force_full_refresh`

Triggers a full historical data refresh, reimporting up to 5 years of data. Use this to:
- Recover from data gaps
- Repopulate statistics after database issues
- Force a complete resync of historical data

**Service Data:**

| Field | Required | Description |
|-------|----------|-------------|
| `entry_id` | No | Config entry ID of a specific integration to refresh. If not provided, all National Grid integrations are refreshed. |

**Example automation:**
```yaml
service: national_grid.force_full_refresh
data: {}
```

## Troubleshooting

### Missing Historical Data

If you notice gaps in your historical statistics:
1. Call the `national_grid.force_full_refresh` service
2. Wait for the refresh to complete (check logs for "Force full refresh completed")
3. Verify data in Developer Tools > Statistics

### Double Counting in Energy Dashboard

If energy values appear doubled:
- Ensure you're only using ONE statistic type per energy source (either hourly OR interval, not both)
- The integration automatically prevents overlap between AMI and interval data

### Logs

Enable debug logging for detailed information:

```yaml
logger:
  default: info
  logs:
    custom_components.national_grid: debug
```
