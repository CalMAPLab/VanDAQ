"""Local tile server URLs for Plotly mapbox and dash-leaflet TileLayer."""
import urllib.error
import urllib.request


def get_mapbox_style(config):
    """Return Plotly mapbox style URL or built-in fallback style name."""
    mapping = config.get("mapping", {})
    tile_server = mapping.get("tile_server", {})
    fallback = tile_server.get("fallback_style", "open-street-map")

    if not tile_server.get("enabled"):
        return fallback

    base_url = tile_server.get("base_url", "http://127.0.0.1:8080").rstrip("/")
    style_path = tile_server.get("style_path", "/styles/norcal/style.json")
    style_url = f"{base_url}{style_path}"

    try:
        request = urllib.request.Request(style_url, method="GET")
        with urllib.request.urlopen(request, timeout=2) as response:
            if 200 <= response.status < 300:
                return style_url
    except (urllib.error.URLError, OSError, TimeoutError):
        pass

    log = config.get("logger")
    if log:
        log.warning(
            "Local tile server unreachable at %s; using %s",
            style_url,
            fallback,
        )
    return fallback


def _style_base_path(tile_server):
    """Directory URL for a style (no trailing style.json)."""
    style_path = tile_server.get("style_path", "/styles/norcal/style.json")
    if style_path.endswith("/style.json"):
        return style_path[: -len("/style.json")]
    if style_path.endswith(".json"):
        return style_path.rsplit("/", 1)[0]
    return style_path.rstrip("/")


def _raster_path(tile_server):
    raster = tile_server.get("raster_tiles_url")
    if raster:
        return raster if raster.startswith("/") else f"/{raster}"
    style_base = _style_base_path(tile_server)
    if not style_base.startswith("/"):
        style_base = f"/{style_base}"
    return f"{style_base}/{{z}}/{{x}}/{{y}}.png"


def _probe_tile_base(base_url, path, timeout=1):
    """HEAD a sample tile; return base_url if reachable."""
    sample = path.replace("{z}", "10").replace("{x}", "163").replace("{y}", "395")
    url = f"{base_url.rstrip('/')}{sample}"
    try:
        request = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if 200 <= response.status < 300:
                return base_url.rstrip("/")
    except (urllib.error.URLError, OSError, TimeoutError):
        pass
    return None


def get_tile_url(config):
    """
    Raster XYZ template for dl.TileLayer.

    Requires full tileserver-gl with serve_rendered: true for offline PNG tiles.
    Probes candidate base URLs (configured, 127.0.0.1, LAN IP) — Docker often
    binds 127.0.0.0.1 only while yaml may list 192.168.x.x.
    """
    mapping = config.get("mapping", {})
    tile_server = mapping.get("tile_server", {})
    fallback = tile_server.get(
        "fallback_tiles_url",
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    )

    if not tile_server.get("enabled"):
        return fallback

    path = _raster_path(tile_server)
    if path.startswith("http"):
        return path

    # Browser must use the configured host (e.g. 192.168.1.100), not 127.0.0.1 from
    # server-side probing — the dashboard server can reach localhost while the
    # user's browser cannot.
    configured = tile_server.get("base_url", "http://192.168.1.100:8080").rstrip("/")
    tile_template = f"{configured}{path}"

    log = config.get("logger")
    if _probe_tile_base(configured, path):
        if log:
            log.info("Leaflet tiles for browser: %s", tile_template)
        return tile_template

    if log:
        log.warning(
            "Tile server not reachable at %s from dashboard host; "
            "browser will still use %s (check Docker binds 0.0.0.0:8080)",
            configured,
            tile_template,
        )
    return tile_template


def get_tile_subdomains(config, tile_url=None):
    """Subdomains only for {s} OSM-style URLs; leave empty for local tileserver."""
    url = tile_url or get_tile_url(config)
    if "{s}" in url:
        return config.get("mapping", {}).get("tile_server", {}).get("subdomains", "abc")
    return ""


def get_tile_attribution(config):
    mapping = config.get("mapping", {})
    tile_server = mapping.get("tile_server", {})
    if tile_server.get("enabled"):
        return "© OpenStreetMap contributors (offline NorCal tiles)"
    return "© OpenStreetMap contributors"


def get_leaflet_basemap(config):
    """Raster URL, subdomains, attribution for dash-leaflet TileLayer."""
    url = get_tile_url(config)
    subdomains = get_tile_subdomains(config)
    return url, subdomains, get_tile_attribution(config)


def get_leaflet_tile_url(config):
    url, _subdomains, _attribution = get_leaflet_basemap(config)
    return url
