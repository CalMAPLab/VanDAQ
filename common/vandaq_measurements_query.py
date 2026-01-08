"""

VanDAQ
Mobile Atmospheric Data Acquisition System

Author: Robert Jay (Robin) Weber
Affiliation: University of California, Berkeley

Copyright (c) 2025 The Regents of the University of California
Released under the BSD 3-Clause License.
"""

from sqlalchemy import create_engine, and_
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func
import pandas as pd
from vandaq_schema import *

# Assume engine is already created with the appropriate database URL
# engine = create_engine('postgresql://user:password@host:port/dbname')
engine = create_engine('postgresql://vandaq:p3st3r@169.229.157.3:5432/vandaq-sandbox', echo=False)
# Create a session
Session = sessionmaker(bind=engine)
session = Session()

def get_measurements(engine, start_time=None, end_time=None, last_only=False):
    session = sessionmaker(bind=engine)()

    # Base query joining all relevant tables
    base_query = session.query(
        func.date_trunc('second', DimTime.time).label('sample_time'),
        DimPlatform.platform,
        DimInstrument.instrument,
        DimParameter.parameter,
        DimUnit.unit,
        DimAcquisitionType.acquisition_type,
        func.avg(FactMeasurement.value).label('avg_value')
    ).join(
        FactMeasurement, FactMeasurement.sample_time_id == DimTime.id
    ).join(
        DimInstrument, FactMeasurement.instrument_id == DimInstrument.id
    ).join(
        DimParameter, FactMeasurement.parameter_id == DimParameter.id
    ).join(
        DimUnit, FactMeasurement.unit_id == DimUnit.id
    ).join(
        DimAcquisitionType, FactMeasurement.acquisition_type_id == DimAcquisitionType.id
    ).group_by(
        func.date_trunc('second', DimTime.time),
        DimInstrument.instrument,
        DimParameter.parameter,
        DimUnit.unit,
        DimAcquisitionType.acquisition_type
    )

    # Apply time filters if provided
    if start_time:
        base_query = base_query.filter(DimTime.time >= start_time)
    if end_time:
        base_query = base_query.filter(DimTime.time <= end_time)

    # If last_only is True, modify the query to return only the last available second
    if last_only:
        # Subquery to find the latest sample_time from FactMeasurement within the filtered range
        latest_time_subquery = session.query(
            func.max(func.date_trunc('second', DimTime.time))
        ).join(
            FactMeasurement, FactMeasurement.sample_time_id == DimTime.id
        ).filter(
            and_(
                DimTime.time >= start_time if start_time else True,
                DimTime.time <= end_time if end_time else True
            )
        ).scalar_subquery()

        # Filter the main query to only return rows matching the latest sample_time
        base_query = base_query.filter(func.date_trunc('second', DimTime.time) == latest_time_subquery)

    # Execute query and load into a pandas DataFrame
    df = pd.read_sql(base_query.statement, session.bind)

    # Create a column name from the combination of instrument, parameter, unit, and acquisition_type
    df['measurement'] = df['platform'] + ' | ' +df['instrument'] + ' | ' + df['parameter'] + ' | ' + df['unit'] + ' | ' + df['acquisition_type']

    # Pivot the DataFrame to get sample_time as index and measurement combinations as columns
    df_pivot = df.pivot_table(index='sample_time', columns='measurement', values='avg_value', aggfunc='mean')

    # Drop rows with no measurements (all NaNs)
    df_pivot.dropna(how='all', inplace=True)

    # Sort the DataFrame by sample_time in ascending order (if not last_only)
    if not last_only:
        df_pivot.sort_index(inplace=True)

    # include the time index as the first column
    df_pivot['sample_time']=df_pivot.index
    cols = df_pivot.columns.tolist()
    cols = cols[-1:] + cols[:-1]
    df_pivot = df_pivot[cols]

    # Close the session
    session.close()

    return df_pivot


# Example usage
# engine = create_engine('postgresql://user:password@localhost:5432/mydatabase')
#df = get_measurements(engine, start_time='2024-08-01', end_time='2024-08-30', last_only=True)
#print(df)

