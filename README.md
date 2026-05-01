# speed-test-tui

Terminal-based internet speed test built with Python, `httpx`, and `rich`.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

For development:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Usage

Running `speed-test` without `--json` or `--run-once` starts an **interactive session**:

```bash
speed-test
```

When running in a terminal, the interactive prompt provides **inline command completion and a live suggestion toolbar** (powered by `prompt_toolkit`). In non-TTY environments or when `prompt_toolkit` is unavailable, it falls back to the standard prompt so scripted usage continues to work.

Session commands:

| Command | Description |
|---------|-------------|
| `/run` | Run a speed test with current settings |
| `/preset <name>` | Switch to a preset (cloudflare, ru-moscow) |
| `/presets` | List available presets |
| `/server` | Show current server URL |
| `/help` | Show help |
| `/quit`, `/q`, `/exit` | Exit the session |

Non-interactive modes:

```bash
# Run one test and exit
speed-test --run-once

# Output results as JSON and exit
speed-test --json

# Run against a custom compatible server
speed-test --server https://speed.cloudflare.com \
  --download-url 'https://speed.cloudflare.com/__down?bytes=25000000' \
  --upload-url 'https://speed.cloudflare.com/__up' --run-once

# Skip upload test
speed-test --run-once --no-upload

# Use fake engine for testing (no network)
speed-test --fake --run-once

# Run as a module
python -m speed_test_tui --fake --run-once

# Use the Russian Moscow preset (when Cloudflare is blocked)
speed-test --preset ru-moscow --run-once
```

## Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--server` | `-s` | `https://speed.cloudflare.com` | Base server URL for ping checks |
| `--download-url` | | Cloudflare `__down` endpoint | Download endpoint |
| `--upload-url` | | Cloudflare `__up` endpoint | Upload endpoint |
| `--no-upload` | | `False` | Skip upload test |
| `--duration` | `-d` | `10.0` | Test duration in seconds per phase |
| `--concurrency` | `-c` | `4` | Number of concurrent connections |
| `--json` | | `False` | Output results as JSON and exit |
| `--run-once` | | `False` | Run one test and exit |
| `--list-presets` | | `False` | List available presets and exit |
| `--preset` | | `cloudflare` | Speed-test server preset (cloudflare, ru-moscow) |
| `--fake` | | `False` | Use fake engine (no network) |

## Presets

| Preset | Server | Download URL | Upload URL |
|--------|--------|-------------|-------------|
| `cloudflare` | `https://speed.cloudflare.com` | `__down?bytes=25000000` | `__up` |
| `ru-moscow` | `http://speedtest.mosoblcom.ru:8080` | `/speedtest/random4000x4000.jpg` | `/speedtest/upload.php` |

Presets set the `--server`, `--download-url`, and `--upload-url` defaults. 
Explicit `--server`, `--download-url`, or `--upload-url` flags override the preset values.

Example:
```bash
# Use the Moscow preset
speed-test --preset ru-moscow

# Override just the server, keep Moscow download/upload URLs
speed-test --preset ru-moscow --server https://my-custom-server.example.com
```

## Development

```bash
# Install dev dependencies
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

# Run tests
python -m pytest

# Run tests with coverage
python -m pytest --cov=speed_test_tui --cov-report=term-missing
```

## License

MIT
