import sys
import os
from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy import create_engine, text
from vandaq_2step_measurements_query import get_2step_query
import pytz   # Or use from zoneinfo import ZoneInfo for Python 3.9+
import yaml


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
DATABASE_URI = 'postgresql+psycopg2://vandaq:p3st3r@localhost:5432/vandaq-dev'

# Establish database connection
engine = create_engine(DATABASE_URI)

# Set date filter
if len(sys.argv) > 1:
    date_str = sys.argv[1]
    try:
        query_date = datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        print("Please provide the date in YYYY-MM-DD format.")
        sys.exit(1)
else:
    query_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

# Define start and end of the date range (start_time is midnight, end_time is midnight of the next day)
start_time = query_date.replace(hour=0, minute=0, second=0, microsecond=0)
end_time = start_time + timedelta(days=1)

gmt_timezone = pytz.timezone('GMT')

for platform in config['platforms']:
    timezone = config[platform]['timezone']
    local_tz = pytz.timezone(config[platform]['timezone'])
    gmt_start_time = (local_tz.localize(start_time)).astimezone(gmt_timezone)
    gmt_end_time = (local_tz.localize(end_time)).astimezone(gmt_timezone)
    destDir = os.path.join(filedir,config[platform]['subdir']) 

    df = get_2step_query(engine, gmt_start_time, gmt_end_time, platform = platform)

    df = add_timezone_column(df, 'sample_time', 'US/Pacific')

    # Write DataFrame to CSV with header and formatted datetime columns
    file_name = f"measurements_{platform}_{start_time.strftime('%Y-%m-%d')}.csv"
    df.to_csv(os.path.join(filedir,file_name), index=False)

    print(f"Measurements saved to {file_name}")

