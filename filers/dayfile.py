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
import pytz   # Or use from zoneinfo import ZoneInfo for Python 3.9+
import yaml
import argparse
sys.path.append('/home/vandaq/vandaq/common')
from vandaq_2step_measurements_query import get_measurements_with_alarms_from_view
from vandaq_2step_measurements_query import get_measurements_with_alarms_and_locations



def add_timezone_column(df, time_col, target_tz):
    """
    Adds a new column to the DataFrame with the specified time zone conversion
    and reorders the columns to position the new column next to the original time column.

    Parameters:
    - df (pd.DataFrame): The DataFrame containing the time data.
    - time_col (str): The name of the column with UTC times.
    - target_tz (str): The target time zone (e.g., 'US/Pacific').

    Returns:
    - pd.DataFrame: The modified DataFrame with the new time zone column.
    """
    if time_col not in df.columns:
        raise ValueError(f"Column '{time_col}' not found in DataFrame.")

    # Ensure the sample_time column is in datetime format
    df[time_col] = pd.to_datetime(df[time_col])

    # Convert the times to the specified timezone
    target_timezone = pytz.timezone(target_tz)
    new_col_name = f"{time_col}_{target_tz.replace('/', '_')}"
    df[new_col_name] = df[time_col].dt.tz_localize('UTC').dt.tz_convert(target_timezone)

    # Reorder columns to place the new column next to the original time column
    col_index = df.columns.get_loc(time_col)  # Find the index of the original column
    reordered_columns = (
        list(df.columns[:col_index + 1])  # Columns before and including the original column
        + [new_col_name]  # Add the new time zone column
        + list(df.columns[col_index + 1:-1])  # Remaining columns excluding the new column
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
    
# Replace with your PostgreSQL connection details
DATABASE_URI = config['db_connect_string']

# Establish database connection
engine = create_engine(DATABASE_URI)

gmt_timezone = pytz.timezone('GMT')


parser.add_argument('data_date', nargs='?', default=None,
                    help='the date of the data (local timezone)')
parser.add_argument('--nogps', action='store_true',
                    help='dump all data regardless of if there are geolocations')
args = parser.parse_args()


# Set date filter
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

# Define start and end of the date range (start_time is midnight, end_time is midnight of the next day)
start_time = query_date.replace(hour=0, minute=0, second=0, microsecond=0)
end_time = start_time + timedelta(days=1)

for platform in config['platforms']:
    timezone = config[platform]['timezone']
    main_gps = config[platform]['gps_instrument']
    local_tz = pytz.timezone(config[platform]['timezone'])
    gmt_start_time = (local_tz.localize(start_time)).astimezone(gmt_timezone)
    gmt_end_time = (local_tz.localize(end_time)).astimezone(gmt_timezone)
    destDir = os.path.join(filedir,config[platform]['subdir']) 

    if no_gps:
        st_time = datetime.now()
        print(f'Starting non-geolocated query at {datetime.now()}')
        df = get_measurements_with_alarms_from_view(engine, start_time=gmt_start_time, end_time=gmt_end_time, platform = platform, wide=False)
        print(f'non-geolocated query completed at {datetime.now()}, took {(datetime.now()-st_time).total_seconds()} seconds')
    else:
        print('Starting geolocated query at {datetime.now()}')
        df = get_measurements_with_alarms_and_locations(engine, start_time=gmt_start_time, end_time=gmt_end_time, gps_instrument=main_gps, platform = platform)
    if len(df) > 0:
        df = add_timezone_column(df, 'sample_time', 'US/Pacific')

        if len(df) == 0:
            if no_gps:
                print('no data for {parser.data_date}')
            else:
                print('no geolocation data for {parser.data_date}')
            exit()

        # Write DataFrame to CSV with header and formatted datetime columns
        nogeo = ''
        if no_gps:
            nogeo = 'no-geolocations_'
        file_name = f"measurements_{platform}_{start_time.strftime('%Y-%m-%d')}_{nogeo}long.csv"
        print(f'at {datetime.now()} writing file {file_name}')
        df.to_csv(os.path.join(filedir,file_name), index=False)


        # df = get_measurements_with_alarms_and_locations(engine, gmt_start_time, end_time=gmt_end_time, platform = platform, wide=True)
        # df = add_timezone_column(df, 'sample_time', 'US/Pacific')

        # # Write DataFrame to CSV with header and formatted datetime columns
        # file_name = f"measurements_{platform}_{start_time.strftime('%Y-%m-%d')}_wide.csv"
        # df.to_csv(os.path.join(filedir,file_name), index=False)

        print(f"Measurements saved to {file_name}")
    else:
        print(f"No measurements found for {platform} between {start_time} and {end_time}.")
        continue
