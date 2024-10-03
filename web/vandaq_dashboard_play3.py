import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
from numpy import isnan
import random
import plotly.graph_objs as go
import pandas as pd
import datetime
from vandaq_measurements_query import get_measurements
from sqlalchemy import create_engine, and_

# Initialize the Dash app
app = dash.Dash(__name__)

# Database connection
engine = create_engine('postgresql://vandaq:p3st3r@128.32.222.186:5432/vandaq-sandbox', echo=False)

sample_time = datetime.datetime.now()

def get_last_valid_value(dataList, column):
    for row in reversed(dataList):
        if not isnan(row[column]):
            return row['sample_time'], row[column] 

def get_instrument_measurements(engine):
    # Fetch the latest measurement set
    df = get_measurements(engine, start_time=datetime.datetime.now()-datetime.timedelta(minutes=5))

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
            
def create_trend_plot(instrument_data):
    instrument_data = instrument_data.dropna()
    return go.Figure(
        go.Scatter(
            x=instrument_data.index,
            y=instrument_data.values,
            mode="lines",
            line=dict(color="rgba(0, 123, 255, 0.8)"),  # light blue line with transparency
        )
    ).update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )

def create_grid_cell(graph,text):
    # Use dcc.Graph for trend plot background and overlay html for the text
    cell = html.Div(
            style={
                "position": "relative",
                "width": "30%",
                "padding-bottom": "30%",
                "display": "inline-block",
                "margin": "10px",
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
                    },
                ),
                html.Div(
                    children=text,
                    style={
                        "position": "absolute",
                        "top": "50%",
                        "left": "50%",
                        "transform": "translate(-50%, -50%)",
                        "color": "red",
                        "font-size": "24px",
                        "font-weight": "bold",
                        "text-align": "left",
                    },
                ),
            ],
        )
    return cell


# Function that returns a list of objects (in this case, strings)
def get_list_of_items():
    global sample_time 
    measurements, df = get_instrument_measurements(engine)
    sample_time = measurements[0]
    items = []
    for instrument in measurements:
        seconds_ago = 0
        if 'dict' in str(type(instrument)):
            col = ' | '.join([instrument['instrument'],instrument['readings'][0]['parameter'],instrument['readings'][0]['unit'],instrument['readings'][0]['type']])
            graph = create_trend_plot(df[col])
            instrument_name = html.H2(instrument['instrument'].replace('_',' '))
            reading_cells = [instrument_name]
            for reading in instrument['readings']:
                reading_string = reading['parameter'] + ': ' + str(reading['value'])[0:8] + ' '+ reading['unit']
                reading_line = None
                if 'engineering' in reading['type']:
                    reading_line = html.H4(reading_string)  
                else:
                    reading_line = html.H3(reading_string)
                reading_cells.append(reading_line)
                if 'seconds_ago' in reading.keys():
                    seconds_ago = reading['seconds_ago']
            if seconds_ago > 1:
                reading_cells.insert(1,'as of '+str(seconds_ago)+' seconds ago')
            items.append(create_grid_cell(graph,reading_cells))
                
    return items, sample_time

# Define the layout of the app
app.layout = html.Div([
    dcc.Interval(id='interval-component', interval=1*1000, n_intervals=0),
    html.H1('VanDAQ Operator Dashboard',style={'textAlign':'left'}),
    html.Div(' Last sample time: '+ sample_time.strftime("%m/%d/%Y, %H:%M:%S"),id='sample_timestamp'),

    html.Div(id='grid-container',style={"textAlign": "left"})
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
    
    sample_timestamp = ' Last sample time: '+ sample_time.strftime("%m/%d/%Y, %H:%M:%S")
    # Return the grid layout with inline CSS
    return grid_items, sample_timestamp

# Run the app
server = app.server
if __name__ == '__main__':
    app.run_server(debug=True)
