
import sys
from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy import create_engine, text

filedir = './filers/files/day/'

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

# SQL Query for the view filtered by date
sql_query = text("""
    SELECT *
    FROM measurement_expanded
    WHERE sample_time >= :start_time
    AND sample_time < :end_time
    ORDER BY sample_time
""")

# Execute query and load results into a DataFrame
with engine.connect() as connection:
    results = connection.execute(sql_query, {'start_time': start_time, 'end_time': end_time})
    df = pd.DataFrame(results.fetchall(), columns=results.keys())

# Convert datetime columns to the specified format
datetime_columns = ['acquisition_time', 'instrument_time', 'sample_time']
for column in datetime_columns:
    if column in df.columns:
        df[column] = pd.to_datetime(df[column]).dt.strftime('%Y/%m/%d %H:%M:%S.%f')

# Write DataFrame to CSV with header and formatted datetime columns
file_name = f"measurements_{start_time.strftime('%Y-%m-%d')}.csv"
df.to_csv(filedir+file_name, index=False)

print(f"Measurements saved to {file_name}")

