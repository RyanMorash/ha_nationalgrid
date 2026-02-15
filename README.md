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

| Parameter         | Description                                                                      |
| ----------------- | -------------------------------------------------------------------------------- |
| Username          | Your National Grid online account email or username                              |
| Password          | Your National Grid online account password                                       |
| Selected Accounts | Which linked billing accounts to monitor (shown only if multiple accounts exist) |

## Removal

1. Go to **Settings > Devices & Services**.
2. Find the **National Grid** integration entry.
3. Click the three-dot menu and select **Delete**.
4. Optionally, remove the `custom_components/national_grid` folder and restart Home Assistant.

## Data Sources

The integration uses two different APIs that serve different purposes:

### Electric Hourly Usage (Recommended for Energy Dashboard)

- **Data Type**: Verified/validated hourly readings
- **History**: Up to 5 years
- **Delay**: ~2-day delay (API only returns data older than 2 days from midnight)
- **Statistics**: `national_grid:{sp}_electric_hourly_usage`, `national_grid:{sp}_electric_return_hourly_usage`

> **Note**: `{sp}` is your meter's service point identifier. For example: `national_grid:123456789_electric_hourly_usage`. You can find your service point number in the device info for your meter in Home Assistant.

**Use this for the Energy Dashboard** - it has years of historical data and is the authoritative source for your usage.

### Electric Interval Usage (Real-time, Last 2 Days Only)

- **Data Type**: Unverified/temporary 15-minute readings
- **History**: **Last 2 days only** (from midnight)
- **Delay**: Near real-time
- **Statistics**: `national_grid:{sp}_electric_interval_usage`, `national_grid:{sp}_electric_interval_return_usage`

This fills the gap between "now" and when Hourly data becomes available. The integration enforces a 2-day cutoff to ensure **no overlap** with Hourly data.

## Entities

The integration creates the following entities for each meter on your account:

### Sensors

| Entity             | Description                       | Unit                       | Device Class |
| ------------------ | --------------------------------- | -------------------------- | ------------ |
| Last Billing Usage | Most recent monthly billing usage | kWh (electric) / CCF (gas) | Energy / Gas |
| Last Billing Cost  | Most recent monthly billing cost  | $                          | Monetary     |

### Binary Sensors

| Entity      | Description                             | Category   |
| ----------- | --------------------------------------- | ---------- |
| Smart Meter | Whether the meter is an AMI smart meter | Diagnostic |

### Device Information

Each meter device includes detailed information:

| Field            | Description                                                  |
| ---------------- | ------------------------------------------------------------ |
| Name             | Fuel type and meter designation (e.g., "Electric Meter")     |
| Model            | Meter type (AMI Smart Meter, Smart Meter, or Standard Meter) |
| Serial Number    | Meter number                                                 |

## Data Updates

The integration refreshes data at the **18th minute of every hour**, but not all data is fetched every time — see [Update Schedule](#update-schedule) for details.

### First Setup

On first setup, the integration imports full historical data:

- Up to 5 years of AMI hourly usage data
- Up to 2 days worth of interval read data (if available from the API)
- 15 months of billing usage data

### Midnight Refresh (00:18)

A full data fetch including:

- Billing account information and meter details
- Energy usage records for the last 15 months
- Energy cost records for the current billing period
- AMI hourly usage data (last 5 days — catches newly available readings)
- Interval reads (last 2 days, cleared and reimported)

### Hourly Refresh (01:18 - 23:18)

A lightweight fetch of only:

- Interval reads (15-minute granularity) for electric smart meters

## Long-Term Statistics

### Electric Meters

| Statistic ID                                        | Source       | Description              | History     |
| --------------------------------------------------- | ------------ | ------------------------ | ----------- |
| `national_grid:{sp}_electric_hourly_usage`          | Hourly API   | Verified consumption     | **Years** ✓ |
| `national_grid:{sp}_electric_return_hourly_usage`   | Hourly API   | Verified return (solar)  | **Years** ✓ |
| `national_grid:{sp}_electric_interval_usage`        | Interval API | Real-time consumption    | Last 2 days |
| `national_grid:{sp}_electric_interval_return_usage` | Interval API | Real-time return (solar) | Last 2 days |

### Gas Meters

| Statistic ID                          | Source     | Description     | History     |
| ------------------------------------- | ---------- | --------------- | ----------- |
| `national_grid:{sp}_gas_hourly_usage` | Hourly API | Gas consumption | **Years** ✓ |

### No Overlap Design

The integration ensures **no overlap** between Hourly and Interval statistics by enforcing a 2-day cutoff:
- **Hourly Usage**: Contains verified data older than ~2 days (API enforced)
- **Interval Usage**: Contains only the last 2 days from midnight (integration enforced)

Because they cover different time periods, you can safely add **both** to the Energy Dashboard. However, for most users, **Hourly Usage alone is recommended** since it provides years of verified historical data. Use Interval only if you need real-time visibility into the most recent 2 days.

### Energy Dashboard Setup

To add these statistics to the Energy dashboard:

1. Go to **Settings > Dashboards > Energy**
2. Under **Electricity grid**:
   - **Recommended**: Add only `national_grid:{sp}_electric_hourly_usage` as "Grid consumption" (verified data, years of history)
   - **Optional**: Also add `national_grid:{sp}_electric_interval_usage` for real-time data (last 2 days only, no overlap)
   - If you have solar, add `national_grid:{sp}_electric_return_hourly_usage` (and optionally `national_grid:{sp}_electric_interval_return_usage`) as "Return to grid"
3. Under **Gas consumption**:
   - Add `national_grid:{sp}_gas_hourly_usage`


## Services

### `national_grid.force_full_refresh`

Triggers a full historical data refresh, reimporting up to 5 years of data. Use this to:

- Recover from data gaps
- Repopulate statistics after database issues
- Force a complete resync of historical data

**Service Data:**

| Field      | Required | Description                                                                                                          |
| ---------- | -------- | -------------------------------------------------------------------------------------------------------------------- |
| `entry_id` | No       | Config entry ID of a specific integration to refresh. If not provided, all National Grid integrations are refreshed. |

**Example automation:**

```yaml
service: national_grid.force_full_refresh
data: {}
```

## Update Schedule

The integration refreshes data at the **18th minute of every hour**:

| Time | Refresh Type | What's Fetched |
|------|--------------|----------------|
| **00:18** (midnight) | Full refresh | All data: billing, usage, costs, AMI hourly (last 5 days), interval (last 2 days) |
| **01:18 - 23:18** | Interval-only | Interval reads only (hourly data unchanged) |

### Why This Schedule?

- **Hourly Usage** data becomes available around midnight each day (with a ~2-day delay)
- **Interval** data is near real-time and updates frequently
- The midnight refresh fetches fresh AMI data from the API, and any newly available readings are imported incrementally (continuing from the last recorded statistic)
- Interval statistics are always cleared and reimported (last 2 days only) to ensure accuracy
- Hourly refreshes (01:18-23:18) only update interval stats to minimize API calls

## Troubleshooting

### Understanding Hourly vs Interval Statistics

**Important**: Hourly Usage and Interval Usage are **separate statistics** that don't overlap due to the 2-day cutoff.

- `national_grid:{sp}_electric_hourly_usage` - Verified data, years of history, ~2-day delay
- `national_grid:{sp}_electric_interval_usage` - Real-time data, **last 2 days only** (yesterday + today)

The integration automatically manages these to avoid overlap:
- At midnight, hourly stats are fully reimported (filling any gaps from newly available API data)
- Interval stats are always cleared and reimported (last 2 days only)
- This ensures Hourly has all historical data, and Interval only fills the recent gap

For the **Energy Dashboard**, **Hourly Usage is recommended** as the primary source for accurate historical tracking. You can optionally add Interval Usage for real-time monitoring of the most recent 2 days (there will be no double-counting).

### Missing Historical Data

If you notice gaps in your statistics:
1. Call `national_grid.force_full_refresh` service
2. Wait for completion (check logs for "Statistics import complete")
3. Note: The Hourly API has a ~2-day delay, so the most recent 2 days won't be available

**What Force Full Refresh does:**
- Reimports all available Hourly Usage data (fills gaps)
- Does NOT clear Interval Usage statistics (that happens automatically at midnight)

### Logs

Enable debug logging for detailed information:

```yaml
logger:
  default: info
  logs:
    custom_components.national_grid: debug
```