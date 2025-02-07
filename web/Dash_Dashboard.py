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
    last_valid_index = df[column].last_valid_index()
    if last_valid_index:
        return df[column][last_valid_index]
    return None

def get_instrument_measurements(engine,config):
    # Fetch the latest measurement set
    #df = get_measurements(engine, start_time=datetime.datetime.now()-datetime.timedelta(minutes=5))
    df = get_2step_query_with_alarms(engine, datetime.datetime.now()-datetime.timedelta(minutes=5),wide=False)
    if len(df) > 0:
        if 'display_timezone' in config:
            df['sample_time'] = df['sample_time'].dt.tz_localize('UTC').dt.tz_convert(config['display_timezone'])
            df.set_index('sample_time', inplace = True, drop=False)
    data = transform_instrument_dataframe(df)
    return data, df          

graph_line_colors = ["rgba(0, 123, 255, 0.8)",# light blue line with transparency
                     "rgba(182, 10, 10, 0.8)",# light red line with transparency
                     "rgba(29, 163, 11, 0.8)",# light green line with transparency
                     "rgba(140, 18, 189, 0.8)",# light purple line with transparency
                     "rgba(161, 159, 9, 0.8)"]# light yellow line with transparency
            
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

    # Create layout with multiple y-axes if separate scales are enabled
    layout = go.Layout(
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=show_axes, showgrid=False, tickfont=dict(color='lightblue')),
        yaxis=dict(visible=show_axes, side='right', showgrid=False, tickfont=dict(color='lightblue')),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        shapes=shapes,
        showlegend=False
    )

    # Dynamically add additional y-axes for separate scales
    if separate_scales:
        layout.yaxis = dict(
            domain=y_axis_domains[0], 
            showgrid=False, 
            tickfont=dict(color='lightblue')
        )
        for i, domain in enumerate(y_axis_domains[1:], start=1):
            layout[f"yaxis{i+1}"] = dict(
                domain=domain,
                showgrid=False,
                tickfont=dict(color='lightblue'),
                anchor="x"
            )

    return go.Figure(graphs, layout)

def create_grid_cell(graph,text, instrument = None):
    # Use dcc.Graph for trend plot background and overlay html for the text
    if instrument:
        cell_id = {'type': 'instrument_cell', 'index': instrument} 
    else:
        cell_id = None
    class_name = 'instrument_cell'
    cell_style={
        "position": "relative",
        "width": "48%",
        "padding-bottom": "15%",
        "display": "inline-block",
        "margin": "10px",
        "background-color": "black"
    }
    if graph:
        graph_cell =  dcc.Graph(
            figure=graph,
            config={"displayModeBar": False},
            style={
                "position": "absolute",
                "top": 0,
                "left": 0,
                "height": "100%",
                "width": "100%",
                "background-color": "black"
            },
        )
    else:
        graph_cell = html.Div([],            
                style={
                "position": "absolute",
                "top": 0,
                "left": 0,
                "height": "100%",
                "width": "100%",
                "background-color": "black"
            })
    cell_children=[
        graph_cell,
        html.Div(
            children=text,
            style={
                "position": "absolute",
                #"top": "50%",
                #"left": "50%",
                #"transform": "translate(-50%, -50%)",
                "color": "white",
                "font-family": "sans-serif",
#                      "font-size": "24px",
#                      "font-weight": "bold",
                    #"text-align": "left",
            },
        ),
    ]
    if cell_id:
        cell = html.Div(
                id=cell_id,
                className=class_name, 
                style=cell_style,
                children=cell_children,
                #n_clicks=0
            )
    else:
        cell = html.Div(
                className=class_name, 
                style=cell_style,
                children=cell_children,
                #n_clicks=0
            )
    return cell

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
                instrument_name = html.H2(instrument_text.replace('_',' '), className=alarm_box_style)
                items.append(create_grid_cell(None,html.Div([instrument_name, html.H1('NO DATA')],className='no_data_label')))
            else:
                instrument = instrument[0]
                instrument_text = list(instrument.keys())[0]
                if instrument_text in config['display_params']:
                    graph_params = config['display_params'][instrument_text]['graph']
                    graph_data = [{'parameter':param['parameter'], 'measurements':param['measurements']} for param in instrument[instrument_text] if param['parameter'] in graph_params]
                    graph = None
                    separate_scales = config['display_params'][instrument_text].get('separate_scales',False)
                    graph = create_trend_plot(graph_data, config, separate_scales=separate_scales)
                    alarm_level = max([max(list(data['measurements']['max_alarm_level'][-5:])) for data in graph_data])
                    alarm_box_style = None
                    if alarm_level == 2:
                        alarm_box_style = 'flashing-box-alarm'
                    elif alarm_level == 1:
                        alarm_box_style = 'flashing-box-warning'
                    instrument_name = html.H2(instrument_text.replace('_',' '), className=alarm_box_style)
                    
                    reading_cells = [instrument_name]
                    for parameter in instrument[instrument_text]:
                        parameter_text = parameter['parameter']
                        do_display = False
                        if parameter_text in config['display_params'][instrument_text]['display']:
                            do_display = True
                            # Vulnerability here v
                            try:
                                reading_string = parameter_text + ': ' + '{:.4f}'.format(get_last_valid_value(parameter['measurements'],'value')) + ' '+ parameter['unit']
                            except TypeError as e:
                                reading_string = 'Bad Value: '+ str(get_last_valid_value(parameter['measurements'],'value'))
                            reading_line = None
                            if 'engineering' in parameter['acquisition_type']:
            #                   reading_line = html.Div(reading_string,className='engineering_reading')  
                                reading_line = None  
                            else:
                                if do_display:
                                    reading_line = html.Div(reading_string,className='ambient_reading')
                                else:
                                    reading_line = None
                            if reading_line:
                                reading_cells.append(reading_line)
                            sample_time = get_last_valid_value(parameter['measurements'],'sample_time')
                    items.append(create_grid_cell(graph,reading_cells, instrument = instrument_text))
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
            parameter_name = html.H2(parameter_text, className=alarm_box_style)
            aqu_type_text = html.H3(aqu_type_text)
            reading_cells = [parameter_name, aqu_type_text]
            reading_string = ''

            try:
                reading_string = '{:.4f}'.format(get_last_valid_value(parameter['measurements'],'value')) + ' '+ parameter['unit']
            except TypeError as e:
                reading_string = 'Bad Value: '+ str(get_last_valid_value(parameter['measurements'],'value'))
            if 'engineering' in aqu_type_text:
                reading_line = html.Div(reading_string,className='engineering_reading')  
            else:
                reading_line = html.Div(reading_string,className='ambient_reading')
            if reading_line:
                reading_cells.append(reading_line)
            sample_time = get_last_valid_value(parameter['measurements'],'sample_time')
            items.append(create_grid_cell(graph,reading_cells))

    return items, sample_time, dataFrame, measurements


local_styles ={
    'font-family': 'sans-serif',
    'background-color': 'black',
    'color':'white'
}

refresh_secs = 1

# Layout for the dashboard page
def layout_dashboard(config):
    global latest_pages
    if latest_pages:
        content = latest_pages['dashboard']
    else:
        content = ['Awaiting data...']
    layout = html.Div([
        dcc.Interval(id='interval', interval=refresh_secs * 1000, n_intervals=0),
        dcc.Store(id="cache-timestamp", data=None),  # To store the last seen timestamp
        dcc.Store(id="instrument_zoom", data = None),
        html.H1('VanDAQ Operator Dashboard', style={'text-align': 'left'}, id='clickhere', n_clicks=0),
        html.Div('',id='sample_timestamp'),
        dcc.Checklist(
            options=[{'label': 'Freeze', 'value': 'suspend'}],
            id='suspend-updates',
            value=[],  # Default: updates are not suspended
            style={'margin-bottom': '10px'}
        ),
        html.Div(id='grid-container', children=content)
    ])
    return layout


latest_pages = None
latest_page_time = None
latest_sample_time = None
latest_data_frame = None
latest_measurements_dict = None


def update_dashboard(app, engine, config):

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
        for t in ctx.triggered:
            if t['value']:
                tr = json.loads(t['prop_id'].replace('.n_clicks',''))
                #print(f'Cell Clicked {datetime.datetime.now()} {tr["index"]}')
                instrument = tr['index']
                with lock:
                    page = latest_pages[instrument]
                return tr['index'], page
        raise PreventUpdate

    @app.callback(
        Output('instrument_zoom', 'data', allow_duplicate=True),
        Output('grid-container', 'children', allow_duplicate=True),
        Input('zoom_back_button', 'n_clicks'),
        prevent_initial_call=True    
    )
    def zoom_back_clicked(clicks):
        global latest_pages
        if clicks > 0:
            global latest_pages
            with lock:
                page = latest_pages['dashboard']
            #print(f'Clicked back button {datetime.datetime.now()}')
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
            State('suspend-updates', 'value'),
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
                sample_timestamp = f'Last sample time: {cached_sample_time.strftime("%m/%d/%Y, %H:%M:%S")}'
                if instrument_zoom:
                    items = latest_pages[instrument_zoom]                
                                
                #print(f'Returning updated page {instrument_zoom}')
                return items, sample_timestamp, cached_timestamp

        #print(f'Preventing update {datetime.datetime.now()}')                
        return no_update, no_update, no_update
        #raise PreventUpdate


# Periodically regenerate the page content in the background
def regenerate_pages(engine, config, lock):
    regpage = True
    count = 0
    pages = {}
    while True:
        if regpage:
            # Here is the expensive query and page-build
            #print(f'Starting dash regenerate {datetime.datetime.now()}')                
            st_time = datetime.datetime.now()
            pages['dashboard'], sample_time, dataFrame, measurements = build_page_contents(engine, config)
            instruments = dataFrame['instrument'].unique()
            for instrument in instruments:
                pages[instrument],stime,df,meas = build_page_contents(engine, config, measurements=measurements, zoom_to_instrument=instrument)
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
            #print(f'Finished dash regenerate {datetime.datetime.now()} {(datetime.datetime.now() - st_time).total_seconds()}')                
        time.sleep(0.1)  # give some time back to the main thread


