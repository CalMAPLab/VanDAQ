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
from vandaq_2step_measurements_query import get_2step_query
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

def get_last_valid_value(dataList, column):
    for row in reversed(dataList):
        if not isnan(row[column]):
            return row['sample_time'], row[column] 

def get_instrument_measurements(engine):
    # Fetch the latest measurement set
    #df = get_measurements(engine, start_time=datetime.datetime.now()-datetime.timedelta(minutes=5))
    df = get_2step_query(engine, datetime.datetime.now()-datetime.timedelta(minutes=5))
    outlist = []
    data = df.to_dict('records')
    instrument = ''
    instrument_rec = {}
    reading = {}
    sample_time = datetime.datetime.now()
    for col in df.columns:
        if 'sample_time' in col:
            sample_time = data[-1][col]
            outlist.append(sample_time)
        if '|' in col:
            rowtime, rowval = get_last_valid_value(data,col)
            items = col.split(' | ')
            if instrument != items[0]:
                if instrument_rec:
                    outlist.append(instrument_rec)
                instrument = items[0]
                instrument_rec = {'instrument':instrument,'readings':[]}
            reading = {'parameter':items[1],'value':rowval,'unit':items[2],'type':items[3]}
            reading['seconds_ago'] = (sample_time - rowtime).total_seconds() 
            instrument_rec['readings'].append(reading)
    if instrument_rec:
        outlist.append(instrument_rec)
    return outlist, df          

graph_line_colors = ["rgba(0, 123, 255, 0.8)",# light blue line with transparency
                     "rgba(182, 10, 10, 0.8)",# light red line with transparency
                     "rgba(29, 163, 11, 0.8)",# light green line with transparency
                     "rgba(140, 18, 189, 0.8)",# light purple line with transparency
                     "rgba(161, 159, 9, 0.8)"]# light yellow line with transparency
            
def create_trend_plot(instrument_data_list):
    graphs = []
    i = 0
    num = len(instrument_data_list)
    for instrument_data in instrument_data_list:
        instrument_data = instrument_data.dropna()
        graph = go.Scatter(
            x=instrument_data.index,
            y=instrument_data.values,
            text = instrument_data.name,
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


# Function that returns a list of objects (in this case, strings)
def get_list_of_items():
    global sample_time 
    before_query = datetime.datetime.now()
    #print('query starts '+before_query.strftime('%Y%m%d_%H%M%S'))
    measurements, df = get_instrument_measurements(engine)
    after_query = datetime.datetime.now()
    #print('query completes '+after_query.strftime('%Y%m%d_%H%M%S'))
    print('Query took '+str((after_query-before_query).total_seconds())+' seconds')
    sample_time = measurements[0]
    items = []
    for instrument in measurements:
        seconds_ago = 0
        if 'dict' in str(type(instrument)):
            instrument_text = instrument['instrument']
            graph_columns = []
            col = None
            if instrument_text in config['display_params']:
                columns = df.columns.tolist()
                for graph_col in config['display_params'][instrument_text]['graph']:
                    graph_columns += [df[c] for c in columns if instrument_text in c and ('| '+graph_col+' |') in c]
                if col:
                    col = col[0]
            if not col:        
                col = ' | '.join([instrument['instrument'],instrument['readings'][0]['parameter'],instrument['readings'][0]['unit'],instrument['readings'][0]['type']])
            graph = create_trend_plot(graph_columns)
            instrument_name = html.H2(instrument['instrument'].replace('_',' '))
            reading_cells = [instrument_name]
            do_display = True
            for reading in instrument['readings']:
                do_display = True
                if instrument_text in config['display_params']:
                    if config['display_params'][instrument_text]['display']:
                        if not str(reading['parameter']) in config['display_params'][instrument_text]['display']:
                            do_display = False
                reading_string = reading['parameter'] + ': ' + '{:.4f}'.format(reading['value']) + ' '+ reading['unit']
                reading_line = None
                if 'engineering' in reading['type']:
#                   reading_line = html.Div(reading_string,className='engineering_reading')  
                    reading_line = None  
                else:
                    if do_display:
                        reading_line = html.Div(reading_string,className='ambient_reading')
                    else:
                        reading_line = None
                if reading_line:
                    reading_cells.append(reading_line)
                if 'seconds_ago' in reading.keys():
                    seconds_ago = reading['seconds_ago']
            if seconds_ago > 1:
                reading_cells.insert(1,'as of '+str(seconds_ago)+' seconds ago')
            items.append(create_grid_cell(graph,reading_cells))
                
    return items, sample_time


local_styles ={
    'font-family': 'sans-serif',
    'background-color': 'black',
    'color':'white'
}

refresh_secs = 5

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
