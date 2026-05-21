"""
VanDAQ live drive map — dash-leaflet + canvas GeoJSON points.

Basemap: offline tileserver-gl raster tiles (serve_rendered: true).
Track: single GeoJSON layer; colors from hideout via assets/map_style.js.
"""
import copy
import json
import os
import time
from datetime import date, datetime, timedelta
from glob import glob
from threading import Lock, Thread

import dash
import dash_leaflet as dl
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytz
from dash import Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from dash_extensions.javascript import Namespace
from transitions import Machine

from map_tile_style import get_tile_attribution, get_tile_subdomains, get_tile_url
from wind_rose import (
    build_wind_rose_figure,
    day_cache_missing_wind,
    empty_wind_rose_figure,
    instruments_for_map_query,
)
from vandaq_2step_measurements_query import (
    get_all_geolocations,
    get_measurements_with_alarms_and_locations,
)

NS = Namespace("dashExtensions", "vandaqMap")

VIRIDIS_HEX = [
    "#440154", "#482777", "#3f4a8a", "#31678e", "#26838f",
    "#1f9d8a", "#6cce5a", "#b6de2b", "#fee825", "#fde725",
]

COLORBAR_STRIP_HEIGHT = 18

query_results = {}
lock = Lock()
logger = None
myConfig = None

FULL_REFRESH_EVERY = 100


class MapMachine(object):
    states = [
        "start", "wait_new_data", "wait_old_data",
        "refresh_new_map", "refresh_old_map", "idle",
    ]

    def __init__(self, config, initial_state="start"):
        self.config = config
        self.machine = Machine(model=self, states=MapMachine.states, initial=initial_state)
        self.machine.add_transition(
            "request_new_data", "start", "wait_new_data",
            before="set_date", after="order_date_data",
        )
        self.machine.add_transition(
            "date_selector_changed", "wait_new_data", "wait_old_data",
            conditions=self.is_not_today, before="set_date", after="order_date_data",
        )
        self.machine.add_transition(
            "date_selector_changed", "wait_old_data", "wait_new_data",
            conditions=self.is_today, before="set_date", after="order_date_data",
        )
        self.machine.add_transition(
            "date_selector_changed", "idle", "wait_old_data",
            conditions=self.is_not_today, before="set_date", after="order_date_data",
        )
        self.machine.add_transition(
            "date_selector_changed", "idle", "wait_new_data",
            conditions=self.is_today, before="set_date", after="order_date_data",
        )
        self.machine.add_transition(
            "date_selector_changed", "refresh_new_map", "wait_old_data",
            conditions=self.is_not_today, before="set_date", after="order_date_data",
        )
        self.machine.add_transition(
            "date_selector_changed", "refresh_old_map", "wait_new_data",
            conditions=self.is_today, before="set_date", after="order_date_data",
        )
        self.machine.add_transition("data_arrived", "wait_new_data", "refresh_new_map")
        self.machine.add_transition("data_arrived", "wait_old_data", "refresh_old_map")
        self.machine.add_transition("map_refreshed", "refresh_new_map", "wait_new_data")
        self.machine.add_transition("map_refreshed", "refresh_old_map", "idle")
        self.machine.add_transition("param_changed", "wait_new_data", "refresh_new_map")
        self.machine.add_transition("param_changed", "idle", "refresh_old_map")

    def set_date(self, date=date.today()):
        if logger:
            logger.debug("set_date -> %s", date)
        self.date = date

    def order_date_data(self, **kwargs):
        global query_results
        day = kwargs.get("date", self.date)
        if logger:
            logger.debug("order_date_data -> %s", day)
        with lock:
            if query_results.get("data", {}).get(day, None) is None:
                query_results.setdefault("data", {})[day] = None

    def is_today(self, **kwargs):
        day = kwargs.get("date", self.date)
        return day == today_date(self.config)

    def is_not_today(self, **kwargs):
        day = kwargs.get("date", self.date)
        return day != today_date(self.config)

    def data_ready(self):
        global query_results
        if query_results.get("data", None) is None:
            return False
        with lock:
            return query_results["data"].get(self.date, None) is not None

    def get_data(self):
        global query_results
        with lock:
            return copy.copy(query_results["data"].get(self.date, None))

    def serialize(self):
        return json.dumps({"state": self.state, "date": str(self.date)})

    @classmethod
    def deserialize(cls, config, data):
        try:
            obj = cls(config, initial_state=data["state"])
        except Exception as e:
            if logger:
                logger.debug("failed to deserialize FSM: %s", e)
            obj = cls(config)
        if data.get("date"):
            obj.date = date.fromisoformat(data["date"])
        return obj


def get_geolocations(engine, config, timezone=None):
    geo_df = get_all_geolocations(engine)
    if not geo_df.empty and timezone:
        geo_df["sample_time"] = (
            geo_df["sample_time"].dt.tz_localize("UTC").dt.tz_convert(timezone)
        )
        geo_df.set_index("sample_time", inplace=True, drop=False)
    return geo_df


def find_missing_dates(dates):
    if not dates:
        return []
    sorted_dates = sorted(dates)
    start_date = sorted_dates[0]
    end_date = sorted_dates[-1]
    all_dates = {
        start_date + timedelta(days=i)
        for i in range((end_date - start_date).days + 1)
    }
    return sorted(all_dates - set(sorted_dates))


def get_instruments_and_params(df):
    ip = {
        "platforms": df["platform"].unique(),
        "gps_instruments": df["gps"].unique(),
        "instruments": {},
    }
    for instrument in df["instrument"].unique():
        inst_recs = df[df["instrument"] == instrument]
        ip["instruments"][instrument] = inst_recs["parameter"].unique()
    return ip


def today_date(config):
    local_tz = pytz.utc
    if "display_timezone" in config:
        local_tz = pytz.timezone(config["display_timezone"])
    mapping = config.get("mapping", {})
    if mapping.get("test_day"):
        test_day = datetime.strptime(mapping["test_day"], "%m/%d/%Y").date()
        if mapping.get("test_hour_offset") is not None:
            hour_offset = int(mapping["test_hour_offset"])
            the_date = (
                pytz.utc.localize(datetime.now() + timedelta(hours=hour_offset))
                .astimezone(local_tz)
                .date()
            )
            if the_date != test_day:
                return test_day
            return the_date
        return test_day
    return pytz.utc.localize(datetime.now()).astimezone(local_tz).date()


def today_end_time(config):
    local_tz = pytz.utc
    if "display_timezone" in config:
        local_tz = pytz.timezone(config["display_timezone"])
    if config["mapping"].get("test_day"):
        end_time = pytz.utc.localize(datetime.now()).astimezone(local_tz).time()
        if config["mapping"].get("test_hour_offset") is not None:
            hour_offset = int(config["mapping"]["test_hour_offset"])
            end_datetime = datetime.combine(date.today(), end_time) + timedelta(hours=hour_offset)
            end_time = end_datetime.time()
        return end_time
    return datetime.now().time().replace(hour=23, minute=59, second=59, microsecond=0)


def empty_featurecollection():
    return {"type": "FeatureCollection", "features": []}


def df_to_featurecollection(df, parameter_label):
    if df is None or len(df) == 0:
        return empty_featurecollection()
    lats = df["latitude"].to_numpy()
    lons = df["longitude"].to_numpy()
    vals = df["value"].to_numpy()
    times = df["sample_time"].astype(str).to_numpy()
    units = df["unit"].dropna().unique()
    unit_str = units[0] if len(units) else ""
    features = []
    for lat, lon, val, t in zip(lats, lons, vals, times):
        if not (np.isfinite(lat) and np.isfinite(lon)):
            continue
        v = float(val) if np.isfinite(val) else None
        if v is not None:
            tip = f"{t}<br>{parameter_label}: {v:.3f} {unit_str}"
        else:
            tip = str(t)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
            "properties": {"value": v, "tooltip": tip},
        })
    return {"type": "FeatureCollection", "features": features}


def calculate_initial_view(df, config):
    mapping = config.get("mapping", {})
    default = mapping.get("default_center", [37.87, -122.27])
    default_zoom = int(mapping.get("default_zoom", 12))
    if df is None or len(df) == 0:
        return list(default), default_zoom
    min_lat, max_lat = df["latitude"].min(), df["latitude"].max()
    min_lon, max_lon = df["longitude"].min(), df["longitude"].max()
    center = [(min_lat + max_lat) / 2, (min_lon + max_lon) / 2]
    max_range = max(max_lat - min_lat, max_lon - min_lon)
    if max_range > 10:
        zoom = 4
    elif max_range > 1:
        zoom = 6
    elif max_range > 0.1:
        zoom = 9
    elif max_range > 0.01:
        zoom = 12
    else:
        zoom = 16
    return center, zoom


def load_community_geojson(config, names):
    layers = []
    if not names:
        return layers
    for item in names:
        if not item:
            continue
        shape_path = os.path.join(config["shape_file_dir"], f"{item}.geojson")
        try:
            with open(shape_path) as f:
                geojson_data = json.load(f)
        except OSError as e:
            if logger:
                logger.warning("could not read %s: %s", shape_path, e)
            continue
        layers.append(
            dl.GeoJSON(
                data=geojson_data,
                id={"type": "community-shape", "name": item},
                options=dict(style=dict(color="red", weight=3, fillOpacity=0.0)),
            )
        )
    return layers


def colorbar_panel_children(min_val, max_val, unit_str):
    """HTML legend bottom-right; solid strips (Dash often drops CSS gradients)."""
    strips = [
        html.Div(
            style={
                "backgroundColor": color,
                "width": "24px",
                "height": f"{COLORBAR_STRIP_HEIGHT}px",
                "flexShrink": 0,
            },
        )
        for color in reversed(VIRIDIS_HEX)
    ]
    max_label = f"{max_val:.3g}"
    if unit_str:
        max_label = f"{max_label} {unit_str}"
    return [
        html.Div(max_label, className="map-colorbar-label"),
        html.Div(strips, className="map-colorbar-strips"),
        html.Div(f"{min_val:.3g}", className="map-colorbar-label"),
    ]


def default_hideout():
    return dict(
        min=0.0,
        max=1.0,
        colorscale=VIRIDIS_HEX,
        circleOptions=dict(radius=4, weight=0, fillOpacity=0.85),
    )


def layout_map_display(config):
    global query_results
    platform = config["mapping"].get("default_platform")
    gps = config["mapping"].get("default_gps")
    check_interval = config["mapping"].get("map_check_secs", 3)
    mapping = config.get("mapping", {})
    default_center = mapping.get("default_center", [37.87, -122.27])
    default_zoom = int(mapping.get("default_zoom", 12))
    map_max_zoom = int(mapping.get("map_max_zoom", 18))
    map_native_max_zoom = int(mapping.get("map_native_max_zoom", 16))

    shapefiles = glob(f"{config['shape_file_dir']}/*.geojson")
    shapes = [""]
    for sf in shapefiles:
        if sf.endswith(".geojson"):
            shapes.append(os.path.basename(sf).replace(".geojson", ""))

    for i in range(200):
        if query_results.get("gps_dates") is not None:
            break
        time.sleep(0.1)

    gps_dates = query_results.get("gps_dates")
    if gps_dates:
        date_picker = dcc.DatePickerSingle(
            id="date-picker",
            min_date_allowed=min(gps_dates),
            max_date_allowed=max(gps_dates),
            disabled_days=find_missing_dates(gps_dates),
            display_format="YYYY-MM-DD",
            date=today_date(config),
            disabled=False,
        )
    else:
        td = today_date(config)
        date_picker = dcc.DatePickerSingle(
            id="date-picker",
            min_date_allowed=td,
            max_date_allowed=td,
            display_format="YYYY-MM-DD",
            date=td,
            disabled=False,
        )

    tile_url = get_tile_url(config)
    tile_subdomains = get_tile_subdomains(config, tile_url)
    tile_attribution = get_tile_attribution(config)
    tile_layer_kwargs = dict(
        url=tile_url,
        attribution=tile_attribution,
        maxZoom=map_max_zoom,
        maxNativeZoom=map_native_max_zoom,
        id="base-tile-layer",
    )
    if tile_subdomains:
        tile_layer_kwargs["subdomains"] = tile_subdomains
    log = config.get("logger")
    if log:
        log.info("Leaflet basemap tiles: %s", tile_url)

    leaflet_map = dl.Map(
        id="leaflet-map",
        center=default_center,
        zoom=default_zoom,
        maxZoom=map_max_zoom,
        minZoom=3,
        style={"width": "100%", "height": "100%"},
        preferCanvas=False,
        trackResize=True,
        zoomControl=True,
        scrollWheelZoom=True,
        children=[
            dl.TileLayer(**tile_layer_kwargs),
            dl.LayerGroup(id="community-layer"),
            dl.GeoJSON(
                id="track-geojson",
                data=empty_featurecollection(),
                pointToLayer=NS("point_to_layer"),
                onEachFeature=NS("on_each_feature"),
                hideout=default_hideout(),
            ),
            dl.LayerGroup(id="here-layer"),
        ],
    )

    return html.Div([
        html.Div([
            html.H1("Drive Map"),
            dcc.Checklist(
                options=[{"label": " Today only", "value": "today"}],
                id="today-checkbox",
                value=["today"],
            ),
        ], className="page-toolbar"),
        dcc.Interval(id="check-interval", interval=check_interval * 1000, n_intervals=0),
        dcc.Store(id="refresh-trigger", data=0),
        dcc.Store(
            id="map-state",
            data={"today_data_len": 0, "map_displayed": False, "initial_view_set": False},
        ),
        dcc.Store(id="fsm-store", data=None, storage_type="session"),
        html.Div([
            html.Div([html.Div("Date"), html.Div(date_picker)]),
            html.Div([
                html.Div("Platform"),
                html.Div(dcc.Dropdown(
                    id="platform-selector",
                    options=query_results.get("gps_platforms", []),
                    value=platform,
                    clearable=False,
                )),
            ]),
            html.Div([
                html.Div("GPS"),
                html.Div(dcc.Dropdown(
                    id="gps-selector",
                    options=query_results.get("gps_instruments", []),
                    value=gps,
                    clearable=False,
                )),
            ]),
            html.Div([
                html.Div("Instrument"),
                html.Div(dcc.Dropdown(
                    id="instrument-selector",
                    options=query_results.get("env_instruments", []),
                    value=None,
                    clearable=False,
                )),
            ]),
            html.Div([
                html.Div("Parameter"),
                html.Div(dcc.Dropdown(
                    id="parameter-selector",
                    options=query_results.get("env_parameters", []),
                    value=None,
                    clearable=False,
                )),
            ]),
            html.Div([
                html.Div("Places"),
                html.Div(dcc.Dropdown(
                    id="community-selector",
                    options=shapes,
                    value=None,
                    multi=True,
                    clearable=True,
                )),
            ]),
            html.Button("Center", id="center-button", className="map-control-button", n_clicks=0),
        ], className="map-toolbar"),
        html.Div(
            id="map-container",
            className="leaflet-map-wrapper map-container-panel",
            style={"position": "relative", "width": "100%", "height": "700px", "minHeight": "700px"},
            children=[
                leaflet_map,
                html.Div(
                    id="wind-rose-panel",
                    children=[
                        dcc.Graph(
                            id="wind-rose",
                            figure=empty_wind_rose_figure(),
                            style={"width": "100%", "height": "100%", "margin": 0},
                            config={"displayModeBar": False},
                        ),
                    ],
                ),
                html.Div(
                    id="map-status",
                    children="Loading map data…",
                ),
                html.Div(
                    id="map-colorbar-panel",
                    className="map-colorbar-panel",
                    children=colorbar_panel_children(0, 1, ""),
                ),
            ],
        ),
        html.P(f"Tiles: {tile_attribution}", className="map-attribution"),
    ], className="page-panel map-page")


def update_map_page(app, engine, config):
    global myConfig, lock, logger

    myConfig = config
    logger = config.get("logger")
    lock = Lock()
    Thread(target=requery_geo, args=(engine, config, lock), daemon=True).start()

    @app.callback(
        Output("fsm-store", "data", allow_duplicate=True),
        Output("refresh-trigger", "data", allow_duplicate=True),
        Output("map-state", "data", allow_duplicate=True),
        Output("platform-selector", "options"),
        Output("platform-selector", "value"),
        Output("gps-selector", "options"),
        Output("gps-selector", "value"),
        Output("instrument-selector", "options"),
        Output("instrument-selector", "value"),
        Output("parameter-selector", "options", allow_duplicate=True),
        Output("parameter-selector", "value", allow_duplicate=True),
        Input("check-interval", "n_intervals"),
        State("map-state", "data"),
        State("refresh-trigger", "data"),
        State("instrument-selector", "options"),
        State("fsm-store", "data"),
        prevent_initial_call=True,
    )
    def check_needs_update(_n, map_state, refresh_trigger, instrument_selector, fsm_data):
        if fsm_data:
            fsm = MapMachine.deserialize(config, json.loads(fsm_data))
        else:
            fsm = MapMachine(config)

        if fsm.state == "start":
            fsm.request_new_data(date=today_date(myConfig))
        elif fsm.state == "refresh_old_map":
            fsm.machine.set_state("wait_old_data")
        elif fsm.state == "refresh_new_map":
            fsm.machine.set_state("wait_new_data")

        idle = (
            no_update, no_update, no_update,
            no_update, no_update, no_update, no_update,
            no_update, no_update, no_update, no_update,
        )
        instruments = instrument = platforms = platform = gpss = gps = no_update
        parameters = parameter = no_update

        if fsm.state == "wait_new_data" and fsm.data_ready():
            df = fsm.get_data()
            map_state = dict(map_state) if map_state else {}
            if len(df) > map_state.get("today_data_len", 0) or not map_state.get("map_displayed"):
                inst_params = get_instruments_and_params(df)
                if map_state.get("today_data_len", 0) == 0:
                    platforms = list(inst_params["platforms"])
                    platform = platforms[0]
                    gpss = list(inst_params["gps_instruments"])
                    gps = gpss[0]
                    instruments = list(inst_params["instruments"].keys())
                    instrument = instruments[0]
                    parameters = list(inst_params["instruments"][instrument])
                    parameter = parameters[0]
                elif sorted(inst_params["instruments"].keys()) != sorted(instrument_selector or []):
                    instruments = list(inst_params["instruments"].keys())
                try:
                    fsm.data_arrived()
                except Exception as e:
                    if logger:
                        logger.debug("wait_new_data fsm.data_arrived: %s", e)
                map_state["today_data_len"] = len(df)
                return (
                    fsm.serialize(), (refresh_trigger or 0) + 1, map_state,
                    platforms, platform, gpss, gps,
                    instruments, instrument, parameters, parameter,
                )
        elif fsm.state == "wait_old_data" and fsm.data_ready():
            df = fsm.get_data()
            inst_params = get_instruments_and_params(df)
            instruments = list(inst_params["instruments"].keys())
            instrument = instruments[0]
            platforms = list(inst_params["platforms"])
            platform = platforms[0]
            gpss = list(inst_params["gps_instruments"])
            gps = gpss[0]
            parameters = list(inst_params["instruments"][instrument])
            parameter = parameters[0]
            try:
                fsm.data_arrived()
            except Exception as e:
                if logger:
                    logger.debug("wait_old_data fsm.data_arrived: %s", e)
            return (
                fsm.serialize(), (refresh_trigger or 0) + 1, no_update,
                platforms, platform, gpss, gps,
                instruments, instrument, parameters, parameter,
            )

        return (fsm.serialize(), *idle[1:])

    @app.callback(
        Output("fsm-store", "data", allow_duplicate=True),
        Output("date-picker", "disabled"),
        Output("refresh-trigger", "data", allow_duplicate=True),
        Output("date-picker", "date"),
        Output("map-status", "children", allow_duplicate=True),
        Input("today-checkbox", "value"),
        Input("date-picker", "date"),
        State("refresh-trigger", "data"),
        State("fsm-store", "data"),
        prevent_initial_call=True,
    )
    def date_change(today, date_val, refresh, fsm_data):
        if fsm_data:
            fsm = MapMachine.deserialize(config, json.loads(fsm_data))
        else:
            fsm = MapMachine(config)
        if fsm.state == "start":
            return fsm.serialize(), no_update, no_update, no_update, no_update

        picker_date = datetime.strptime(date_val, "%Y-%m-%d").date()
        date_changed_to = no_update
        disable_date_picker = no_update

        for t in ctx.triggered:
            if "date-picker" in t["prop_id"]:
                try:
                    fsm.date_selector_changed(date=picker_date)
                except Exception as e:
                    if logger:
                        logger.debug("fsm.date_selector_changed: %s", e)
            if "today-checkbox" in t["prop_id"]:
                if today == ["today"]:
                    disable_date_picker = True
                    td = today_date(myConfig)
                    fsm.date_selector_changed(date=td)
                    date_changed_to = td
                else:
                    fsm.date_selector_changed(date=picker_date)
                    date_changed_to = picker_date

        if date_changed_to is not no_update:
            return (
                fsm.serialize(), disable_date_picker,
                (refresh or 0) + 1, date_changed_to, "Loading data…",
            )
        return fsm.serialize(), no_update, no_update, no_update, no_update

    @app.callback(
        Output("fsm-store", "data", allow_duplicate=True),
        Output("track-geojson", "data"),
        Output("track-geojson", "hideout"),
        Output("here-layer", "children"),
        Output("community-layer", "children"),
        Output("map-colorbar-panel", "children"),
        Output("wind-rose", "figure"),
        Output("map-state", "data", allow_duplicate=True),
        Output("leaflet-map", "viewport"),
        Output("map-status", "children"),
        Input("refresh-trigger", "data"),
        Input("platform-selector", "value"),
        Input("gps-selector", "value"),
        Input("parameter-selector", "value"),
        Input("community-selector", "value"),
        State("instrument-selector", "value"),
        State("date-picker", "date"),
        State("map-state", "data"),
        State("fsm-store", "data"),
        prevent_initial_call=True,
    )
    def update_map(
        _refresh, sel_platform, sel_gps, sel_parameter, sel_community,
        sel_instrument, date_val, map_state, fsm_data,
    ):
        spy_time = datetime.now()
        parameter_changed = any(
            t["prop_id"] == "parameter-selector.value" for t in ctx.triggered
        )

        if not fsm_data:
            raise PreventUpdate
        fsm = MapMachine.deserialize(config, json.loads(fsm_data))

        if (not parameter_changed) and ("wait" in fsm.state):
            raise PreventUpdate

        if ":" in str(date_val):
            picker_date = datetime.strptime(str(date_val), "%Y-%m-%dT%H:%M:%S").date()
        else:
            picker_date = datetime.strptime(str(date_val), "%Y-%m-%d").date()
        fsm.date = picker_date

        df = fsm.get_data()
        empty_return = (
            fsm.serialize(),
            empty_featurecollection(),
            default_hideout(),
            [], no_update,
            colorbar_panel_children(0, 1, ""),
            no_update,
            dict(map_state) if map_state else {},
            no_update,
            "No data",
        )

        if not isinstance(df, pd.DataFrame) or len(df) == 0:
            return empty_return

        filtered = df[
            (df["platform"] == sel_platform)
            & (df["parameter"] == sel_parameter)
            & (df["gps"] == sel_gps)
            & (df["instrument"] == sel_instrument)
        ].sort_index()

        n_pts = len(filtered)
        if logger:
            logger.debug(
                "update_map: %d points %s/%s (%.3fs)",
                n_pts, sel_instrument, sel_parameter,
                (datetime.now() - spy_time).total_seconds(),
            )

        if n_pts == 0:
            ms = dict(map_state) if map_state else {}
            ms["map_displayed"] = False
            return (
                fsm.serialize(),
                empty_featurecollection(),
                default_hideout(),
                [], no_update,
                colorbar_panel_children(0, 1, ""),
                no_update,
                ms, no_update,
                "No points for this selection",
            )

        lower = float(filtered["value"].quantile(0.05))
        upper = float(filtered["value"].quantile(0.95))
        if not (np.isfinite(lower) and np.isfinite(upper)) or upper <= lower:
            lower = float(filtered["value"].min())
            upper = float(filtered["value"].max())
            if upper <= lower:
                upper = lower + 1.0
        units = filtered["unit"].dropna().unique()
        unit_str = units[0] if len(units) else ""

        fc = df_to_featurecollection(filtered, sel_parameter)
        hideout = dict(
            min=lower,
            max=upper,
            colorscale=VIRIDIS_HEX,
            circleOptions=dict(radius=4, weight=0, fillOpacity=0.85),
        )

        last = df.iloc[-1]
        here_children = [
            dl.CircleMarker(
                center=[float(last["latitude"]), float(last["longitude"])],
                radius=10,
                color="red",
                fillColor="red",
                fillOpacity=0.9,
                weight=2,
                children=[dl.Tooltip("You are here")],
            ),
        ]

        community_children = load_community_geojson(config, sel_community or [])
        wind_fig = build_wind_rose_figure(config, df) or empty_wind_rose_figure()

        map_state = dict(map_state) if map_state else {}
        viewport_update = no_update
        if not map_state.get("initial_view_set"):
            center, zoom = calculate_initial_view(filtered, config)
            viewport_update = dict(center=center, zoom=zoom, transition="flyTo")
            map_state["initial_view_set"] = True
        map_state["map_displayed"] = True

        if "wait" not in fsm.state:
            try:
                fsm.map_refreshed()
            except Exception as e:
                if logger:
                    logger.debug("fsm.map_refreshed: %s", e)

        status = f"{n_pts} points · {sel_parameter} ({unit_str})"
        return (
            fsm.serialize(),
            fc, hideout, here_children, community_children,
            colorbar_panel_children(lower, upper, unit_str),
            wind_fig,
            map_state, viewport_update, status,
        )

    @app.callback(
        Output("leaflet-map", "viewport", allow_duplicate=True),
        Input("center-button", "n_clicks"),
        State("fsm-store", "data"),
        State("leaflet-map", "viewport"),
        prevent_initial_call=True,
    )
    def center_map(_n, fsm_data, current_viewport):
        if not fsm_data:
            raise PreventUpdate
        fsm = MapMachine.deserialize(config, json.loads(fsm_data))
        df = fsm.get_data()
        if not (isinstance(df, pd.DataFrame) and len(df) > 0):
            raise PreventUpdate
        last = df.iloc[-1]
        zoom = (current_viewport or {}).get("zoom", 14)
        return dict(
            center=[float(last["latitude"]), float(last["longitude"])],
            zoom=zoom,
            transition="flyTo",
        )

    @app.callback(
        Output("parameter-selector", "options", allow_duplicate=True),
        Output("parameter-selector", "value", allow_duplicate=True),
        Input("instrument-selector", "value"),
        State("fsm-store", "data"),
        prevent_initial_call=True,
    )
    def set_instrument_param_options(instrument, fsm_data):
        if fsm_data:
            fsm = MapMachine.deserialize(config, json.loads(fsm_data))
        else:
            fsm = MapMachine(config)
        df = fsm.get_data()
        if df is not None and len(df) > 0 and instrument:
            inst_params = get_instruments_and_params(df)
            params = inst_params["instruments"].get(instrument)
            if params is not None and len(params) > 0:
                return list(params), params[0]
        raise PreventUpdate

    app.clientside_callback(
        """
        function(tab) {
            if (tab !== "map-display") {
                return window.dash_clientside.no_update;
            }
            setTimeout(function() {
                window.dispatchEvent(new Event("resize"));
                document.querySelectorAll(".leaflet-control-colorbar").forEach(function(el) {
                    el.remove();
                });
                document.querySelectorAll(".leaflet-top.leaflet-left .leaflet-control").forEach(function(el) {
                    if (!el.classList.contains("leaflet-control-zoom")) {
                        el.remove();
                    }
                });
            }, 350);
            return Date.now();
        }
        """,
        Output("leaflet-map", "invalidateSize"),
        Input("tabs", "value"),
        prevent_initial_call=False,
    )

    app.clientside_callback(
        """
        function(tab) {
            if (tab !== "map-display") {
                return window.dash_clientside.no_update;
            }
            var host = window.location.hostname || "192.168.10.5";
            return "http://" + host + ":8080/styles/norcal/{z}/{x}/{y}.png";
        }
        """,
        Output("base-tile-layer", "url"),
        Input("tabs", "value"),
        prevent_initial_call=False,
    )

    if logger:
        logger.info("Dash_Mapper_Leaflet: canvas track + FSM loaded")


def requery_geo(engine, config, thread_lock):
    global query_results
    query_results = {}
    local_tz = pytz.timezone(config.get("display_timezone", "UTC"))
    tz_name = config.get("display_timezone", "UTC")

    gf = get_geolocations(engine, config, timezone=tz_name)
    if gf.empty:
        query_results["gps_dates"] = []
        return

    query_results.update({
        "gps_dates": [
            datetime.fromordinal(d.toordinal())
            for d in gf["sample_time"].dt.date.unique()
        ],
        "gps_instruments": gf["instrument"].unique(),
        "gps_platforms": gf["platform"].unique(),
        "all_geolocations": gf,
        "data": {today_date(config): None},
    })

    full_refresh_counter = FULL_REFRESH_EVERY
    instruments = instruments_for_map_query(config)

    while True:
        today = today_date(config)
        with thread_lock:
            if today not in query_results["data"]:
                query_results["data"][today] = None

        if query_results["data"].get(today) is not None:
            first_time = local_tz.localize(
                datetime(today.year, today.month, today.day, 0, 0, 0),
            ).astimezone(pytz.utc)
            day_end_time = today_end_time(config)
            last_time = local_tz.localize(
                datetime(
                    today.year, today.month, today.day,
                    day_end_time.hour, day_end_time.minute, day_end_time.second,
                ),
            ).astimezone(pytz.utc)

            full_refresh_counter -= 1
            full_refresh = full_refresh_counter <= 0
            cached = query_results["data"][today]
            if day_cache_missing_wind(config, cached):
                full_refresh = True
            if full_refresh:
                full_refresh_counter = FULL_REFRESH_EVERY
            elif isinstance(cached, pd.DataFrame) and not cached.empty:
                first_time = cached["sample_time"].max().astimezone(pytz.utc) + timedelta(seconds=1)

            df = get_measurements_with_alarms_and_locations(
                engine,
                start_time=first_time,
                end_time=last_time,
                instruments=instruments,
                platform=None,
                gps_instrument=None,
                acquisition_type="measurement_calibrated,measurement_raw",
            )

            if len(df) > 0:
                df["sample_time"] = (
                    df["sample_time"].dt.tz_localize("UTC").dt.tz_convert(tz_name)
                )
                df.set_index("sample_time", inplace=True, drop=False)
                with thread_lock:
                    if not full_refresh:
                        query_results["data"][today] = pd.concat(
                            [query_results["data"][today], df],
                        )
                    else:
                        query_results["data"][today] = df
                    inst = get_instruments_and_params(query_results["data"][today])
                    query_results["env_instruments"] = list(inst["instruments"].keys())

        with thread_lock:
            empty_days = [
                d for d, v in query_results["data"].items()
                if v is None or day_cache_missing_wind(config, v)
            ]
        for day in empty_days:
            first_time = local_tz.localize(
                datetime(day.year, day.month, day.day, 0, 0, 0),
            ).astimezone(pytz.utc)
            day_end_time = today_end_time(config)
            last_time = local_tz.localize(
                datetime(
                    day.year, day.month, day.day,
                    day_end_time.hour, day_end_time.minute, day_end_time.second,
                ),
            ).astimezone(pytz.utc)
            df = get_measurements_with_alarms_and_locations(
                engine,
                start_time=first_time,
                end_time=last_time,
                instruments=instruments,
                platform=None,
                gps_instrument=None,
                acquisition_type="measurement_calibrated,measurement_raw",
            )
            if not df.empty:
                df["sample_time"] = (
                    df["sample_time"].dt.tz_localize("UTC").dt.tz_convert(tz_name)
                )
                df.set_index("sample_time", inplace=True, drop=False)
                with thread_lock:
                    query_results["data"][day] = df

        time.sleep(config["mapping"].get("map_check_secs", 3))
