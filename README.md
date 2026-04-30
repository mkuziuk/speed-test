# speed-test-tui

Terminal-based internet speed test built with Python, `httpx`, and `rich`.

## Installation

```bash
pip install -e .
```

For development:

```bash
pip install -e ".[dev]"
```

## Usage

```bash
# Run a speed test against the default Cloudflare speed-test endpoints
speed-test

# Run against a custom compatible server
speed-test --server https://speed.cloudflare.com \
  --download-url 'https://speed.cloudflare.com/__down?bytes=25000000' \
  --upload-url 'https://speed.cloudflare.com/__up'

# Skip upload test
speed-test --no-upload

# Output results as JSON
speed-test --json

# Use fake engine for testing (no network)
speed-test --fake

# Run as a module
python -m speed_test_tui --fake
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
| `--json` | | `False` | Output results as JSON |
| `--fake` | | `False` | Use fake engine (no network) |
| `--debug` | | `False` | Enable debug output |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=speed_test_tui --cov-report=term-missing
```

## License

MIT
