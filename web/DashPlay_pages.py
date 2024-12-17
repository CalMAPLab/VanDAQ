import dash
from dash import Dash, dcc, html, Input, Output, State, dash_table
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

# import other dashboard pages
from Dash_Alarm_Table import *
from Dash_Dashboard import *

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

# Main layout with tabs
app.layout = html.Div([
    dcc.Tabs(id='tabs', value='dashboard', children=[
        dcc.Tab(label='Dashboard', value='dashboard'),
        dcc.Tab(label='Alarm Table', value='alarm-table')
    ]),
    html.Div(id='tab-content')
])

# Callback to update tab content
@app.callback(
    Output('tab-content', 'children'),
    Input('tabs', 'value')
)
def render_tab(tab_name):
    if tab_name == 'dashboard':
        return layout_dashboard()
    elif tab_name == 'alarm-table':
        return layout_alarm_table()


update_alarm_table(app, engine, config)
update_dashboard(app, engine, config)

# Run the app
server = app.server
if __name__ == '__main__':
    app.run_server(debug=True)
