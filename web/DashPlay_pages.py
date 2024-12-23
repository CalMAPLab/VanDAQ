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

update_dashboard(app, engine, get_config())
update_alarm_table(app, engine, get_config())

# Callback to update tab content
@app.callback(
    Output('tab-content', 'children'),
    Input('tabs', 'value'),
    suppress_callback_exceptions=True
)
def render_tab(tab_name):
    if tab_name == 'dashboard':
        return layout_dashboard(get_config())
    elif tab_name == 'alarm-table':
        ret = layout_alarm_table(get_config())
        return ret


# Run the app
server = app.server
if __name__ == '__main__':
    app.run_server(debug=True)
