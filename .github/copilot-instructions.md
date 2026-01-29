# Copilot Instructions for ha_nationalgrid

## Project Overview

This is a **Home Assistant custom integration** for National Grid utility accounts. The repository is ~540KB with 79 files and ~1,400 lines of Python code in the integration. It's based on the `ludeeus/integration_blueprint` template.

**Key technologies:**
- **Language**: Python 3.13+ (required for Home Assistant 2025.2.4+)
- **Framework**: Home Assistant custom component
- **API Library**: `aionatgrid==0.4.0` (from https://github.com/ryanmorash/aionatgrid)
- **Distribution**: HACS (Home Assistant Community Store)
- **Linter/Formatter**: Ruff (version 0.14.14)
- **Testing**: pytest with pytest-homeassistant-custom-component

## Build & Validation Commands

### Essential Commands (Always Run These)

**IMPORTANT: Python 3.13+ is required.** If Python 3.12 or earlier is available, many commands will fail with dependency resolution errors because Home Assistant 2025.2.4+ requires Python >=3.13.0.

#### 1. Install Dependencies
```bash
python3 -m pip install -r requirements.txt
# OR use the helper script:
scripts/setup
```
**When to run**: First time setup, after any changes to requirements.txt, or after any dependency errors.

#### 2. Lint Code (REQUIRED before commit)
```bash
# Using script (recommended):
scripts/lint

# OR manually:
python3 -m ruff format .
python3 -m ruff check . --fix
```
**When to run**: Always run before committing code changes. The CI workflow will fail if linting fails.

**Expected output**: 
- `ruff format`: "X files left unchanged" or "X files reformatted"
- `ruff check`: "All checks passed!" or specific errors to fix

#### 3. Lint Check Only (CI validation)
```bash
python3 -m ruff check .
python3 -m ruff format . --check
```
**When to run**: To verify code passes CI checks without modifying files.

#### 4. Run Tests
```bash
pytest
# OR with coverage:
pytest --cov=custom_components.national_grid --cov-report=term-missing
```
**When to run**: After any code changes to verify functionality.

**Note**: Tests require `pytest-homeassistant-custom-component` which pulls in Home Assistant and many dependencies. Installation may take 2-3 minutes.

### Development Environment

#### Local Development with Home Assistant
```bash
scripts/develop
```
**What it does**:
1. Creates `config/` directory if it doesn't exist
2. Initializes Home Assistant configuration
3. Sets `PYTHONPATH` to include `custom_components/`
4. Starts Home Assistant on port 8123 in debug mode

**When to run**: To manually test the integration in a running Home Assistant instance.

**Requirements**: 
- Must have Python 3.13+
- Will create `config/` directory (gitignored except configuration.yaml)
- Home Assistant will be accessible at http://localhost:8123

#### DevContainer (VS Code)
The repository includes `.devcontainer.json` configured with:
- Python 3.13 container
- Port 8123 forwarded for Home Assistant
- Auto-runs `scripts/setup` on container creation
- Pre-configured VS Code extensions (ruff, python, pylance)

**To use**: Open in VS Code, click "Reopen in Container" when prompted.

## CI/CD Workflows

### Workflows Run on Every PR and Push to Main

#### 1. Lint Workflow (`.github/workflows/lint.yml`)
**Runs**: On push/PR to main
**Steps**:
1. Checkout code
2. Setup Python 3.13
3. Install requirements: `pip install -r requirements.txt`
4. Run `python3 -m ruff check .`
5. Run `python3 -m ruff format . --check`

**Failure causes**: 
- Formatting issues (run `scripts/lint` locally to fix)
- Linting errors (run `ruff check . --fix` or fix manually)

#### 2. Validate Workflow (`.github/workflows/validate.yml`)
**Runs**: On push/PR to main, daily at midnight, or manual dispatch
**Steps**:
1. **hassfest validation**: Home Assistant's official validator checks:
   - manifest.json structure and required fields
   - dependencies listed correctly
   - version format
   - Required files exist (strings.json, translations/, etc.)
2. **HACS validation**: Validates HACS compatibility:
   - hacs.json format
   - Repository structure
   - Integration category is "integration"
   - Currently ignores missing "brands" (brand images in home-assistant/brands repo)

**Failure causes**:
- Invalid manifest.json
- Missing required fields in hacs.json
- Incorrect integration structure
- Missing strings.json or translations

## Project Structure & Architecture

### Directory Layout
```
/
├── .github/
│   ├── workflows/          # CI workflows (lint.yml, validate.yml)
│   ├── ISSUE_TEMPLATE/     # GitHub issue templates
│   └── dependabot.yml      # Dependabot config (ignores homeassistant updates)
├── custom_components/
│   └── national_grid/      # Integration code (all Python files here)
│       ├── __init__.py     # Entry point, setup coordinator
│       ├── coordinator.py  # DataUpdateCoordinator, API calls
│       ├── config_flow.py  # UI configuration flow
│       ├── sensor.py       # Sensor entities (usage, cost)
│       ├── binary_sensor.py # Binary sensor entities (smart meter status)
│       ├── entity.py       # Base entity class
│       ├── const.py        # Constants (DOMAIN, units, etc.)
│       ├── data.py         # Type aliases
│       ├── statistics.py   # Import long-term statistics to HA recorder
│       ├── manifest.json   # Integration metadata (REQUIRED for HA)
│       ├── strings.json    # UI strings
│       └── translations/   # Localized strings
├── config/
│   └── configuration.yaml  # Development HA config (only file not gitignored)
├── tests/                  # pytest tests
├── scripts/
│   ├── setup              # Install dependencies
│   ├── lint               # Format and lint code
│   └── develop            # Run Home Assistant with integration loaded
├── requirements.txt       # Production dependencies
├── requirements_test.txt  # Test dependencies (pytest-homeassistant-custom-component)
├── .ruff.toml            # Ruff configuration (based on HA core)
├── pyproject.toml        # Python project config (pytest settings)
├── hacs.json             # HACS metadata
├── .devcontainer.json    # VS Code devcontainer configuration
└── .gitignore            # Ignores config/* except configuration.yaml
```

### Integration Architecture

**Standard Home Assistant custom component pattern:**

1. **Entry Setup** (`__init__.py`):
   - `async_setup_entry()`: Creates coordinator, sets up platforms
   - `async_unload_entry()`: Cleanup on removal
   - Update interval: 1 hour
   - Platforms: `sensor`, `binary_sensor`

2. **Data Coordinator** (`coordinator.py`):
   - `NationalGridDataUpdateCoordinator` extends `DataUpdateCoordinator`
   - Uses `aionatgrid.NationalGridClient` for API calls
   - Fetches: billing accounts, meters, usage, costs, AMI data, interval reads
   - Stores data in dataclasses: `MeterData`, `NationalGridCoordinatorData`
   - Exception handling: Translates `aionatgrid` exceptions to HA exceptions

3. **Configuration Flow** (`config_flow.py`):
   - Two-step flow: username/password → account selection
   - Supports reauthentication
   - Multi-account support via `CONF_SELECTED_ACCOUNTS`

4. **Entities** (`sensor.py`, `binary_sensor.py`):
   - All inherit from `NationalGridEntity` (which extends `CoordinatorEntity`)
   - Device registered per meter with device info
   - Sensors: Last Billing Usage, Last Billing Cost
   - Binary Sensors: Smart Meter status

5. **Statistics Import** (`statistics.py`):
   - Imports hourly/interval data to HA's recorder as external statistics
   - Enables Energy Dashboard integration
   - Converts therms → CCF for gas (1 therm = 1.038 CCF)

### Key Files & Configuration

**Integration Metadata** (`custom_components/national_grid/manifest.json`):
- Domain: `national_grid`
- Dependencies: `["recorder"]`
- Requirements: `["aionatgrid==0.4.0"]`
- Integration type: `hub`
- IoT class: `cloud_polling`
- Version: `0.1.0`
- Requires Home Assistant 2025.2.4+

**Linting Configuration** (`.ruff.toml`):
- Target: Python 3.13
- Based on Home Assistant core pyproject.toml
- Selects: `ALL` rules with specific ignores
- Special per-file ignores for tests/
- Black-compatible formatting
- Max complexity: 25

**Development Config** (`config/configuration.yaml`):
```yaml
default_config:
homeassistant:
  debug: true
logger:
  default: info
  logs:
    custom_components.national_grid: debug
```

## Common Issues & Solutions

### Python Version Errors
**Problem**: `ERROR: Could not find a version that satisfies the requirement homeassistant==2025.2.4`

**Cause**: Python version < 3.13

**Solution**: This project requires Python 3.13+. Use the devcontainer (which has Python 3.13) or install Python 3.13+ locally.

### Import Errors in Tests
**Problem**: `ModuleNotFoundError: No module named 'homeassistant'`

**Cause**: Home Assistant not installed

**Solution**: 
```bash
pip install -r requirements_test.txt
# This installs pytest-homeassistant-custom-component which includes Home Assistant
```

### Lint Failures in CI
**Problem**: CI lint workflow fails

**Solution**: Always run `scripts/lint` before committing:
```bash
scripts/lint
git add .
git commit -m "..."
```

### Hassfest Validation Failures
**Problem**: `validate.yml` workflow fails on hassfest step

**Common causes**:
- Modified manifest.json incorrectly
- Missing required fields
- Wrong dependency versions

**Solution**: Check manifest.json against Home Assistant's schema. Key fields:
- `domain`, `name`, `version`, `requirements`, `dependencies`
- `config_flow: true` required for UI configuration
- `integration_type: "hub"` required for multi-device integrations

## Code Style & Patterns

### Always Follow These Patterns

1. **Type Hints**: Use type hints throughout. Import types in `TYPE_CHECKING` block to avoid circular imports:
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
```

2. **Coordinator Pattern**: All entities inherit from `NationalGridEntity` which extends `CoordinatorEntity`
   - Access coordinator data: `self.coordinator.data`
   - Automatic updates when coordinator refreshes

3. **Runtime Data**: Config entry stores coordinator directly:
```python
entry.runtime_data = coordinator  # No wrapper dataclass
```

4. **Constants**: Define in `const.py`, import via `from .const import DOMAIN, _LOGGER`

5. **Unit Conversions**: Use helper `therms_to_ccf()` from `const.py` for gas conversions

6. **Error Handling**: Catch `aionatgrid` exceptions, translate to HA exceptions:
   - `InvalidAuthError` → `ConfigEntryAuthFailed`
   - Other errors → `UpdateFailed`

### Code Formatting Rules
- **Indentation**: 4 spaces
- **Line endings**: LF (\n)
- **Quotes**: Let ruff decide (usually double for strings)
- **Imports**: Organized by ruff (standard, third-party, local)
- **Comments**: Only when necessary to explain complex logic

## Quick Reference: Before Committing

1. **Run lint**: `scripts/lint` (or manually: `ruff format . && ruff check . --fix`)
2. **Check lint passes**: `ruff check . && ruff format . --check`
3. **Run tests**: `pytest` (if you have pytest-homeassistant-custom-component installed)
4. **Verify changes**: Check that only intended files are modified
5. **Commit**: Use clear commit messages

## Additional Resources

- **Home Assistant Developer Docs**: https://developers.home-assistant.io/
- **Integration Blueprint**: https://github.com/ludeeus/integration_blueprint
- **aionatgrid Library**: https://github.com/ryanmorash/aionatgrid
- **HACS**: https://hacs.xyz/
- **Ruff Documentation**: https://docs.astral.sh/ruff/
