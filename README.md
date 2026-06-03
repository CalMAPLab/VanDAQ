# VanDAQ

VanDAQ is an open-source scientific data-acquisition system for mobile or fixed platforms carrying multiple instruments. It normalizes heterogeneous instrument outputs, writes them to PostgreSQL, packages submissions for central aggregation, and offers Dash-based diagnostic dashboards plus alarm handling and control.

## Components

- **Acquirer**: per-instrument readers that parse incoming data, apply alarms, and push measurement dicts into a POSIX message queue.
- **Collector**: ingests queued or file-based measurements, batches inserts into PostgreSQL, and (on remote platforms) rolls submission files for transfer.
- **Submitter**: ships submission files from remote platforms to the central server over SSH/SFTP.
- **Dashboards**: Plotly Dash web app for live diagnostics, alarms, maps, and instrument controls.
- **Filers**: scripts to export database data into analysis-ready text files.
- **vandaq_admin**: CLI utility to manage processes and configs.

## Documentation

- [Overview](doc/overview.md): architecture, theory of operation, and core processes.
- [Data chain configuration](doc/data_chain_configuration.md): YAML keys for acquirer, collector, submitter, dashboards, and admin tools.
- [Network configuration](doc/network_configuration.md): network paths and connectivity for remote vs. central deployments.
- [Operation and troubleshooting](doc/operation_and_troubleshooting.md): runtime guidance and common fixes.
- [Concise notes](doc/concise_notes.md): quick reminders and tips.
- Assets used by the docs are in `doc/assets/`.

## Repository layout

- `acquirer/`: instrument readers and configs.
- `collector/`: database inserter and submission file handling.
- `submitter/`: transfer of submission files to central servers.
- `web/`: Dash application definitions.
- `schema/`: database schema definitions.
- `vandaq_admin/`: admin CLI code and configs.
- `filers/`, `utils/`, `common/`, `va/`: shared helpers and data export tooling.
- `doc/`: documentation listed above.
- `tests/`: pytest unit tests.
- `archive/web_tests/`: retired manual scripts formerly under `web/tests/`.

## Testing

Tests use [pytest](https://docs.pytest.org/) with coverage via [pytest-cov](https://pytest-cov.readthedocs.io/). Hardware SDKs (LabJack, Phidget) are not required for the default suite.

### Setup

```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements-dev.txt
```

### Run tests

```bash
make test              # unit tests (excludes integration)
make coverage          # tests + terminal report + htmlcov/index.html
make coverage-xml      # tests + coverage.xml (same format CI uploads)
```

Or directly:

```bash
pytest -m "not integration"
```

### What is tested

- Acquirer parsing, alarms, and NMEA handling (production YAML configs)
- Serial line buffering with mocked `serial.Serial`
- Collector `Inserter` dimension cache and batch insert (in-memory SQLite)

### Test markers

- `integration` — needs PostgreSQL or POSIX message queues; skipped in CI
- `hardware` — needs serial, LabJack, or Phidget devices

Run integration tests locally only when those services are available:

```bash
pytest -m integration
```

### Continuous integration

On push and pull request, [`.github/workflows/test.yml`](.github/workflows/test.yml) runs the unit test suite on Ubuntu with Python 3.10. Download `coverage.xml` from the workflow run **Artifacts** (`coverage-report`).

## License

Licensed under the BSD 3-Clause License (see `LICENSE`).

## Contributing

Please open issues or pull requests with fixes and improvements; see `CONTRIBUTORS.md` for acknowledgements.
