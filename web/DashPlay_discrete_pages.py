import dash
from dash import Dash, dcc, html, Input, Output, State, dash_table
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
from numpy import isnan
import plotly.graph_objs as go
import yaml
from sqlalchemy import create_engine

# import other dashboard pages
from Dash_Alarm_Table import *
from Dash_Dashboard import *
from Dash_Mapper import layout_map_display, update_map_page

# Initialize the Dash app
app = dash.Dash(__name__, suppress_callback_exceptions=True)

def get_config(): 
    configfile_name = '/home/vandaq/vandaq/web/DashPlay.yaml'
    try:
        configfile = open(configfile_name,'r')
        config = yaml.load(configfile, Loader=yaml.FullLoader)
        configfile.close()
    except:
        print("Cannot load config file "+configfile_name)
        exit()
    return config

config = get_config()

# Database connection
if config and ('db_connect_string' in config):
    connect_string = config['db_connect_string']
else:
    connect_string = 'postgresql://vandaq:p3st3r@localhost:5432/vandaq-dev'

engine = create_engine(connect_string, echo=False)

tabstyle = {'padding':'5px 25px'}
# Main layout with tabs
app.layout = html.Div([
    dcc.Tabs(id='tabs', value='dashboard', children=[
        dcc.Tab(label='Dashboard', value='dashboard', style=tabstyle, selected_style=tabstyle),
        dcc.Tab(label='Alarm Table', value='alarm-table', style=tabstyle, selected_style=tabstyle),
        dcc.Tab(label='Map', value='map-display', style=tabstyle, selected_style=tabstyle)
    ]),
    html.Div(id='tab-content')
])

update_dashboard(app, engine, get_config())
update_alarm_table(app, engine, get_config())
try:
    update_map_page(app, engine, get_config())
except Exception as e:
    print(e)
# Callback to update tab content
@app.callback(
    Output('tab-content', 'children'),
    Input('tabs', 'value'),
    suppress_callback_exceptions=True
)
def render_tab(tab_name):
    if tab_name == 'dashboard':
        ret = layout_dashboard(get_config())
    elif tab_name == 'alarm-table':
        ret = layout_alarm_table(get_config())
    elif tab_name == 'map-display':
        ret = layout_map_display(get_config())
    return ret


# Run the app
server = app.server
if __name__ == '__main__':
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run_server(debug=False, dev_tools_ui=False, dev_tools_props_check=False)
