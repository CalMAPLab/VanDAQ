# Acquirer Configuration Manual

This guide explains how to author YAML configs for acquirers in `acquirer/config/`. Each config selects an acquirer type via `type` and supplies connection, parsing, queue, and logging details. Keys marked **required** must be present for that acquirer type; others are optional.

## Common keys (all acquirers)

- `platform`**required**: platform name (e.g., vehicle ID).
- `instrument`**required**: instrument identifier.
- `type`**required**: picks the acquirer class:`simpleSerial`,`serialPolled`,`serial_nmea_GPS`,`serial_nmea`,`networkStreaming`,`simulated`,`simulated_GPS`,`LabJack`,`Phidget`.
- `queue`**required**: POSIX MQ used to emit measurements.
  - `name` (e.g.,`/dev-measurements`)
  - `max_msg_size`,`max_msgs`
- `command_queue` /`response_queue`: optional POSIX MQs for instrument commands/responses.
  - `name`,`max_msg_size`,`max_msgs`;`response_header` can be used to filter instrument replies.
- `measurement_delay_secs`: optional latency offset applied to`sample_time`.
- `verbose`: optional (>0 to print queued messages).
- `alarms`: optional per-parameter alarm rules (`value_<`,`value_>`,`value_=`,`value_!=`,`substr_is`) that attach alarm metadata to measurements.
- `logs`**required**: file-based logger configuration.
  - `log_dir`,`log_file`,`log_level`,`logger_name`

## Alarm rules

Define alarms under an `alarms` block keyed by parameter name. Each rule is a one-key map using these operators (supported in `acquirers.py`):

- `value_<`: trigger when`value` is less than threshold
- `value_>`: trigger when`value` exceeds threshold
- `value_=`: trigger when`value` equals threshold
- `value_!=`: trigger when`value` differs from threshold
- `substr_is`: for string fields, compare a substring (`substr_begin`,`substr_end`,`value`)

Each operator maps to an object:

```yaml
alarms:
  CO:
    - value_<:
        value: 0
        alarm_level: alarm          # string; matches dim table values
        alarm_type: underrange      # string; matches dim table values
        alarm_message: "CO below zero"
        impacts_data: true          # optional; defaults true
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

## SerialStreamAcquirer (`type: simpleSerial`)

Continuous serial stream parsed into delimited items.

- `connection: serial`
- `serial`:`device`,`baud`
- `stream`:
  - `line_delimiter`: defaults to newline if omitted.
  - `item_delimiter`
  - `items`: comma list; use`x` to skip positions. May include`inst_datetime`,`inst_date`,`inst_time`.
  - `formats`: comma list matching`items` (`f` float,`s`/`h` string, datetime format strings for instrument time fields).
  - `units`: comma list matching`items`
  - `acqTypes`: comma list matching`items`
  - `scalers`: optional comma list (defaults to`1`); applied to float items.
  - `aggregate_seconds` /`aggregate_items`: optional aggregation window (seconds) and per-item aggregation (`mean`,`min`,`max`,`first`,`last`) instead of per-line emission.
  - `cycle_time`: optional sleep between loops.
- `init`: optional map of strings sent once after opening the port.
- `response_header`: optional prefix used to route instrument responses to`response_queue`.

## SerialPolledAcquirer (`type: serialPolled`)

Poll/response over serial at `data_freq_secs`.

- Inherits SerialStream requirements plus:
- `data_freq_secs`: polling interval.
- `poll`: map of poll definitions keyed arbitrarily; each poll entry:
  - `request_string`: bytes written to the port.
  - `response_len_min` /`response_len_max` (optional): expected byte counts for timeout handling.
  - `item_delimiter`: delimiter for response parsing.
  - `items`,`formats`,`units`,`acqTypes`, optional`scalers`: same pattern as SerialStream.
  - `key_delimiter`: if present, treat response as key/value pairs and extract values.
  - `trim_response_begin` /`trim_response_end`: slice response before parsing.
- `wait_for_response_secs`: optional delay after sending a command before reading a response.

## SerialNmeaGPSAcquirer (`type: serial_nmea_GPS`)

Lightweight NMEA GPS reader for latitude/longitude/speed/direction.

- `connection: serial`
- `serial`:`device`,`baud`
- `measurement_delay_secs`: optional
  No`stream` parsing rules are needed; the acquirer decodes NMEA RMC sentences directly.

## SerialNmeaAcquirer (`type: serial_nmea`)

General NMEA sentence decoder configured per sentence type.

- `connection: serial`
- `serial`:`device`,`baud`
- `data`:
  - `sentence_delimiter` (optional, default newline)
  - `sentence_types`: map keyed by NMEA sentence type (e.g.,`MWV`,`GGA`,`MDA`); each contains fields:
    - `<field_name>`:
      - `parameter`,`unit`,`format` (`f` float or`s` string),`acqType`
      - `scaler` optional for numeric scaling
- `measurement_delay_secs`: optional

## NetworkStreamingAcquirer (`type: networkStreaming`)

Receives pickled dictionaries over ZeroMQ PULL.

- `connection: network`
- `network`:`address` (bind host),`port`
- `dictionaries`: comma-separated list of dict keys expected in the incoming message.
- For each dictionary name listed:
  - Either`keys`: comma list of indices to pull from the dict (converted to strings)**or**`items`: comma list of dict keys.
  - `formats`,`units`,`acqTypes`: comma lists aligned to`items`.
  - Optional`wholeDict` block:`parameter`,`unit`,`acqType` to store the entire dict as a string.
- `measurement_delay_secs`: optional

## SimulatedAcquirer (`type: simulated`)

Generates synthetic signals for testing.

- `stream`: defines output layout
  - `item_delimiter`
  - `items`,`formats`,`units`,`acqTypes` (like SerialStream)
- `simulate`:
  - `cycle_secs`: emission interval
  - For each parameter named in`stream.items`:`signal` (`sine`,`triangle`,`sawtooth`,`square`,`random`),`period`,`min`,`max`

## SimulatedGPSAcquirer (`type: simulated_GPS`)

Replays lat/lon pairs from a CSV file.

- `datafile`: path to CSV with`latitude` and`longitude` columns
- `cycletime`: seconds between samples
- `measurement_delay_secs`: optional

## LabJackAcquirer (`type: LabJack`)

Reads analog/digital channels via LabJack LJM.

- `device_type`,`connection_type`,`identifier`: device selectors for`ljm.openS`
- `data_freq_secs`: output cadence (seconds)
- `Parameters`: list of parameter definitions; each item is a single-key map:
  - `<param_name>`:
    - `signal_type`:`Analog` or`Digital`
    - `channel_name`: LJM channel name (e.g.,`AIN0`,`FIO0`)
    - `unit`,`aquisition_type` (note spelling follows existing configs)
    - Analog options:`preamp_gain`,`v_offset`,`v_per_unit`,`range`,`negative_channel`
    - Aggregation (optional for analog):`aggregate` (`mean`/`max`/`min`) and`aggregate_hz`
- `measurement_delay_secs`: optional

## PhidgetAcquirer (`type: Phidget`)

Reads analog/digital channels from a Phidget hub.

- `identifier`: device serial
- `data_freq_secs`: output cadence
- `Parameters`: list of parameter definitions; each item is a single-key map:
  - `<param_name>`:
    - `signal_type`:`Analog` or`Digital`
    - `channel_name`: hub port
    - For analog:`v_offset`,`v_per_unit`, optional`aggregate` +`aggregate_hz`
    - `unit`,`aquisition_type`
- `measurement_delay_secs`: optional

## Example: serial stream skeleton

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
