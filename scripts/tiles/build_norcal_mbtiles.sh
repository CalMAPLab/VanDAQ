#!/usr/bin/env bash
# Build vector MBTiles for Northern / Central California (offline Dash basemap).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLANETILER_JAR="${SCRIPT_DIR}/planetiler.jar"
OSM_PBF="${SCRIPT_DIR}/california-latest.osm.pbf"
OUTPUT_DIR="/var/lib/vandaq/tiles"
OUTPUT_MBTILES="${OUTPUT_DIR}/norcal.mbtiles"

# west, south, east, north — NorCal + Central CA
BOUNDS="-124.5,35.5,-119.0,42.0"
MAX_ZOOM=16
JAVA_MEM="${JAVA_MEM:-8g}"

if [[ ! -f "${PLANETILER_JAR}" ]]; then
  echo "Missing ${PLANETILER_JAR}" >&2
  echo "Download from: https://github.com/onthegomap/planetiler/releases/latest/download/planetiler.jar" >&2
  exit 1
fi

if [[ ! -f "${OSM_PBF}" ]]; then
  echo "Missing ${OSM_PBF}" >&2
  echo "Download from: https://download.geofabrik.de/north-america/us/california-latest.osm.pbf" >&2
  exit 1
fi

if [[ ! -d "${OUTPUT_DIR}" ]]; then
  echo "Creating ${OUTPUT_DIR} (may prompt for sudo)..."
  sudo mkdir -p "${OUTPUT_DIR}"
  sudo chown "$(whoami):$(id -gn)" "${OUTPUT_DIR}"
fi

cd "${SCRIPT_DIR}"

echo "Building ${OUTPUT_MBTILES} (bounds=${BOUNDS}, maxzoom=${MAX_ZOOM})..."
echo "First run downloads OpenMapTiles helper data into ${SCRIPT_DIR}/data/sources (needs network)."
java -Xmx"${JAVA_MEM}" -jar "${PLANETILER_JAR}" \
  --download \
  --osm-path="${OSM_PBF}" \
  --output="${OUTPUT_MBTILES}" \
  --bounds="${BOUNDS}" \
  --maxzoom="${MAX_ZOOM}" \
  --force

echo "Done: ${OUTPUT_MBTILES}"
ls -lh "${OUTPUT_MBTILES}"

DOCKER_TILES="/home/vandaq/tiles/norcal.mbtiles"
if [[ -d "$(dirname "${DOCKER_TILES}")" ]]; then
  echo "Copying to ${DOCKER_TILES} for tileserver Docker..."
  cp -f "${OUTPUT_MBTILES}" "${DOCKER_TILES}"
  ls -lh "${DOCKER_TILES}"
  echo "Restart tileserver: bash /home/vandaq/vandaq/scripts/tiles/start-tileserver-docker.sh"
fi
