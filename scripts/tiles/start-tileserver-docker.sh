#!/usr/bin/env bash
# Start full tileserver-gl (raster PNG + vector). Do NOT use tileserver-gl-light for Dash.
set -euo pipefail

TILES_DIR="/home/vandaq/tiles"
CONTAINER="vandaq-tileserver"
# Full GL serves /styles/{id}/{z}/{x}/{y}.png — light does not.
IMAGE="maptiler/tileserver-gl:v5.6.0"

if [[ ! -f "${TILES_DIR}/norcal.mbtiles" ]]; then
  echo "Missing ${TILES_DIR}/norcal.mbtiles" >&2
  exit 1
fi
if [[ ! -f "${TILES_DIR}/config.json" ]]; then
  echo "Missing ${TILES_DIR}/config.json" >&2
  exit 1
fi

mkdir -p "${TILES_DIR}/fonts"

if ! grep -q '"serve_rendered"[[:space:]]*:[[:space:]]*true' "${TILES_DIR}/config.json"; then
  echo "Add \"serve_rendered\": true to the norcal style in ${TILES_DIR}/config.json" >&2
  exit 1
fi

sudo docker rm -f "${CONTAINER}" 2>/dev/null || true
sudo docker pull "${IMAGE}"
sudo docker run -d --name "${CONTAINER}" --restart unless-stopped \
  -v "${TILES_DIR}:/data:ro" \
  -p 0.0.0.0:8080:8080 \
  "${IMAGE}" \
  --config /data/config.json -p 8080 -u 127.0.0.1

echo ""
echo "Started ${CONTAINER}. After ~10s:"
echo "  curl -sI http://127.0.0.1:8080/styles/norcal/10/163/395.png | head -1"
echo "Homepage should say 'Vector and raster' (both active), not struck-through raster."
