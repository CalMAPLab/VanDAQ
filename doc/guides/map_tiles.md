# Offline map tiles (VanDAQ van)

Build a local NorCal/Central California basemap for the Dash Leaflet map, then serve raster PNG tiles with **Docker** (`tileserver-gl`). This matches the VanDAQ van setup: MBTiles under `/home/vandaq/tiles/`, container `vandaq-tileserver` on port **8080**.

Scripts live in `[scripts/tiles/](../../scripts/tiles/)`. Dashboard settings: `[web/DashPlay.yaml](../../web/DashPlay.yaml)` → `mapping.tile_server`.

Large downloads are gitignored (`*.pbf`, `*.mbtiles`, `planetiler.jar`).

## Prerequisites

- Java 21+ — `sudo apt install -y openjdk-21-jre-headless` on Ubuntu 22.04
- Docker (this van uses **snap** Docker; commands below use `sudo docker`)
- ~20 GB free disk for OSM extract + MBTiles
- Network for the one-time Planetiler/OSM download (and periodic tile refresh)

## 1. Download Planetiler

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

This writes `/var/lib/vandaq/tiles/norcal.mbtiles` and, when `/home/vandaq/tiles/` exists, **copies** the file there for the tileserver container.

Typical runtime: 30–90 minutes at zoom 16.

Keep these in sync:

- `MAX_ZOOM` in `[scripts/tiles/build_norcal_mbtiles.sh](../../scripts/tiles/build_norcal_mbtiles.sh)` (default **16**)
- `mapping.map_native_max_zoom` in `DashPlay.yaml`

On the first run, Planetiler downloads helper data into `scripts/tiles/data/sources/` (~1–2 GB, once).

## 4. One-time tileserver data directory

The Docker container mounts `/home/vandaq/tiles` as `/data`. Create it once:

```bash
mkdir -p /home/vandaq/tiles/fonts
cp /home/vandaq/vandaq/deploy/tileserver/style-norcal.json /home/vandaq/tiles/
```

Create `/home/vandaq/tiles/config.json` with raster serving enabled (paths are relative to `/data` inside the container):

```json
{
  "options": {
    "paths": {
      "root": "/data",
      "fonts": "/data/fonts"
    }
  },
  "data": {
    "norcal": {
      "mbtiles": "norcal.mbtiles"
    }
  },
  "styles": {
    "norcal": {
      "style": "style-norcal.json",
      "serve_rendered": true,
      "serve_data": true,
      "tilejson": {
        "bounds": [-124.5, 35.5, -119.0, 42.0],
        "format": "png"
      }
    }
  }
}
```

After a successful build (step 3), `norcal.mbtiles` should be in `/home/vandaq/tiles/`.

## 5. Start tileserver (Docker)

Use the repo script maptiler/tileserver-gl:

```bash
bash /home/vandaq/vandaq/scripts/tiles/start-tileserver-docker.sh
```

That pulls `maptiler/tileserver-gl:v5.6.0`, runs container `vandaq-tileserver`, and binds **0.0.0.0:8080**.

Verify:

```bash
curl -sI http://127.0.0.1:8080/styles/norcal/10/163/395.png | head -1
```

Expect `HTTP/1.1 200 OK`.

Manage the service:

```bash
sudo docker start vandaq-tileserver
sudo docker stop vandaq-tileserver
sudo docker logs -f vandaq-tileserver
```

## 6. Enable in Dash

In `web/DashPlay.yaml`, under `mapping.tile_server`:

```yaml
tile_server:
  enabled: true
  base_url: "http://<van-lan-ip>:8080"   # or http://127.0.0.1:8080 for local-only
  style_path: "/styles/norcal/style.json"
  raster_tiles_url: "/styles/norcal/{z}/{x}/{y}.png"
```

Use the van’s LAN address when browsers on other machines open the dashboard.

## Refresh tiles

On good Wi‑Fi (e.g. quarterly):

```bash
cd /home/vandaq/vandaq
./scripts/tiles/build_norcal_mbtiles.sh
bash /home/vandaq/vandaq/scripts/tiles/start-tileserver-docker.sh
```

## OSM attribution

© [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors

## Note on `deploy/tileserver/`

Files under `[deploy/tileserver/](../../deploy/tileserver/)` include a **systemd + npm** layout (`/etc/vandaq/tileserver`, `/var/lib/vandaq/tiles`) used on some hosts. **This van uses Docker and `/home/vandaq/tiles` only** — ignore the systemd/npm paths unless you deliberately migrate.