from sqlalchemy.orm import aliased
from sqlalchemy import select, func
from datetime import datetime, timedelta
import pandas as pd
from vandaq_schema import *

def get_2step_query(engine, start_time):
    session = sessionmaker(bind=engine)()
 
    # Step 1: Subquery to get the last 5 minutes of measurements
    subquery = (
        select(FactMeasurement)
        .where(FactMeasurement.sample_time >= start_time)
        .subquery()
    )

    # Step 2: Main query to join with dimension tables using the subquery
    query = (
        select(
            subquery.c.id,
            subquery.c.sample_time,
            subquery.c.value,
            subquery.c.string,
            DimInstrument.instrument,
            DimParameter.parameter,
            DimUnit.unit,
            DimAcquisitionType.acquisition_type,
            DimPlatform.platform
        )
        .join(DimInstrument, subquery.c.instrument_id == DimInstrument.id)
        .join(DimParameter, subquery.c.parameter_id == DimParameter.id)
        .join(DimUnit, subquery.c.unit_id == DimUnit.id)
        .join(DimAcquisitionType, subquery.c.acquisition_type_id == DimAcquisitionType.id)
        .join(DimPlatform, subquery.c.platform_id == DimPlatform.id)
    )

    # Execute the query and fetch all results
    results = session.execute(query).fetchall()

    # Convert the result to a pandas DataFrame
    column_names = [
        "id",
        "sample_time",
        "value",
        "string",
        "instrument",
        "parameter",
        "unit",
        "acquisition_type",
        "platform"
    ]
    df = pd.DataFrame(results, columns=column_names)

    
    # Create a column name from the combination of instrument, parameter, unit, and acquisition_type
    df['measurement'] = df['instrument'] + ' | ' + df['parameter'] + ' | ' + df['unit'] + ' | ' + df['acquisition_type']

    # Pivot the DataFrame to get sample_time as index and measurement combinations as columns
    df_pivot = df.pivot_table(index='sample_time', columns='measurement', values='value', aggfunc='mean')

    # Drop rows with no measurements (all NaNs)
    df_pivot.dropna(how='all', inplace=True)

    # Sort the DataFrame by sample_time in ascending order (if not last_only)
    #if not last_only:
    #    df_pivot.sort_index(inplace=True)

    # include the time index as the first column
    df_pivot['sample_time']=df_pivot.index
    cols = df_pivot.columns.tolist()
    cols = cols[-1:] + cols[:-1]
    df_pivot = df_pivot[cols]

    # Close the session
    session.close()

    return df_pivot

# Execute the query
#results = session.execute(query).all()
