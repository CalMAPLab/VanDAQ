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



sample_time = datetime.datetime.now()

config = None
engine = None


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

def get_instrument_measurements(engine,config):
    # Fetch the latest measurement set
    #df = get_measurements(engine, start_time=datetime.datetime.now()-datetime.timedelta(minutes=5))
    st_time = datetime.datetime.now()
    logger.debug(f'get_instrument_measurements: Starting query at {st_time}')
    include_engineering = config.get('include_engineering', True)
    df = get_2step_query_with_alarms(engine, datetime.datetime.now()-datetime.timedelta(minutes=5),wide=False, include_engineering=include_engineering)
    if len(df) > 0:
        if 'display_timezone' in config:
            df['sample_time'] = df['sample_time'].dt.tz_localize('UTC').dt.tz_convert(config['display_timezone'])
            df.set_index('sample_time', inplace = True, drop=False)
    data = transform_instrument_dataframe(df)
    logger.debug(f'get_instrument_measurements: Finished query in {(datetime.datetime.now()-st_time).total_seconds()} seconds')
    return data, df          

graph_line_colors = [
    "#2563eb",
    "#dc2626",
    "#059669",
    "#7c3aed",
    "#d97706",
]

PLOT_AXIS_TICK_SIZE = 13


def legend_item(color, label):
    return html.Span(
        [
            html.Span(className="legend-swatch", style={"backgroundColor": color}),
            html.Span(label.replace("_", " "), className="legend-label"),
        ],
        className="legend-item",
    )


def build_trace_legend(graph_data):
    if not graph_data:
        return None
    return html.Div(
        [
            legend_item(graph_line_colors[i % len(graph_line_colors)], g["parameter"])
            for i, g in enumerate(graph_data)
        ],
        className="cell-legend-row",
    )


def build_cell_header(title, graph_data=None, alarm_class=None):
    """Instrument title and trace legend on one row."""
    row = [html.H2(title.replace("_", " "), className=alarm_class)]
    legend = build_trace_legend(graph_data)
    if legend is not None:
        row.append(legend)
    return html.Div(row, className="cell-header-row")


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

    # Define y-axis domains dynamically if using separate scales
    y_axis_domains = [(i / num_traces, (i + 1) / num_traces) for i in range(num_traces)] if separate_scales else [(0, 1)]

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
                color = 'rgba(255,0,0,0.6)' if row['max_alarm_level'] == 2 else 'rgba(255,255,0,0.6)'
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

def create_grid_cell(graph, text, instrument=None):
    """Instrument card: labels in header above chart (no overlay on data)."""
    if instrument:
        cell_id = {'type': 'instrument_cell', 'index': instrument}
    else:
        cell_id = None
    class_name = 'instrument_cell'
    if graph:
        graph_cell = dcc.Graph(
            figure=graph,
            config={"displayModeBar": False},
            style={"height": "100%", "width": "100%"},
        )
    else:
        graph_cell = html.Div(className="cell-chart-empty")
    cell_children = [
        html.Div(children=text, className="cell-header"),
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
            instrument = [i for i in measurements if i.get(inst)]
            if not instrument:
                instrument_text = inst
                alarm_box_style = 'flashing-box-alarm'
                no_data_header = build_cell_header(inst, alarm_class=alarm_box_style)
                items.append(create_grid_cell(
                    None,
                    html.Div([no_data_header, html.Span('NO DATA', className='no-data-badge')],
                             className='no_data_label'),
                ))
            else:
                instrument = instrument[0]
                instrument_text = list(instrument.keys())[0]
                if instrument_text in config['display_params']:
                    graph_params = config['display_params'][instrument_text]['graph']
                    graph_data = [{'parameter':param['parameter'], 'measurements':param['measurements']} for param in instrument[instrument_text] if param['parameter'] in graph_params]
                    graph = None
                    separate_scales = config['display_params'][instrument_text].get('separate_scales',False)
                    graph = create_trend_plot(graph_data, config, show_axes = True, separate_scales=separate_scales)
                    try:
                        alarm_level = max([max(list(data['measurements']['max_alarm_level'][-5:])) for data in graph_data])
                    except ValueError as e:
                        alarm_level = 0
                    alarm_box_style = None
                    if alarm_level == 2:
                        alarm_box_style = 'flashing-box-alarm'
                    elif alarm_level == 1:
                        alarm_box_style = 'flashing-box-warning'
                    header = build_cell_header(
                        instrument_text, graph_data=graph_data, alarm_class=alarm_box_style,
                    )
                    for parameter in instrument[instrument_text]:
                        sample_time = get_last_valid_value(
                            parameter['measurements'], 'sample_time',
                        )
                    items.append(create_grid_cell(graph, header, instrument=instrument_text))
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
            graph = create_trend_plot(graph_data, config, zoomed=True, show_axes=True)
            alarm_level = max(parameter['measurements']['max_alarm_level'][-5:])
            alarm_box_style = None
            if alarm_level == 2:
                alarm_box_style = 'flashing-box-alarm'
            elif alarm_level == 1:
                alarm_box_style = 'flashing-box-warning'
            header = build_cell_header(
                parameter_text, graph_data=graph_data, alarm_class=alarm_box_style,
            )
            sample_time = get_last_valid_value(parameter['measurements'], 'sample_time')
            items.append(create_grid_cell(graph, header))

    return items, sample_time, dataFrame, measurements


refresh_secs = 5

# Layout for the dashboard page
def layout_dashboard(config):
    global latest_pages
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
        global latest_pages
        logger.debug(f'Dashboard:  Got to instrument_cell_clicked: {datetime.datetime.now()}')
        for t in ctx.triggered:
            if t['value']:
                tr = json.loads(t['prop_id'].replace('.n_clicks',''))
                #print(f'Cell Clicked {datetime.datetime.now()} {tr["index"]}')
                instrument = tr['index']
                with lock:
                    page = latest_pages[instrument]
                return tr['index'], page
        logger.debug(f'Returning from instrument_cell_clicked: {datetime.datetime.now()}')

        raise PreventUpdate

    @app.callback(
        Output('instrument_zoom', 'data', allow_duplicate=True),
        Output('grid-container', 'children', allow_duplicate=True),
        Input('zoom_back_button', 'n_clicks'),
        prevent_initial_call=True    
    )
    def zoom_back_clicked(clicks):
        global latest_pages
        logger.debug(f'Dashboard:  Got to zoom_back_clicked: {datetime.datetime.now()}')
        if clicks > 0:
            global latest_pages
            with lock:
                page = latest_pages['dashboard']
            #print(f'Clicked back button {datetime.datetime.now()}')
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
        prevent_initial_call=True
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
                last_seen_timestamp = datetime.datetime.strptime(last_seen_timestamp,'%Y-%m-%dT%H:%M:%S.%f')
            with lock:
                cached_timestamp = latest_page_time
            if cached_timestamp and ((last_seen_timestamp is None) or (cached_timestamp > last_seen_timestamp)):
                with lock:
                    cached_timestamp = latest_page_time
                    items = latest_pages['dashboard']
                    cached_sample_time = latest_sample_time
                if isinstance(cached_sample_time, datetime.datetime):
                    sample_timestamp = f'Last sample time: {cached_sample_time.strftime("%m/%d/%Y, %H:%M:%S")}'
                else:
                    sample_timestamp = ''
                if instrument_zoom:
                    items = latest_pages[instrument_zoom]                
                                
                #print(f'Returning updated page {instrument_zoom}')
                logger.debug(f'Dashboard:  Returning from to update_page -- page updated: {datetime.datetime.now()}')
                return items, sample_timestamp, cached_timestamp

        #print(f'Preventing update {datetime.datetime.now()}')                
        logger.debug(f'Dashboard:  Returning from to update_page -- no update: {datetime.datetime.now()}')
        return no_update, no_update, no_update
        #raise PreventUpdate


# Periodically regenerate the page content in the background
def regenerate_pages(engine, config, lock):
    regpage = True
    count = 0
    pages = {}
    logger.info('Dashboard:  regenerate_pages: Starting dashboard background page regeneration thread')
    while True:
        if regpage:
            try:
                st_time = datetime.datetime.now()
                pages['dashboard'], sample_time, dataFrame, measurements = build_page_contents(
                    engine, config,
                )
                logger.debug(
                    'Dashboard: regenerate_pages: main page build took %.3fs',
                    (datetime.datetime.now() - st_time).total_seconds(),
                )
                if dataFrame is not None and len(dataFrame) > 0:
                    for instrument in dataFrame['instrument'].unique():
                        pages[instrument], _, _, _ = build_page_contents(
                            engine, config,
                            measurements=measurements,
                            zoom_to_instrument=instrument,
                        )
                global latest_pages
                global latest_page_time
                global latest_sample_time
                global latest_data_frame
                global latest_measurements_dict
                with lock:
                    latest_pages = pages
                    latest_page_time = datetime.datetime.now()
                    latest_sample_time = sample_time
                    latest_data_frame = dataFrame
                    latest_measurements_dict = measurements
                logger.debug(
                    'regenerate_pages: finished all page regenerations in %.3fs',
                    (datetime.datetime.now() - st_time).total_seconds(),
                )
            except Exception:
                logger.exception('Dashboard: regenerate_pages failed')
        time.sleep(0.1)  # give some time back to the main thread


