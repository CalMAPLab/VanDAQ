import dash
from dash import dcc, html, Input, Output
import plotly.express as px
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import pytz
from threading import Thread, Lock

from sqlalchemy import create_engine

from vandaq_2step_measurements_query import get_measurements_with_alarms_and_locations
from vandaq_2step_measurements_query import get_all_geolocations


timezone = pytz.timezone('US/Pacific')

def get_geolocations(engine):
    geo_df = get_all_geolocations(engine)
    geo_df['sample_time'] = geo_df['sample_time'].dt.tz_localize(pytz.utc).dt.tz_convert(timezone)
    return geo_df

app = dash.Dash(__name__)

connect_string = 'postgresql://vandaq:p3st3r@localhost:5432/vandaq-test'

engine = create_engine(connect_string, echo=False)

latest_data_frame = None
latest_sample_time = None
gps_dates = None
gps_instruments = None
gps_platforms = None
env_instruments = None
env_parameters = None

from datetime import datetime, timedelta

def find_missing_dates(dates):
    """
    Finds the missing dates between the first and last dates in a list.

    Args:
        dates (list of datetime): A list of datetime objects.

    Returns:
        list of datetime: A list of missing dates between the first and last dates.
    """
    if not dates:
        return []

    # Sort the dates and find the range
    sorted_dates = sorted(dates)
    start_date = sorted_dates[0]
    end_date = sorted_dates[-1]

    # Create a set of all dates in the range
    all_dates = {start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)}

    # Find the missing dates
    existing_dates = set(sorted_dates)
    missing_dates = sorted(all_dates - existing_dates)

    return missing_dates

def layout_map_display(config):
    global latest_data_frame
    global latest_sample_time
    global gps_dates
    global gps_instruments
    global gps_platforms
    global env_instruments
    global env_parameters
    # wait for query data to become available
    while not latest_sample_time:
        time.sleep(0.1)
    return html.Div([
    html.H1("Drive Map"),
    html.Div([
        #html.H3("platform"),
        dcc.DatePickerSingle(
            id='date-picker',
            min_date_allowed=min(gps_dates),
            max_date_allowed=max(gps_dates),
            disabled_days=find_missing_dates(gps_dates),
            display_format='YYYY-MM-DD',
            date=min(gps_dates)
        ),
        dcc.Dropdown(
            id='platform-selector',
            options=gps_platforms,
            value=gps_platforms[0],
            clearable=False
        ),
        dcc.Dropdown(
            id='gps-selector',
            options=gps_instruments,
            value=gps_instruments[0],
            clearable=False
        ),
        dcc.Dropdown(
            id='parameter-selector',
            options=env_parameters,
            value=env_parameters[0],
            clearable=False
        ),
        dcc.Dropdown(
            id='instrument-selector',
            options=env_instruments,
            value=env_instruments[0],
            clearable=False
        ),
    ],style={"display": "flex", "flexDirection": "row", "gap": "10px"}),
    dcc.Graph(id="map-graph", responsive=True, config={"scrollZoom": True})
])

def update_map_page(app, engine, config):

    lock = Lock()
    Thread(target=requery_geo, args=(engine, config, lock), daemon=True).start()

    @app.callback(
        Output("map-graph", "figure"),
        Input("platform-selector", "value"),
        Input("gps-selector", "value"),
        Input("parameter-selector", "value"),
        Input("instrument-selector", "value"),
        Input("date-picker", "date"),
        #Input("time-start", "value"),
        #Input("time-end", "value")
    )
    def update_map(sel_platform, sel_gps, sel_parameter, sel_instrument, date):
        global latest_data_frame
        global latest_sample_time
        # Combine date and time
        #spy_time = datetime.now()
        #print(f'got to update-map at {(datetime.now()-spy_time).microseconds} usec')
        start_datetime = f"{date} 00:00:00"
        end_datetime = f"{date} 23:59:59"
        
        with lock:
            df = latest_data_frame
            # Filter data
            filtered_df = df[(df["sample_time"] >= start_datetime)
                            & (df["sample_time"] <= end_datetime)
                            & (df["platform"] == sel_platform)
                            & (df["parameter"] == sel_parameter)
                            & (df["gps"] == sel_gps)
                            & (df["instrument"] == sel_instrument)
                            ].sort_index()

        # Generate map
        print(len(filtered_df))
        if len(filtered_df) > 500:
            filtered_df=filtered_df[0:500]
        try:
            fig = px.scatter_mapbox(
                filtered_df,
                lat="latitude",
                lon="longitude",
                color="value",
                hover_name="sample_time",
                mapbox_style="open-street-map",
                title=f"Tracks Colored by {sel_parameter} in {filtered_df['unit'].unique()[0]}",
                zoom=15
            )
            #print('got back from line_mapbox')
        except Exception as e:
            print(str(e))
        #print('we have a fig')
        #print(f'finished update at {(datetime.now()-spy_time).microseconds} usec')
        return fig

# Periodically regenerate the map data in the background
def requery_geo(engine, config, lock):
    # Here is the expensive query and page-build
    global latest_data_frame
    global latest_sample_time
    global gps_dates
    global gps_instruments
    global gps_platforms
    global env_instruments
    global env_parameters
    last_measurement_id = None
    while True:
        #print(f'--starting background map refresh at {datetime.now()}')
        gf = get_geolocations(engine)

        gps_instruments_l = gf['instrument'].unique()
        gps_platforms_l = gf['platform'].unique()
        gps_dates_a = gf['sample_time'].dt.date.unique()
        gps_dates_l = [datetime.fromordinal(d.toordinal()) for d in gps_dates_a]
        last_sample_time = max(gf['sample_time'])
        df = None

        if not isinstance(latest_data_frame, pd.DataFrame) or len(latest_data_frame) == 0:
            df = get_measurements_with_alarms_and_locations(engine, start_time=min(gps_dates_l), end_time=max(gps_dates_l))
            env_parameters_l = list(df[(df["acquisition_type"] == 'measurement_calibrated')]['parameter'].unique())
            env_instruments_l = list(df[(df["acquisition_type"] == 'measurement_calibrated')]['instrument'].unique())
        else:
            last_id = latest_data_frame['id'].max()
            df = get_measurements_with_alarms_and_locations(engine, after_id=last_id)
            if len(df) > 0:
                df = pd.concat([latest_data_frame, df])            
                env_parameters_l = list(df[(df["acquisition_type"] == 'measurement_calibrated')]['parameter'].unique())
                env_instruments_l = list(df[(df["acquisition_type"] == 'measurement_calibrated')]['instrument'].unique())

        if isinstance(df, pd.DataFrame) and len(df) > 0:
            with lock:
                latest_sample_time = last_sample_time
                latest_data_frame = df
                gps_dates = gps_dates_l
                gps_instruments = gps_instruments_l
                gps_platforms = gps_platforms_l
                env_instruments = env_instruments_l
                env_parameters = env_parameters_l
        #print(f'--finished background map refresh at {datetime.now()}')

        time.sleep(0.1)  # give some time back to the main thread



if __name__ == "__main__":

    app.run_server(debug=True)