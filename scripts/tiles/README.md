# Offline map tiles (Northern / Central California)

Build a local vector MBTiles file for the VanDAQ Dash map, then serve it with
[tileserver-gl](https://github.com/maptiler/tileserver-gl). See `deploy/tileserver/`
for the server config and systemd unit.

Large artifacts are gitignored (`*.pbf`, `*.mbtiles`, `planetiler.jar`).

## Prerequisites

- Java 21+ (`java -version`) — `sudo apt install -y openjdk-21-jre-headless` on Ubuntu 22.04
- ~20 GB free disk (OSM download + MBTiles output)
- Good network for the one-time download/build

## 1. Download Planetiler

From the van (in this directory):

```bash
cd /home/vandaq/vandaq/scripts/tiles
curl -L -o planetiler.jar \
  https://github.com/onthegomap/planetiler/releases/latest/download/planetiler.jar
```

## 2. Download California OSM extract

```bash
cd /home/vandaq/vandaq/scripts/tiles
curl -L -o california-latest.osm.pbf \
  https://download.geofabrik.de/north-america/us/california-latest.osm.pbf
```

## 3. Build MBTiles

```bash
cd /home/vandaq/vandaq
./scripts/tiles/build_norcal_mbtiles.sh
```

Output: `/var/lib/vandaq/tiles/norcal.mbtiles` (requires sudo to create `/var/lib/vandaq/tiles`).

Typical runtime: 30–90 minutes at zoom 14; zoom 16 is slower and produces a larger file (~1–2 GB).

Set `MAX_ZOOM` in `build_norcal_mbtiles.sh` and `mapping.map_native_max_zoom` in `DashPlay.yaml` to the same value.

On the first run, Planetiler also downloads helper datasets (Natural Earth, water
polygons, etc.) into `scripts/tiles/data/sources/` — requires network once, ~1–2 GB extra.

## 4. Install tileserver (vector MBTiles)

GitHub no longer publishes `tileserver-gl-linux-x64.tar.gz`. Use **npm** (recommended) or **Docker**.

Install config from this repo first:

```bash
sudo mkdir -p /etc/vandaq/tileserver /var/lib/vandaq/tiles
sudo cp /home/vandaq/vandaq/deploy/tileserver/config.json /etc/vandaq/tileserver/
sudo cp /home/vandaq/vandaq/deploy/tileserver/style-norcal.json /etc/vandaq/tileserver/
```

### Option A — npm (`tileserver-gl-light`, vector only)

For **offline raster PNG tiles** (Leaflet `TileLayer`), use **full** `tileserver-gl` instead — see Option A2 below. `serve_rendered: true` in `config.json` has no effect on `-light`.

### Option A2 — npm (`tileserver-gl`, raster + vector)

Van needs Node 20+ and MapLibre fonts under `/etc/vandaq/tileserver/fonts`:

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
sudo npm install -g tileserver-gl@5.6.0
sudo ln -sf "$(command -v tileserver-gl)" /usr/local/bin/tileserver-gl
```

Ensure `deploy/tileserver/config.json` has `"serve_rendered": true` on the `norcal` style. Verify:

```bash
curl -sI http://127.0.0.1:8080/styles/norcal/10/163/395.png
```

Dash `DashPlay.yaml` uses `raster_tiles_url: "/styles/norcal/{z}/{x}/{y}.png"`.

Python deps for the Leaflet map page:

```bash
pip install dash-leaflet dash-extensions
```

### Option A (legacy) — npm (`tileserver-gl-light`)

Van needs Node 20+ (Ubuntu 22.04 ships Node 12, which is too old):

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
sudo npm install -g tileserver-gl-light@5.6.0
sudo ln -sf "$(command -v tileserver-gl-light)" /usr/local/bin/tileserver-gl
```

Then install and start systemd (expects `/usr/local/bin/tileserver-gl`):

```bash
sudo cp /home/vandaq/vandaq/deploy/tileserver/vandaq-tileserver.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vandaq-tileserver
```

### Option B — Docker

Snap Docker often cannot bind-mount `/var/lib/...`. Use tiles under `/home/vandaq/tiles/`:

```bash
mkdir -p /home/vandaq/tiles/fonts
cp /var/lib/vandaq/tiles/norcal.mbtiles /home/vandaq/tiles/
# If the symlink fails inside Docker, copy instead:
# cp /var/lib/vandaq/tiles/norcal.mbtiles /home/vandaq/tiles/

sudo docker pull maptiler/tileserver-gl-light:v5.6.0
sudo docker rm -f vandaq-tileserver 2>/dev/null
sudo docker run -d --name vandaq-tileserver --restart unless-stopped \
  -v /home/vandaq/tiles:/data:ro \
  -v /etc/vandaq/tileserver:/config:ro \
  -p 127.0.0.1:8080:8080 \
  maptiler/tileserver-gl-light:v5.6.0 \
  --config /config/config-docker.json -p 8080 -u 0.0.0.0
```

Copy `config-docker.json` to `/etc/vandaq/tileserver/` with the other config files.

Skip systemd if using Docker; manage with `docker start|stop vandaq-tileserver`.

### Verify

   ```bash
   curl -s http://127.0.0.1:8080/ | head
   curl -s http://127.0.0.1:8080/styles/norcal/style.json | head
   ```

## 5. Enable in Dash

In `web/DashPlay.yaml`, under `mapping.tile_server`, set `enabled: true` after
Step 5 (Dash code) is deployed and the tile server is running.

Use `base_url: "http://127.0.0.1:8080"` for local display on the van, or the
van LAN IP if browsers on other machines load the dashboard.

## Refresh tiles

Re-run `./scripts/tiles/build_norcal_mbtiles.sh` when on good Wi‑Fi (e.g. quarterly),
then `sudo systemctl restart vandaq-tileserver`.

## OSM attribution

© [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors
