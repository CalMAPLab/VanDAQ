# Installation (VanDAQ DAQ host)

First-time setup for a **remote** measurement platform (van or field Linux host): PostgreSQL, Python environment, YAML configuration, and starting the data chain with `vandaq_admin`.

For architecture context see [Overview](../overview.md). For YAML keys see [Data chain configuration](../reference/data_chain_configuration.md). To add instruments after install see [Adding a new instrument](../guides/adding_a_new_instrument.md).

## Prerequisites

- Ubuntu 22.04 LTS (or similar) with sudo
- Python 3.10+
- PostgreSQL 14+ (schema dump was taken from PG 14)
- Network access to install packages; serial/USB permissions for hardware instruments as needed

## 1. Clone the repository

```bash
git clone <your-vandaq-repo-url> /home/vandaq/vandaq
cd /home/vandaq/vandaq
```

Adjust the path if your install root differs; examples below use `/home/vandaq/vandaq`.

## 2. PostgreSQL database

Create a database and role:

```bash
sudo -u postgres createuser -d -P vandaq
sudo -u postgres createdb -O vandaq vandaq-dev
```

Load the schema from the repo dump:

```bash
psql -U vandaq -d vandaq-dev -f /home/vandaq/vandaq/schema/vandaq_schema_dump.sql
```

The dump may enable extensions such as `pg_cron`; if `CREATE EXTENSION` fails, install the matching PostgreSQL contrib packages or remove those sections for a minimal install.

Set `connect_string` in `collector/vandaq_collector.yaml` and `db_connect_string` in `web/DashPlay.yaml` to your database URL, for example:

```text
postgresql://vandaq:YOUR_PASSWORD@localhost:5432/vandaq-dev
```

## 3. Python environment

```bash
cd /home/vandaq/vandaq
python3 -m venv env
source env/bin/activate
pip install -r requirements-dev.txt
```

`requirements-dev.txt` covers the acquirer, collector, and test stack (NumPy, pandas, SQLAlchemy, PyYAML, pyserial, pyzmq, ipcqueue, etc.).

**Dashboard** (when you run the Dash app on this host) also needs:

```bash
pip install dash plotly dash-bootstrap-components dash-leaflet dash-extensions
```

**Optional hardware** (install only if used):

- LabJack: LabJack LJM Python package per [LabJack documentation](https://labjack.com/support/software/installation/ljm-python)
- Phidget: `pip install Phidget22`

## 4. Configure the data chain

Edit these files for your platform (see [Data chain configuration](../reference/data_chain_configuration.md)):


| File                              | Purpose                                               |
| --------------------------------- | ----------------------------------------------------- |
| `vandaq_admin.yaml`               | Which processes to start; directory paths             |
| `collector/vandaq_collector.yaml` | DB URL, POSIX queue name, submission file directories |
| `acquirer/config/*.yaml`          | One file per instrument (copy and adapt examples)     |
| `submitter/vandaq_submitter.yaml` | Central server SSH/SFTP (remote platforms only)       |
| `web/DashPlay.yaml`               | Dashboard DB URL, map, `display_params`               |


**POSIX queue:** Remote acquirers and the collector must use the same queue settings. Default name is `/dev-measurements` with `max_msg_size` and `max_msgs` matching in acquirer and collector YAML. Queues are created automatically when processes start (`ipcqueue`).

**Submission directories** (remote collector):

```bash
mkdir -p /home/vandaq/vandaq/collector/submission/submitted
```

**Logs:** `vandaq_admin` appends to log files under `acquirer/log/`, `collector/log/`, and `submitter/log/`; those directories should be writable.

## 5. Start processes

From the repo root with your venv activated (if you use one):

```bash
cd /home/vandaq/vandaq
./vandaq_admin startup
./vandaq_admin status
```

`startup` launches components enabled in `vandaq_admin.yaml` (collector, acquirers for each `acquirer/config/*.yaml`, submitter, optional Spider PSD ingest).

To start a single component:

```bash
./vandaq_admin startup collector
./vandaq_admin startup MyInstrument   # substring match on config filename
```

## 6. Verify

### Processes

```bash
./vandaq_admin status
```

You should see `vandaq_collector.py` and one `vandaq_acquirer.py` per active config.

### Collector log

```bash
tail -f /home/vandaq/vandaq/collector/log/collector.log
```

### Database

Replace `ExampleSensor` with an instrument name from your acquirer config:

```sql
SELECT id, instrument FROM instrument WHERE instrument = 'ExampleSensor';

SELECT t.sample_time, p.parameter, m.value
FROM measurement m
JOIN instrument i ON m.instrument_id = i.id
JOIN parameter p ON m.parameter_id = p.id
JOIN time t ON m.time_id = t.id
WHERE i.instrument = 'ExampleSensor'
ORDER BY t.sample_time DESC
LIMIT 10;
```

If no rows appear, check that acquirer and collector queue names match and that the acquirer log shows data. See [Adding a new instrument](../guides/adding_a_new_instrument.md) for more verification steps.

### Optional: offline map tiles

If the dashboard uses a local basemap, follow [Offline map tiles](../guides/map_tiles.md) before setting `mapping.tile_server.enabled: true` in `DashPlay.yaml`.

## 7. Dashboard (optional)

The Dash app is started separately from `vandaq_admin`. Typical development launch:

```bash
cd /home/vandaq/vandaq/web
source ../env/bin/activate
python3 DashPlay_pages.py
```

Production deployment uses Apache + mod_wsgi for the dashboard; see [Operation and troubleshooting — Dashboard (Apache)](operation_and_troubleshooting.md#dashboard-apache) and [`web/DashPlay.conf`](../../web/DashPlay.conf).

## Next steps

- [Adding a new instrument](../guides/adding_a_new_instrument.md)
- [Network configuration](network_configuration.md) (central aggregation)
- [Operation and troubleshooting](operation_and_troubleshooting.md)

