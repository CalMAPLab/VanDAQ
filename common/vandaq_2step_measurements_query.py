"""

VanDAQ
Mobile Atmospheric Data Acquisition System

Author: Robert Jay (Robin) Weber
Affiliation: University of California, Berkeley

Copyright (c) 2025 The Regents of the University of California
Released under the BSD 3-Clause License.
"""

from sqlalchemy.orm import aliased, sessionmaker
from sqlalchemy import create_engine, select, exists, func, and_, case
from datetime import datetime, timedelta, date
import pandas as pd
from vandaq_schema import *
from collections import defaultdict

def get_2step_query(engine, start_time, end_time=None, platform=None):
    session = sessionmaker(bind=engine)()

    if not end_time:
        end_time = datetime.now()

    platform_id = None

    if platform:
        platform_query = (
            select(DimPlatform)
            .where((DimPlatform).platform == platform))
        compiled_query = platform_query.compile(session.bind, compile_kwargs={"literal_binds": True})

        pdf = pd.read_sql(str(compiled_query), session.bind)
        if pdf.shape[0]:
             platform_id = int(pdf['id'][0])
                
    # Step 1: Subquery to get the time frame of measurements
    if platform_id:
        subquery = (
            select(FactMeasurement)
            .where(and_((FactMeasurement.sample_time >= start_time),
                    (FactMeasurement.sample_time <= end_time),
                    (FactMeasurement.platform_id == platform_id)
                    ))  
            .subquery()
        )        
    else:    
        subquery = (
            select(FactMeasurement)
            .where(and_((FactMeasurement.sample_time >= start_time),
                    (FactMeasurement.sample_time <= end_time)))  
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


    compiled_query = query.compile(session.bind, compile_kwargs={"literal_binds": True})

    # Use pandas to execute the compiled query and load it into a DataFrame
    df = pd.read_sql(str(compiled_query), session.bind)

    '''
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
    '''
    
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

def get_2step_query_with_alarms(engine, start_time, end_time=None, platform=None, wide=True, include_engineering=True):
    session = sessionmaker(bind=engine)()

    if not end_time:
        end_time = datetime.now()

    platform_id = None

    if platform:
        platform_query = (
            select(DimPlatform)
            .where(DimPlatform.platform == platform))
        compiled_query = platform_query.compile(session.bind, compile_kwargs={"literal_binds": True})

        pdf = pd.read_sql(str(compiled_query), session.bind)
        if pdf.shape[0]:
            platform_id = int(pdf['id'][0])

    # Step 1: Subquery to get the time frame of measurements
    if platform_id:
        measurement_subquery = (
            select(FactMeasurement)
            .where(and_((FactMeasurement.sample_time >= start_time),
                        (FactMeasurement.sample_time <= end_time),
                        (FactMeasurement.platform_id == platform_id)))
            .order_by(FactMeasurement.sample_time)
            .subquery()
        )
    else:
        measurement_subquery = (
            select(FactMeasurement)
            .where(and_((FactMeasurement.sample_time >= start_time),
                        (FactMeasurement.sample_time <= end_time)))
            .order_by(FactMeasurement.sample_time)
            .subquery()
        )

    if not include_engineering:
        # Get the id of the "engineering" acquisition type from the DimAcquisitionType table
        engineering_query = (
            select(DimAcquisitionType.id)
            .where(DimAcquisitionType.acquisition_type == "engineering")
        )
        compiled_query = engineering_query.compile(session.bind, compile_kwargs={"literal_binds": True})
        pdf = pd.read_sql(str(compiled_query), session.bind)
        engineering_id = int(pdf['id'][0]) if not pdf.empty else None
        if engineering_id:
            measurement_subquery = (
                select(measurement_subquery)
                .where(measurement_subquery.c.acquisition_type_id != engineering_id)
                .subquery()
            )

    # Step 2: Scoped alarm aggregation
    alarm_aggregation = (
        select(
            FactAlarm.measurement_id,
            func.count(FactAlarm.id).label("alarm_count"),
            func.max(FactAlarm.alarm_level_id).label("max_alarm_level"),
            func.string_agg(FactAlarm.message, "|").label("concatenated_messages")
        )
        .where(FactAlarm.measurement_id.in_(
            select(measurement_subquery.c.id)
        ))
        .group_by(FactAlarm.measurement_id)
        .subquery()
    )

    # Step 3: Main query
    query = (
        select(
            measurement_subquery.c.id,
            measurement_subquery.c.sample_time,
            measurement_subquery.c.value,
            measurement_subquery.c.string,
            DimInstrument.instrument,
            DimParameter.parameter,
            DimUnit.unit,
            DimAcquisitionType.acquisition_type,
            DimPlatform.platform,
            func.coalesce(alarm_aggregation.c.alarm_count, 0).label("alarm_count"),
            func.coalesce(alarm_aggregation.c.max_alarm_level, 0).label("max_alarm_level"),
            func.coalesce(alarm_aggregation.c.concatenated_messages, "").label("alarm_messages")
        )
        .join(DimInstrument, measurement_subquery.c.instrument_id == DimInstrument.id)
        .join(DimParameter, measurement_subquery.c.parameter_id == DimParameter.id)
        .join(DimUnit, measurement_subquery.c.unit_id == DimUnit.id)
        .join(DimAcquisitionType, measurement_subquery.c.acquisition_type_id == DimAcquisitionType.id)
        .join(DimPlatform, measurement_subquery.c.platform_id == DimPlatform.id)
        .outerjoin(alarm_aggregation, measurement_subquery.c.id == alarm_aggregation.c.measurement_id)
#        .order_by(FactMeasurement.sample_time)
    )

    compiled_query = query.compile(session.bind, compile_kwargs={"literal_binds": True})

    # Use pandas to execute the compiled query and load it into a DataFrame
    df = pd.read_sql(str(compiled_query), session.bind)

    df.set_index('sample_time', inplace=True, drop=False)
    if wide:

        # Create a column name from the combination of instrument, parameter, unit, and acquisition_type
        df['measurement'] = (
            df['instrument'] + ' | ' + df['parameter'] + ' | ' + df['unit'] + ' | ' + df['acquisition_type']
        )

        # Pivot the DataFrame
        df_pivot = df.pivot(index='sample_time', columns='measurement', values=[
            'value', 'string', 'alarm_count', 'max_alarm_level', 'alarm_messages'
        ])

        # Flatten the multi-index columns
        df_pivot.columns = [' | '.join(col).strip() for col in df_pivot.columns.values]

        # Drop rows with no measurements (all NaNs in "value" columns)
        value_columns = [col for col in df_pivot.columns if 'value' in col]
        df_pivot.dropna(subset=value_columns, how='all', inplace=True)

        # Sort columns by instrument and parameter, and reorder within each measurement group
        def column_sort_key(col_name):
            parts = col_name.split(" | ")
            measurement_part = " | ".join(parts[1:3])  # Instrument and Parameter
            column_type = parts[0]  # value, string, etc.
            column_order = ['value', 'string', 'alarm_count', 'max_alarm_level', 'alarm_messages']
            return (measurement_part, column_order.index(column_type) if column_type in column_order else 99)

        df_pivot = df_pivot[sorted(df_pivot.columns, key=column_sort_key)]

        # Add the time index as the first column
        df_pivot['sample_time'] = df_pivot.index
        cols = df_pivot.columns.tolist()
        cols = cols[-1:] + cols[:-1]
        df_pivot = df_pivot[cols]
        df = df_pivot

    # Close the session
    session.close()

    return df

def get_measurements_with_alarms_from_view(engine, start_time, end_time=None, platform=None, wide=True):
    session = sessionmaker(bind=engine)()

    if not end_time:
        end_time = datetime.now()

    platform_id = None

    if platform:
        platform_query = (
            select(DimPlatform)
            .where(DimPlatform.platform == platform))
        compiled_query = platform_query.compile(session.bind, compile_kwargs={"literal_binds": True})

        pdf = pd.read_sql(str(compiled_query), session.bind)
        if pdf.shape[0]:
            platform_id = int(pdf['id'][0])

    # View query
    if platform:
        measurement_query = (
            select(ViewMeasurementAndAlarm)
            .where(and_((ViewMeasurementAndAlarm.sample_time >= start_time),
                        (ViewMeasurementAndAlarm.sample_time <= end_time),
                        (ViewMeasurementAndAlarm.platform == platform)))
            .order_by(ViewMeasurementAndAlarm.sample_time)

        )
    else:
        measurement_query = (
            select(ViewMeasurementAndAlarm)
            .where(and_((ViewMeasurementAndAlarm.sample_time >= start_time),
                        (ViewMeasurementAndAlarm.sample_time <= end_time)))
            .order_by(ViewMeasurementAndAlarm.sample_time)
            .subquery()
        )


    compiled_query = measurement_query.compile(session.bind, compile_kwargs={"literal_binds": True})

    # Use pandas to execute the compiled query and load it into a DataFrame
    df = pd.read_sql(str(compiled_query), session.bind)

    df.set_index('sample_time', inplace=True, drop=False)
    if wide:

        # Create a column name from the combination of instrument, parameter, unit, and acquisition_type
        df['measurement'] = (
            df['instrument'] + ' | ' + df['parameter'] + ' | ' + df['unit'] + ' | ' + df['acquisition_type']
        )

        # Pivot the DataFrame
        df_pivot = df.pivot(index='sample_time', columns='measurement', values=[
            'value', 'string', 'alarm_count', 'max_alarm_level', 'alarm_messages'
        ])

        # Flatten the multi-index columns
        df_pivot.columns = [' | '.join(col).strip() for col in df_pivot.columns.values]

        # Drop rows with no measurements (all NaNs in "value" columns)
        value_columns = [col for col in df_pivot.columns if 'value' in col]
        df_pivot.dropna(subset=value_columns, how='all', inplace=True)

        # Sort columns by instrument and parameter, and reorder within each measurement group
        def column_sort_key(col_name):
            parts = col_name.split(" | ")
            measurement_part = " | ".join(parts[1:3])  # Instrument and Parameter
            column_type = parts[0]  # value, string, etc.
            column_order = ['value', 'string', 'alarm_count', 'max_alarm_level', 'alarm_messages']
            return (measurement_part, column_order.index(column_type) if column_type in column_order else 99)

        df_pivot = df_pivot[sorted(df_pivot.columns, key=column_sort_key)]

        # Add the time index as the first column
        df_pivot['sample_time'] = df_pivot.index
        cols = df_pivot.columns.tolist()
        cols = cols[-1:] + cols[:-1]
        df_pivot = df_pivot[cols]
        df = df_pivot

    # Close the session
    session.close()

    return df

def get_all_geolocations(engine):
    session = sessionmaker(bind=engine)()

    geo_query = (
        select(DimGeolocation.id,
               DimGeolocation.sample_time_id,
               (DimTime.time).label('sample_time'),
               DimGeolocation.platform_id,
               DimPlatform.platform,
               DimGeolocation.instrument_id,
               DimInstrument.instrument,
               DimGeolocation.latitude,
               DimGeolocation.longitude
               )
        .join(DimTime, DimTime.id == DimGeolocation.sample_time_id)
        .join(DimPlatform, DimPlatform.id == DimGeolocation.platform_id)
        .join(DimInstrument, DimInstrument.id == DimGeolocation.instrument_id)
        # checking for equality of a field with itself filters out NaNs
        .where(and_((DimGeolocation.latitude != 0),(DimGeolocation.longitude != 0),(DimGeolocation.latitude == DimGeolocation.latitude),(DimGeolocation.longitude == DimGeolocation.longitude),(DimGeolocation.latitude != 'NaN'),(DimGeolocation.longitude != 'NaN')))
        .order_by(DimGeolocation.sample_time_id)        
    )
    compiled_query = geo_query.compile(session.bind, compile_kwargs={"literal_binds": True})

    # Use pandas to execute the compiled query and load it into a DataFrame
    df = pd.read_sql(str(compiled_query), session.bind)

    df.set_index('sample_time', inplace=True, drop=False)

    return df


def get_measurements_with_alarms_and_locations_tooSlow(engine, start_time=None, gps_instrument=None, end_time=None, platform=None, after_id=None):
    session = sessionmaker(bind=engine)()


    platform_id = None

    if platform:
        platform_query = (
            select(DimPlatform)
            .where(DimPlatform.platform == platform))
        compiled_query = platform_query.compile(session.bind, compile_kwargs={"literal_binds": True})

        pdf = pd.read_sql(str(compiled_query), session.bind)
        if pdf.shape[0]:
            platform_id = int(pdf['id'][0])


    if gps_instrument:
        platform_query = (
            select(DimInstrument)
            .where(DimInstrument.instrument == gps_instrument))
        compiled_query = platform_query.compile(session.bind, compile_kwargs={"literal_binds": True})

        pdf = pd.read_sql(str(compiled_query), session.bind)
        if pdf.shape[0]:
            gps_instrument_id = int(pdf['id'][0])

    # Step 1: Subquery to get the time frame of measurements
    measurement_query = (
        select(FactMeasurement)
        .order_by(FactMeasurement.sample_time)
    )

    if start_time:
        measurement_query = measurement_query.where(FactMeasurement.sample_time >= start_time)
    
    if end_time:
        measurement_query = measurement_query.where(FactMeasurement.sample_time  <= end_time)

    if platform_id:
        measurement_query = measurement_query.where(FactMeasurement.platform_id == platform_id)

    if after_id:
        measurement_query = measurement_query.where(FactMeasurement.id > after_id)

    measurement_subquery = measurement_query.subquery()

    # subquery for geolocations
    geolocation_subquery = (
        select(DimGeolocation, DimInstrument.instrument.label("gps"))
        .join(DimInstrument,DimGeolocation.instrument_id == DimInstrument.id)
        .where(and_((DimGeolocation.latitude != 0),(DimGeolocation.longitude != 0),(DimGeolocation.latitude == DimGeolocation.latitude),(DimGeolocation.longitude == DimGeolocation.longitude),(DimGeolocation.latitude != 'NaN'),(DimGeolocation.longitude != 'NaN')))
        .order_by(DimGeolocation.sample_time_id)       
    ).subquery()
    
    # Step 2: Scoped alarm aggregation
    alarm_aggregation = (
        select(
            FactAlarm.measurement_id,
            func.count(FactAlarm.id).label("alarm_count"),
            func.max(FactAlarm.alarm_level_id).label("max_alarm_level"),
            func.string_agg(FactAlarm.message, "|").label("concatenated_messages")
        )
        .where(FactAlarm.measurement_id.in_(
            select(measurement_subquery.c.id)
        ))
        .group_by(FactAlarm.measurement_id)
    ).subquery()


    # Step 3: Main query
    query = (
        select(
            measurement_subquery.c.id,
            measurement_subquery.c.sample_time,
            measurement_subquery.c.value,
            measurement_subquery.c.string,
            DimInstrument.instrument,
            DimParameter.parameter,
            DimUnit.unit,
            DimAcquisitionType.acquisition_type,
            DimPlatform.platform,
            geolocation_subquery.c.gps,
            geolocation_subquery.c.latitude,
            geolocation_subquery.c.longitude,
            func.coalesce(alarm_aggregation.c.alarm_count, 0).label("alarm_count"),
            func.coalesce(alarm_aggregation.c.max_alarm_level, 0).label("max_alarm_level"),
            func.coalesce(alarm_aggregation.c.concatenated_messages, "").label("alarm_messages")
        )
        .join(DimInstrument, measurement_subquery.c.instrument_id == DimInstrument.id)
        .join(DimParameter, measurement_subquery.c.parameter_id == DimParameter.id)
        .join(DimUnit, measurement_subquery.c.unit_id == DimUnit.id)
        .join(DimAcquisitionType, measurement_subquery.c.acquisition_type_id == DimAcquisitionType.id)
        .join(DimPlatform, measurement_subquery.c.platform_id == DimPlatform.id)
        #.join(DimGeolocation, and_((measurement_subquery.c.sample_time_id == DimGeolocation.sample_time_id),(DimGeolocation.instrument_id == gps_instrument_id)))
        #.join(gps_inst_table, DimGeolocation.instrument_id == gps_inst_table.id)
        .outerjoin(alarm_aggregation,(measurement_subquery.c.id == alarm_aggregation.c.measurement_id))
        .join(geolocation_subquery, (measurement_subquery.c.sample_time_id == geolocation_subquery.c.sample_time_id))
        #.where(and_((DimGeolocation.latitude != 0),(DimGeolocation.longitude != 0)))
        #.order_by(FactMeasurement.sample_time)
    )

    compiled_query = query.compile(session.bind, compile_kwargs={"literal_binds": True})

    # Use pandas to execute the compiled query and load it into a DataFrame
    df = pd.read_sql(str(compiled_query), session.bind)

    df.set_index('sample_time', inplace=True, drop=False)

    return df

def get_measurements_with_alarms_and_locations(engine, start_time=None, acquisition_type=None, instruments=None, gps_instrument=None, end_time=None, platform=None, after_id=None):
    session = sessionmaker(bind=engine)()

    instrument_ids = None

    if instruments:
        if isinstance(instruments, str):
            instruments = [instruments]
        instrument_query = (
            select(DimInstrument.id)
            .where(DimInstrument.instrument.in_(instruments))
        )
        compiled_query = instrument_query.compile(session.bind, compile_kwargs={"literal_binds": True})
        pdf = pd.read_sql(str(compiled_query), session.bind)
        instrument_ids = pdf['id'].astype(int).tolist() if not pdf.empty else []

    platform_id = None

    if platform:
        platform_query = (
            select(DimPlatform)
            .where(DimPlatform.platform == platform))
        compiled_query = platform_query.compile(session.bind, compile_kwargs={"literal_binds": True})

        pdf = pd.read_sql(str(compiled_query), session.bind)
        if pdf.shape[0]:
            platform_id = int(pdf['id'][0])

    gps_instrument_id = None

    if gps_instrument:
        platform_query = (
            select(DimInstrument)
            .where(DimInstrument.instrument == gps_instrument))
        compiled_query = platform_query.compile(session.bind, compile_kwargs={"literal_binds": True})

        pdf = pd.read_sql(str(compiled_query), session.bind)
        if pdf.shape[0]:
            gps_instrument_id = int(pdf['id'][0])

    acquisition_type_ids = None

    # if acquisition_type:
    #     acquisition_type_query = (
    #         select(DimAcquisitionType)
    #         .where(DimAcquisitionType.acquisition_type == acquisition_type))
    #     compiled_query = acquisition_type_query.compile(session.bind, compile_kwargs={"literal_binds": True})

    #     pdf = pd.read_sql(str(compiled_query), session.bind)
    #     if pdf.shape[0]:
    #         acquisition_type_id = int(pdf['id'][0])

    if acquisition_type:
        acquisition_types = [atype.strip() for atype in acquisition_type.split(",")]
        
        acquisition_type_query = (
            select(DimAcquisitionType.id)
            .where(DimAcquisitionType.acquisition_type.in_(acquisition_types))
        )
        
        compiled_query = acquisition_type_query.compile(session.bind, compile_kwargs={"literal_binds": True})
        
        pdf = pd.read_sql(str(compiled_query), session.bind)
        
        acquisition_type_ids = pdf['id'].astype(int).tolist() if not pdf.empty else []
   

    # subquery for geolocations
    geolocation_subquery = (
        select(DimGeolocation, DimTime.time.label('sample_time'), DimInstrument.instrument.label("gps"))
        .join(DimInstrument,DimGeolocation.instrument_id == DimInstrument.id)
        .join(DimTime,DimGeolocation.sample_time_id == DimTime.id)
        .where(and_((DimGeolocation.latitude != 0),(DimGeolocation.longitude != 0),(DimGeolocation.latitude == DimGeolocation.latitude),(DimGeolocation.longitude == DimGeolocation.longitude),(DimGeolocation.latitude != 'NaN'),(DimGeolocation.longitude != 'NaN')))
        .order_by(DimGeolocation.sample_time_id)       
    )

    if platform_id:
        geolocation_subquery = geolocation_subquery.where(DimGeolocation.platform_id == platform_id)

    if gps_instrument_id:
        geolocation_subquery = geolocation_subquery.where(DimGeolocation.instrument_id == gps_instrument_id)

    if start_time:
        geolocation_subquery = geolocation_subquery.where(DimTime.time >= start_time)
    
    if end_time:
        geolocation_subquery = geolocation_subquery.where(DimTime.time  <= end_time)

    geolocation_subquery = geolocation_subquery.subquery()


    # Step 1: Subquery to get the time frame of measurements
    measurement_query = (
        select(FactMeasurement)
        .where(FactMeasurement.sample_time_id.in_(select(geolocation_subquery.c.sample_time_id)))
        .order_by(FactMeasurement.sample_time)
    )

    # if acquisition_type_id:
    #     measurement_query = measurement_query.where(FactMeasurement.acquisition_type_id == acquisition_type_id)

    if acquisition_type_ids:  # Check if the list is not empty
        measurement_query = measurement_query.where(FactMeasurement.acquisition_type_id.in_(acquisition_type_ids))

    if after_id:
        measurement_query = measurement_query.where(FactMeasurement.id > after_id)

    if instrument_ids is not None:
        measurement_query = measurement_query.where(FactMeasurement.instrument_id.in_(instrument_ids))
    
    measurement_subquery = measurement_query.subquery()

    
    # Step 2: Scoped alarm aggregation
    alarm_aggregation = (
        select(
            FactAlarm.measurement_id,
            func.count(FactAlarm.id).label("alarm_count"),
            func.max(FactAlarm.alarm_level_id).label("max_alarm_level"),
            func.bool_or(FactAlarm.data_impacted).label("data_impacted"),
            func.string_agg(FactAlarm.message, "|").label("concatenated_messages")
        )
        .where(FactAlarm.measurement_id.in_(
            select(measurement_subquery.c.id)
        ))
        .group_by(FactAlarm.measurement_id)
    ).subquery()


    # Step 3: Main query
    query = (
        select(
            measurement_subquery.c.id,
            measurement_subquery.c.sample_time,
            measurement_subquery.c.value,
            measurement_subquery.c.string,
            DimInstrument.instrument,
            DimParameter.parameter,
            DimUnit.unit,
            DimAcquisitionType.acquisition_type,
            DimPlatform.platform,
            geolocation_subquery.c.gps,
            geolocation_subquery.c.latitude,
            geolocation_subquery.c.longitude,
            func.coalesce(alarm_aggregation.c.alarm_count, 0).label("alarm_count"),
            func.coalesce(alarm_aggregation.c.max_alarm_level, 0).label("max_alarm_level"),
            func.coalesce(alarm_aggregation.c.data_impacted).label("data_impacted"),
            func.coalesce(alarm_aggregation.c.concatenated_messages, "").label("alarm_messages")
        )
        .join(DimInstrument, measurement_subquery.c.instrument_id == DimInstrument.id)
        .join(DimParameter, measurement_subquery.c.parameter_id == DimParameter.id)
        .join(DimUnit, measurement_subquery.c.unit_id == DimUnit.id)
        .join(DimAcquisitionType, measurement_subquery.c.acquisition_type_id == DimAcquisitionType.id)
        .join(DimPlatform, measurement_subquery.c.platform_id == DimPlatform.id)
        #.join(DimGeolocation, and_((measurement_subquery.c.sample_time_id == DimGeolocation.sample_time_id),(DimGeolocation.instrument_id == gps_instrument_id)))
        #.join(gps_inst_table, DimGeolocation.instrument_id == gps_inst_table.id)
        .outerjoin(alarm_aggregation,(measurement_subquery.c.id == alarm_aggregation.c.measurement_id))
        .join(geolocation_subquery, (measurement_subquery.c.sample_time_id == geolocation_subquery.c.sample_time_id))
        #.where(and_((DimGeolocation.latitude != 0),(DimGeolocation.longitude != 0)))
        #.order_by(FactMeasurement.sample_time)
    )


    compiled_query = query.compile(session.bind, compile_kwargs={"literal_binds": True})

    # Use pandas to execute the compiled query and load it into a DataFrame
    df = pd.read_sql(str(compiled_query), session.bind)

    df.set_index('sample_time', inplace=True, drop=False)

    return df

def get_measurements_with_locations_opt(
    engine,
    start_time=None,
    acquisition_type=None,
    instruments=None,
    gps_instrument=None,
    end_time=None,
    platform=None,
    after_id=None
):
    Session = sessionmaker(bind=engine)
    with Session() as session:

        # --- Resolve IDs ---------------------------------------------------------
        instrument_ids = None
        if instruments:
            if isinstance(instruments, str):
                instruments = [instruments]
            instrument_ids = [i[0] for i in session.query(DimInstrument.id)
                            .filter(DimInstrument.instrument.in_(instruments)).all()]

        platform_id = None
        if platform:
            res = session.query(DimPlatform.id).filter(DimPlatform.platform == platform).first()
            platform_id = res[0] if res else None

        gps_instrument_id = None
        if gps_instrument:
            res = session.query(DimInstrument.id).filter(DimInstrument.instrument == gps_instrument).first()
            gps_instrument_id = res[0] if res else None

        acquisition_type_ids = None
        if acquisition_type:
            acquisition_types = [a.strip() for a in acquisition_type.split(",")]
            acquisition_type_ids = [i[0] for i in session.query(DimAcquisitionType.id)
                                    .filter(DimAcquisitionType.acquisition_type.in_(acquisition_types)).all()]

        # --- Quick existence check in DimGeolocation using DimTime ---------------
        g = DimGeolocation
        t = DimTime

        geo_filter = [g.sample_time_id == t.id]  # join to time table

        if start_time:
            geo_filter.append(t.time >= start_time)
        if end_time:
            geo_filter.append(t.time <= end_time)
        if platform_id:
            geo_filter.append(g.platform_id == platform_id)
        if gps_instrument_id:
            geo_filter.append(g.instrument_id == gps_instrument_id)

        exists_query = select(exists().where(and_(*geo_filter)))
        has_geos = session.execute(exists_query).scalar()
        if not has_geos:
            columns = [
                "id", "sample_time", "value", "string",
                "instrument", "parameter", "unit", "acquisition_type", "platform",
                "latitude", "longitude", "gps"
            ]
            return pd.DataFrame(columns=columns).set_index("sample_time", drop=False)

        # --- Base measurement slice (partition-friendly) ------------------------
        m = FactMeasurement
        measurement_query = select(
            m.id,
            m.sample_time,
            m.sample_time_id,
            m.value,
            m.string,
            m.instrument_id,
            m.parameter_id,
            m.unit_id,
            m.acquisition_type_id,
            m.platform_id,
        )
        if start_time:
            measurement_query = measurement_query.where(m.sample_time >= start_time)
        if end_time:
            measurement_query = measurement_query.where(m.sample_time <= end_time)
        if instrument_ids:
            measurement_query = measurement_query.where(m.instrument_id.in_(instrument_ids))
        if acquisition_type_ids:
            measurement_query = measurement_query.where(m.acquisition_type_id.in_(acquisition_type_ids))
        if platform_id:
            measurement_query = measurement_query.where(m.platform_id == platform_id)
        if after_id:
            measurement_query = measurement_query.where(m.id > after_id)

        measurement_sub = measurement_query.subquery()

        # --- Geolocation join ----------------------------------------------------
        geo_join = (g.sample_time_id == measurement_sub.c.sample_time_id)
        if gps_instrument_id:
            geo_join = and_(geo_join, g.instrument_id == gps_instrument_id)
        if platform_id:
            geo_join = and_(geo_join, g.platform_id == platform_id)

        # --- Join lookup tables --------------------------------------------------
        inst = DimInstrument
        p = DimParameter
        u = DimUnit
        acq = DimAcquisitionType
        plat = DimPlatform
        gps_inst = aliased(DimInstrument)  # alias for GPS instrument

        final_query = (
            select(
                measurement_sub.c.id,
                measurement_sub.c.sample_time,
                measurement_sub.c.value,
                measurement_sub.c.string,
                inst.instrument,
                p.parameter,
                u.unit,
                acq.acquisition_type,
                plat.platform,
                g.latitude,
                g.longitude,
                gps_inst.instrument.label("gps"),
            )
            .join(inst, measurement_sub.c.instrument_id == inst.id)
            .join(p, measurement_sub.c.parameter_id == p.id)
            .join(u, measurement_sub.c.unit_id == u.id)
            .join(acq, measurement_sub.c.acquisition_type_id == acq.id)
            .join(plat, measurement_sub.c.platform_id == plat.id)
            .join(g, geo_join)
            .join(gps_inst, g.instrument_id == gps_inst.id)
            .order_by(measurement_sub.c.sample_time)
        )

        compiled_query = final_query.compile(session.bind, compile_kwargs={"literal_binds": True})
        df = pd.read_sql(str(compiled_query), session.bind)
        df.set_index("sample_time", inplace=True, drop=False)
        return df

def is_consistently_increasing(column):
    """
    Test if a Pandas Series of datetimes consistently increases.
    """
    diffs = column.diff().total_seconds().dropna()
    return (diffs >= 0).all()  # No negative differences

def transform_instrument_dataframe(df, use_dataframes=True):
    """
    Transforms a pandas DataFrame into a nested data structure grouped by instrument and parameter.

    Parameters:
    - df (pd.DataFrame): Input DataFrame with columns ['sample_time', 'value', 'string', 'instrument', 'parameter', 'unit',
      'acquisition_type', 'alarm_count', 'max_alarm_level', 'alarm_messages'].
    - use_dataframes (bool): If True, packages measurement lists as pandas DataFrames. Otherwise, uses lists of dictionaries.

    Returns:
    - list: Nested data structure as described.
    """
    # Initialize the structure to hold the results
    result = []
    
    # Group by instrument and parameter
    grouped = df.groupby(['instrument', 'parameter', 'unit', 'acquisition_type'])
    
    # Create a dictionary to hold data by instrument
    instrument_dict = defaultdict(list)

    for (instrument, parameter, unit, acquisition_type), group in grouped:
        # Extract measurements for the current parameter group
        if use_dataframes:
            measurements = group[['sample_time', 'value', 'string', 'alarm_count', 'max_alarm_level', 'alarm_messages']]
            # Occasionally observation times get scrambled during groupby 
            if not is_consistently_increasing(measurements.index):
                measurements = measurements.sort_index()
        else:
            measurements = group[['sample_time', 'value', 'string', 'alarm_count', 'max_alarm_level', 'alarm_messages']]
            measurements = measurements.to_dict(orient='records')
        
        # Create a parameter entry
        parameter_entry = {
            'parameter': parameter,
            'unit': unit,
            'acquisition_type': acquisition_type,
            'measurements': measurements
        }

        # Add this parameter entry to the corresponding instrument
        instrument_dict[instrument].append(parameter_entry)

    # Convert the dictionary to the desired list structure
    for instrument, parameters in instrument_dict.items():
        result.append({instrument: parameters})

    return result

def get_alarm_table(engine, start_time=date.today(), end_time=None, platform=None, column_names_only=False):

    if not end_time:
        end_time = datetime.now()

    platform_id = None

    if platform:
        platform_query = (
            select(DimPlatform)
            .where(DimPlatform.platform == platform))
        compiled_query = platform_query.compile(session.bind, compile_kwargs={"literal_binds": True})

        pdf = pd.read_sql(str(compiled_query), session.bind)
        if pdf.shape[0]:
            platform_id = int(pdf['id'][0])


    # Step 3: Main query
    query = (
        select(
            DimPlatform.platform,
            DimTime.time,
            DimInstrument.instrument,
            DimAlarmLevel.alarm_level,
            DimAlarmType.alarm_type,
            DimParameter.parameter,
            FactAlarm.message,
            FactAlarm.data_impacted,
            FactMeasurement.value,
            FactMeasurement.string
        )
        .join(DimTime, FactAlarm.sample_time_id == DimTime.id)
        .join(DimInstrument, FactAlarm.instrument_id == DimInstrument.id)
        .join(DimParameter, FactAlarm.parameter_id == DimParameter.id)
        .join(DimPlatform, FactAlarm.platform_id == DimPlatform.id)
        .join(DimAlarmLevel, FactAlarm.alarm_level_id == DimAlarmLevel.id)
        .join(DimAlarmType, FactAlarm.alarm_type_id == DimAlarmType.id)
        .join(FactMeasurement, FactAlarm.measurement_id == FactMeasurement.id)
        .where(and_((DimTime.time >= start_time),
                    (DimTime.time <= end_time)))
        .order_by(DimTime.time)
    )

    if column_names_only:
        return [col.name for col in query.exported_columns]
    
    session = sessionmaker(bind=engine)()
    compiled_query = query.compile(session.bind, compile_kwargs={"literal_binds": True})

    # Use pandas to execute the compiled query and load it into a DataFrame
    df = pd.read_sql(str(compiled_query), session.bind)

    return df


# Run the app
if __name__ == '__main__':

#"2024-12-14 17:26:25"
    #startTime = datetime.now()
    startTime = datetime(2024,11,20,18,47,26) 
    endTime = startTime + timedelta(hours=8)
    #startTime = datetime.now() - timedelta(minutes=5)
    #endTime = datetime.now()
    # Database connection
    engine = create_engine('postgresql://vandaq:p3st3r@localhost:5432/vandaq-test', echo=False)

    df = get_measurements_with_alarms_and_locations(engine, startTime, 'Aeris_CH4_C2H6', end_time=endTime)
#    struct = transform_instrument_dataframe(df)
    print(df)
 