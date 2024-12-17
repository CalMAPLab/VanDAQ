import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
from numpy import isnan
import random
import plotly.graph_objs as go
import pandas as pd
import datetime
import yaml
#from vandaq_measurements_query import get_measurements
from vandaq_2step_measurements_query import get_2step_query_with_alarms
from vandaq_2step_measurements_query import transform_instrument_dataframe
from sqlalchemy import create_engine, and_

# Initialize the Dash app
app = dash.Dash(__name__)

configfile_name = '/home/vandaq/vandaq/web/DashPlay.yaml'
try:
    configfile = open(configfile_name,'r')
    config = yaml.load(configfile, Loader=yaml.FullLoader)
    configfile.close()
except:
    print("Cannot load config file "+configfile_name)
    exit()

# Database connection
engine = create_engine('postgresql://vandaq:p3st3r@localhost:5432/vandaq-dev', echo=False)

sample_time = datetime.datetime.now()

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

def create_trend_plot(instrument_data_list):
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
def get_list_of_items():
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
        graph_params = config['display_params'][instrument_text]['graph']
        graph_data = [{'parameter':param['parameter'], 'measurements':param['measurements']} for param in instrument[instrument_text] if param['parameter'] in graph_params]
        graph = create_trend_plot(graph_data)
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
                reading_string = parameter_text + ': ' + '{:.4f}'.format(get_last_valid_value(parameter['measurements'],'value')) + ' '+ parameter['unit']
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

refresh_secs = 2


# Define the layout of the app
app.layout = html.Div(children=[ 
    dcc.Interval(id='interval-component', interval=refresh_secs*1000, n_intervals=0),
    html.H1('VanDAQ Operator Dashboard',style={'text-align':'left'}),
    html.Div(' Last sample time (UTC): '+ sample_time.strftime("%m/%d/%Y, %H:%M:%S"),id='sample_timestamp'),
    html.Div(id='grid-container')
])

@app.callback(
    Output('grid-container', 'children'),
    Output('sample_timestamp', 'children'),
    Input('interval-component', 'n_intervals')
)
def update_grid(n):
    items, sample_time = get_list_of_items()
    num_rows = min(5, len(items))  # You can adjust the number of rows if needed
    
    # Generate a list of Div elements for the grid
    #grid_items = [html.Div(item, className="grid-item") for item in items]
    grid_items = items
    
    sample_timestamp = ' Last sample time (UTC): '+ sample_time.strftime("%m/%d/%Y, %H:%M:%S")
    # Return the grid layout with inline CSS
    return grid_items, sample_timestamp

# Run the app
server = app.server
if __name__ == '__main__':
    app.run_server(debug=True)
