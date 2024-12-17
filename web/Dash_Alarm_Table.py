import dash
from dash import Dash, dcc, html, Input, Output, State, dash_table
import pandas as pd
import datetime
from vandaq_2step_measurements_query import get_alarms

# Initialize the Dash app
app = dash.Dash(__name__)

# Define a placeholder DataFrame for the alarm table (replace with your database query results)
def get_alarm_data():
    data = [
        {"id": 1, "time": datetime.datetime.utcnow(), "type": "High", "description": "Temperature exceeded threshold"},
        {"id": 2, "time": datetime.datetime.utcnow(), "type": "Low", "description": "Pressure below threshold"}
    ]
    return pd.DataFrame(data)

# Layout for the alarm table page
def layout_alarm_table():
    return html.Div([
        html.H1('Alarm Table', style={'text-align': 'left'}),
        html.Button('Suspend Updates', id='suspend-updates', n_clicks=0),
        html.Button('Resume Updates', id='resume-updates', n_clicks=0),
        dash_table.DataTable(
            id='alarm-table',
            columns=[
                {'name': 'ID', 'id': 'id'},
                {'name': 'Time', 'id': 'time'},
                {'name': 'Type', 'id': 'type'},
                {'name': 'Description', 'id': 'description'}
            ],
            style_table={'overflowX': 'auto'},
            style_cell={'textAlign': 'left'},
            filter_action='native',
            sort_action='native',
            page_action='native',
            page_current=0,
            page_size=10
        )
    ])

# Callback for the alarm table page
def update_alarm_table(app, engine, config):
    @app.callback(
        Output('alarm-table', 'data'),
        [Input('resume-updates', 'n_clicks')],
        [State('suspend-updates', 'n_clicks')],
        prevent_initial_call=True
    )
    def update_alarm_table(resume_clicks, suspend_clicks):
        ctx = dash.callback_context
        if ctx.triggered and ctx.triggered[0]['prop_id'] == 'suspend-updates.n_clicks':
            return dash.no_update
        alarm_data = get_alarm_data(engine)
        return alarm_data.to_dict('records')

