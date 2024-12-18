import dash
from dash import Dash, dcc, html, Input, Output, State, dash_table
import pandas as pd
import datetime
from vandaq_2step_measurements_query import get_alarm_table

# Initialize the Dash app
app = dash.Dash(__name__)

engine = None

# Define a placeholder DataFrame for the alarm table (replace with your database query results)
def get_alarm_data(engine):
    data = get_alarm_table(engine,start_time = datetime.datetime.now()-datetime.timedelta(minutes=5))
    return data

def get_alarm_columns(engine):
    cols = get_alarm_table(engine, column_names_only=True)
    return [{'name':col.replace('_',' '), 'id': col} for col in cols]



# Layout for the alarm table page
def layout_alarm_table():
    return html.Div([
        html.H1('Alarm Table', style={'text-align': 'left'}),
        dcc.Checklist(
            options=[{'label': 'Suspend updates', 'value': 'suspend'}],
            id='suspend-updates',
            value=[],  # Default: updates are not suspended
            style={'margin-bottom': '10px'}
        ),
        dcc.Interval(
            id='update-interval',
            interval=1000,  # 1-second interval
            n_intervals=0
        ),
        dash_table.DataTable(
            id='alarm-table',
            columns = get_alarm_columns(engine),
            style_table={
                'height': '400px',  # Limit height for the scrollable area
                'overflowY': 'auto',  # Ensure smooth vertical scrolling
                'overflowX': 'auto',  # Allow horizontal scrolling if needed
                'border': '1px solid #444',  # Ensure clear boundaries
                'background': 'black',
                'color': 'white'
            },
            style_cell={'textAlign': 'left', 'background':'black', 'color':'white'},
            style_filter={'textAlign': 'left', 'background':'black', 'color':'white', 'textColor':'yellow'},
            filter_action='native',
            sort_action='native',
            page_action='native',
            page_current=0,
            page_size=10,
            fixed_rows={'headers': True},  # Keep headers fixed while scrolling
            sort_by=[{'column_id': 'time', 'direction': 'desc'}]
        )
    ])



# Callback for the alarm table page
def update_alarm_table(app, sqlengine, config):
    @app.callback(
        Output('alarm-table', 'data'),
        [Input('update-interval', 'n_intervals'),
         Input('suspend-updates', 'value')]
    )
    def update_alarm_table_callback(n_intervals, suspend_updates):
        # Check if updates are suspended
        if 'suspend' in suspend_updates:
            return dash.no_update

        # Fetch data from the database (simulated here)
        alarm_data = get_alarm_data(sqlengine)
        return alarm_data.to_dict('records')