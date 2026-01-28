# National Grid Integration for Home Assistant

A custom [Home Assistant](https://www.home-assistant.io/) integration that provides energy usage, cost, and meter data from [National Grid](https://www.nationalgridus.com/) utility accounts. It uses the [aionatgrid](https://github.com/ryanmorash/aionatgrid) library to communicate with National Grid's API.

This integration polls your National Grid account once per hour and creates sensor and binary sensor entities for each meter linked to your account, giving you visibility into your electricity and gas billing data directly in Home Assistant.

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

## Data Updates

The integration polls National Grid's API **every hour**. Each update fetches:

- Billing account information and meter details
- Energy usage records for the last 12 months
- Energy cost records for the current billing period
- AMI (smart meter) energy usage data for meters that support it
- Interval reads (15-minute granularity) for electric smart meters

Historical usage and cost data are also imported as **long-term statistics** into Home Assistant's recorder, enabling the Energy dashboard and long-term trend analysis.
