from ipcqueue import posixmq
from datetime import datetime, timedelta, timezone
import pytz
import os
import sys
import time
import yaml
import logging
import lzma
import pickle
import operator
import shutil
from glob import glob
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from sqlalchemy import create_engine, and_, text, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker, relationship
from vandaq_schema import *
from collections import defaultdict


first_insert = True
platform_dict = None
instrument_dict = None
parameter_dict = None
unit_dict = None
acquisition_type_dict = None
alarm_type_dict = None
alarm_level_dict = None

def insert_measurment_into_database(session, message):
    global first_insert
    global platform_dict
    global instrument_dict
    global parameter_dict
    global unit_dict
    global acquisition_type_dict
    global alarm_type_dict
    global alarm_level_dict
    try:        
        # pre-query dimension tables into dicts
        if first_insert:
            platform_dict = {
                record.platform: record.id for record in session.query(DimPlatform).all()
            }
            instrument_dict = {
                record.instrument: record.id for record in session.query(DimInstrument).all()
            }
            parameter_dict = {
                record.parameter: record.id for record in session.query(DimParameter).all()
            }
            unit_dict = {
                record.unit: record.id for record in session.query(DimUnit).all()
            }
            acquisition_type_dict = {
                record.acquisition_type: record.id for record in session.query(DimAcquisitionType).all()
            }
            alarm_type_dict = {
                record.alarm_type: record.id for record in session.query(DimAlarmType).all()
            }
            alarm_level_dict = {
                record.alarm_level: record.id for record in session.query(DimAlarmLevel).all()
            }
            first_insert = False
            
            

        platform_id = platform_dict.get(message['platform'])
        if not platform_id:
            platform_record = DimPlatform(platform=message['platform'])
            session.add(platform_record)
            session.flush()  # Ensure the ID is generated
            platform_id = platform_record.id
            platform_dict[message['platform']] = platform_id
            session.commit()

        # Check if the instrument already exists, otherwise insert it
        instrument_id = instrument_dict.get(message['instrument'])
        if not instrument_id:
            instrument_record = DimInstrument(instrument=message['instrument'])
            session.add(instrument_record)
            session.flush()  # Ensure the ID is generated
            instrument_id = instrument_record.id
            instrument_dict[message['instrument']] = instrument_id
            session.commit()


        # Check if the parameter already exists, otherwise insert it
        # in case an instrument non-response alarm comes in (no paramater)
        parameter_record = None
        if 'parameter' in message:
            parameter_id = parameter_dict.get(message['parameter'])
            if not parameter_id:
                parameter_record = DimParameter(parameter=message['parameter'])
                session.add(parameter_record)
                session.flush()  # Ensure the ID is generated
                parameter_id = parameter_record.id
                parameter_dict[message['parameter']] = parameter_id
                session.commit()

        # Check if the unit already exists, otherwise insert it
        unit_id = unit_dict.get(message['unit'])
        if not unit_id:
            unit_record = DimUnit(unit=message['unit'])
            session.add(unit_record)
            session.flush()  # Ensure the ID is generated
            unit_id = unit_record.id
            unit_dict[message['unit']] = unit_id
            session.commit()

        # Check if the acquisition type already exists, otherwise insert it
        acquisition_type_id = acquisition_type_dict.get(message['acquisition_type'])
        if not acquisition_type_id:
            acquisition_type_record = DimAcquisitionType(acquisition_type=message['acquisition_type'])
            session.add(acquisition_type_record)
            session.flush()  # Ensure the ID is generated
            acquisition_type_id = acquisition_type_record.id
            acquisition_type_dict[message['acquisition_type']] = acquisition_type_id
            session.commit()

        # Check if the acquire time already exists, otherwise insert it
        acq_time_record = session.query(DimTime).filter_by(time=message['acquisition_time']).first()
        if not acq_time_record:
            acq_time_record = DimTime(time=message['acquisition_time'])
            session.add(acq_time_record)
            session.flush()  # Ensure the ID is generated

        inst_has_timestamp = 'instrument_time' in message and (type(message['instrument_time']).__name__ == 'datetime')

        if inst_has_timestamp:
            # Check if the instrument time already exists, otherwise insert it
            inst_time_record = session.query(DimTime).filter_by(time=message['instrument_time']).first()
            if not inst_time_record:
                inst_time_record = DimTime(time=message['instrument_time'])
                session.add(inst_time_record)
                session.flush()  # Ensure the ID is generated

        # Check if the sample time already exists, otherwise insert it
        sample_time_record = session.query(DimTime).filter_by(time=message['sample_time']).first()
        if not sample_time_record:
            sample_time_record = DimTime(time=message['sample_time'])
            session.add(sample_time_record)
            session.flush()  # Ensure the ID is generated

        if message['acquisition_type'] == 'GPS':
        # Check if the geolocation record already exists, otherwise insert it
            geolocation_record = session.query(DimGeolocation).filter(
                   and_(
                    DimGeolocation.sample_time_id == sample_time_record.id,
                    DimGeolocation.platform_id == platform_id,
                    DimGeolocation.instrument_id == instrument_id
                )
            ).first()

            if not geolocation_record:
                geolocation_record = DimGeolocation(sample_time_id = sample_time_record.id,
                                            platform_id=platform_id,
                                            instrument_id=instrument_id)
                session.add(geolocation_record)
                session.flush()
                session.refresh(geolocation_record)  # Ensures the `id` is loaded from the database
            if message['parameter'] == 'latitude':
                geolocation_record.latitude = message['value']
                session.flush()
                session.refresh(geolocation_record)
            if message['parameter'] == 'longitude':
                geolocation_record.longitude = message['value']
                session.flush()
                session.refresh(geolocation_record)


   
        # Add an instrument measurement record if not already there
        inst_meas_record = session.query(InstrumentMeasurements).filter_by(
            platform_id=platform_id,
            instrument_id=instrument_id,
            acquisition_type_id=acquisition_type_id,
            parameter_id=parameter_id,
            unit_id=unit_id).first()
        if not inst_meas_record:
            inst_meas_record = InstrumentMeasurements(
                platform_id=platform_id,
                instrument_id=instrument_id,
                acquisition_type_id=acquisition_type_id,
                parameter_id=parameter_id,
                unit_id=unit_id)
            session.add(inst_meas_record)
            session.flush()

        measurementString = None
        measurementValue = None

        if 'string' in message.keys():
            measurementString = message['string']

        if 'value' in message.keys():
            measurementValue = message['value']
        measurement_record = None

        if (measurementValue is not None) or measurementString:          
            # Insert the measurement with the dimension IDs
            if inst_has_timestamp:
                measurement_record = FactMeasurement(
                    platform_id=platform_id,
                    instrument_id=instrument_id,
                    parameter_id=parameter_id,
                    unit_id=unit_id,
                    acquisition_type_id=acquisition_type_id,
                    acquisition_time_id=acq_time_record.id,
                    instrument_time_id=inst_time_record.id,
                    sample_time_id=sample_time_record.id,
                    sample_time=message['sample_time'],
                    value=measurementValue,
                    string=measurementString
                )
            else:
                measurement_record = FactMeasurement(
                    platform_id=platform_id,
                    instrument_id=instrument_id,
                    parameter_id=parameter_id,
                    unit_id=unit_id,
                    acquisition_type_id=acquisition_type_id,
                    acquisition_time_id=acq_time_record.id,
                    sample_time_id=sample_time_record.id,
                    sample_time=message['sample_time'],
                    value=measurementValue,
                    string=measurementString
                )
            session.add(measurement_record)
            session.flush()  # Commit the transaction

        if 'alarms' in message:
            for alarm in message['alarms']:
                # Check if the alarm type already exists, otherwise insert it
                alarm_type_id = alarm_type_dict.get(alarm['alarm_type'])
                if not alarm_type_id:
                    alarm_type_record = DimAlarmType(alarm_type=alarm['alarm_type'])
                    session.add(alarm_type_record)
                    session.flush()  # Ensure the ID is generated
                    alarm_type_id = alarm_type_record.id
                    alarm_type_dict[alarm['alarm_type']] = alarm_type_id
                    session.commit()

                # Check if the alarm level already exists, otherwise insert it
                alarm_level_id = alarm_level_dict.get(alarm['alarm_level'])
                if not alarm_level_id:
                    alarm_level_record = DimAlarmLevel(alarm_level=alarm['alarm_level'])
                    session.add(alarm_level_record)
                    session.flush()  # Ensure the ID is generated
                    alarm_level_id = alarm_level_record.id
                    alarm_level_dict[alarm['alarm_level']] = alarm_level_id
                    session.commit()
                
                alarm_message = alarm['alarm_message']
                parameter_id_local = None
                if parameter_record:
                    parameter_id_local = parameter_record.id
                measurement_id_local = None
                if measurement_record:
                    measurement_id_local = measurement_record.id

                alarm_record = FactAlarm(
                    platform_id=platform_id,
                    measurement_id=measurement_record.id,
                    instrument_id=instrument_id,
                    parameter_id=parameter_id,
                    sample_time_id=sample_time_record.id,
                    alarm_type_id=alarm_type_id,
                    alarm_level_id=alarm_level_id,
                    data_impacted=alarm['data_impacted'],
                    message=alarm['alarm_message']
                )
                session.add(alarm_record)
                session.flush()  # Commit the transaction
        session.commit()
                
        return True

    except IntegrityError as e:
        session.rollback()    # Roll back the transaction on error
        logger.error(f"Failed to insert data due to integrity constraint violation - {e}.")
        return False

class Inserter:
    def __init__(self, session, config):
        self.session = session
        self.config = config
        self.dimension_cache = {
            'platform': {},
            'instrument': {},
            'parameter': {},
            'unit': {},
            'acquisition_type': {},
            'alarm_type': {},
            'alarm_level': {},
            'time': {},
            'geolocation':{}
        }
        self.insert_batch_seconds = self.config.get('insert_batch_seconds',1)
        self.cache_time_seconds = self.config.get('cache_time_seconds', 3600)
        self.load_dimension_cache()
        
    def load_dimension_cache(self):
        self.dimension_cache["platform"] = {
            record.platform: record.id for record in self.session.query(DimPlatform).all()
        }
        self.dimension_cache["instrument"] = {
            record.instrument: record.id for record in self.session.query(DimInstrument).all()
        }
        self.dimension_cache["parameter"] = {
            record.parameter: record.id for record in self.session.query(DimParameter).all()
        }
        self.dimension_cache["unit"] = {
            record.unit: record.id for record in self.session.query(DimUnit).all()
        }
        self.dimension_cache["acquisition_type"] = {
            record.acquisition_type: record.id for record in self.session.query(DimAcquisitionType).all()
        }
        self.dimension_cache["alarm_type"] = {
            record.alarm_type: record.id for record in self.session.query(DimAlarmType).all()
        }
        self.dimension_cache["alarm_level"] = {
            record.alarm_level: record.id for record in self.session.query(DimAlarmLevel).all()
        }

    def get_or_create_record(self, session, model, lookup_field, value, cache_dict):
        record_id = cache_dict.get(value)
        if not record_id:
            record = session.query(model).filter(getattr(model, lookup_field) == value).first()
            if not record:
                record = model(**{lookup_field: value})
                session.add(record)
                session.flush()  # Ensure the ID is generated
            record_id = record.id
            cache_dict[value] = record_id
        return record_id    

    def get_or_create_dimension(self, model, field, value, cache_key):
        return self.get_or_create_record(self.session, model, field, value, self.dimension_cache[cache_key])

    def get_or_create_time_dimension(self, time):
        if time is None:
            return None
        time = time.replace(microsecond=0)
        time_id = self.dimension_cache['time'].get(time);
        if time_id:
            return time_id
        # if this time is not in the time dimension cache, 
        # attempt to retrieve times cache_time_seconds before 
        # and after the given time
        start_time = time - timedelta(seconds=self.cache_time_seconds) 
        end_time = time + timedelta(seconds=self.cache_time_seconds)

        times_in_db = self.session.query(DimTime).where(
            and_((DimTime.time >= start_time),
            (DimTime.time <= end_time))      
        ).all()
        times_in_table = [rec.time.replace(microsecond=0) for rec in times_in_db]
        # generate a list of seconds between the start and end
        times = [start_time.replace(microsecond=0) + timedelta(seconds=i)
            for i in range(int((end_time - start_time).total_seconds()) + 1)]
        # make a list of times not in the time dimension table
        missing_times = [{'time':newTime} for newTime in times if newTime not in times_in_table]
        if missing_times:
            #add the missing times to the time dimension table
            self.session.bulk_insert_mappings(DimTime, missing_times)
            self.session.commit()
            # requery the whole time swath
            times_in_db = self.session.query(DimTime).where(
                and_((DimTime.time >= start_time),
                (DimTime.time <= end_time))      
            ).all()
        times_in_db = {rec.time: rec.id for rec in times_in_db}
        self.dimension_cache['time'] = self.dimension_cache['time'] | times_in_db
        return self.dimension_cache['time'].get(time)
            
    def batch_insert_measurements(self, measurements):
        try:
            # filter out any alarms from the measurements
            filtered_measurements = [
                {key: value for key, value in measurement.items() if key != 'alarms'}
                for measurement in measurements
            ]
            
            # Build the core insert statement
            stmt = insert(FactMeasurement).returning(FactMeasurement.id)
            
            # Execute with multiple rows of data
            result = self.session.execute(stmt, filtered_measurements)
            
            # Fetch all returned IDs
            inserted_ids = result.scalars().all()
            
            # Update measurements with the returned IDs
            updated_measurements = [
                {**measurement, "id": result_id}
                for measurement, result_id in zip(measurements, inserted_ids)
            ]
            
            return updated_measurements

        except IntegrityError as e:
            self.logger.error(f"batch_insert_measurements integrity error: {str(e)}")
            return []
        except Exception as e:
            self.logger.error(f"batch_insert_measurements unknown error: {str(e)}")
            return []    

    def batch_insert_alarms(self, alarms):
        if len(alarms) == 0:
            return
        try:            
            # Build the core insert statement
            stmt = insert(FactAlarm)
            
            # Execute with multiple rows of data
            result = self.session.execute(stmt, alarms)
       
        except IntegrityError as e:
            self.logger.error(f"batch_insert_alarms integrity error: {str(e)}")
            return []
        except Exception as e:
            self.logger.error(f"batch_insert_alarms unknown error: {str(e)}")
            return []    

    def batch_insert_geolocations(self, geolocations):
        if len(geolocations) == 0:
            return
        try:            
            # Build the core insert statement
            stmt = insert(DimGeolocation)
            
            # Execute with multiple rows of data
            result = self.session.execute(stmt, geolocations)
       
        except IntegrityError as e:
            self.logger.error(f"batch_insert_geolocations integrity error: {str(e)}")
            return []
        except Exception as e:
            self.logger.error(f"batch_insert_geolocations unknown error: {str(e)}")
            return []    

    def merge_gps_coordinates(self,gps_records):
        # Group records by common keys (platform_id, instrument_id, sample_time_id)
        grouped = defaultdict(dict)
        for record in gps_records:
            key = (record['platform_id'], record['instrument_id'], record['sample_time_id'])
            grouped[key].update(record)

        # Build the final list of merged dictionaries
        merged_records = [
            {'platform_id': key[0], 'instrument_id': key[1], 'sample_time_id': key[2], 
            'longitude': value.get('longitude'), 'latitude': value.get('latitude')}
            for key, value in grouped.items()
        ]
        return merged_records
        
    def insert_subbatch(self, messages):
        measurements = []
        alarms = []
        coordinates = []
        # Prepare and batch insert measurements
        for message in messages:
            measurement = {
                'platform_id': self.get_or_create_dimension(DimPlatform, 'platform', message['platform'], 'platform'),
                'instrument_id': self.get_or_create_dimension(DimInstrument, 'instrument', message['instrument'], 'instrument'),
                'parameter_id': self.get_or_create_dimension(DimParameter, 'parameter', message['parameter'], 'parameter'),
                'unit_id': self.get_or_create_dimension(DimUnit, 'unit', message['unit'], 'unit'),
                'acquisition_type_id': self.get_or_create_dimension(DimAcquisitionType, 'acquisition_type', message['acquisition_type'], 'acquisition_type'),
                'sample_time': message.get('sample_time'),
                'acquisition_time_id': self.get_or_create_time_dimension(message.get('acquisition_time')),
                'instrument_time_id': self.get_or_create_time_dimension(message.get('instrument_time')),
                'sample_time_id': self.get_or_create_time_dimension(message.get('sample_time')),
                'value': message.get('value'),
                'string': message.get('string'),
                'alarms': message.get('alarms',[])
            }
            measurements.append(measurement)
            # if the measurement is a GPS cordinate, prepare the coordinate for the geolocation dimension table
            if message.get('acquisition_type') == 'GPS' and message['value']:
                coordinate = {
                    'platform_id': measurement['platform_id'],
                    'instrument_id': measurement['instrument_id'],
                    'sample_time_id': self.get_or_create_time_dimension(message.get('sample_time')),
                    message['parameter']: message['value']
                }
                coordinates.append(coordinate)
        measurements = self.batch_insert_measurements(measurements)
        # Now that IDs have been assigned to the measurements, extracte and prep the alarms
        for measurement in measurements:            
            for alarm in measurement.get('alarms',[]):
                alarm_rec = {
                    'platform_id': measurement['platform_id'],
                    'measurement_id': measurement['id'],
                    'instrument_id': measurement['instrument_id'],
                    'parameter_id': measurement['parameter_id'],
                    'sample_time_id': self.get_or_create_time_dimension(measurement['sample_time']),
                    'alarm_type_id': self.get_or_create_dimension(DimAlarmType, 'alarm_type', alarm['alarm_type'], 'alarm_type'),
                    'alarm_level_id': self.get_or_create_dimension(DimAlarmLevel, 'alarm_level', alarm['alarm_level'], 'alarm_level'),
                    'data_impacted': alarm['data_impacted'],           
                    'alarm_message': alarm['alarm_message'],           
                }
                alarms.append(alarm_rec)
        self.batch_insert_alarms(alarms)
        if coordinates:
            geolocations = self.merge_gps_coordinates(coordinates)
            self.batch_insert_geolocations(geolocations) 
        self.session.commit()
        
    def insert_batch(self, batch):
        earliest_time = min(batch,key=lambda x:x['sample_time'])['sample_time'].replace(microsecond=0)
        latest_time = max(batch,key=lambda x:x['sample_time'])['sample_time'].replace(microsecond=0)
        times = []
        mid_time = earliest_time
        while mid_time <= latest_time:
            times.append(mid_time)
            mid_time += timedelta(seconds=self.insert_batch_seconds)
        for time in times:
            sub_batch = [rec for rec in batch if rec['sample_time'].replace(microsecond=0) == time]
            batch = [rec for rec in batch if rec['sample_time'].replace(microsecond=0) != time]
            self.insert_subbatch(sub_batch)   
                    
        

        
def submit_measurement(measurement, submit_time, config):
    # collect measurements, and store into files at configured intervals  
    global submissions
    changed_file = False
    if (datetime.now() - submit_time).total_seconds() / 60 >= config['submissions']['submit_file_minutes']:
        # Time to write the submission file
        filename = os.path.join(config['submissions']['submit_file_dir'], 
                        config['submissions']['submit_file_basename'])
        timezone = None
        if 'submit_file_timezone' in config['submissions']:
            timezone = config['submissions']['submit_file_timezone']
            filename += submit_time.astimezone(pytz.timezone(timezone)).strftime('%Y%m%d_%H%M%S')
            if 'submit_file_tz_abbr' in config['submissions']:
                filename += '_' + config['submissions']['submit_file_tz_abbr']+'_'
        else:
            filename += submit_time.strftime('%Y%m%d_%H%M%S')
        filename += '.sbm'
        # write to temp file then rename so partial 
        # files are not picked up by the submitter 
        temp_file_name = filename+'.temp'
        with lzma.open(temp_file_name,'wb') as file:
            pickle.dump(submissions,file)
        shutil.move(temp_file_name, filename)
        submissions = []
        changed_file = True
    submissions.append(measurement)
    return changed_file

def open_queue(config, logger):
    myMaxMsgSize = config['queue']['max_msg_size']
    myMaxMsgs = config['queue']['max_msgs']
    myQname = config['queue']['name']
    qExists = False
    # check if queue already exists
    try:
        queue = posixmq.Queue(myQname)
        qExists = True
    except OSError as e:
        logger.debug('Queue does not yet exist')
    if qExists:
        attribs = queue.qattr()
        # if queue exists, check to make sure it is big enough
        if attribs['max_size'] < myMaxMsgs or attribs['max_msgbytes'] < myMaxMsgSize:
            # destroy the queue if it is too small
            queue.close()
            queue.unlink()
            qExists = False
    if not qExists:
        # create the queue if it doesn't exist or has been detroyed
        queue = posixmq.Queue(myQname, maxsize=myMaxMsgs, maxmsgsize=myMaxMsgSize)
    # KLUDGE-- bug in posixmq-- does not update internal member variables
    # _max_msg_size and _maxsize to match actual queue attributes, but uses them to 
    # size the receive buffer, causing "too big" error on large messages.  Set these variables.
    attribs = queue.qattr()
    queue._max_msg_size = attribs['max_msgbytes']
    queue._maxsize = attribs['max_size']
    return queue

def get_submission_files(directory,file_pattern):
    pattern = os.path.join(directory,file_pattern)
    files = glob(pattern)
    if files:
        current_time = time.time()
        files = [{'filename':file, 'age_seconds':current_time - os.path.getmtime(file)} for file in files]
        files.sort(key=operator.itemgetter('age_seconds'), reverse=True)    
    return files
     

def load_config_file(filename):
    try:
        configfile = open(filename)
        config = yaml.load(configfile, Loader=yaml.FullLoader)
        configfile.close()
        return config
    except:
        print("Cannot load config file "+sys.argv[1])
        return None

def get_messages_from_file(filename):
    messages = []
    with lzma.open(filename,'rb') as file:
        messages = pickle.load(file)
    return messages    

def move_file_to_submitted(filename, submitted_path):
    file_dir = os.path.dirname(filename)
    file_name = os.path.basename(filename)
    try:
        if not os.path.exists(submitted_path):
            os.makedirs(submitted_path)
        if os.path.exists(os.path.join(submitted_path,file_name)):
            os.remove(filename)
        else:
            shutil.move(filename, submitted_path)
    except Exception as e:
        logger.error("error moving file {} to {}, err = {}".format(filename, submitted_path,str(e)))

# load configuration file
if len(sys.argv) < 2:
    print("Error: Must supply a configuration file")
    exit()
    
config_file_name = sys.argv[1]    

config = load_config_file(config_file_name)
if not config:
    print("Cannot load config file "+sys.argv[1])
    exit()

# create logger
log_file = os.path.join(config['logs']['log_dir'], config['logs']['log_file'])
logging.basicConfig(
    filename = log_file,
    encoding="utf-8",
    filemode="a",
    format="{asctime} - {levelname} - {message}",
    style="{",
    datefmt="%Y-%m-%d %H:%M:%S",    
)
logger = logging.getLogger(config['logs']['logger_name'])
logger.setLevel(config['logs']['log_level'])
handler = TimedRotatingFileHandler(log_file, when="midnight", interval=1, backupCount=30)
handler.setLevel(logging.INFO)
logger.addHandler(handler)

collector_input = None
submit_file_directory = None
submitted_file_directory = None
submit_file_pattren = None

logger.info('Starting collector')
if 'queue' in config:
    queue = open_queue(config, logger)
    if queue:
        collector_input = 'queue'
else:
    if 'submissions' in config:
        collector_input = 'submissions'
        submission_file_directory = config['submissions']['submit_file_dir']
        submitted_file_directory = config['submissions']['submitted_file_dir']
        submit_file_pattren = config['submissions']['submit_file_pattern']
        
engine = create_engine(config['connect_string'], echo=False)

Session = sessionmaker(bind=engine)
session = Session()

submissions = []
sumbission_start_time = datetime.now()

inserter = Inserter(session, config)
times = inserter.get_or_create_time_dimension(datetime.now()-timedelta(days=5))

batch_insert = True 

queued_recs_to_batch = config.get('queued_recs_to_batch', 1000)

while True:
    message = []
    if collector_input == 'queue':
        while len(message) < queued_recs_to_batch:
            try:
                record = queue.get()
                # GPS acquireres package their coordinates as lists
                # to keep coords from being separated in batching
                if isinstance(record,list):
                    for r in record:
                        message.append(r)
                else:
                    message.append(record)
                #continue
            except Exception as e:
                logger.error("exception in get from queue")
                logger.error(e)
            else:
                logger.debug(str(message))
    elif collector_input == 'submissions':
        files = get_submission_files(submission_file_directory, submit_file_pattren) 
        time.sleep(0.5)
        if files:
            file = files[0]
            logger.info(f'Starting on submission file {file}')
            try:
                message = get_messages_from_file(file['filename'])
            except Exception as e:
                logger.error('Could not unpickle {}, error = {}'.format(file['filename'], str(e)))
                move_file_to_submitted(file['filename'], submitted_file_directory+'rejected/')
            else:     
                files.remove(file)
                move_file_to_submitted(file['filename'], submitted_file_directory) 
                logger.info('Moved submission file {} to {}'.format(file['filename'], submitted_file_directory))
                        
    file_start_time = datetime.now()

    if message and batch_insert:
        numRecords = len(message)
        start_time = datetime.now()
        inserter.insert_batch(message)
        end_time = datetime.now()
        exec_secs = (end_time - start_time).total_seconds()
        logger.info(f"{numRecords} inserted, insert took {exec_secs} seconds, {exec_secs/numRecords} secs per record")
    else:

        for measurement in message:
            if 'acquisition_type' in measurement.keys():
                start_time = datetime.now()
                success = insert_measurment_into_database(session, measurement)
                end_time = datetime.now()
                exec_secs = (end_time - start_time).total_seconds()
                logger.info(f"record {measurement['parameter']} {measurement['acquisition_type']} insert took {exec_secs} seconds")
                #print(f'message insert took {exec_secs} seconds')
                if success:
                    #logger.debug("Measurement inserted successfully.")
                    pass
                else:
                    logger.error("Measurement insertion failed: "+str(measurement))
                #print(str(len(submissions))+'submissions to '+sumbission_start_time.strftime("%Y-%m-%d %H:%M:%S"))
                if collector_input == 'queue':
                    if submit_measurement(measurement, sumbission_start_time, config):
                        sumbission_start_time = datetime.now()
    if message:
        file_end_seconds = (datetime.now()-file_start_time).total_seconds()
        logger.info(f'message cluster (submit file) length {len(message)} messages processed in {file_end_seconds} seconds')
                   

