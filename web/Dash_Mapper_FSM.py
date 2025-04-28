import dash
from dash import dcc, html, Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate
import plotly.express as px
import pandas as pd
import numpy as np
import copy
from datetime import datetime, timedelta, date
import time
import pytz
import random
import json
from threading import Thread, Lock
from sqlalchemy import create_engine
from transitions import Machine

from vandaq_2step_measurements_query import get_measurements_with_alarms_and_locations
from vandaq_2step_measurements_query import get_all_geolocations

global query_results
global logger
query_results = {}

class MapMachine(object):
    states = ['start','wait_new_data','wait_old_data','refresh_new_map','refresh_old_map','idle']

    def __init__(self, config, initial_state='start'):
        self.config = config
        # Create state machine
        self.machine = Machine(model=self, states=MapMachine.states, initial=initial_state)
        # add transitions
        self.machine.add_transition('request_new_data','start','wait_new_data',before='set_date',after='order_date_data')
        self.machine.add_transition('date_selector_changed','wait_new_data','wait_old_data',conditions=self.is_not_today,before='set_date',after='order_date_data')
        self.machine.add_transition('date_selector_changed','wait_old_data','wait_new_data',conditions=self.is_today,before='set_date',after='order_date_data')
        self.machine.add_transition('date_selector_changed','idle','wait_old_data',conditions=self.is_not_today,before='set_date',after='order_date_data')
        self.machine.add_transition('date_selector_changed','idle','wait_new_data',conditions=self.is_today,before='set_date',after='order_date_data')
        self.machine.add_transition('date_selector_changed','refresh_new_map','wait_old_data',conditions=self.is_not_today,before='set_date',after='order_date_data')
        self.machine.add_transition('date_selector_changed','refresh_old_map','wait_new_data',conditions=self.is_today,before='set_date',after='order_date_data')
        self.machine.add_transition('data_arrived','wait_new_data','refresh_new_map')
        self.machine.add_transition('data_arrived','wait_old_data','refresh_old_map')
        self.machine.add_transition('map_refreshed','refresh_new_map','wait_new_data')
        self.machine.add_transition('map_refreshed','refresh_old_map','idle')
        self.machine.add_transition('param_changed','wait_new_data','refresh_new_map')
        self.machine.add_transition('param_changed','idle','refresh_old_map')

    def set_date(self,date=date.today()):
        logger.debug(f'set_date -> {date}')
        self.date = date
    
    def order_date_data(self, **kwargs):
        global query_results
        global lock
        date = kwargs.get("date", self.date)  # Use self.date if date isn't explicitly passed
        logger.debug(f'order_date_data -> {date}')
        with lock:
            if query_results['data'].get(date, None) is None:
                query_results['data'][date] = None
    
    def is_today(self, **kwargs):
        date = kwargs.get("date", self.date)  # Use self.date if date isn't explicitly passed
        logger.debug(f'{date} is_today -> {date == today_date(self.config)}')
        return date == today_date(self.config)

    def is_not_today(self, **kwargs):
        date = kwargs.get("date", self.date)
        logger.debug(f'{date} is_not_today -> {date != today_date(self.config)}')
        return date != today_date(self.config)        

    def data_ready(self):
        global query_results
        global lock
        dataReady = (query_results['data'].get(self.date,None) is not None)
        logger.debug(f'{self.date} data_ready -> {dataReady}')
        with lock:
            return dataReady

    def get_data(self):
        global query_results
        global lock
        with lock:
            return copy.copy(query_results['data'].get(self.date,None))
    
    def serialize(self):
        """Serialize FSM state."""
        return json.dumps({'state': self.state, 'date': str(self.date)})

    @classmethod
    def deserialize(cls, config, data):
        """Reconstruct FSM from stored state."""
        try:
            obj = cls(config, initial_state=data['state'])
        except Exception as e:
            print (f'failed to deserialize: {e}')
        obj.date = date.fromisoformat(data['date']) if data['date'] else None
        return obj        


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
    ip['platforms'] = df['platform'].unique()
    ip['gps_instruments'] = df['gps'].unique()
    instruments = df['instrument'].unique()
    ip['instruments'] = {}
    for instrument in instruments:
        inst_recs = df[(df["instrument"] == instrument)]
        params = inst_recs['parameter'].unique()
        ip['instruments'][instrument] = params
    return ip

check_interval = 2

def layout_map_display(config):
    global query_results
    platform = config['mapping'].get('default_platform')
    gps = config['mapping'].get('default_gps')
    check_interval = config['mapping'].get('map_check_secs', 2)

    while query_results.get('gps_dates') == None:
        time.sleep(0.1)

    page = html.Div([
    html.H1("Drive Map"),
    dcc.Interval(id='check-interval', interval=check_interval * 1000, n_intervals=0),
    dcc.Checklist(
        options=[{'label': 'Today', 'value': 'today'}],
        id='today-checkbox',
        value=['today'],  # Default: today's map
        style={'margin-bottom': '10px'}
    ),
    dcc.Store(id="refresh-trigger", data=0), 
    #html.Button('Do',id="do-something", n_clicks=0), 
    dcc.Store(id="map-state", data={'today_data_len':0, 'map_displayed':False}), 
    dcc.Store(id="fsm-store", data=None, storage_type="session"), 
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
        html.Button('Center',id="center-button", className='map-control-button', n_clicks=0),
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
    global myConfig
    global lock
    global logger

    # for debug:
    global mapState
    mapState = None

    myConfig = config
    logger = config['logger']

    lock = Lock()
    Thread(target=requery_geo, args=(engine, config, lock), daemon=True).start()

    @app.callback(
        Output('fsm-store', 'data', allow_duplicate=True),
        Output('refresh-trigger','data',allow_duplicate=True),
        Output('map-state','data',allow_duplicate=True),
        Output('platform-selector','options'),
        Output('platform-selector','value'),
        Output('gps-selector','options'),
        Output('gps-selector','value'),
        Output('instrument-selector','options'),
        Output('instrument-selector','value'),
        Output('parameter-selector','options',allow_duplicate=True),
        Output('parameter-selector','value',allow_duplicate=True),
        Input('check-interval','n_intervals'),
        State('map-state','data'),
        State('refresh-trigger','data'),
        State('instrument-selector','options'),
        State('fsm-store', 'data'),
        prevent_initial_call=True
    )
    def check_needs_update(check_interval, map_state, refresh_trigger, instrument_selector, fsm_data):
        global myConfig
        # Reconstruct FSM from stored state or create a new one
        if fsm_data:
            fsm = MapMachine.deserialize(config, json.loads(fsm_data))
        else:
            fsm = MapMachine(config)

        if fsm.state == 'start':
            fsm.request_new_data(date=today_date(myConfig))
        elif fsm.state == 'refresh_old_map':
            fsm.machine.set_state('wait_old_data')
        elif fsm.state == 'refresh_new_map':
            fsm.machine.set_state('wait_new_data')

        logger.debug(f'check_needs_update, state = {fsm.state} check interval = {check_interval}')
        # prepare selector value variables
        instruments = no_update
        instrument = no_update
        platforms = no_update
        platform = no_update
        gpss = no_update
        gps = no_update
        parameters = no_update
        parameter = no_update
        if fsm.state == 'wait_new_data':
            if fsm.data_ready():
                df = fsm.get_data()
                if len(df) > map_state['today_data_len'] or map_state['map_displayed'] is False:
                    inst_params = get_instruments_and_params(df)
                    if map_state['today_data_len'] == 0:
                        # this is a first update, populate the selectors
                        platforms = inst_params['platforms']
                        platform = platforms[0]
                        gpss = inst_params['gps_instruments']
                        gps = gpss[0]
                        instruments = list(inst_params['instruments'].keys())
                        instrument = instruments[0]
                        parameters = inst_params['instruments'][instrument]
                        parameter = parameters[0]
                    elif sorted(list(inst_params['instruments'].keys())) != sorted(list(instrument_selector)):
                        # a new instrument has shown up during the drive
                        # Don't disturb the selcted instrument
                        instruments = list(inst_params['instruments'].keys())                
                    logger.debug(f'check_needs_update before new data arrives state = {fsm.state}')
                    try:
                        fsm.data_arrived()
                    except Exception as e:
                        logger.debug(f'wait_new_data Exception on fsm,data_arrived e= {e}')
                    logger.debug(f'check_needs_update after new data arrives state = {fsm.state}')
                    map_state['today_data_len'] = len(df)
                    logger.debug(f'check_needs_update exiting, map_state = {map_state}')
                return fsm.serialize(), refresh_trigger+1,map_state,platforms,platform,gpss,gps,instruments,instrument,parameters,parameter   
        elif fsm.state == 'wait_old_data':
            if fsm.data_ready():
                df = fsm.get_data()
                inst_params = get_instruments_and_params(df)
                instruments = list(inst_params['instruments'].keys())
                instrument = instruments[0]
                platforms = inst_params['platforms']
                platform = platforms[0]
                gpss = inst_params['gps_instruments']
                gps = gpss[0]
                parameters = inst_params['instruments'][instrument]
                parameter = parameters[0]
                logger.debug(f'check_needs_update before old data arrives state = {fsm.state}')
                try:
                    fsm.data_arrived()
                except Exception as e:
                    logger.debug(f'wait_old_data Exception on fsm,data_arrived e= {e}')
                logger.debug(f'check_needs_update after old data arrives state = {fsm.state}')
                return fsm.serialize(),refresh_trigger+1,no_update,platforms,platform,gpss,gps,instruments,instrument,parameters,parameter   

        return fsm.serialize(),no_update,no_update,no_update,no_update,no_update,no_update,no_update,no_update,no_update,no_update  

    @app.callback(
        Output('fsm-store', 'data',allow_duplicate=True),
        Output("date-picker", "disabled"),
        Output("refresh-trigger", "data"),
        Output("date-picker", "date"),
        Output("map-container", "children",allow_duplicate=True),
        Input("today-checkbox", "value"),
        Input("date-picker", "date"),
        State("refresh-trigger", "data"),
        State('fsm-store', 'data'),
        prevent_initial_call=True
    )
    def date_change(today, date, refresh, fsm_data):
        global myConfig
        date_changed_to = no_update
        today_cb_changed = False
        disable_date_picker = False
        map = no_update

        # Reconstruct FSM from stored state or create a new one
        if fsm_data:
            fsm = MapMachine.deserialize(config, json.loads(fsm_data))
        else:
            fsm = MapMachine(config)
        if fsm.state == 'start':
            return fsm.serialize(), no_update, no_update, no_update, no_update, no_update

        picker_date = datetime.strptime(date, '%Y-%m-%d').date()


        logger.debug(f'got to date_change:  date= {date} today={today}')
        for t in ctx.triggered:
            if 'date-picker' in t['prop_id']:
                try:
                    fsm.date_selector_changed(date=picker_date)
                except Exception as e:
                    logger.debug(f'fsm.date_selector_changed failed with {e}')               
            if 'today-checkbox' in t['prop_id']:
                today_cb_changed = True

        if today_cb_changed:
            if today == ["today"]:
                today = today_date(myConfig)
                disable_date_picker = True
                fsm.date_selector_changed(date=today)               
                date_changed_to = today
            else:
                logger.debug(f'in date_change before fsm.date_selector_changed, date = {picker_date} state = {fsm.state}')
                fsm.date_selector_changed(date=picker_date)               
                date_changed_to = picker_date

        if date_changed_to:  
            map = html.H2('Awaiting data...')

            
            return fsm.serialize(), disable_date_picker, refresh+1, date_changed_to, map

        return fsm.serialize(), no_update, no_update, no_update, no_update


        

    @app.callback(
        Output('fsm-store', 'data', allow_duplicate=True),
        Output("map-container", "children",allow_duplicate=True),
        Output('map-state', 'data', allow_duplicate=True),
        Input("refresh-trigger", "data"),
        Input('platform-selector','value'),
        Input('gps-selector','value'),
        Input('parameter-selector','value'),
        State('instrument-selector','value'),
        State('date-picker','date'),
        State('map-state', 'data'),
        State('fsm-store', 'data'),
        prevent_initial_call=True
    )
    def update_map(refresh, sel_platform, sel_gps, sel_parameter, sel_instrument, date, map_state, fsm_data):
        # Combine date and time
        spy_time = datetime.now()

        global mapState

        logger.debug(f'got to update-map at {(datetime.now()-spy_time).total_seconds()} sec, map_state = {map_state}')
        logger.debug(f'update-map , map_state global mapState = {mapState}')

        # this is a horrible kluge
        # map_state store has not been updating upon map panning/zooming
        # so we use the global mapState to get the last updated map_state
        # if mapState and mapState.get('_last_updated'):
        #     map_state = mapState

        parameter_changed = False
        for t in ctx.triggered:
            trigger = t['prop_id']
            if trigger == 'parameter-selector.value':
                parameter_changed = True
            logger.debug(f'update-map trigger {trigger} ')
            logger.debug(f'update-map trigger {trigger} ')

        # Reconstruct FSM from stored state or return
        if fsm_data:
            fsm = MapMachine.deserialize(config, json.loads(fsm_data))
        else:
            return no_update, no_update, no_update

        # if the parameter has changed, we need to refresh the map regardless of state
        if parameter_changed:
            logger.debug('map parameter has changed')
        if (not parameter_changed) and ('wait' in fsm.state):
            return no_update, no_update, no_update


        if ':' in date:
            date = datetime.strptime(date, "%Y-%m-%dT%H:%M:%S").date()
        else:
            date = datetime.strptime(date, "%Y-%m-%d").date()
        
        df = fsm.get_data()        
        
        if isinstance(df, pd.DataFrame):
            logger.debug(f'update-map: about to filter {len(df)} records of data {(datetime.now()-spy_time).total_seconds()} sec')

            # Filter data
            filtered_df = df[(df["platform"] == sel_platform)
                            & (df["parameter"] == sel_parameter)
                            & (df["gps"] == sel_gps)
                            & (df["instrument"] == sel_instrument)
                            ].sort_index()

            # Generate map
            logger.debug(f'update-map: data filtered {(datetime.now()-spy_time).total_seconds()} sec')
            logger.debug(f'update-map: now have {len(filtered_df)} data points')
            if len(filtered_df) > 0:
                if map_state.get('map-position'):
                    logger.debug(f'update-map: mapbox map-position = {map_state["map-position"]}')
                    zoom =  map_state['map-position']['zoom']
                    center = map_state['map-position']['center']
                else:
                    zoom, center = calculate_zoom_level(filtered_df)
                    map_state['map-position'] = {}
                    map_state['map-position'] ['zoom'] = zoom
                    map_state['map-position'] ['center'] = center

                try:
                    # Calculate the 5th and 95th percentiles
                    lower_bound = filtered_df["value"].quantile(0.05)
                    upper_bound = filtered_df["value"].quantile(0.95)
                    logger.debug(f'About to render map, center = {center}, zoom = {zoom}, map state = {map_state}')
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
                        center=center,
                        color_continuous_scale=px.colors.sequential.Viridis,
                        range_color=[lower_bound, upper_bound]
                    )
                    # Add a "You are here" marker for the last data point
                    last_point = df.iloc[-1] if not filtered_df.empty else None
                    if last_point is not None:
                        fig.add_scattermapbox(
                            lat=[last_point["latitude"]],
                            lon=[last_point["longitude"]],
                            mode="markers+text",
                            marker={"size": 20, "color": "red", "symbol": "circle"},
                            text=["You are here"],
                            textposition="top right",
                            showlegend=False,
                            name="Current Location"
                        )

                    map = dcc.Graph(figure=fig, id="map-graph", responsive=True, config={"scrollZoom": True, 'responsive':True})
                    map_state['map_displayed'] = True
                    logger.debug(f'update-map: map created {(datetime.now()-spy_time).total_seconds()} sec')
                except Exception as e:
                    logger.debug(f'update-map: died in exception {e} {(datetime.now()-spy_time).total_seconds()} sec')
                    return fsm.serialize(), no_update, no_update
            else:
                map = html.H1('No Data')
        else:
            map = html.H1('No Data')

        #print('we have a fig')
        #print(f'finished update at {(datetime.now()-spy_time).microseconds} usec')
        
        logger.debug(f'update-map: exiting at {(datetime.now()-spy_time).total_seconds()} sec')
        if not 'wait' in fsm.state:
            try:
                fsm.map_refreshed()
            except Exception as e:
                logger.debug(f'Exception at fsm.map_refreshed() - e={e}')
        
        logger.debug(f'about to return from map refresh, state ={fsm.state}, map_state = {map_state}')

        return fsm.serialize(), map, map_state

    @app.callback(
        Output("refresh-trigger", "data", allow_duplicate=True),
        #Output("map-state", "data", allow_duplicate=True),
        Output("map-state", "data", allow_duplicate=False),
        Input("center-button", "n_clicks"),
        State("map-state", "data"),
        State("refresh-trigger", "data"),
        State('fsm-store', 'data'),
        prevent_initial_call=True
    )
    def center_map(n_clicks, map_state, trigger_data, fsm_data):
        lastcoord = None
        if fsm_data:
            fsm = MapMachine.deserialize(config, json.loads(fsm_data))
        else:
            fsm = MapMachine(config)
        df = fsm.get_data()
        if isinstance(df, pd.DataFrame) and (len(df) > 0):
            rec = df.iloc[-1]
            lastcoord = {'lat':float(rec['latitude']), 'lon':float(rec['longitude'])}
        else:
            return no_update, no_update
        if lastcoord:
            map_state['map-position']["center"] = lastcoord
            logger.debug(f'centered map to {lastcoord}, map_state = {map_state}')
            return trigger_data+1, map_state
        return no_update, no_update


    @app.callback(
        Output("map-state", "data", allow_duplicate=True),
        Input("map-graph", "relayoutData"),
        State("map-state", "data"),
        prevent_initial_call=True
    )
    def store_map_view(relayoutData, map_state):
        global mapState
        logger.debug(f'got to store_map_view, relayoutData = {relayoutData}, map_state = {map_state}')
        if not relayoutData:
            return no_update
        
        #new_state = map_state.copy()
        new_state = map_state
        if not new_state.get('map-position'):
            new_state['map-position'] = {}
        # Capture zoom level
        if "mapbox.zoom" in relayoutData:
            new_state['map-position']["zoom"] = relayoutData["mapbox.zoom"]
            logger.debug(f'Map zoomed to {relayoutData["mapbox.zoom"]}')

        # Capture map center (panning)
        if "mapbox.center" in relayoutData:
            new_state['map-position']["center"] = relayoutData["mapbox.center"]
            logger.debug(f'Map panned to {relayoutData["mapbox.center"]}')

        new_state["_last_updated"] = datetime.now().isoformat()
        logger.debug(f'exiting store_map_view, map_state = {new_state}')
        mapState = new_state
        return new_state



    @app.callback(
        Output('parameter-selector','options',allow_duplicate=True),
        Output('parameter-selector','value',allow_duplicate=True),
        Input('instrument-selector','value'),
        State('fsm-store', 'data'),
        prevent_initial_call=True
    )
    def set_instrument_param_options(instrument, fsm_data):
        logger.debug(f'Callback thread set_instrument_param_options {instrument} ')
        if fsm_data:
            fsm = MapMachine.deserialize(config, json.loads(fsm_data))
        else:
            fsm = MapMachine(config)
        df = fsm.get_data()
        if df is not None and len(df) > 0:
            spy_time = datetime.now()
            inst_params = get_instruments_and_params(df)
            logger.debug(f'set_instrument_param_options, get_instruments_and_params took  {(datetime.now()-spy_time).total_seconds()} seconds')
            params = inst_params['instruments'][instrument]
            #print(f'setting instrument params to {params}')
            return params, params[0]
        return no_update, no_update


def requery_geo(engine, config, lock):
    """Periodically regenerates map data in the background."""
    global query_results
    logger = config['logger']
    rg_id = random.randint(1, 10)

    # Initialize query results
    query_results = {
    }

    local_tz = pytz.timezone(config.get('display_timezone', 'UTC'))

    # Get initial geolocation data
    gf = get_geolocations(engine, config, timezone=config.get('display_timezone', 'UTC'))
    query_results.update({
        'gps_dates': [datetime.fromordinal(d.toordinal()) for d in gf['sample_time'].dt.date.unique()],
        'gps_instruments': gf['instrument'].unique(),
        'gps_platforms': gf['platform'].unique(),
        'all_geolocations': gf,
        'data':{today_date(config):None}
    })

    FULL_REFERESH_EVERY = 10
    full_refresh_counter = FULL_REFERESH_EVERY

    while True:
        # first check for new data for today (if today's data previously fetched)
        today = today_date(config)
        # In case map is run overnight into a new day 
        if not today in query_results['data']:
            query_results['data'][today] = None
        if query_results['data'][today] is not None:
            first_time = local_tz.localize(datetime(today.year, today.month, today.day, 0, 0, 0)).astimezone(pytz.utc)
            last_time = local_tz.localize(datetime(today.year, today.month, today.day, 23, 59, 59)).astimezone(pytz.utc)
            full_refresh_counter -= 1
            full_refresh = False
            if full_refresh_counter <= 0:
                full_refresh = True
                full_refresh_counter = FULL_REFERESH_EVERY
                logger.debug(f'requery_geo full_refresh = {full_refresh}, first_time = {first_time}, last_time = {last_time}')
            else:
                first_time = query_results['data'][today]['sample_time'].max().astimezone(pytz.utc)+timedelta(0,1) if isinstance(query_results['data'][today], pd.DataFrame) and not query_results['data'][today].empty else first_time
            # Fetch new measurements
            df = get_measurements_with_alarms_and_locations(
                engine, start_time=first_time, end_time=last_time,
                platform=None, gps_instrument=None, acquisition_type='measurement_calibrated,measurement_raw'
            )
            # if there's new data to add to today
            if len(df) > 0:
                if not full_refresh:
                    logger.debug(f'requery_geo got additional data for today: {len(df)} records')
                    # convert to local time
                    df['sample_time'] = df['sample_time'].dt.tz_localize('UTC').dt.tz_convert(config.get('display_timezone', 'UTC'))
                    df.set_index('sample_time', inplace=True, drop=False)
                    # concatinate data to today's dataframe
                    with lock: 
                        query_results['data'][today] = pd.concat([query_results['data'][today], df])            
                else:
                    logger.debug(f'requery_geo got new data for today: {len(df)} records')
                    # convert to local time
                    df['sample_time'] = df['sample_time'].dt.tz_localize('UTC').dt.tz_convert(config.get('display_timezone', 'UTC'))
                    df.set_index('sample_time', inplace=True, drop=False)
                    # set today's dataframe to the new data
                    with lock: 
                        query_results['data'][today] = df

        # query for any selected days that do not yet have data 
        empty_days = [day for day in query_results['data'].keys() if query_results['data'][day] is None]
        for day in empty_days:
            first_time = local_tz.localize(datetime(day.year, day.month, day.day, 0, 0, 0)).astimezone(pytz.utc)
            last_time = local_tz.localize(datetime(day.year, day.month, day.day, 23, 59, 59)).astimezone(pytz.utc)
            logger.debug(f'requery_geo original first time ={first_time}, end_time={last_time}')
            start_time = datetime.now()

            logger.debug(f'requery_geo about to query start_time={first_time}, end_time={last_time}')
            # Fetch new measurements
            df = get_measurements_with_alarms_and_locations(
                engine, start_time=first_time, end_time=last_time,
                platform=None, gps_instrument=None, acquisition_type='measurement_calibrated,measurement_raw'
            )
            logger.debug(f'requery_geo got new data for day {day}: {len(df)} records')
 
            if not df.empty:
                df['sample_time'] = df['sample_time'].dt.tz_localize('UTC').dt.tz_convert(config.get('display_timezone', 'UTC'))
                df.set_index('sample_time', inplace=True, drop=False)
                with lock:
                    query_results['data'][day] = df           

        time.sleep(0.5)  # Prevent excessive CPU usage

if __name__ == "__main__":
    app = dash.Dash(__name__)

    connect_string = 'postgresql://vandaq:p3st3r@localhost:5432/vandaq-dev'

    engine = create_engine(connect_string, echo=False)

    app.run_server(debug=True)