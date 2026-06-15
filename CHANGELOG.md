# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Hygiene pass: untrack runtime artifacts that `.gitignore` already excludes (`acquirer/test_data/`, `filers/files/`, acquirer log placeholder); gitignore `.vscode/` (editor-specific debug config).
- Move pre-submitter `sender/` scripts and alternate dashboard variants to `archive/sender/` and `archive/web/`; remove duplicate `web/Dash_Mapper_FSM copy.py`.

### Added

- README layout corrections, day-file export ops (`filers/dayfile.py`), and VOCUS Windows/TofDaq bridge documentation.
- `requirements.txt` for runtime deps (data chain, dashboard, submitter, filers); `requirements-hardware.txt` for optional Phidget; `requirements-dev.txt` now includes runtime via `-r requirements.txt`. Declared dependencies in `pyproject.toml`.

## [1.1.0] - 2026-06-04

First public release on [CalMAPLab/VanDAQ](https://github.com/CalMAPLab/VanDAQ) `main`, combining field-hardening work from mobile deployments with documentation, automated testing, example-only tracked configuration, and gitignored local YAML overlays for deployment secrets.

### Added

#### Documentation ([PR #2](https://github.com/CalMAPLab/VanDAQ/pull/2))

- Central documentation hub at `doc/index.md` with sections for getting started, operations, guides, reference, and development.
- Reformatted `doc/overview.md` (readable paragraphs, measurement-dict table, architecture figure `doc/assets/VanDAQ_architecture.png`).
- **Operations:** `doc/operations/installation.md` (DAQ host setup), `doc/operations/network_configuration.md` (remote vs central topology, `.sbm` submission files, multi-van `submit_file_basename`, firewall notes, offline/pending-file behavior), `doc/operations/operation_and_troubleshooting.md` (day-to-day commands, logs, Apache reload).
- **Guides:** `doc/guides/map_tiles.md` (NorCal/Central California offline tiles via Planetiler + Docker `tileserver-gl` on the van; content migrated from `scripts/tiles/README.md` with a short pointer left in scripts), `doc/guides/adding_a_new_instrument.md` (YAML → acquirer → PostgreSQL → optional Dash wiring).
- **Reference:** `doc/reference/data_chain_configuration.md` (complete YAML reference for acquirer, collector, submitter, dashboard, and `vandaq_admin`, with placeholder examples only), `doc/reference/database_schema.md` with ER diagram (`doc/assets/database_schema.png`).
- **Development:** `doc/development/testing.md` (pytest, markers, CI artifacts).
- `CHANGELOG.md` and `CITATION.cff` for release citation and version history.

#### Testing and CI ([PR #1](https://github.com/CalMAPLab/VanDAQ/pull/1))

- Pytest unit suite under `tests/` (~40 cases) with `integration` and `hardware` markers; default CI runs `not integration` only.
- Coverage via `.coveragerc`, `Makefile` targets (`test`, `coverage`, `coverage-xml`), and `requirements-dev.txt` / `pyproject.toml` (`pythonpath` for component imports, `norecursedirs` excluding `env/`).
- `tests/conftest.py` mocks LabJack, Phidget, and optional `ipcqueue` so acquirer/collector code imports without hardware.
- Tests cover: record parsing and alarms, simulated waveforms, serial line buffering, acquirer parsing against production YAML fixtures, collector config/filename helpers, `Inserter` dimension cache and batch insert (SQLite fixtures), import smoke checks.
- GitHub Actions workflow `.github/workflows/test.yml` on push/PR (Python 3.10, terminal coverage report, `coverage.xml` artifact — no third-party coverage service).
- Legacy manual scripts moved from `web/tests/` to `archive/web_tests/` with README warnings about hardcoded DB URLs.

#### Dashboard and live map

- Offline basemap pipeline: Planetiler build scripts, Docker `tileserver-gl`, `deploy/tileserver/` config, dashboard `mapping.tile_server` wiring ([PR #1 on enterprise fork / merged as offline map tiles work]).
- Live map: Leaflet drive map, historic replay, configurable instrument queries, multiple shapefiles and community points, wind rose with vector mean, improved color scales and gap-fill requery for late-arriving data.
- Dashboard UX: light theme, compact instrument plot headers, clearer alarm styling on cards and plots, faster refresh (~5–7 s) with incremental caching.

#### Instruments and ingest

- Spider MAGIC PSD file ingest (`utils/spider_psd_ingest.py`) enqueueing spectrum data for dashboard display; `vandaq_admin` support for ingest process.
- Van deployment configs updated for Phidget voltage input, TSI 3789 CPC, and VOCUS.
- Acquirer improvements over the release lineage: generic NMEA (Airmar weather station), LabJack subclass, Phidget voltage support, instrument controls tab, optional suppression of engineering readouts on dashboard, exponent parsing fix, aggregated >1 Hz `None` guard (e.g. Ecophysics), per-team alarm thresholds, scalers on serial records.

#### Collector, database, and central aggregation

- PostgreSQL retention: `pg_cron` procedure `delete_old_records` and refreshed `schema/vandaq_schema_dump.sql`.
- Remote submission file basename convention `submit_van1_` (and documented multi-van naming on central host).
- Collector ingests newest submission files first on central replay.

#### Local configuration overlays

- `common/config_loader.py` merges optional gitignored `*.local.yaml` over tracked YAML at startup (collector, submitter, dashboard, acquirers, filers, `vandaq_admin`).
- Example overlay files: `collector/vandaq_collector.local.yaml.example`, `submitter/vandaq_submitter.local.yaml.example`, `web/DashPlay.local.yaml.example`; per-instrument `acquirer/config/<Instrument>.local.yaml` beside the tracked config.
- Unit tests for the config loader (`tests/unit/test_config_loader.py`) and updated collector helper tests.

#### Repository and licensing

- BSD 3-Clause `LICENSE`, `CONTRIBUTORS.md` (maintainer and author credits).
- Public GitHub home at `CalMAPLab/VanDAQ` (history consolidated from prior Berkeley Enterprise development).
- `va` symlink to `vandaq_admin`; admin launcher prefers venv Python.
- `.gitignore` entries for Python venv, Spider PSD runtime data, `*.local.yaml`, and `.env` patterns (PR #3); runtime secrets live in ignored local overlays, not in tracked YAML.

### Changed

- README documentation section points to `doc/index.md`; testing section points to `doc/development/testing.md`.
- Tracked YAML and Python defaults normalized to **example** values ([PR #3](https://github.com/CalMAPLab/VanDAQ/pull/3)): placeholder database URLs (`YOUR_PASSWORD`), example central hostnames, generic LAN tileserver address.
- `vandaq_admin`, acquirer, collector, submitter, filers, and Dash entrypoints load configuration through the shared overlay helper instead of raw `yaml.safe_load` only.
- `doc/operations/installation.md` documents the `.local.yaml` workflow.
- Collector aligned with current acquirer config paths on van1; `Inserter` wrapped so module import does not start the infinite loop (enables unit tests).
- Optimized historic map queries; shapefile layering fix so boundaries are not hidden under wind-rose layers.
- `vandaq_admin` third argument to start/stop/status a single module.

### Fixed

- Serial acquirer path handling on van1 collector deployments.
- Dashboard overnight slowdown caused by per-cycle module reload.
- Collector UTC handling in `get_time_from_submit_filename` (`timezone` name no longer shadows `datetime.timezone`).
- Collector alarm insert mapping (`message` column).
- Acquirer logging crash; instrument control fixes after van install.
- Map data-prep bug; empty geolocation query handling; dashboard alarm totals when no data present.
- Queue permission and command/reply queue exception handling.
- Various map pan/zoom and query-thread stability fixes in the Dash mapper lineage.

## [1.0.0] - 2025-11-17

Tagged on an earlier internal development line (`9296cd0`, message: “Establishing VanDAQ version 1.0.0”). That tag is **not** an ancestor of public `main`; functional work through the 2025–2026 campaign season (maps, controls, collector/submitter hardening, and van deployments) is summarized above under **1.1.0**.

Notable items on the pre-public lineage included:

- Dash 3.x mapper with finite-state historic replay and multi-instrument map tests.
- Wind rose and community/boundary shapefile layers on the live map.
- Instrument controls tab and remote command queues.
- Submitter logging implementation and collector submission-file rollover.
- Day-file export column for `data_impacted` alarm flag and performance-oriented DB views for queries without geolocations.

