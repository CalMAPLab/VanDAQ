# VanDAQ Data Acquisition System Overview

This repository implements a mobile measurement lab pipeline: instrument data are ingested by hardware-specific acquirers, buffered through POSIX message queues, persisted to a relational schema, optionally bundled for offline submission, and surfaced through Dash-based dashboards.

## Data Flow
- **Acquirers (`acquirer/`)** read instruments (serial, network, LabJack, Phidget, simulators, GPS) using YAML configs in `acquirer/config/`. They parse records into dicts with keys such as `platform`, `instrument`, `parameter`, `unit`, `acquisition_type`, `sample_time`, `acquisition_time`, `instrument_time`, and either `value` or `string`. Alarms can be attached per-parameter. Measurements are pushed to a POSIX message queue (default `/dev-measurements`).
- **Collector (`collector/vandaq_collector.py`)** drains either the queue or `.sbm` submission files and batches inserts into PostgreSQL via SQLAlchemy. It maintains dimension caches (platform, instrument, parameter, unit, acquisition type, alarm metadata, time) and writes to fact tables for measurements and alarms. GPS coordinates are merged into a geolocation dimension. It also writes rolling submission files for offline transfer when queue-driven.
- **Submitter (`submitter/vandaq_submitter.py`)** monitors the submission directory and, when network/SSH reachability checks pass, SFTP-transfers new `.sbm` files to a stationary host and archives them locally.
- **Dash dashboards (`web/`)** provide live visualization, mapping, and alarms (e.g., `web/Dash_Dashboard.py`, `web/Dash_Mapper_FSM.py`). They query the database through helpers in `common/vandaq_2step_measurements_query.py` / `common/vandaq_measurements_query.py` to pivot measurements for display.
- **Administration (`vandaq_admin`)** starts/stops acquirers, collector, and submitter based on `vandaq_admin.yaml`, and can clear the measurement queue.

## Key Components
- **Acquirer base/types** (`acquirer/acquirers.py`): base `Acquirer` handles queues and alarm logic. Variants include `SerialStreamAcquirer`, `SerialPolledAcquirer`, NMEA GPS readers, network streaming receiver, simulators, and LabJack/Phidget readers. Each runs an infinite loop to parse instrument output into measurement dicts.
- **Standalone runner** (`acquirer/vandaq_acquirer.py`): loads a config, configures logging, builds the correct acquirer via `AquirerFactory`, and executes it.
- **Collector** (`collector/vandaq_collector.py`): configurable via `collector/vandaq_collector.yaml` (queue-driven) or `collector/vandaq_collector_submission.yaml` (file-driven). Supports batching by sample time second (`insert_batch_seconds`) and time-dimension caching.
- **Database schema** (`common/vandaq_schema.py`, `schema/` SQL dumps): dimensional model with tables for platform, instrument, parameter, unit, acquisition type, time, geolocation, and alarm metadata; fact tables `measurement` and `alarm`; helper view `measurement_alarm_view`.
- **Submission mover** (`submitter/vandaq_submitter.py` + `submitter/vandaq_submitter.yaml`): SSH/SFTP transfer loop with ping-based reachability guard and log rotation.
- **Senders** (`sender/`): scripts for pushing data from specialized sources (e.g., Vocus TOF) into the system over sockets.
- **Utilities** (`utils/tattle.py`): periodic SSH heartbeat to a central server.

## Configuration & Paths
- Acquirer configs: `acquirer/config/*.yaml` (instrument connection details, parsing formats, alarms, queues, logging).
- Collector config/logs: `collector/vandaq_collector.yaml` or `collector/vandaq_collector_submission.yaml`; logs in `collector/log/`.
- Submission directory: `collector/submission/` (live) and `collector/submission/submitted/` (archive).
- Submitter config: `submitter/vandaq_submitter.yaml`; logs in `submitter/log/`.
- Admin defaults: `vandaq_admin.yaml` sets component directories and which services auto-launch.

## Runtime Notes
- Message queue: POSIX MQ via `ipcqueue.posixmq`; defaults to `/dev-measurements` with configurable size limits.
- Alarms: per-parameter rules in acquirer configs add alarm entries to measurements; collector maps them into `alarm` fact rows with levels/types.
- Time handling: collector normalizes timestamps into a `time` dimension; `insert_batch_seconds` controls grouping to avoid partial-second splits.
- Logging: each component uses rotating file handlers; log locations are configured alongside configs.

## Typical Use
1. Define/enable instrument YAMLs in `acquirer/config/`.
2. Start the stack with `./vandaq_admin startup` (or targeted `start/stop` commands) to launch acquirers and collector; enable submitter if remote syncing is needed.
3. Verify data landing in PostgreSQL and, if applicable, in submission files.
4. Run Dash apps in `web/` to visualize measurements, maps, and alarms.
