# Testing and CI

VanDAQ uses [pytest](https://docs.pytest.org/) with [pytest-cov](https://pytest-cov.readthedocs.io/) for coverage. The default suite runs without LabJack, Phidget, or live PostgreSQL.

## Setup

```bash
cd /home/vandaq/vandaq
python3 -m venv env
source env/bin/activate
pip install -r requirements-dev.txt
```

`requirements-dev.txt` installs pytest, pytest-cov, pytest-mock, and the Python packages needed to import acquirer and collector code under test.

## Run tests

From the repo root:

```bash
make test              # unit tests (excludes integration)
make coverage          # tests + terminal report + htmlcov/index.html
make coverage-xml      # tests + coverage.xml (CI artifact format)
```

Or directly:

```bash
pytest -m "not integration"
```

## What is tested

- Acquirer parsing, alarms, and NMEA handling (including production YAML configs under `acquirer/config/`)
- Serial line buffering with mocked `serial.Serial`
- Collector `Inserter` dimension cache and batch insert (in-memory SQLite via test fixtures)

Tests live under `tests/`. Shared fixtures and optional-hardware mocks are in `tests/conftest.py`.

## Test markers


| Marker        | Meaning                                                        |
| ------------- | -------------------------------------------------------------- |
| `integration` | Needs PostgreSQL or POSIX message queues; **excluded from CI** |
| `hardware`    | Needs serial, LabJack, or Phidget devices                      |


Run integration tests only on a host with those services:

```bash
pytest -m integration
```

Run hardware tests only when devices are connected:

```bash
pytest -m hardware
```

## Continuous integration

On push and pull request, `[.github/workflows/test.yml](../../.github/workflows/test.yml)` runs on Ubuntu with Python 3.10:

```bash
pytest -m "not integration" --cov --cov-report=term-missing --cov-report=xml
```

Download `coverage.xml` from the workflow run **Artifacts** (`coverage-report`).

## Related

- [README — repository layout](../../README.md#repository-layout)

