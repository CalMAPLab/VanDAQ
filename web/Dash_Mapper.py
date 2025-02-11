import dash
from dash import dcc, html, Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate
import plotly.express as px
import pandas as pd
import numpy as np
import copy
from datetime import datetime, timedelta
import time
import pytz
import random
from threading import Thread, Lock

from sqlalchemy import create_engine

from vandaq_2step_measurements_query import get_measurements_with_alarms_and_locations
from vandaq_2step_measurements_query import get_all_geolocations


def get_geolocations(engine, config, timezone= None):
    geo_df = get_all_geolocations(engine)
    if timezone:
        geo_df['sample_time'] = geo_df['sample_time'].dt.tz_localize('UTC').dt.tz_convert(timezone)
        geo_df.set_index('sample_time', inplace = True, drop=False)
    return geo_df




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

def get_instruments_and_params(df):
    ip = {}
    instruments = df['instrument'].unique()
    for instrument in instruments:
        inst_recs = df[(df["instrument"] == instrument)]
        params = inst_recs['parameter'].unique()
        ip[instrument] = params
    return ip



def layout_map_display(config):
    global query_results
    platform = config['mapping'].get('default_platform')
    gps = config['mapping'].get('default_gps')

    while query_results.get('gps_dates') == None:
        time.sleep(0.1)

    page = html.Div([
    html.H1("Drive Map"),
    dcc.Interval(id='check-interval', interval=1 * 1000, n_intervals=0),
    dcc.Checklist(
        options=[{'label': 'Today', 'value': 'today'}],
        id='today-checkbox',
        value=['today'],  # Default: today's map
        style={'margin-bottom': '10px'}
    ),
    dcc.Store(id="refresh-trigger", data=0), 
    #html.Button('Do',id="do-something", n_clicks=0), 
    dcc.Store(id="map-state", data={}), 
    html.Div([
        #html.H3("platform"),
        html.Div([
            html.Div("Date"),
            html.Div(
                dcc.DatePickerSingle(
                    id='date-picker',
                    min_date_allowed=min(query_results['gps_dates']),
                    max_date_allowed=max(query_results['gps_dates']),
                    disabled_days=find_missing_dates(query_results['gps_dates']),
                    display_format='YYYY-MM-DD',
                    date=today_date(config),
                    disabled=True
                ))
            ]),
        html.Div([
            html.Div("Platform"),
            html.Div(
                dcc.Dropdown(
                    id='platform-selector',
                    options=query_results.get('gps_platforms',[]),
                    value=platform,
                    clearable=False
                )
            )
        ]),
        html.Div([
            html.Div("GPS"),
            html.Div(
                dcc.Dropdown(
                    id='gps-selector',
                    options=query_results.get('gps_instruments',[]),
                    value=gps,
                    clearable=False
                )
            )
        ]),
        html.Div([
            html.Div("Instrument"),
            html.Div(
                dcc.Dropdown(
                    id='instrument-selector',
                    options=query_results.get('env_instruments',[]),
                    value=None,
                    clearable=False
                )
            )
        ]),
        html.Div([
            html.Div("Parameter"),
            html.Div(
            dcc.Dropdown(
                id='parameter-selector',
                options=query_results.get('env_parameters',[]),
                value=None,
                clearable=False
            )
            )
        ]),
    ]
    ,style={"display": "flex", "flexDirection": "row", "gap": "10px"}),
    html.Div(id='map-container', children='Awaiting data...')
    ])
    return page

def calculate_mapbox(dataframe):
    min_lat, max_lat = dataframe["latitude"].min(), dataframe["latitude"].max()
    min_lon, max_lon = dataframe["longitude"].min(), dataframe["longitude"].max()
    mapbox = {'style': "carto-positron", 'bounds':{"west": min_lon, "east": max_lon, "south": min_lat, "north": max_lat}}
    return mapbox

def calculate_zoom_level(dataframe):
    """Estimate an appropriate zoom level based on dataset extent."""
    min_lat, max_lat = dataframe["latitude"].min(), dataframe["latitude"].max()
    min_lon, max_lon = dataframe["longitude"].min(), dataframe["longitude"].max()
    lat_range = max_lat - min_lat
    lon_range = max_lon - min_lon
    max_range = max(lat_range, lon_range)
    center={"lat": (min_lat + max_lat) / 2, "lon": (min_lon + max_lon) / 2}

    if max_range > 10:
        zoom = 4  # Zoomed out for large areas
    elif max_range > 1:
        zoom = 6
    elif max_range > 0.1:
        zoom = 9
    elif max_range > 0.01:
        zoom = 12
    else:
        zoom = 14  # Zoomed in for small distances
    
    return zoom, center

def today_date(config):
    local_tz = pytz.utc
    if 'display_timezone' in config:
        local_tz =  pytz.timezone(config['display_timezone'])
    return pytz.utc.localize(datetime.now()).astimezone(local_tz).date()


def update_map_page(app, engine, config):
    global query_results

    lock = Lock()
    Thread(target=requery_geo, args=(engine, config, lock), daemon=True).start()


    @app.callback(
        Output("date-picker", "disabled"),
        Output("refresh-trigger", "data"),
        Output("date-picker", "date"),
        Output('map-state','data', allow_duplicate=True),
        Output('platform-selector','options'),
        Output('platform-selector','value'),
        Output('gps-selector','options'),
        Output('gps-selector','value'),
        Output("map-container", "children",allow_duplicate=True),
        Input("today-checkbox", "value"),
        Input("date-picker", "date"),
        State("refresh-trigger", "data"),
        State('map-state', 'data'),
        prevent_initial_call=True
    )
    def date_change(today, date, refresh, map_state):
        global query_results
        date_changed_to = None
        today_cb_changed = False
        disable_date_picker = False
        map = no_update
        for t in ctx.triggered:
            if 'date-picker' in t['prop_id']:
                picker_date = datetime.strptime(t['value'], '%Y-%m-%d').date()
                if picker_date != query_results['day']:
                    query_results['day'] = picker_date
                    date_changed_to = picker_date
                    map_state['needs_refresh'] = True
            if 'today-checkbox' in t['prop_id']:
                today_cb_changed = True

        if today_cb_changed:
            map_state['needs_refresh'] = True
            if today == ["today"]:
                today = today_date(config)
                disable_date_picker = True
                date_changed_to = today
            else:
                picker_date = datetime.strptime(date, '%Y-%m-%d').date()
                date_changed_to = picker_date

        if date_changed_to:  
            if map_state.get('map-position'):
                map_state.pop('map-position')
            start_time = datetime(query_results['day'].year, query_results['day'].month, query_results['day'].day,0,0,0)
            end_time = datetime(query_results['day'].year, query_results['day'].month, query_results['day'].day,23,59,59)
            gl = query_results['all_geolocations']
            geo_subset = gl[(gl["sample_time"] >= start_time)
                            & (gl["sample_time"] <= end_time)]
            platforms = list(geo_subset['platform'].unique())
            gpss = list(geo_subset['instrument'].unique())
            platform = None
            if platforms:
                platform = platforms[0]
            gps = None
            if gpss:
                gps = gpss[0]
            with lock:
                query_results['day'] = date_changed_to
                #query_results['latest_data_frame'][query_results['day']] = None
                query_results['selected_platform'] = platform
                query_results['selected_gps'] = gps
                query_results['awaiting_data'] = True
            map = html.H2('Awaiting data...')


            if not date_changed_to:
                date_changed_to = no_update

            return disable_date_picker, refresh+1, date_changed_to, map_state, platforms, platform, gpss, gps, map

        raise PreventUpdate


        

    @app.callback(
        Output("map-container", "children",allow_duplicate=True),
        Output('map-state', 'data', allow_duplicate=True),
        Input("refresh-trigger", "data"),
        Input('platform-selector','value'),
        Input('gps-selector','value'),
        Input('parameter-selector','value'),
        State('instrument-selector','value'),
        State('date-picker','date'),
        State('map-state', 'data'),
        prevent_initial_call=True
    )
    def update_map(refresh, sel_platform, sel_gps, sel_parameter, sel_instrument, date, map_state):
        global query_results
        # Combine date and time
        spy_time = datetime.now()
        #print(f'got to update-map at {(datetime.now()-spy_time).total_seconds()} sec')

        if ':' in date:
            date = datetime.strptime(date, "%Y-%m-%dT%H:%M:%S").date()
        else:
            date = datetime.strptime(date, "%Y-%m-%d").date()
        start_datetime = datetime(date.year, date.month, date.day, 0, 0, 0)
        end_datetime = datetime(date.year, date.month, date.day, 23, 59, 59)
        if 'display_timezone' in config:
            local_tz = pytz.timezone(config['display_timezone'])
            start_datetime = local_tz.localize(start_datetime).astimezone(pytz.utc)
            end_datetime = local_tz.localize(end_datetime).astimezone(pytz.utc)
        qr = {}
        with lock:
            qr = query_results
        
        df = qr['latest_data_frame'].get(qr['day'],None)
        if isinstance(df, pd.DataFrame):
            #print(f'about to filter data {(datetime.now()-spy_time).total_seconds()} sec')

            # Filter data
            filtered_df = df[(df["sample_time"] >= start_datetime)
                            & (df["sample_time"] <= end_datetime)
                            & (df["platform"] == sel_platform)
                            & (df["parameter"] == sel_parameter)
                            & (df["gps"] == sel_gps)
                            & (df["instrument"] == sel_instrument)
                            ].sort_index()

            # Generate map
            #print(f'data filtered {(datetime.now()-spy_time).total_seconds()} sec')
            #print(len(filtered_df))
            if len(filtered_df) > 0:
                if map_state.get('map-position'):
                    zoom =  map_state['map-position']['zoom']
                    center = map_state['map-position']['center']
                else:
                    zoom, center = calculate_zoom_level(filtered_df)
                    map_state['map-position'] = {}
                    map_state['map-position'] ['zoom'] = zoom
                    map_state['map-position'] ['center'] = center

                try:
                    fig = px.scatter_mapbox(
                        filtered_df,
                        lat="latitude",
                        lon="longitude",
                        color="value",
                        height=600,
                        hover_name="sample_time",
                        mapbox_style="open-street-map",
                        title=f"Tracks Colored by {sel_parameter} in {filtered_df['unit'].unique()[0]}",
                        zoom=zoom, 
                        center=center
                    )
                    #fig.update_layout(mapbox=bounding_box)
                    map = dcc.Graph(figure=fig, id="map-graph", responsive=True, config={"scrollZoom": True})
                    #print(f'map created {(datetime.now()-spy_time).total_seconds()} sec')
                    #print('got back from line_mapbox')
                except Exception as e:
                    #print(str(e))
                    raise PreventUpdate
            else:
                map = html.H1('No Data')
        else:
            map = html.H1('No Data')

        if qr.get('awaiting_data'):
            map = html.H2('Awaiting data...')
        #print('we have a fig')
        #print(f'finished update at {(datetime.now()-spy_time).microseconds} usec')
        

        return map, map_state

    @app.callback(
        Output("map-state", "data", allow_duplicate=True),
        Input("map-graph", "relayoutData"),
        State("map-state", "data"),
        prevent_initial_call=True
    )
    def store_map_view(relayoutData, map_state):
        if not relayoutData:
            raise dash.exceptions.PreventUpdate
        
        new_state = map_state.copy()
        if not new_state.get('map-position'):
            new_state['map-position'] = {}
        # Capture zoom level
        if "mapbox.zoom" in relayoutData:
            new_state['map-position']["zoom"] = relayoutData["mapbox.zoom"]
            #print(f'Map zoomed to {relayoutData["mapbox.zoom"]}')

        # Capture map center (panning)
        if "mapbox.center" in relayoutData:
            new_state['map-position']["center"] = relayoutData["mapbox.center"]
            #print(f'Map panned to {relayoutData["mapbox.center"]}')

        return new_state


    @app.callback(
        Output('refresh-trigger','data',allow_duplicate=True),
        Output('map-state','data',allow_duplicate=True),
        Output('instrument-selector','options'),
        Output('instrument-selector','value'),
        Input('check-interval','n_intervals'),
        State('map-state','data'),
        State('refresh-trigger','data'),
        prevent_initial_call=True
    )
    def check_needs_update(check_interval, map_state, refresh_trigger):
        global query_results
        #print('got here')
        new_data_for_day = False
        with lock:
            day = query_results.get('day')
            new_data_for_day = query_results.get('new_data_for_day')
            df = None
            if day:
                    df = query_results['latest_data_frame'].get(day)        

        if new_data_for_day:
            df_last_sample_time = df['sample_time'].max()
            map_state['needs_refresh'] = True
            map_state['latest_sample_time'] = df_last_sample_time
            return refresh_trigger+1, map_state, no_update, no_update 

        if map_state.get('needs_refresh'):
            day = query_results.get('day')
            if day:
                if isinstance(df, pd.DataFrame) and (len(df) > 0) and (not query_results.get('awaiting_data')):
                    inst_params = get_instruments_and_params(df)
                    instruments = list(inst_params.keys())
                    params = inst_params[instruments[0]]
                    map_state['needs_refresh'] = False
                    return refresh_trigger+1, map_state, instruments, instruments[0] 
        #raise PreventUpdate
        return no_update,no_update,no_update,no_update   

    @app.callback(
        Output('parameter-selector','options'),
        Output('parameter-selector','value'),
        Input('instrument-selector','value'),
        prevent_initial_call=True
    )
    def set_instrument_param_options(instrument):
        global query_results
        day = query_results.get('day')
        if day:
            df = query_results['latest_data_frame'].get(day)
            if isinstance(df, pd.DataFrame) and len(df) > 0:
                inst_params = get_instruments_and_params(df)
                params = inst_params[instrument]
                #print(f'setting instrument params to {params}')
                return params, params[0]
        return no_update

# Periodically regenerate the map data in the background
def requery_geo(engine, config, lock):
    # Here is the expensive query and page-build
    global query_results
    rg_id = random.randint(1, 10)
    query_results = {}
    query_results['latest_data_frame'] = {}
    last_measurement_id = None
    local_tz = pytz.utc
    if 'display_timezone' in config:
        local_tz =  pytz.timezone(config['display_timezone'])
    todays_date = today_date(config)
    query_results['day'] = todays_date
    last_day = today_date(config)
    platform = config['mapping'].get('default_platform')
    gps = config['mapping'].get('default_gps')
    gf = get_geolocations(engine, config)

    gps_instruments_l = gf['instrument'].unique()
    gps_platforms_l = gf['platform'].unique()
    gps_dates_a = gf['sample_time'].dt.date.unique()
    gps_dates_l = [datetime.fromordinal(d.toordinal()) for d in gps_dates_a]
    query_results['gps_dates'] = gps_dates_l
    query_results['gps_instruments'] = gps_instruments_l
    query_results['gps_platforms'] = gps_platforms_l
    query_results['all_geolocations'] = gf
    while True:
        #print(f'--starting background map refresh at {datetime.now()}')
        df = None

        map_day = query_results['day']

        # if last_day != map_day:
        #     print(f'thread {rg_id} - Changing from day {last_day} to {map_day}')
        # else:
        #     print(f'thread {rg_id} - day is {map_day}')

        previous_df = query_results['latest_data_frame'].get(map_day,None)
        first_time =  local_tz.localize(datetime(map_day.year, map_day.month, map_day.day, 0,0,0)).astimezone(pytz.utc)
        last_time =  local_tz.localize(datetime(map_day.year, map_day.month, map_day.day, 23,59,59)).astimezone(pytz.utc)

        if not isinstance(previous_df, pd.DataFrame) or (len(previous_df) == 0):
            last_measurement_id = None
        else:
            if isinstance(previous_df, pd.DataFrame) and len(previous_df) > 0:
                last_measurement_id = previous_df['id'].max()

        last_day = map_day
        start_time = datetime.now()
        platform = None
        gps = None
        df = get_measurements_with_alarms_and_locations(engine, start_time=first_time, end_time=last_time, platform=platform, gps_instrument=gps, acquisition_type='measurement_calibrated', after_id = last_measurement_id)
        #print(f'thread {rg_id} - map query got {len(df)} records, last meas_id = {last_measurement_id}, took {(datetime.now() - start_time).total_seconds()} seconds')
        new_data_for_day = False
        if len(df) > 0:
            if 'display_timezone' in config:
                df['sample_time'] = df['sample_time'].dt.tz_localize('UTC').dt.tz_convert(config['display_timezone'])
                df.set_index('sample_time', inplace = True, drop=False)
        if last_measurement_id and isinstance(previous_df, pd.DataFrame) and (len(df) > 0):
            df = pd.concat([previous_df, df])
            new_data_for_day = True
        elif isinstance(previous_df, pd.DataFrame):
            df = previous_df

        if isinstance(df, pd.DataFrame) and len(df) > 0:
            new_results = copy.copy(query_results)
            new_results['latest_data_frame'][map_day] = df
            new_results['awaiting_data'] = False
            new_results['new_data_for_day'] = new_data_for_day

            with lock:
                query_results = new_results
        else:
            query_results['latest_sample_time'] = datetime.now()

        time.sleep(0.5)  # give some time back to the main thread



if __name__ == "__main__":
    app = dash.Dash(__name__)

    connect_string = 'postgresql://vandaq:p3st3r@localhost:5432/vandaq-test'

    engine = create_engine(connect_string, echo=False)

    app.run_server(debug=True)