from ipcqueue import posixmq
from datetime import datetime, timedelta
import os
import sys
import yaml
import logging
import lzma
import pickle
from logging.handlers import TimedRotatingFileHandler
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker, relationship
from vandaq_schema import *

def insert_measurment_into_database(session, message):
	try:		
		# Check if the platform already exists, otherwise insert it
		platform_record = session.query(DimPlatform).filter_by(
			platform=message['platform'],).first()
		if not platform_record:
			platform_record = DimPlatform(platform=message['platform'])
			session.add(platform_record)
			session.flush()  # Ensure the ID is generated

		# Check if the instrument already exists, otherwise insert it
		instrument_record = session.query(DimInstrument).filter_by(
			instrument=message['instrument'],).first()
		if not instrument_record:
			instrument_record = DimInstrument(instrument=message['instrument'])
			session.add(instrument_record)
			session.flush()  # Ensure the ID is generated

		 # Check if the parameter already exists, otherwise insert it
		parameter_record = session.query(DimParameter).filter_by(
			parameter=message['parameter']).first()
		if not parameter_record:
			parameter_record = DimParameter(parameter=message['parameter'])
			session.add(parameter_record)
			session.flush()  # Ensure the ID is generated

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

		if 'string' in message.keys():
			measurementString = message['string']
		else:
			measurementString = None

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
				value=message['value'],
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
				value=message['value'],
				string=measurementString
			)

		session.add(measurement_record)
		session.commit()  # Commit the transaction
		return True

	except IntegrityError:
		session.rollback()	# Roll back the transaction on error
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
		filename += submit_time.strftime('%Y%m%d_%H%M%S')
		filename += '.sbm'
		with lzma.open(filename,'wb') as file:
			pickle.dump(submissions,file)
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


# load configuration file
if len(sys.argv) < 2:
    print("Error: Must supply a configuration file")
    exit()

try:
    configfile = open(sys.argv[1],'r')
    config = yaml.load(configfile, Loader=yaml.FullLoader)
    configfile.close()
except:
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

logger.info('Starting collector')
queue = open_queue(config, logger)

engine = create_engine(config['connect_string'], echo=False)

Session = sessionmaker(bind=engine)
session = Session()

submissions = []
sumbission_start_time = datetime.now()

while True:
	try:
		message = queue.get()
	except Exception as e:
		logger.error("exception in get from queue")
		logger.error(e)
	else:
		logger.debug(str(message))
		for measurement in message:
			if 'acquisition_type' in measurement.keys():
				success = insert_measurment_into_database(session, measurement)
				if success:
					logger.debug("Measurement inserted successfully.")
				else:
					logger.error("Measurement insertion failed: "+str(measurement))
				#print(str(len(submissions))+'submissions to '+sumbission_start_time.strftime("%Y-%m-%d %H:%M:%S"))
				if submit_measurement(measurement, sumbission_start_time, config):
					sumbission_start_time = datetime.now()
					

