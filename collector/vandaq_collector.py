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
from sqlalchemy import create_engine, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker, relationship
from vandaq_schema import *

def insert_measurment_into_database(session, message):
    try:        
        # Check if the platform already exists, otherwise insert it
        sttime = datetime.now()
        platform_record = session.query(DimPlatform).filter_by(
            platform=message['platform'],).first()
        if not platform_record:
            platform_record = DimPlatform(platform=message['platform'])
            session.add(platform_record)
            session.flush()  # Ensure the ID is generated
        platform_us = (datetime.now()-sttime).microseconds
        print('Platform query took {} microseconds'.format(str(platform_us)))

        sttime = datetime.now()
        # Check if the instrument already exists, otherwise insert it
        instrument_record = session.query(DimInstrument).filter_by(
            instrument=message['instrument'],).first()
        if not instrument_record:
            instrument_record = DimInstrument(instrument=message['instrument'])
            session.add(instrument_record)
            session.flush()  # Ensure the ID is generated

        instrument_us = (datetime.now()-sttime).microseconds
        print('Instrument query took {} microseconds'.format(str(instrument_us)))

         # Check if the parameter already exists, otherwise insert it
        sttime = datetime.now()
        # in case an instrument non-response alarm comes in (no paramater)
        parameter_record = None
        if 'parameter' in message:
            parameter_record = session.query(DimParameter).filter_by(
                parameter=message['parameter']).first()
            if not parameter_record:
                parameter_record = DimParameter(parameter=message['parameter'])
                session.add(parameter_record)
                session.flush()  # Ensure the ID is generated

        parameter_us = (datetime.now()-sttime).microseconds
        print('Parameter query took {} microseconds'.format(str(parameter_us)))

        # Check if the unit already exists, otherwise insert it
        unit_record = session.query(DimUnit).filter_by(
            unit=message['unit']).first()
        if not unit_record:
            unit_record = DimUnit(unit=message['unit'])
            session.add(unit_record)
            session.flush()  # Ensure the ID is generated

        # Check if the acquisition type already exists, otherwise insert it
        acquisition_type_record = session.query(DimAcquisitionType).filter_by(
            acquisition_type=message['acquisition_type']).first()
        if not acquisition_type_record:
            acquisition_type_record = DimAcquisitionType(acquisition_type=message['acquisition_type'])
            session.add(acquisition_type_record)
            session.flush()  # Ensure the ID is generated

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
                    DimGeolocation.platform_id == platform_record.id,
                    DimGeolocation.instrument_id == instrument_record.id
                )
            ).first()

            if not geolocation_record:
                geolocation_record = DimGeolocation(sample_time_id = sample_time_record.id,
                                            platform_id=platform_record.id,
                                            instrument_id=instrument_record.id)
                session.add(geolocation_record)
                session.flush()
            if message['parameter'] == 'latitude':
                geolocation_record.latitude = message['value']
                session.flush()
            if message['parameter'] == 'longitude':
                geolocation_record.longitude = message['value']
                session.flush()


   
        # Add an instrument measurement record if not already there
        inst_meas_record = session.query(InstrumentMeasurements).filter_by(
            platform_id=platform_record.id,
            instrument_id=instrument_record.id,
            acquisition_type_id=acquisition_type_record.id,
            parameter_id=parameter_record.id,
            unit_id=unit_record.id).first()
        if not inst_meas_record:
            inst_meas_record = InstrumentMeasurements(
                platform_id=platform_record.id,
                instrument_id=instrument_record.id,
                acquisition_type_id=acquisition_type_record.id,
                parameter_id=parameter_record.id,
                unit_id=unit_record.id)
            session.add(inst_meas_record)
            session.flush()

        measurementString = None
        measurementValue = None

        if 'string' in message.keys():
            measurementString = message['string']

        if 'value' in message.keys():
            measurementValue = message['value']
        measurement_record = None
        sttime = datetime.now()
        if measurementValue or measurementValue:          
            # Insert the measurement with the dimension IDs
            if inst_has_timestamp:
                measurement_record = FactMeasurement(
                    platform_id=platform_record.id,
                    instrument_id=instrument_record.id,
                    parameter_id=parameter_record.id,
                    unit_id=unit_record.id,
                    acquisition_type_id=acquisition_type_record.id,
                    acquisition_time_id=acq_time_record.id,
                    instrument_time_id=inst_time_record.id,
                    sample_time_id=sample_time_record.id,
                    sample_time=message['sample_time'],
                    value=measurementValue,
                    string=measurementString
                )
            else:
                measurement_record = FactMeasurement(
                    platform_id=platform_record.id,
                    instrument_id=instrument_record.id,
                    parameter_id=parameter_record.id,
                    unit_id=unit_record.id,
                    acquisition_type_id=acquisition_type_record.id,
                    acquisition_time_id=acq_time_record.id,
                    sample_time_id=sample_time_record.id,
                    sample_time=message['sample_time'],
                    value=measurementValue,
                    string=measurementString
                )
            session.add(measurement_record)
            session.flush()  # Commit the transaction
            measurement_us = (datetime.now()-sttime).microseconds
            print('Measuremment insert took {} microseconds'.format(str(measurement_us)))

        if 'alarms' in message:
            for alarm in message['alarms']:
                # Check if the alarm type already exists, otherwise insert it
                alarm_type_record = session.query(DimAlarmType).filter_by(
                    alarm_type=alarm['alarm_type']).first()
                if not alarm_type_record:
                    alarm_type_record = DimAlarmType(alarm_type=alarm['alarm_type'])
                    session.add(alarm_type_record)
                    session.flush()  # Ensure the ID is generated

                # Check if the alarm level already exists, otherwise insert it
                alarm_level_record = session.query(DimAlarmLevel).filter_by(
                    alarm_level=alarm['alarm_level']).first()
                if not alarm_level_record:
                    alarm_level_record = DimAlarmLevel(alarm_level=alarm['alarm_level'])
                    session.add(alarm_level_record)
                    session.flush()  # Ensure the ID is generated
                
                alarm_message = alarm['alarm_message']
                parameter_id_local = None
                if parameter_record:
                    parameter_id_local = parameter_record.id
                measurement_id_local = None
                if measurement_record:
                    measurement_id_local = measurement_record.id

                alarm_record = FactAlarm(
                    platform_id=platform_record.id,
                    measurement_id=measurement_id_local,
                    instrument_id=instrument_record.id,
                    parameter_id=parameter_id_local,
                    sample_time_id=sample_time_record.id,
                    alarm_type_id=alarm_type_record.id,
                    alarm_level_id=alarm_level_record.id,
                    data_impacted=alarm['data_impacted'],
                    message=alarm['alarm_message']
                )
                session.add(alarm_record)
                session.flush()  # Commit the transaction
        session.commit()
                
        return True

    except IntegrityError:
        session.rollback()    # Roll back the transaction on error
        logger.error("Failed to insert data due to integrity constraint violation.")
        return False

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


while True:
    message = []
    if collector_input == 'queue':
        try:
            message = queue.get()
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
            try:
                message = get_messages_from_file(file['filename'])
            except Exception as e:
                logger.error('Could not unpickle {}, error = {}'.format(file['filename'], str(e)))
                move_file_to_submitted(file['filename'], submitted_file_directory+'rejected/')
            else:     
                files.remove(file)
                move_file_to_submitted(file['filename'], submitted_file_directory) 
                logger.debug('Moved submission file {} to {}'.format(file['filename'], submitted_file_directory))
                        
    for measurement in message:
        if 'acquisition_type' in measurement.keys():
            success = insert_measurment_into_database(session, measurement)
            if success:
                #logger.debug("Measurement inserted successfully.")
                pass
            else:
                logger.error("Measurement insertion failed: "+str(measurement))
            #print(str(len(submissions))+'submissions to '+sumbission_start_time.strftime("%Y-%m-%d %H:%M:%S"))
            if collector_input == 'queue':
                if submit_measurement(measurement, sumbission_start_time, config):
                    sumbission_start_time = datetime.now()
                    

