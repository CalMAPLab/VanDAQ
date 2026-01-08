"""

VanDAQ
Mobile Atmospheric Data Acquisition System

Author: Robert Jay (Robin) Weber
Affiliation: University of California, Berkeley

Copyright (c) 2025 The Regents of the University of California
Released under the BSD 3-Clause License.
"""

import time

def debugwait(message, iters):
    print(message+' waiting...')
    for i in range(0,iters):
        print('.',end='')
        time.sleep(0.1)
    print(':')

import sys
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
from sqlalchemy import create_engine, text
import pytz
import yaml
import argparse
sys.path.append('/home/vandaq/vandaq/common')
from vandaq_2step_measurements_query import (
    get_measurements_with_alarms_from_view,
    get_measurements_with_alarms_and_locations,
    get_all_geolocations
)

def add_timezone_column(df, time_col, target_tz):
    if time_col not in df.columns:
        raise ValueError(f"Column '{time_col}' not found in DataFrame.")
    df[time_col] = pd.to_datetime(df[time_col])
    target_timezone = pytz.timezone(target_tz)
    new_col_name = f"{time_col}_{target_tz.replace('/', '_')}"
    df[new_col_name] = df[time_col].dt.tz_localize('UTC').dt.tz_convert(target_timezone)
    col_index = df.columns.get_loc(time_col)
    reordered_columns = (
        list(df.columns[:col_index + 1]) + [new_col_name] + list(df.columns[col_index + 1:-1])
    )
    df = df[reordered_columns]
    return df

parser = argparse.ArgumentParser(description='VanDAQ create daily data file starting at midnight')

configfile_name = '/home/vandaq/vandaq/filers/dayfile.yaml'
try:
    configfile = open(configfile_name,'r')
    config = yaml.load(configfile, Loader=yaml.FullLoader)
    configfile.close()
except:
    print("Cannot load config file "+configfile_name)
    exit()

filedir = './filers/files/day/'
if 'directory' in config:
    filedir = config['directory']

DATABASE_URI = config['db_connect_string']
engine = create_engine(DATABASE_URI)
gmt_timezone = pytz.timezone('GMT')

parser.add_argument('data_date', nargs='?', default=None,
                    help='the date of the data (local timezone)')
parser.add_argument('--nogps', action='store_true',
                    help='dump all data regardless of if there are geolocations')
parser.add_argument('--all_drive_data', action='store_true',
                    help='dump all data from first to last geolocation point for the day')
args = parser.parse_args()

if args.data_date:
    date_str = args.data_date
    try:
        query_date = datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        print("Please provide the date in YYYY-MM-DD format.")
        sys.exit(1)
else:
    local_tz = pytz.timezone(config['timezone'])
    query_date = datetime.now().replace(tzinfo=gmt_timezone).astimezone(local_tz).replace(hour=0, minute=0, second=0, microsecond=0,tzinfo=None)

no_gps = args.nogps
all_drive_data = args.all_drive_data

start_time = query_date.replace(hour=0, minute=0, second=0, microsecond=0)
end_time = start_time + timedelta(days=1)

for platform in config['platforms']:
    timezone = config[platform]['timezone']
    main_gps = config[platform]['gps_instrument']
    local_tz = pytz.timezone(timezone)
    gmt_start_time = (local_tz.localize(start_time)).astimezone(gmt_timezone)
    gmt_end_time = (local_tz.localize(end_time)).astimezone(gmt_timezone)
    destDir = os.path.join(filedir,config[platform]['subdir'])

    if all_drive_data:
        geo_df = get_all_geolocations(engine)
        geo_df = geo_df[geo_df['platform'] == platform]
        geo_df['sample_time'] = pd.to_datetime(geo_df['sample_time']).dt.tz_localize('UTC')
        geo_df = geo_df[(geo_df['sample_time'] >= gmt_start_time) & (geo_df['sample_time'] <= gmt_end_time)]

        if geo_df.empty:
            print(f"No geolocation data found for platform {platform} on {query_date}")
            continue

        gps_start = geo_df['sample_time'].min()
        gps_end = geo_df['sample_time'].max()

        print(f"Using GPS window: {gps_start} to {gps_end}")

        st_time = datetime.now()
        print(f'Starting drive-range data query at {datetime.now()}')
        df = get_measurements_with_alarms_from_view(engine, start_time=gps_start, end_time=gps_end, platform=platform, wide=False)
        print(f'Drive-range query completed at {datetime.now()}, took {(datetime.now()-st_time).total_seconds()} seconds')

    elif no_gps:
        st_time = datetime.now()
        print(f'Starting non-geolocated query at {datetime.now()}')
        df = get_measurements_with_alarms_from_view(engine, start_time=gmt_start_time, end_time=gmt_end_time, platform=platform, wide=False)
        print(f'non-geolocated query completed at {datetime.now()}, took {(datetime.now()-st_time).total_seconds()} seconds')

    else:
        print(f'Starting geolocated query at {datetime.now()}')
        df = get_measurements_with_alarms_and_locations(engine, start_time=gmt_start_time, end_time=gmt_end_time, gps_instrument=main_gps, platform=platform)

    if len(df) > 0:
        df = add_timezone_column(df, 'sample_time', 'US/Pacific')

        if len(df) == 0:
            if no_gps:
                print(f'no data for {args.data_date}')
            else:
                print(f'no geolocation data for {args.data_date}')
            exit()

        prefix = ''
        if all_drive_data:
            prefix = 'drive_range_'
        elif no_gps:
            prefix = 'no-geolocations_'

        file_name = f"measurements_{platform}_{start_time.strftime('%Y-%m-%d')}_{prefix}long.csv"
        print(f'at {datetime.now()} writing file {file_name}')
        df.to_csv(os.path.join(filedir, file_name), index=False)

        print(f"Measurements saved to {file_name}")
    else:
        print(f"No measurements found for {platform} between {start_time} and {end_time}.")
        continue
