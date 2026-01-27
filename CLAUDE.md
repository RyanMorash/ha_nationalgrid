# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Home Assistant custom integration for National Grid, based on the `ludeeus/integration_blueprint` template. It uses HACS for distribution and requires Home Assistant 2025.2.4+.

## Development Commands

```bash
# Install dependencies (run first time or after requirements.txt changes)
scripts/setup

# Start Home Assistant with the integration loaded (creates config/ dir if needed)
scripts/develop

# Format and lint code (uses ruff)
scripts/lint
```

The devcontainer is configured for VS Code with Python 3.13 and exposes Home Assistant on port 8123.

## Architecture

The integration follows the standard Home Assistant custom component pattern:

- **`__init__.py`**: Entry setup with `async_setup_entry`/`async_unload_entry`. Configures the coordinator with 1-hour update interval and forwards to platforms (sensor, binary_sensor, switch).

- **`api.py`**: `IntegrationBlueprintApiClient` class handles HTTP communication via aiohttp. Currently points to jsonplaceholder.typicode.com as placeholder. Custom exceptions: `IntegrationBlueprintApiClientError`, `IntegrationBlueprintApiClientCommunicationError`, `IntegrationBlueprintApiClientAuthenticationError`.

- **`coordinator.py`**: `BlueprintDataUpdateCoordinator` extends Home Assistant's `DataUpdateCoordinator` for centralized data polling. Translates API exceptions to HA-specific ones (`ConfigEntryAuthFailed`, `UpdateFailed`).

- **`config_flow.py`**: `BlueprintFlowHandler` implements UI configuration. Collects username/password, validates credentials by calling the API, uses slugified username as unique_id.

- **`entity.py`**: `IntegrationBlueprintEntity` base class extends `CoordinatorEntity`. Sets up device info and unique_id from config entry.

- **`data.py`**: `IntegrationBlueprintData` dataclass holds runtime data (client, coordinator, integration reference). `IntegrationBlueprintConfigEntry` type alias for typed config entries.

- **`const.py`**: Domain (`nationalgrid`), logger, and attribution string.

- **Platform files** (`sensor.py`, `binary_sensor.py`, `switch.py`): Each defines entity descriptions and entity classes inheriting from `IntegrationBlueprintEntity`.

## Key Patterns

- All entities inherit from `IntegrationBlueprintEntity` which handles coordinator binding and device registration
- Runtime data stored in `entry.runtime_data` as `IntegrationBlueprintData` dataclass
- API client passed through runtime_data, coordinator fetches via `client.async_get_data()`
- Uses `CoordinatorEntity` pattern for automatic state updates

## Code Style

- Uses ruff for formatting and linting
- Uses black-compatible formatting (via ruff)
- Type hints throughout with `TYPE_CHECKING` imports for circular dependency prevention
