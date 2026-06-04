# VanDAQ Data Chain Process Configuration Manual

Each process in the VanDAQ data chain is configured via a YAML file of key/value pairs. Installing and operating VanDAQ is largely a matter of editing these files.

Processes covered in this manual:

- **acquirer**
- **collector**
- **submitter**
- **dashboard** (`web/DashPlay.yaml`)
- **vandaq_admin** (CLI process manager)

The sections below list the keys each process expects.

## Acquirer Configuration

VanDAQ runs one **acquirer** process per instrument. Each acquirer is configured by a YAML file in `/home/vandaq/vandaq/acquirer/config/`. On startup, `vandaq_admin` runs `vandaq_acquirer.py` once per `*.yaml` in that directory, passing the config file path on the command line.

Each config sets platform and instrument names, connection and parsing rules, POSIX queues for measurements (and optional command/response queues), optional alarms, and logging. Keys marked **required** must be present for that acquirer `type`; others are optional.

For a full integration walkthrough (startup, verification, dashboard), see [Adding a new instrument](../guides/adding_a_new_instrument.md).

### Common keys (all acquirer types)

- `platform` **required**: platform name (e.g. vehicle ID).
- `instrument` **required**: instrument identifier (unique on this host).
- `type` **required**: acquirer class — `simpleSerial`, `serialPolled`, `serial_nmea_GPS`, `serial_nmea`, `networkStreaming`, `simulated`, `simulated_GPS`, `LabJack`, `Phidget`.
- `queue` **required**: POSIX message queue for measurements.
  - `name` (e.g. `/dev-measurements`)
  - `max_msg_size`, `max_msgs`
- `command_queue` / `response_queue`: optional queues for instrument commands and replies.
  - `name`, `max_msg_size`, `max_msgs`; `response_header` filters replies onto `response_queue`.
- `measurement_delay_secs`: optional latency offset applied to `sample_time`.
- `verbose`: optional; values above zero print queued messages.
- `alarms`: optional per-parameter rules (`value_<`, `value_>`, `value_=`, `value_!=`, `substr_is`) that attach alarm metadata to measurements.
- `logs` **required**: `log_dir`, `log_file`, `log_level`, `logger_name`.

### Alarm rules

Define alarms under an `alarms` block keyed by parameter name. Each rule is a one-key map using these operators (supported in `acquirers.py`):

- `value_<`: trigger when `value` is less than threshold
- `value_>`: trigger when `value` exceeds threshold
- `value_=`: trigger when `value` equals threshold
- `value_!=`: trigger when `value` differs from threshold
- `substr_is`: for string fields, compare a substring (`substr_begin`, `substr_end`, `value`)

Each operator maps to an object:

```yaml
alarms:
  CO:
    - value_<:
        value: 0
        alarm_level: alarm          # string; matches dim table values
        alarm_type: underrange      # string; matches dim table values
        alarm_message: "CO below zero"
        impacts_data: true          ## optional; defaults true
  Status:
    - substr_is:
        substr_begin: 0
        substr_end: 3
        value: "ERR"
        alarm_level: warning
        alarm_type: status_flag
        alarm_message: "Instrument reported ERR"
        impacts_data: false
```

Example configs like `acquirer/config/Aeris_CH4_C2H6.yaml` show multiple rules per parameter; the collector records triggered alarms in the `alarm` fact table with links to the measurement.

### SerialStreamAcquirer (`type: simpleSerial`)

Continuous serial stream parsed into delimited items.

- `connection: serial`
- `serial`: `device`, `baud`
- `stream`:
  - `line_delimiter`: defaults to newline if omitted.
  - `item_delimiter`
  - `items`: comma-separated list; use `x` to skip positions. May include `inst_datetime`, `inst_date`, `inst_time`.
  - `formats`: comma-separated list matching `items` (`f` float, `s`/`h` string, or datetime format strings for instrument time fields).
  - `units`: comma-separated list matching `items`
  - `acqTypes`: comma-separated list matching `items`
  - `scalers`: optional comma-separated list (defaults to `1`); applied to float items.
  - `aggregate_seconds` / `aggregate_items`: optional aggregation window (seconds) and per-item aggregation (`mean`, `min`, `max`, `first`, `last`) instead of per-line emission.
  - `cycle_time`: optional sleep between loops.
- `init`: optional map of strings sent once after opening the port.
- `response_header`: optional prefix used to route instrument responses to `response_queue`.

### SerialPolledAcquirer (`type: serialPolled`)

Poll/response over serial at `data_freq_secs`.

- Inherits SerialStream requirements plus:
- `data_freq_secs`: polling interval.
- `poll`: map of poll definitions keyed arbitrarily; each poll entry:
  - `request_string`: bytes written to the port.
  - `response_len_min` / `response_len_max` (optional): expected byte counts for timeout handling.
  - `item_delimiter`: delimiter for response parsing.
  - `items`, `formats`, `units`, `acqTypes`, optional `scalers`: same pattern as SerialStream.
  - `key_delimiter`: if present, treat response as key/value pairs and extract values.
  - `trim_response_begin` / `trim_response_end`: slice response before parsing.
- `wait_for_response_secs`: optional delay after sending a command before reading a response.

### SerialNmeaGPSAcquirer (`type: serial_nmea_GPS`)

Lightweight NMEA GPS reader for latitude/longitude/speed/direction.

- `connection: serial`
- `serial`: `device`, `baud`
- `measurement_delay_secs`: optional
- No `stream` block is required; the acquirer decodes NMEA RMC sentences directly.

### SerialNmeaAcquirer (`type: serial_nmea`)

General NMEA sentence decoder configured per sentence type.

- `connection: serial`
- `serial`: `device`, `baud`
- `data`:
  - `sentence_delimiter` (optional, default newline)
  - `sentence_types`: map keyed by NMEA sentence type (e.g. `MWV`, `GGA`, `MDA`); each contains fields:
    - `<field_name>`:
      - `parameter`, `unit`, `format` (`f` float or `s` string), `acqType`
      - `scaler` optional for numeric scaling
- `measurement_delay_secs`: optional

### NetworkStreamingAcquirer (`type: networkStreaming`)

Receives pickled dictionaries over ZeroMQ PULL.

- `connection: network`
- `network`: `address` (bind host), `port`
- `dictionaries`: comma-separated list of dict keys expected in the incoming message.
- For each dictionary name listed:
  - Either `keys`: comma-separated indices to pull from the dict (converted to strings), **or** `items`: comma-separated dict keys.
  - `formats`, `units`, `acqTypes`: comma-separated lists aligned to `items`.
  - Optional `wholeDict` block: `parameter`, `unit`, `acqType` to store the entire dict as a string.
- `measurement_delay_secs`: optional

### SimulatedAcquirer (`type: simulated`)

Generates synthetic signals for testing.

- `stream`: defines output layout
  - `item_delimiter`
  - `items`, `formats`, `units`, `acqTypes` (like SerialStream)
- `simulate`:
  - `cycle_secs`: emission interval
  - For each parameter named in `stream.items`: `signal` (`sine`, `triangle`, `sawtooth`, `square`, `random`), `period`, `min`, `max`

### SimulatedGPSAcquirer (`type: simulated_GPS`)

Replays lat/lon pairs from a CSV file.

- `datafile`: path to CSV with `latitude` and `longitude` columns
- `cycletime`: seconds between samples
- `measurement_delay_secs`: optional

### LabJackAcquirer (`type: LabJack`)

Reads analog/digital channels via LabJack LJM.

- `device_type`, `connection_type`, `identifier`: device selectors for `ljm.openS`
- `data_freq_secs`: output cadence (seconds)
- `Parameters`: list of parameter definitions; each item is a single-key map:
  - `<param_name>`:
    - `signal_type`: `Analog` or `Digital`
    - `channel_name`: LJM channel name (e.g. `AIN0`, `FIO0`)
    - `unit`, `aquisition_type` (spelling matches existing configs)
    - Analog options: `preamp_gain`, `v_offset`, `v_per_unit`, `range`, `negative_channel`
    - Aggregation (optional for analog): `aggregate` (`mean` / `max` / `min`) and `aggregate_hz`
- `measurement_delay_secs`: optional

### PhidgetAcquirer (`type: Phidget`)

Reads analog/digital channels from a Phidget hub.

- `identifier`: device serial
- `data_freq_secs`: output cadence
- `Parameters`: list of parameter definitions; each item is a single-key map:
  - `<param_name>`:
    - `signal_type`: `Analog` or `Digital`
    - `channel_name`: hub port
    - For analog: `v_offset`, `v_per_unit`, optional `aggregate` and `aggregate_hz`
    - `unit`, `aquisition_type`
- `measurement_delay_secs`: optional

### Example: serial stream skeleton

Incoming serial lines matching this config could look like:

```
2024-08-14 12:00:00,21.3,1013.2
2024-08-14 12:00:01,21.4,1013.3
```

```yaml
platform: van1
instrument: ExampleSensor
type: simpleSerial
queue:
  name: "/dev-measurements"
  max_msg_size: 8000
  max_msgs: 50
connection: serial
serial:
  device: "/dev/ttyUSB0"
  baud: 19200
stream:
  line_delimiter: "\r\n"
  item_delimiter: ","
  items: "inst_datetime,T,P"
  formats: "%Y-%m-%d %H:%M:%S,f,f"
  units: "datetime,deg_c,mbar"
  acqTypes: "inst_datetime,measurement_calibrated,measurement_calibrated"
logs:
  log_dir: "/home/vandaq/vandaq/acquirer/log"
  log_file: "acquirer_ExampleSensor.log"
  log_level: "INFO"
  logger_name: "ExampleSensor"
```

## Collector Configuration

The collector inserts measurements into the database and optionally rolls them into submission bundles for the submitter. Presence of a `queue` block means the collector reads live messages from a POSIX MQ; otherwise it watches a submission directory for `.sbm` files produced elsewhere. Example configs live in `collector/vandaq_collector.yaml` (queue mode) and `collector/vandaq_collector_submission.yaml` (file mode).

### Common keys

- `connect_string` **required**: SQLAlchemy/PostgreSQL URL used by the collector to write to the database.
- `insert_batch_seconds`: optional; defaults to `1`. Groups records that share a `sample_time` second into the same insert batch.
- `cache_time_seconds`: optional; defaults to `3600`. Size (in seconds) of the time-dimension cache window around incoming `sample_time` values.
- `logs` **required**: logger config with `log_dir`, `log_file`, `log_level`, `logger_name`.

### Queue-driven collection (`queue` present)

- `queue` **required**: POSIX MQ to read from; `name`, `max_msg_size`, and `max_msgs` must match (or exceed) the acquirer’s queue settings.
- `queued_recs_to_batch`: optional; defaults to `1000`. Number of queue messages pulled before inserting a batch into the database and rotating submission files.
- `submissions`: controls on-disk bundles for the submitter (even while reading from a queue).
  - `submit_file_dir` **required**: output directory for submission files.
  - `submit_file_basename` **required**: prefix for each submission filename; the collector appends the roll time.
  - `submit_file_minutes` **required**: minutes between file rotations.
  - `submit_file_timezone`: optional; timezone used when stamping filenames.
  - `submit_file_tz_abbr`: optional; abbreviation appended to filenames (e.g. `PST`).

Example (queue mode):

```yaml
queue:
  name: "/dev-measurements"
  max_msg_size: 8000
  max_msgs: 50
connect_string: "postgresql://vandaq:YOUR_PASSWORD@localhost:5432/vandaq-test"
insert_batch_seconds: 1
cache_time_seconds: 3600
queued_recs_to_batch: 1000
logs:
  log_dir: "/home/vandaq/vandaq/collector/log"
  log_file: "collector.log"
  log_level: "INFO"
  logger_name: "collector"
submissions:
  submit_file_dir: "/home/vandaq/vandaq/collector/submission"
  submit_file_basename: "submit_van1_"
  submit_file_minutes: 1
  submit_file_timezone: "America/Los_Angeles"
  submit_file_tz_abbr: "PST"
```

### Submission-file collection (no `queue` block)

Uses prewritten submission files instead of a live queue.

- `submissions` **required**:
  - `submit_file_dir`: directory to scan for `.sbm` files.
  - `submitted_file_dir`: where processed files are moved; failures go to a `rejected/` subfolder.
  - `submit_file_pattern`: glob used to find pending submission files (e.g., `submit_*.sbm`).
  - `submit_file_timezone`: optional; timezone used when parsing timestamps embedded in submission filenames.

## Submitter Configuration

The submitter runs on **remote** platforms. It watches the collector’s submission directory, checks network connectivity to the central server, and transfers new submission files over **SSH/SFTP** (files are typically named `submit_*.sbm`). Config file: `submitter/vandaq_submitter.yaml`. The script expects an RSA private key at `PRIVATE_KEY_PATH`.

### Keys

- `STATIONARY_HOST` **required**: hostname or IP of the central server.
- `SSH_PORT` **required**: SSH port on the central host (often `22`).
- `USERNAME` **required**: SSH username for SFTP.
- `PRIVATE_KEY_PATH` **required**: path to the SSH private key file (no password prompt in the default script).
- `SUBMIT_FILE_PATTERN` **required**: glob for pending files in `DATA_DIR` (e.g. `submit_*.sbm`).
- `DATA_DIR` **required**: directory the collector writes submission files into (must match collector `submissions.submit_file_dir`).
- `ARCHIVE_DIR` **required**: local directory where files are moved after a successful transfer.
- `REMOTE_PATH` **required**: directory on the central server where files are uploaded (must match the central collector’s `submissions.submit_file_dir`).
- `PING_HOST` **required**: host used for a lightweight connectivity check before SSH.
- `CHECK_INTERVAL` **required**: seconds to sleep between transfer attempts.
- `logs` **required**: `log_dir`, `log_file`, `log_level`, `logger_name`.

Example:

```yaml
STATIONARY_HOST: "central.example.org"
SSH_PORT: 22
USERNAME: "vandaq"
PRIVATE_KEY_PATH: "/home/vandaq/.ssh/id_central"
SUBMIT_FILE_PATTERN: "submit_*.sbm"
DATA_DIR: "/home/vandaq/vandaq/collector/submission/"
ARCHIVE_DIR: "/home/vandaq/vandaq/collector/submission/submitted"
REMOTE_PATH: "/home/vandaq/vandaq/collector/submission/"
PING_HOST: "central.example.org"
CHECK_INTERVAL: 10
logs:
  log_dir: "/home/vandaq/vandaq/submitter/log"
  log_file: "submitter.log"
  log_level: "INFO"
  logger_name: "submitter"
```

## Dashboard Configuration

The Dash dashboard is configured in `web/DashPlay.yaml`, loaded at startup by `DashPlay_pages.py`. Restart the dashboard after edits.

### Top-level keys

- `db_connect_string` **required**: PostgreSQL URL for live plots, alarms, and maps.
- `dashboard_refresh_secs`: seconds between dashboard refresh cycles (default `2` in code).
- `dashboard_window_minutes`: minutes of history shown on diagnostic plots (optional).
- `include_engineering`: when false, hide engineering acquisition types from some views (optional).
- `display_timezone`: timezone name for plot axes and tables (e.g. `US/Pacific`).
- `master_GPS`: instrument name used as the primary GPS source on map pages.
- `alarm_shapes`: when true, alarm severity affects plot styling.
- `show_mute_instruments`: include muted instruments in instrument lists.
- `shape_file_dir`: directory of shapefiles for map overlays.
- `logs` **required**: `log_dir`, `log_file`, `log_level`, `logger_name`.

### `mapping` (map page)

- `default_platform`: platform name for map queries.
- `default_gps`: GPS instrument for track display (often matches `master_GPS`).
- `default_center`: `[latitude, longitude]` map center.
- `default_zoom`: initial zoom level.
- `map_native_max_zoom`: maximum zoom baked into offline tiles; must match `MAX_ZOOM` in `scripts/tiles/build_norcal_mbtiles.sh`.
- `map_max_zoom`: maximum zoom the UI allows (can exceed native zoom).
- `map_check_secs`: seconds between map data polls.
- `instruments`: list of instrument names shown on the map page.
- `tile_server`: offline basemap (see [Offline map tiles](../guides/map_tiles.md)).
  - `enabled`: use local tileserver when true.
  - `base_url`: tileserver root (van LAN IP or `http://127.0.0.1:8080`).
  - `style_path`: path to MapLibre style JSON on the tileserver.
  - `raster_tiles_url`: Leaflet tile URL template (PNG raster from full `tileserver-gl`).
  - `fallback_tiles_url`: online OSM tiles when offline tiles are unavailable.
  - `subdomains`: subdomain letters for fallback tiles.
- `wind_rose`: optional wind-rose panel (`show`, `window_minutes`, `num_bins`, `instrument`, `wind_dir_param`, `wind_speed_param`, etc.).

### `display_params`

Per-instrument blocks keyed by dashboard instrument name (may differ slightly from acquirer `instrument` string). Common keys:

- `graph`: parameters plotted as time series.
- `display`: parameters shown in numeric readout panels.
- `separate_scales`: when true, split parameters onto separate y-axes.
- `spectrum` / `spectrum_num_scans`: Spider MAGIC PSD spectrum display options.

### `controls`

List of instrument control panels. Each entry includes:

- `instrument_name`: panel label; should match the acquirer `instrument` value.
- `queue_command` / `queue_response`: POSIX queue `name` values — must match acquirer `command_queue` and `response_queue`.
- `widgets`: UI elements (`button`, `checkbox`, `command_box`, `response_box`). Each sends `command` or paired `command_checked` / `command_unchecked` strings to the instrument.

Example (abbreviated):

```yaml
db_connect_string: "postgresql://vandaq:YOUR_PASSWORD@localhost:5432/vandaq-dev"
dashboard_refresh_secs: 2
master_GPS: "ublox_M8Q_GPS"
display_timezone: "US/Pacific"
mapping:
  default_platform: "van1"
  map_native_max_zoom: 16
  tile_server:
    enabled: true
    base_url: "http://<van-lan-ip>:8080"
    raster_tiles_url: "/styles/norcal/{z}/{x}/{y}.png"
display_params:
  TSI_3789_CPC:
    graph: ["particle_conc"]
    display: ["particle_conc"]
controls:
  - instrument_name: "Aeris_CH4_C2H6"
    queue_command:
      name: "/AERIS_CH4_command"
    queue_response:
      name: "/AERIS_CH4_response"
    widgets:
      - checkbox: "Cal Gas Port"
        command_checked: "port1"
        command_unchecked: "port0"
```

## vandaq_admin Configuration

`vandaq_admin` is the CLI process manager for the data chain. It reads `vandaq_admin.yaml` at the repo root (path is hard-coded in the script).

### `directories`

- `acquirer_directory`, `acquirer_log_directory`
- `collector_directory`, `collector_log_directory`
- `submitter_directory`, `submitter_log_directory`
- `spider_psd_log_directory`: logs for optional Spider PSD ingest

### `components`

- `launch_acquirers`: when true, start one `vandaq_acquirer.py` per `*.yaml` in `{acquirer_directory}config/`.
- `launch_collector`: when true, start `vandaq_collector.py`.
- `launch_submitter`: when true, start `vandaq_submitter.py`.
- `launch_spider_psd_ingest`: when true, start `utils/spider_psd_ingest.py`.
- `collector_config_file`: filename under `collector/` (e.g. `vandaq_collector.yaml`).
- `submitter_config_file`: filename under `submitter/` (e.g. `vandaq_submitter.yaml`).

### CLI commands

Run from the repo root:

```bash
./vandaq_admin startup          # start all enabled components
./vandaq_admin startup collector
./vandaq_admin startup Palas    # acquirer whose config path contains "Palas"
./vandaq_admin stop
./vandaq_admin status
./vandaq_admin clearqueue       # drain POSIX queue (default name /dev-measurements)
```

Example:

```yaml
directories:
  acquirer_directory: "/home/vandaq/vandaq/acquirer/"
  acquirer_log_directory: "/home/vandaq/vandaq/acquirer/log/"
  collector_directory: "/home/vandaq/vandaq/collector/"
  collector_log_directory: "/home/vandaq/vandaq/collector/log/"
  submitter_directory: "/home/vandaq/vandaq/submitter/"
  submitter_log_directory: "/home/vandaq/vandaq/submitter/log/"
  spider_psd_log_directory: "/home/vandaq/vandaq/data/spider_psd/log/"
components:
  launch_acquirers: true
  launch_collector: true
  launch_submitter: true
  launch_spider_psd_ingest: true
  collector_config_file: "vandaq_collector.yaml"
  submitter_config_file: "vandaq_submitter.yaml"
```
