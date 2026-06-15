# Operation and troubleshooting

Day-to-day commands, log locations, and common fixes for a VanDAQ remote (van) host. For first-time setup see [Installation](installation.md). For central submission see [Network configuration](network_configuration.md).

## Routine operations

Run from the repo root (`/home/vandaq/vandaq`):

```bash
./vandaq_admin status
./vandaq_admin startup
./vandaq_admin stop
./vandaq_admin startup collector
./vandaq_admin startup MyInstrument    # substring match on config filename
./vandaq_admin clearqueue                # drain /dev-measurements (default queue)
```

`clearqueue` uses a fixed queue name and size in `vandaq_admin`; if your collector uses a different queue, drain it with the same `name`, `max_msgs`, and `max_msg_size` as in YAML.

Restart pattern after config changes:

```bash
./vandaq_admin stop
./vandaq_admin startup
```

Only `*.yaml` files **directly** in `acquirer/config/` are started. Files under `acquirer/config/disabled/` or `save/` are ignored.

### Day file exports (`filers/dayfile.py`)

Export a calendar day's measurements from PostgreSQL to CSV for offline analysis. Run from the repo root:

```bash
cd /home/vandaq/vandaq
python3 filers/dayfile.py                  # today (local midnight boundary from config)
python3 filers/dayfile.py 2025-06-01       # specific date (YYYY-MM-DD)
python3 filers/dayfile.py 2025-06-01 --nogps           # full day, no GPS filter
python3 filers/dayfile.py 2025-06-01 --all_drive_data    # first-to-last GPS point only
```

Configuration: [`filers/dayfile.yaml`](../../filers/dayfile.yaml)

| Key | Purpose |
|-----|---------|
| `db_connect_string` | Same database the collector writes |
| `directory` | Output root (default under `filers/files/day/`) |
| `platforms` | List of platform names to export |
| Per-platform `gps_instrument` | GPS acquirer name for geolocated exports (e.g. `ublox_M8Q_GPS`) |
| Per-platform `subdir` | Optional subdirectory under `directory` |

Default mode joins measurements with GPS locations for the configured `gps_instrument`. Output files are named `measurements_<platform>_<date>_long.csv` (prefixes `no-geolocations_` or `drive_range_` for the flag variants).

Set `db_connect_string` before first use. If you add a new GPS source, update `gps_instrument` — see [Adding a new instrument](../guides/adding_a_new_instrument.md#next-steps).

### VOCUS (Windows TofDaq bridge)

The VOCUS instrument uses TofDaq on a **Windows PC**. The Linux acquirer ([`acquirer/config/VOCUS.yaml`](../../acquirer/config/VOCUS.yaml), `type: networkStreaming`) listens on port **6969** for pickled `{ms, eng}` messages.

You must also run the Windows bridge script on the TofDaq machine:

- [`archive/sender/VanDAQ_Sender_VOCUS_V1.py`](../../archive/sender/VanDAQ_Sender_VOCUS_V1.py)
- Set `HOST` to the van's LAN IP; ensure firewall allows TCP 6969 from Windows to the van.

See [archive/sender/README.md](../../archive/sender/README.md) for the full two-machine setup.

### Dashboard (Apache)

On the van, the Dash app is usually served by **Apache2 with mod_wsgi**, not `vandaq_admin`. Example site config: `[web/DashPlay.conf](../../web/DashPlay.conf)` (often installed under `/etc/apache2/sites-available/` with the app at `/var/www/DashPlay`).

After changing `**web/DashPlay.yaml`**, dashboard Python code, or WSGI dependencies, reload Apache so the WSGI workers pick up changes:

```bash
sudo systemctl reload apache2
```

If behavior is still stale, use a full restart:

```bash
sudo systemctl restart apache2
```

Acquirer/collector/submitter processes do **not** need a restart for Dash YAML edits. Sample Apache site config: [`web/DashPlay.conf`](../../web/DashPlay.conf).

## Log files


| Component              | Typical path                                                                                            |
| ---------------------- | ------------------------------------------------------------------------------------------------------- |
| Acquirer (per config)  | `acquirer/log/<config_basename>` (no `.yaml` suffix)                                                    |
| Collector              | `collector/log/collector.log`                                                                           |
| Submitter              | `submitter/log/submitter.log`                                                                           |
| Dashboard (app logger) | `web/log/VanDAQ_Dashboard.log` (from `DashPlay.yaml` `logs`; path may differ under `/var/www/DashPlay`) |
| Dashboard (Apache)     | `/var/log/apache2/myflaskapp_error.log` and `myflaskapp_access.log` (names from `DashPlay.conf`)        |
| Spider PSD ingest      | `data/spider_psd/log/spider_psd_ingest.log`                                                             |
| Tileserver (Docker)    | `sudo docker logs vandaq-tileserver`                                                                    |


```bash
tail -f /home/vandaq/vandaq/collector/log/collector.log
tail -f /home/vandaq/vandaq/acquirer/log/acquirer_<Instrument>.log
tail -f /home/vandaq/vandaq/submitter/log/submitter.log
```

## No new data in the database

Work through in order:

1. `**./vandaq_admin status**` — collector and relevant `vandaq_acquirer.py` processes running?
2. **Acquirer log** — serial open errors (`SerialException`), parse errors, or silent loop?
3. **Queue alignment** — acquirer `queue.name` / `max_msg_size` / `max_msgs` must match `collector/vandaq_collector.yaml`.
4. **Verbose acquirer** — set `verbose: 1` temporarily, restart acquirer, confirm dicts print; remove when done.
5. **Collector log** — database connection errors, `IntegrityError`, or queue read failures?
6. **SQL check** — see [Adding a new instrument](../guides/adding_a_new_instrument.md#database-check).

If the acquirer runs but the collector does not, messages pile up in the POSIX queue; use `clearqueue` only if you intend to discard queued data.

## Serial / USB instrument issues

- Confirm device path (`/dev/ttyUSB0`, `/dev/usb_serial_*`, etc.) and permissions (`dialout` group).
- Another process may hold the port; stop other serial terminals or duplicate acquirers.
- Match `baud`, `line_delimiter`, and `stream` layout to a captured sample of instrument output.
- For polled instruments (`serialPolled`), check `data_freq_secs`, `poll` request strings, and `response_len_min` / `max`.

## Dashboard issues

- `**db_connect_string`** in `web/DashPlay.yaml` must reach the same database the collector writes.
- `**display_params**` keys must match acquirer `instrument` and parameter names exactly.
- **Controls** — `queue_command` / `queue_response` names must match acquirer YAML; see [Adding a new instrument](../guides/adding_a_new_instrument.md#controls).
- **Config not visible after edits** — reload Apache (`sudo systemctl reload apache2`); see [Dashboard (Apache)](#dashboard-apache) above.
- **500 / blank page** — check Apache error log (`myflaskapp_error.log`); confirm `mod_wsgi` and the venv `python-path` in `DashPlay.conf` match the deployed tree.

## Map / offline tiles

- Confirm Docker container: `sudo docker ps` should show `vandaq-tileserver`.
- Test raster URL: `curl -sI http://127.0.0.1:8080/styles/norcal/10/163/395.png | head -1` → expect `200`.
- `mapping.tile_server.base_url` in `DashPlay.yaml` must match how browsers reach the van (LAN IP or `127.0.0.1`).
- See [Offline map tiles](../guides/map_tiles.md) to rebuild MBTiles and restart the container.

## Submitter / central aggregation

Symptoms: growing pile of `submit_*.sbm` in `collector/submission/`, nothing new on central DB.

1. `**submitter/log/submitter.log`** — “Network is unavailable”, SSH auth failures, or SFTP errors.
2. **Manual SSH test** — same user, key, host, and port as `vandaq_submitter.yaml` (see [Network configuration](network_configuration.md#ssh-setup)).
3. **Path alignment** — `DATA_DIR`, `REMOTE_PATH`, and central `submit_file_dir` must match.
4. **Central collector** — running file-mode config? Check central `collector/log/` and `submitted/rejected/` under the archive directory.
5. **Disk on van** — pending `.sbm` files not archived until upload succeeds.

## PostgreSQL

- Connection refused: PostgreSQL service down or wrong `connect_string` host/port.
- Authentication failed: user/password mismatch in collector or Dash YAML.
- Load schema if tables missing: `psql ... -f schema/vandaq_schema_dump.sql` ([Installation](installation.md)).

## When to escalate

- Repeated central `rejected/` files after SFTP succeeds.
- Database corruption or migration needs beyond `vandaq_schema_dump.sql`.
- New acquirer `type` or protocol changes — see [Data chain configuration](../reference/data_chain_configuration.md) and developer tests in [README](../../README.md#testing).

## Related

- [Installation](installation.md)
- [Network configuration](network_configuration.md)
- [Adding a new instrument](../guides/adding_a_new_instrument.md)
- [Offline map tiles](../guides/map_tiles.md) (Docker tileserver)

