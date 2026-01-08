"""

VanDAQ
Mobile Atmospheric Data Acquisition System

Author: Robert Jay (Robin) Weber
Affiliation: University of California, Berkeley

Copyright (c) 2025 The Regents of the University of California
Released under the BSD 3-Clause License.
"""

import os
import dash
from dash import Dash, dcc, html, Input, Output, State, dash_table
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
from dash.dependencies import Input, Output
from numpy import isnan
import plotly.graph_objs as go
import yaml
from sqlalchemy import create_engine
import logging
from logging.handlers import TimedRotatingFileHandler

# import other dashboard pages
from Dash_Alarm_Table import *
from Dash_Dashboard import *
from Dash_Mapper_FSM import layout_map_display, update_map_page
from Dash_Instrument_Controls import layout_instrument_controls, instrument_controls

# Initialize the Dash app
app = dash.Dash(__name__, suppress_callback_exceptions=True)
#app = dash.Dash(__name__)


config = {}

configfile_name = '/home/vandaq/vandaq/web/DashPlay.yaml'
try:
    configfile = open(configfile_name,'r')
    config = yaml.load(configfile, Loader=yaml.FullLoader)
    configfile.close()
except:
    print("Cannot load config file "+configfile_name)
    exit()

# create logger
#global logger
log_file = os.path.join(config['logs']['log_dir'], config['logs']['log_file'])
logging.basicConfig(
    filename = log_file,
    encoding="utf-8",
    filemode="a",
    format="{asctime} - {levelname} - {message}",
    style="{",
    datefmt="%Y-%m-%d %H:%M:%S.%f",    
)
logger = logging.getLogger(config['logs']['logger_name'])
logger.setLevel(config['logs']['log_level'])
handler = TimedRotatingFileHandler(log_file, when="midnight", interval=1, backupCount=30)
handler.setLevel(logging.INFO)
logger.addHandler(handler)

# # Set log file permissions to read/write for all users
# import stat
# try:
#     os.chmod(log_file, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH)
# except Exception as e:
#     print(f"Failed to set permissions on log file {log_file}: {e}")

config['logger'] = logger

# Database connection
if config and ('db_connect_string' in config):
    connect_string = config['db_connect_string']
else:
    connect_string = 'postgresql://vandaq:p3st3r@localhost:5432/vandaq-dev'

engine = create_engine(connect_string, echo=False)

update_dashboard(app, engine, config)
update_alarm_table(app, engine, config)
update_map_page(app, engine, config)
instrument_controls(app, engine, config)

tabstyle = {'padding':'5px 25px', 'position': 'sticky'}
# Main layout with tabs
logger.debug('Creating tab layout')
app.layout = html.Div([
    dcc.Tabs(id='tabs', className="tab-container", value='dashboard', children=[
        dcc.Tab(label='Dashboard', value='dashboard', style=tabstyle, selected_style=tabstyle),
        dcc.Tab(label='Alarm Table', value='alarm-table', style=tabstyle, selected_style=tabstyle),
        dcc.Tab(label='Map', value='map-display', style=tabstyle, selected_style=tabstyle),
        dcc.Tab(label='Controls', value='instrument-controls', style=tabstyle, selected_style=tabstyle)
    ]),
    html.Div([
        html.Div(layout_dashboard(config), id="dashboard-content", style={"display": "block"}),
        html.Div(layout_alarm_table(config), id="alarm-table-content", style={"display": "none"}),
        html.Div(layout_map_display(config), id="map-content", style={"display": "none"}),
        html.Div(layout_instrument_controls(config), id="instrument-controls-content", style={"display": "none"})
    ], id='app-content', className='page-content')
])


# Callback to update tab content
@app.callback(
    Output('dashboard-content', 'style'),
    Output('alarm-table-content', 'style'),
    Output('map-content', 'style'),
    Output('instrument-controls-content', 'style'),
    Input('tabs', 'value'),
    suppress_callback_exceptions=True
)
def render_tab(tab_name):
    logger.debug(f'Changing to tab {tab_name}')
    if tab_name == 'dashboard':
        return {"display": "block"}, {"display": "none"}, {"display": "none"}, {"display": "none"}
    elif tab_name == 'alarm-table':
        return {"display": "none"}, {"display": "block"}, {"display": "none"}, {"display": "none"}
    elif tab_name == 'map-display':
        return {"display": "none"}, {"display": "none"}, {"display": "block"}, {"display": "none"}
    elif tab_name == 'instrument-controls':
        return {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "block"}
    raise PreventUpdate


# Run the app
server = app.server
if __name__ == '__main__':
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(debug=False, dev_tools_ui=False, dev_tools_props_check=False)
    #app.run_server(debug=True)
