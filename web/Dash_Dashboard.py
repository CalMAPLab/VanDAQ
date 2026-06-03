"""

VanDAQ
Mobile Atmospheric Data Acquisition System

Author: Robert Jay (Robin) Weber
Affiliation: University of California, Berkeley

Copyright (c) 2025 The Regents of the University of California
Released under the BSD 3-Clause License.
"""

from dash import dcc, html, Input, Output, ALL, MATCH, ctx, State, dash_table, no_update
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
from dash.exceptions import PreventUpdate
from numpy import isnan
import plotly.graph_objs as go
import pandas as pd
import datetime
import time
import copy
import json
from threading import Thread, Lock
#from vandaq_measurements_query import get_measurements
from vandaq_2step_measurements_query import get_2step_query_with_alarms
from vandaq_2step_measurements_query import transform_instrument_dataframe
from sqlalchemy import text



sample_time = datetime.datetime.now()

config = None
engine = None

active_zoom_instrument = None

# Periodic full 5-minute SQL refresh to correct drift (~150 cycles at 2s refresh)
DASHBOARD_FULL_REFRESH_EVERY = 150


def dashboard_window_minutes(config):
    return config.get('dashboard_window_minutes', 5)


def get_last_valid_value(df, column):
    # Get the last valid (non-NaN) value in the specified column
    # Ensure the column exists and is not empty
    if column not in df or df[column].empty:
        return None
    # Drop NaNs and get the last value if possible
    valid_values = df[column].dropna()
    if not valid_values.empty:
        return valid_values.iloc[-1]
    return None

def _apply_display_timezone(df, config):
    if len(df) > 0 and config.get('display_timezone'):
        df['sample_time'] = (
            df['sample_time'].dt.tz_localize('UTC').dt.tz_convert(config['display_timezone'])
        )
        df.set_index('sample_time', inplace=True, drop=False)
    return df


def _trim_to_dashboard_window(df, config):
    """Keep rows within dashboard_window_minutes (UTC naive, pre-display-tz)."""
    if df is None or len(df) == 0:
        return df
    minutes = dashboard_window_minutes(config)
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=minutes)
    st = df['sample_time']
    if hasattr(st.dt, 'tz') and st.dt.tz is not None:
        cutoff = pd.Timestamp(cutoff, tz='UTC').tz_convert(st.dt.tz)
    return df[df['sample_time'] >= cutoff].copy()


def refresh_measurement_cache(engine, config, cached_df=None, force_full=False):
    """
    Read-only incremental fetch: full 5-minute window on cold start, then only new rows.
    Uses existing get_2step_query_with_alarms SELECT only (no schema or write changes).
    """
    st_time = datetime.datetime.now()
    now = datetime.datetime.utcnow()
    window_start = now - datetime.timedelta(minutes=dashboard_window_minutes(config))
    include_engineering = config.get('include_engineering', True)

    if force_full or cached_df is None or len(cached_df) == 0:
        df_new = get_2step_query_with_alarms(
            engine, window_start, end_time=now, wide=False,
            include_engineering=include_engineering,
        )
        merged = df_new
        query_mode = 'full'
    else:
        max_ts = cached_df['sample_time'].max()
        if hasattr(max_ts, 'tzinfo') and max_ts.tzinfo is not None:
            since = max_ts.to_pydatetime() + datetime.timedelta(seconds=1)
        else:
            since = max_ts + datetime.timedelta(seconds=1)
        df_new = get_2step_query_with_alarms(
            engine, since, end_time=now, wide=False,
            include_engineering=include_engineering,
        )
        if len(df_new) == 0:
            merged = cached_df
        elif 'id' in cached_df.columns and 'id' in df_new.columns:
            merged = pd.concat([cached_df, df_new], ignore_index=True)
            merged = merged.drop_duplicates(subset=['id'], keep='last')
        else:
            merged = pd.concat([cached_df, df_new], ignore_index=True)
            merged = merged.drop_duplicates(
                subset=['sample_time', 'instrument', 'parameter', 'acquisition_type'],
                keep='last',
            )
        query_mode = 'incremental'

    merged = _trim_to_dashboard_window(merged, config)
    cache_df_utc = merged.copy()
    display_df = _apply_display_timezone(merged.copy(), config)
    data = transform_instrument_dataframe(display_df)
    elapsed = (datetime.datetime.now() - st_time).total_seconds()
    log = config.get('logger')
    if log:
        log.info(
            'Dashboard: refresh_measurement_cache %s query returned %d rows (%.3fs)',
            query_mode, len(display_df), elapsed,
        )
    return data, display_df, cache_df_utc


def get_instrument_measurements(engine, config, cached_df=None, force_full=False):
    data, display_df, _cache_df_utc = refresh_measurement_cache(
        engine, config, cached_df=cached_df, force_full=force_full,
    )
    return data, display_df

graph_line_colors = [
    "#2563eb",
    "#dc2626",
    "#059669",
    "#7c3aed",
    "#d97706",
]

PLOT_AXIS_TICK_SIZE = 13


def param_alarm_level(measurements):
    if measurements is None or "max_alarm_level" not in measurements.columns:
        return 0
    recent = measurements["max_alarm_level"].dropna()
    if recent.empty:
        return 0
    return int(recent.tail(20).max())


def max_alarm_from_parameters(parameters):
    level = 0
    for param in parameters:
        level = max(level, param_alarm_level(param.get("measurements")))
    return level


def alarm_badge(level):
    if level >= 2:
        return html.Span("ALARM", className="alarm-badge alarm-badge--critical")
    if level >= 1:
        return html.Span("WARNING", className="alarm-badge alarm-badge--warning")
    return None


def legend_item(color, label, alarm_level=0):
    parts = [html.Span(className="legend-swatch", style={"backgroundColor": color})]
    if alarm_level >= 2:
        parts.append(html.Span(className="legend-alarm-dot legend-alarm-dot--critical", title="Alarm"))
    elif alarm_level >= 1:
        parts.append(html.Span(className="legend-alarm-dot legend-alarm-dot--warning", title="Warning"))
    parts.append(html.Span(label.replace("_", " "), className="legend-label"))
    return html.Span(parts, className="legend-item")


def build_trace_legend(graph_data):
    if not graph_data:
        return None
    return html.Div(
        [
            legend_item(
                graph_line_colors[i % len(graph_line_colors)],
                g["parameter"],
                alarm_level=param_alarm_level(g.get("measurements")),
            )
            for i, g in enumerate(graph_data)
        ],
        className="cell-legend-row",
    )


def build_cell_header(title, graph_data=None, alarm_level=0):
    """Instrument title, status badge, and trace legend on one row."""
    row = [html.H2(title.replace("_", " "))]
    badge = alarm_badge(alarm_level)
    if badge is not None:
        row.append(badge)
    legend = build_trace_legend(graph_data)
    if legend is not None:
        row.append(legend)
    return html.Div(row, className="cell-header-row")


def build_spectrum_cell_header(title):
    return html.Div(
        [html.H2(title.replace("_", " "))],
        className="cell-header-row",
    )


def is_consistently_increasing(column):
    """
    Test if a Pandas Series of datetimes consistently increases.
    """
    diffs = column.diff().total_seconds().dropna()
    return (diffs >= 0).all()  # No negative differences


def create_trend_plot(instrument_data_list, config, zoomed=False, show_axes=False, separate_scales=False):
    graphs = []
    shapes = []
    num_traces = len(instrument_data_list)

    if num_traces == 0:
        return go.Figure(
            layout=go.Layout(
                margin=dict(l=4, r=4, t=4, b=4),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            ),
        )

    # Define y-axis domains dynamically if using separate scales
    if separate_scales and num_traces > 0:
        y_axis_domains = [(i / num_traces, (i + 1) / num_traces) for i in range(num_traces)]
    else:
        y_axis_domains = [(0, 1)]
        separate_scales = False

    for i, instrument_data in enumerate(instrument_data_list):
        name = instrument_data['parameter']
        data = instrument_data['measurements']
        graphdata = data[['value']].dropna(axis='index')

        if not is_consistently_increasing(data.index):
            print('Got a hairball!')

        # Define a unique y-axis name (e.g., 'y2', 'y3', ...)
        y_axis_name = f"y{i+1}" if separate_scales else "y"

        # Create line plot with assigned y-axis
        graph = go.Scatter(
            x=graphdata.index,
            y=graphdata['value'],
            text=name,
            mode="lines",
            line=dict(color=graph_line_colors[i]),
            yaxis=y_axis_name
        )
        graphs.append(graph)

        # Add background shapes for alarm levels
        if config.get('alarm_shapes', False) and 'max_alarm_level' in data.columns:
            alarm_intervals = data[data['max_alarm_level'] > 0]
            for idx, row in alarm_intervals.iterrows():
                color = (
                    "rgba(220, 38, 38, 0.22)"
                    if row["max_alarm_level"] == 2
                    else "rgba(217, 119, 6, 0.2)"
                )
                shapes.append({
                    'type': 'rect',
                    'xref': 'x',
                    'yref': y_axis_name,
                    'x0': idx,
                    'x1': idx + pd.Timedelta(seconds=1),
                    'y0': graphdata['value'].min(),
                    'y1': graphdata['value'].max(),
                    'fillcolor': color,
                    'opacity': 0.6,
                    'layer': 'below',
                    'line_width': 0
                })

    tick_font = dict(color="#5c6b7a", size=PLOT_AXIS_TICK_SIZE)
    axis_style = dict(
        visible=show_axes,
        showgrid=True,
        gridcolor="rgba(0,0,0,0.06)",
        tickfont=tick_font,
        linecolor="#d8dee6",
    )
    plot_margin = dict(l=8, r=52, t=8, b=32) if show_axes else dict(l=4, r=4, t=4, b=4)
    layout = go.Layout(
        margin=plot_margin,
        xaxis=dict(**axis_style),
        yaxis=dict(**axis_style, side="right"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        shapes=shapes,
        showlegend=False,
    )

    # Dynamically add additional y-axes for separate scales
    if separate_scales:
        layout.yaxis = dict(
            domain=y_axis_domains[0],
            side="right",
            showgrid=True,
            gridcolor="rgba(0,0,0,0.06)",
            tickfont=tick_font,
            linecolor="#d8dee6",
        )
        for i, domain in enumerate(y_axis_domains[1:], start=1):
            layout[f"yaxis{i+1}"] = dict(
                domain=domain,
                side="right",
                showgrid=True,
                gridcolor="rgba(0,0,0,0.06)",
                tickfont=tick_font,
                linecolor="#d8dee6",
                anchor="x",
            )

    return go.Figure(graphs, layout)


def _dp_from_psd_parameter(parameter: str):
    if not parameter.startswith("dN_") or not parameter.endswith("_nm"):
        return None
    core = parameter[3:-3].replace("p", ".")
    try:
        return float(core)
    except ValueError:
        return None


def _spectrum_rows_to_scan(sample_time, rows):
    scan_id = None
    n_tot = None
    diameters = []
    values = []
    for param, val, _, s in rows:
        if param == "scan_id" and s:
            scan_id = s
            continue
        if param == "N_tot":
            n_tot = val
            continue
        dp = _dp_from_psd_parameter(param)
        if dp is None:
            continue
        diameters.append(dp)
        values.append(val)
    if not diameters:
        return None
    order = sorted(range(len(diameters)), key=lambda i: diameters[i])
    return {
        "sample_time": sample_time,
        "scan_id": scan_id,
        "n_tot": n_tot,
        "diameters": [diameters[i] for i in order],
        "values": [values[i] for i in order],
    }


def fetch_recent_spectra(engine, instrument: str, config, num_scans=5):
    """Last N inverted PSD scans within the dashboard time window (oldest first)."""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(
        minutes=dashboard_window_minutes(config),
    )
    sql = text("""
        SELECT p.parameter, m.value, m.sample_time, m.string
        FROM measurement m
        JOIN instrument i ON m.instrument_id = i.id
        JOIN parameter p ON m.parameter_id = p.id
        WHERE i.instrument = :instrument
          AND m.sample_time >= :cutoff
          AND m.sample_time IN (
            SELECT sample_time FROM (
              SELECT DISTINCT m3.sample_time AS sample_time
              FROM measurement m3
              JOIN instrument i3 ON m3.instrument_id = i3.id
              WHERE i3.instrument = :instrument
                AND m3.sample_time >= :cutoff
              ORDER BY sample_time DESC
              LIMIT :num_scans
            ) recent
          )
        ORDER BY m.sample_time ASC
    """)
    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {"instrument": instrument, "cutoff": cutoff, "num_scans": num_scans},
        ).fetchall()
    if not rows:
        return []

    by_time = {}
    for param, val, sample_time, s in rows:
        by_time.setdefault(sample_time, []).append((param, val, sample_time, s))

    scans = []
    for sample_time in sorted(by_time.keys()):
        scan = _spectrum_rows_to_scan(sample_time, by_time[sample_time])
        if scan:
            scans.append(scan)
    return scans


def _spectrum_scan_label(scan, config):
    label = scan.get("scan_id") or "scan"
    st = scan["sample_time"]
    if config.get("display_timezone"):
        try:
            st = pd.Timestamp(st, tz="UTC").tz_convert(config["display_timezone"])
        except Exception:
            pass
    if hasattr(st, "strftime"):
        label = f"{label} {st.strftime('%H:%M:%S')}"
    return label


SPECTRUM_HISTORY_COLOR = "#b8c4d0"
SPECTRUM_LATEST_COLOR = graph_line_colors[0]


def create_spectrum_plot(scans, config, show_axes=True):
    tick_font = dict(color="#5c6b7a", size=PLOT_AXIS_TICK_SIZE)
    axis_style = dict(
        visible=show_axes,
        showgrid=True,
        gridcolor="rgba(0,0,0,0.06)",
        tickfont=tick_font,
        linecolor="#d8dee6",
    )
    traces = []
    for i, scan in enumerate(scans):
        is_latest = i == len(scans) - 1
        color = SPECTRUM_LATEST_COLOR if is_latest else SPECTRUM_HISTORY_COLOR
        width = 2.5 if is_latest else 1.5
        traces.append(
            go.Scatter(
                x=scan["diameters"],
                y=scan["values"],
                mode="lines+markers",
                line=dict(color=color, width=width),
                marker=dict(size=3 if is_latest else 2, color=color),
                showlegend=False,
                hovertemplate=(
                    f"{_spectrum_scan_label(scan, config)}<br>"
                    "Dp=%{x:.2f} nm<br>"
                    "dN/dlog10Dp=%{y:.2f}<extra></extra>"
                ),
            )
        )
    layout = go.Layout(
        margin=dict(l=8, r=52, t=8, b=40) if show_axes else dict(l=4, r=4, t=4, b=4),
        xaxis=dict(**axis_style, type="log", title="Dp (nm)"),
        yaxis=dict(**axis_style, side="right", title="dN/dlog10Dp (1/cm³)"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    return go.Figure(traces, layout)


def create_grid_cell(graph, header_content, instrument=None, alarm_level=0):
    """Instrument card: labels in header above chart (no overlay on data)."""
    if instrument:
        cell_id = {'type': 'instrument_cell', 'index': instrument}
    else:
        cell_id = None
    class_name = 'instrument_cell'
    if alarm_level >= 2:
        class_name += ' instrument-cell--alarm'
    elif alarm_level >= 1:
        class_name += ' instrument-cell--warning'
    header_class = 'cell-header'
    if alarm_level >= 2:
        header_class += ' cell-header--alarm'
    elif alarm_level >= 1:
        header_class += ' cell-header--warning'
    if graph:
        graph_cell = dcc.Graph(
            figure=graph,
            config={"displayModeBar": False},
            style={"height": "100%", "width": "100%"},
        )
    else:
        graph_cell = html.Div(className="cell-chart-empty")
    cell_children = [
        html.Div(children=header_content, className=header_class),
        html.Div(graph_cell, className="cell-chart"),
    ]
    if cell_id:
        return html.Div(id=cell_id, className=class_name, children=cell_children)
    return html.Div(className=class_name, children=cell_children)

flashing_text = {
            "outline": "2px solid red",    # Red outline
            "display": "inline-block",    # Ensures outline hugs the text
            "padding": "5px",             # Optional spacing
            "animation": "flash 1s infinite"  # Flash animation
        }

# Function that returns a list of objects (in this case, strings)
def build_page_contents(engine, config, measurements = None, dataFrame = None, zoom_to_instrument = None):
    global sample_time 
    show_mute_instruments = config.get('show_mute_instruments')
    instruments = []
    if measurements is None:
        measurements, dataFrame = get_instrument_measurements(engine,config)
    if show_mute_instruments:
        instruments = list(config['display_params'].keys())
    else:
        instruments = [list(m.keys())[0] for m in measurements]
    items = []
    if not zoom_to_instrument:
        for inst in instruments:
            inst_cfg = config['display_params'].get(inst, {})
            if inst_cfg.get('spectrum'):
                num_scans = inst_cfg.get('spectrum_num_scans', 5)
                scans = fetch_recent_spectra(engine, inst, config, num_scans=num_scans)
                if scans:
                    graph = create_spectrum_plot(scans, config)
                    header = build_spectrum_cell_header(inst)
                    sample_time = scans[-1]['sample_time']
                    items.append(create_grid_cell(graph, header, instrument=inst))
                else:
                    no_data_header = build_cell_header(inst, alarm_level=2)
                    items.append(create_grid_cell(
                        None,
                        html.Div([no_data_header, html.Span('NO DATA', className='no-data-badge')],
                                 className='no_data_label'),
                        alarm_level=2,
                    ))
                continue
            instrument = [i for i in measurements if i.get(inst)]
            if not instrument:
                instrument_text = inst
                no_data_header = build_cell_header(inst, alarm_level=2)
                items.append(create_grid_cell(
                    None,
                    html.Div([no_data_header, html.Span('NO DATA', className='no-data-badge')],
                             className='no_data_label'),
                    alarm_level=2,
                ))
            else:
                instrument = instrument[0]
                instrument_text = list(instrument.keys())[0]
                if instrument_text in config['display_params']:
                    graph_params = config['display_params'][instrument_text]['graph']
                    graph_data = [
                        {'parameter': param['parameter'], 'measurements': param['measurements']}
                        for param in instrument[instrument_text]
                        if param['parameter'] in graph_params
                        and len(param['measurements'][['value']].dropna()) > 0
                    ]
                    separate_scales = config['display_params'][instrument_text].get('separate_scales', False)
                    graph = (
                        create_trend_plot(graph_data, config, show_axes=True, separate_scales=separate_scales)
                        if graph_data else None
                    )
                    alarm_level = max_alarm_from_parameters(instrument[instrument_text])
                    header = build_cell_header(
                        instrument_text, graph_data=graph_data, alarm_level=alarm_level,
                    )
                    for parameter in instrument[instrument_text]:
                        sample_time = get_last_valid_value(
                            parameter['measurements'], 'sample_time',
                        )
                    items.append(
                        create_grid_cell(
                            graph, header, instrument=instrument_text, alarm_level=alarm_level,
                        ),
                    )
    else:
        inst_measurements = [m for m in measurements if zoom_to_instrument in m.keys()][0][zoom_to_instrument]
        items.append(html.Div(children=[html.H2(zoom_to_instrument.replace('_',' ')),html.Button('<--Back', id='zoom_back_button', n_clicks=0)]))
        for parameter in inst_measurements:
            if get_last_valid_value(parameter['measurements'],'value') is None:
                continue
            parameter_text = parameter['parameter']
            aqu_type_text = parameter['acquisition_type']
            #graph_params = config['display_params'][instrument_text]['graph']
            graph_data = [{'parameter': parameter_text, 'measurements': parameter['measurements']}]
            graph = create_trend_plot(graph_data, config, show_axes=True)
            alarm_level = param_alarm_level(parameter['measurements'])
            header = build_cell_header(
                parameter_text, graph_data=graph_data, alarm_level=alarm_level,
            )
            sample_time = get_last_valid_value(parameter['measurements'], 'sample_time')
            items.append(create_grid_cell(graph, header, alarm_level=alarm_level))

    return items, sample_time, dataFrame, measurements


# Layout for the dashboard page
def layout_dashboard(config):
    global latest_pages
    refresh_secs = config.get('dashboard_refresh_secs', 2)
    if latest_pages:
        content = latest_pages['dashboard']
    else:
        content = ['Awaiting data...']
    layout = html.Div([
        dcc.Interval(id='interval', interval=refresh_secs * 1000, n_intervals=0),
        dcc.Store(id="cache-timestamp", data=None),
        dcc.Store(id="instrument_zoom", data=None),
        html.Div([
            html.H1('VanDAQ Operator Dashboard', id='clickhere', n_clicks=0),
            html.Div('', id='sample_timestamp', className='sample-timestamp'),
            dcc.Checklist(
                options=[{'label': ' Freeze updates', 'value': 'suspend'}],
                id='suspend-dashboard_updates',
                value=[],
                className='dashboard-freeze',
            ),
        ], className='page-toolbar'),
        html.Div(id='grid-container', children=content),
    ], className='page-panel dashboard-page')
    return layout


latest_pages = None
latest_page_time = None
latest_sample_time = None
latest_data_frame = None
latest_cache_df_utc = None
latest_measurements_dict = None


def update_dashboard(app, engine, config):

    global logger
    logger = config['logger']
    lock = Lock()
    Thread(target=regenerate_pages, args=(engine, config, lock), daemon=True).start()

    @app.callback(
        Output('instrument_zoom', 'data'),
        Output('grid-container', 'children', allow_duplicate=True),
        Input({'type': 'instrument_cell', 'index': ALL}, 'n_clicks'),
        prevent_initial_call=True
    )
    def instrument_cell_clicked(clicks1):
        global latest_pages, latest_measurements_dict, latest_data_frame, active_zoom_instrument
        logger.debug(f'Dashboard:  Got to instrument_cell_clicked: {datetime.datetime.now()}')
        for t in ctx.triggered:
            if t['value']:
                tr = json.loads(t['prop_id'].replace('.n_clicks',''))
                instrument = tr['index']
                with lock:
                    if latest_pages and instrument in latest_pages:
                        page = latest_pages[instrument]
                    elif latest_measurements_dict is not None:
                        page, _, _, _ = build_page_contents(
                            engine, config,
                            measurements=latest_measurements_dict,
                            dataFrame=latest_data_frame,
                            zoom_to_instrument=instrument,
                        )
                        latest_pages[instrument] = page
                    else:
                        raise PreventUpdate
                active_zoom_instrument = instrument
                return instrument, page
        logger.debug(f'Returning from instrument_cell_clicked: {datetime.datetime.now()}')

        raise PreventUpdate

    @app.callback(
        Output('instrument_zoom', 'data', allow_duplicate=True),
        Output('grid-container', 'children', allow_duplicate=True),
        Input('zoom_back_button', 'n_clicks'),
        prevent_initial_call=True    
    )
    def zoom_back_clicked(clicks):
        global latest_pages, active_zoom_instrument
        logger.debug(f'Dashboard:  Got to zoom_back_clicked: {datetime.datetime.now()}')
        if clicks > 0:
            with lock:
                if not latest_pages or 'dashboard' not in latest_pages:
                    raise PreventUpdate
                page = latest_pages['dashboard']
            active_zoom_instrument = None
            logger.debug(f'Dashboard:  Returning from zoom_back_clicked: {datetime.datetime.now()}')
            return None, page
        raise PreventUpdate

    
    @app.callback(
        [
            Output('grid-container', 'children'),
            Output('sample_timestamp', 'children'),
            Output("cache-timestamp", "data"),
        ],
        [
            Input("interval", "n_intervals"),
            State('instrument_zoom', 'data'),
            State('suspend-dashboard_updates', 'value'),
            State("cache-timestamp", "data")
        ],
        prevent_initial_call=False
    )
    def update_page(n_intervals, instrument_zoom, suspend_updates, last_seen_timestamp):
        global latest_pages
        global latest_page_time
        global latest_sample_time
        global latest_measurements_dict
        
        #print(f'In dash update_page {datetime.datetime.now()}')                
        logger.debug(f'Dashboard:  Got to update_page: {datetime.datetime.now()}')

        if 'suspend' in suspend_updates:
            raise PreventUpdate
        else:
            if isinstance(last_seen_timestamp, str):
                try:
                    last_seen_timestamp = datetime.datetime.fromisoformat(last_seen_timestamp)
                except ValueError:
                    last_seen_timestamp = datetime.datetime.strptime(
                        last_seen_timestamp, '%Y-%m-%dT%H:%M:%S.%f',
                    )
            with lock:
                cached_timestamp = latest_page_time
                pages = latest_pages
            if cached_timestamp and pages and 'dashboard' in pages and (
                (last_seen_timestamp is None) or (cached_timestamp > last_seen_timestamp)
            ):
                items = pages['dashboard']
                cached_sample_time = latest_sample_time
                if isinstance(cached_sample_time, datetime.datetime):
                    sample_timestamp = f'Last sample time: {cached_sample_time.strftime("%m/%d/%Y, %H:%M:%S")}'
                else:
                    sample_timestamp = ''
                if instrument_zoom and instrument_zoom in pages:
                    items = pages[instrument_zoom]                
                                
                #print(f'Returning updated page {instrument_zoom}')
                logger.debug(f'Dashboard:  Returning from to update_page -- page updated: {datetime.datetime.now()}')
                ts_out = (
                    cached_timestamp.isoformat()
                    if isinstance(cached_timestamp, datetime.datetime)
                    else cached_timestamp
                )
                return items, sample_timestamp, ts_out

        #print(f'Preventing update {datetime.datetime.now()}')                
        logger.debug(f'Dashboard:  Returning from to update_page -- no update: {datetime.datetime.now()}')
        return no_update, no_update, no_update
        #raise PreventUpdate


# Periodically regenerate the page content in the background
def regenerate_pages(engine, config, lock):
    global latest_pages, latest_page_time, latest_sample_time
    global latest_data_frame, latest_cache_df_utc, latest_measurements_dict
    global active_zoom_instrument

    log = config.get('logger')
    if log:
        log.info('Dashboard: regenerate_pages: Starting background page regeneration thread')
    cycle = 0
    consecutive_query_failures = 0
    while True:
        cycle += 1
        st_time = datetime.datetime.now()
        with lock:
            cached_utc = latest_cache_df_utc
            zoom_inst = active_zoom_instrument

        force_full = (
            cached_utc is None
            or len(cached_utc) == 0
            or (cycle % DASHBOARD_FULL_REFRESH_EVERY == 1)
            or consecutive_query_failures >= 3
        )

        try:
            measurements, dataFrame, cache_df_utc = refresh_measurement_cache(
                engine, config, cached_df=cached_utc, force_full=force_full,
            )
            consecutive_query_failures = 0
        except Exception:
            consecutive_query_failures += 1
            if log:
                log.exception(
                    'Dashboard: regenerate_pages refresh failed (%d consecutive)',
                    consecutive_query_failures,
                )
            if consecutive_query_failures >= 3:
                with lock:
                    latest_cache_df_utc = None
            time.sleep(max(config.get('dashboard_refresh_secs', 2) * 0.5, 0.5))
            continue

        try:
            pages = {}
            pages['dashboard'], sample_time, _, _ = build_page_contents(
                engine, config,
                measurements=measurements,
                dataFrame=dataFrame,
            )

            if zoom_inst and measurements is not None:
                pages[zoom_inst], _, _, _ = build_page_contents(
                    engine, config,
                    measurements=measurements,
                    dataFrame=dataFrame,
                    zoom_to_instrument=zoom_inst,
                )

            elapsed = (datetime.datetime.now() - st_time).total_seconds()
            with lock:
                latest_pages = pages
                latest_page_time = datetime.datetime.now()
                latest_sample_time = sample_time
                latest_data_frame = dataFrame
                latest_cache_df_utc = cache_df_utc
                latest_measurements_dict = measurements
            if log:
                log.info(
                    'Dashboard: regenerate_pages cycle finished in %.3fs (zoom=%s)',
                    elapsed, zoom_inst,
                )
        except Exception:
            if log:
                log.exception(
                    'Dashboard: regenerate_pages UI build failed; keeping SQL cache',
                )
            with lock:
                latest_cache_df_utc = cache_df_utc
                latest_measurements_dict = measurements
                latest_data_frame = dataFrame

        time.sleep(max(config.get('dashboard_refresh_secs', 2) * 0.5, 0.5))


