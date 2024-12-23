from dash import dcc, html, Input, Output, State, dash_table
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
from dash.exceptions import PreventUpdate
from numpy import isnan
import plotly.graph_objs as go
import pandas as pd
import datetime
import time
import copy
from threading import Thread, Lock
#from vandaq_measurements_query import get_measurements
from vandaq_2step_measurements_query import get_2step_query_with_alarms
from vandaq_2step_measurements_query import transform_instrument_dataframe



sample_time = datetime.datetime.now()

config = None
engine = None

def get_last_valid_value(df, column):
    last_valid_index = df[column].last_valid_index()
    last_valid_value = df[column][last_valid_index]
    return last_valid_value

def get_instrument_measurements(engine):
    # Fetch the latest measurement set
    #df = get_measurements(engine, start_time=datetime.datetime.now()-datetime.timedelta(minutes=5))
    df = get_2step_query_with_alarms(engine, datetime.datetime.now()-datetime.timedelta(minutes=5),wide=False)
    data = transform_instrument_dataframe(df)
    return data          

graph_line_colors = ["rgba(0, 123, 255, 0.8)",# light blue line with transparency
                     "rgba(182, 10, 10, 0.8)",# light red line with transparency
                     "rgba(29, 163, 11, 0.8)",# light green line with transparency
                     "rgba(140, 18, 189, 0.8)",# light purple line with transparency
                     "rgba(161, 159, 9, 0.8)"]# light yellow line with transparency
            
def create_trend_plot_old(instrument_data_list):
    graphs = []
    i = 0
    num = len(instrument_data_list)
    for instrument_data in instrument_data_list:
        name = instrument_data['parameter']
        data = instrument_data['measurements']
        #data = data.dropna()
        graph = go.Scatter(
            x=data.index,
            y=data['value'],
            text = name,
            mode="lines",
            line=dict(color=graph_line_colors[i]),  
        )
        graphs.append(graph)
        i += 1

    return go.Figure(
        graphs
    ).update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False  # Hides the legend
    )

def create_trend_plot(instrument_data_list, config):
    graphs = []
    shapes = []  # List to hold the background shapes for alarm levels
    i = 0
    num = len(instrument_data_list)

    for instrument_data in instrument_data_list:
        name = instrument_data['parameter']
        data = instrument_data['measurements']
        # data = data.dropna()

        # Add line plot
        graph = go.Scatter(
            x=data.index,
            y=data['value'],
            text=name,
            mode="lines",
            line=dict(color=graph_line_colors[i]),
        )
        graphs.append(graph)

        # Add background shapes for max_alarm_level > 0
        if 'alarm_shapes' in config and config['alarm_shapes']:
            if 'max_alarm_level' in data.columns:
                alarm_intervals = data[data['max_alarm_level'] > 0]
                for idx, row in alarm_intervals.iterrows():
                    color = 'rgba(255,0,0,0.6)' if row['max_alarm_level'] == 2 else 'rgba(255,255,0,0.6)'
                    shapes.append({
                        'type': 'rect',
                        'xref': 'x',  # Use x-axis as reference
                        'yref': 'paper',  # Use the paper height as reference for full y-axis coverage
                        'x0': idx,  # Start time of the interval
                        'x1': idx + pd.Timedelta(seconds=1),  # End time of the interval
                        'y0': 0,
                        'y1': 1,
                        'fillcolor': color,
                        'opacity': 0.6,
                        'layer': 'below',  # Ensure it appears below the line plot
                        'line_width': 0
                    })

        i += 1

    return go.Figure(
        graphs
    ).update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False),  # Make x-axis visible for easier alignment
        yaxis=dict(visible=False),  # Make y-axis visible for easier understanding
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        shapes=shapes,  # Add the shapes to the layout
        showlegend=False  # Hides the legend
    )

def create_grid_cell(graph,text):
    # Use dcc.Graph for trend plot background and overlay html for the text
    cell = html.Div(
            style={
                "position": "relative",
                "width": "48%",
                "padding-bottom": "15%",
                "display": "inline-block",
                "margin": "10px",
				"background-color": "black"
            },
            children=[
                dcc.Graph(
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
                ),
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
            ],
        )
    return cell

flashing_text = {
            "outline": "2px solid red",    # Red outline
            "display": "inline-block",    # Ensures outline hugs the text
            "padding": "5px",             # Optional spacing
            "animation": "flash 1s infinite"  # Flash animation
        }

# Function that returns a list of objects (in this case, strings)
def get_list_of_items(engine, config):
    global sample_time 
    before_query = datetime.datetime.now()
    #print('query starts '+before_query.strftime('%Y%m%d_%H%M%S'))
    measurements = get_instrument_measurements(engine)
    after_query = datetime.datetime.now()
    #print('query completes '+after_query.strftime('%Y%m%d_%H%M%S'))
    print('Query took '+str((after_query-before_query).total_seconds())+' seconds')
    items = []
    for instrument in measurements:
        seconds_ago = 0
        instrument_text = list(instrument.keys())[0]
        if instrument_text in config['display_params']:
            graph_params = config['display_params'][instrument_text]['graph']
            graph_data = [{'parameter':param['parameter'], 'measurements':param['measurements']} for param in instrument[instrument_text] if param['parameter'] in graph_params]
            graph = None
            graph = create_trend_plot(graph_data, config)
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
                    #if 'seconds_ago' in reading.keys():
                    #    seconds_ago = reading['seconds_ago']
                #if seconds_ago > 1:
                #    reading_cells.insert(1,'as of '+str(seconds_ago)+' seconds ago')
            items.append(create_grid_cell(graph,reading_cells))

    return items, sample_time


local_styles ={
    'font-family': 'sans-serif',
    'background-color': 'black',
    'color':'white'
}

refresh_secs = 1

# Layout for the dashboard page
def layout_dashboard(config):
    return html.Div([
        dcc.Interval(id='interval', interval=refresh_secs * 1000, n_intervals=0),
        dcc.Store(id="cache-timestamp", data=None),  # To store the last seen timestamp
        html.H1('VanDAQ Operator Dashboard', style={'text-align': 'left'}),
        html.Div(id='sample_timestamp'),
        html.Div(id='grid-container', children=['Awaiting data...'])
    ])


latest_page = None
latest_page_time = None

def update_dashboard(app, engine, config):

    lock = Lock()


    Thread(target=regenerate_page, args=(engine, config, lock), daemon=True).start()

    @app.callback(
        [
            Output('grid-container', 'children'),
            Output('sample_timestamp', 'children'),
            Output("cache-timestamp", "data"),
        ],
        [
            Input("interval", "n_intervals"),
            State("cache-timestamp", "data")
        ]
    )
    def update_page(n_intervals, last_seen_timestamp):
        global latest_page
        global latest_page_time
        stime = datetime.datetime.now()
        print('checking for update')
        if isinstance(last_seen_timestamp, str):
            last_seen_timestamp = datetime.datetime.strptime(last_seen_timestamp,'%Y-%m-%dT%H:%M:%S.%f')
        with lock:
            cached_timestamp = latest_page_time
        if cached_timestamp and ((last_seen_timestamp is None) or (cached_timestamp > last_seen_timestamp)):
            with lock:
                cached_timestamp = latest_page_time
                cached_page = copy.copy(latest_page)
            sample_timestamp = f'Last sample time (UTC): {cached_timestamp.strftime("%m/%d/%Y, %H:%M:%S")}'
            etime = datetime.datetime.now()
            print(f'got page in {(etime-stime).total_seconds()} secs')
            return cached_page, sample_timestamp, cached_timestamp
        raise PreventUpdate

# Periodically regenerate the page content in the background
def regenerate_page(engine, config, lock):
    while True:
        #stime = datetime.datetime.now()
        items, sample_time = get_list_of_items(engine, config)
        global latest_page
        global latest_page_time
        with lock:
            latest_page = items
            latest_page_time = datetime.datetime.now()
        #etime = datetime.datetime.now()
        #print(f'rebuilt page in {(etime-stime).total_seconds()} secs')
        time.sleep(0.1)  # Keep refreshing every second


