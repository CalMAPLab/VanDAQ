import sys
import serial
import socket
import zmq
import yaml
import numpy as np
import logging
import pickle
import pandas as pd 
import random
from datetime import datetime, timedelta, time
from statistics import mean
from time import sleep
import pynmea2

doqueue = True
if doqueue:
    from  ipcqueue import posixmq

from collections import defaultdict
from statistics import mean
from datetime import datetime, timedelta

class RecordParser:
    def __init__(self, config):
        self.config = config
        self.buffer = defaultdict(lambda: defaultdict(list))
        self.last_aggregate_time = {}  # Tracks the last aggregation timestamp for each instrument

    def parse_simple_string_to_record(self, line, config_dict=None, item_delimiter=','):
        if not config_dict:
            config_dict = self.config['stream']

        if 'item_delimiter' in config_dict:
            item_delimiter = config_dict['item_delimiter']

        aggregate_seconds = config_dict.get('aggregate_seconds')
        aggregate_items = config_dict.get('aggregate_items')

        # Check for an instrument datetime
        instrument_datetime = None
        instrument_date = None
        instrument_time = None
        next_day = False
        items = config_dict['items'].split(config_dict['item_delimiter'])
        parts = line.split(config_dict['item_delimiter'])
        formats = config_dict['formats'].split(config_dict['item_delimiter'])
        try:
            if 'inst_datetime' in items:
                idx = items.index('inst_datetime')
                dt_string = parts[idx]
                if '24:' in dt_string:
                    next_day = True
                    dt_string = dt_string.replace('24:','00:')
                instrument_datetime = datetime.strptime(dt_string, formats[idx])
                if next_day:
                    instrument_datetime += timedelta(days=1)
                instrument_datetime = instrument_datetime.replace(microsecond=0)
            elif 'inst_date' in items:
                idx = items.index('inst_date')
                instrument_date = datetime.strptime(parts[idx], formats[idx]).date()
            if 'inst_time' in items:
                idx = items.index('inst_time')
                dt_string = parts[idx]
                if '24:' in dt_string:
                    next_day = True
                    dt_string = dt_string.replace('24:','00:')
                instrument_time = datetime.strptime(dt_string, formats[idx]).time()
            if instrument_time and instrument_date:
                instrument_datetime = datetime.combine(instrument_date, instrument_time)        
                instrument_datetime = instrument_datetime.replace(microsecond=0)
            elif instrument_time and not instrument_date:
                instrument_datetime = datetime.combine(datetime(1900, 1, 1, 0, 0, 0).date(), instrument_time)  
                instrument_datetime = instrument_datetime.replace(microsecond=0)
                if next_day:
                    instrument_datetime += timedelta(days=1)
        except Exception as e:                                      
            self.logger.error(f'Error parsing instrument data line: line = {line}, error = {str(e)}')
            return None
        
        # Bypass aggregation if no aggregate settings
        if not aggregate_seconds or not aggregate_items:
            return self._parse_direct(line, config_dict, item_delimiter, instrument_datetime)

        instrument_key = self.config['instrument']
        current_time = datetime.now()

        # Parse the line into parts
        parts = line.strip().split(item_delimiter)
        items = config_dict['items'].split(',')

        # Buffer the data
        for i, part in enumerate(parts):
            if items[i] != 'x':
                try:
                    if config_dict['formats'].split(',')[i] == 'f':
                        self.buffer[instrument_key][items[i]].append(float(part))
                    elif config_dict['formats'].split(',')[i] in ['s', 'h']:
                        self.buffer[instrument_key][items[i]].append(part)
                except ValueError:
                    self.buffer[instrument_key][items[i]].append(None)

        # Check if aggregation interval has elapsed
        if instrument_key not in self.last_aggregate_time:
            self.last_aggregate_time[instrument_key] = current_time            
        time_so_far = (current_time - self.last_aggregate_time[instrument_key]).total_seconds()
        if time_so_far >= aggregate_seconds:
            if instrument_datetime:
                # if we are aggregating, the instrument time should be the beginning of the aggregation period
                instrument_datetime -= timedelta(seconds = aggregate_seconds)
            result = self._aggregate_buffer(instrument_key, config_dict, instrument_datetime)
            self.last_aggregate_time[instrument_key] = current_time
            return result

        return None

    def _parse_direct(self, line, config_dict, item_delimiter, instrument_datetime):
        parts = line.strip().split(item_delimiter)
        items = config_dict['items'].split(',')
        formats = config_dict['formats'].split(',')
        units = config_dict['units'].split(',')
        acqTypes = config_dict['acqTypes'].split(',')
        
        resultList = []
        acquisition_time = datetime.now().replace(microsecond=0)
        sample_time = acquisition_time - timedelta(seconds=self.config.get('measurement_delay_secs', 0))
        
        for i in range(len(parts)):
            if items[i] != 'x':
                try:
                    value = None
                    string = None
                    if formats[i] == 'f':
                        value = float(parts[i])
                    elif formats[i] in ['s','h']:
                        string = parts[i]
                    
                    resultDict = {
                        'platform': self.config['platform'],
                        'instrument': self.config['instrument'],
                        'parameter': items[i],
                        'unit': units[i],
                        'acquisition_type': acqTypes[i],
                        'acquisition_time': acquisition_time,
                        'sample_time': sample_time,
                        'instrument_time': instrument_datetime
                    }
                    if value is not None:
                        resultDict['value'] = value
                    if string is not None:
                        resultDict['string'] = string

                    resultList.append(resultDict)
                except ValueError:
                    continue

        return resultList

    def _aggregate_buffer(self, instrument_key, config_dict, instrument_datetime):
        aggregate_items = config_dict['aggregate_items'].split(',')
        items = config_dict['items'].split(',')
        formats = config_dict['formats'].split(',')
        units = config_dict['units'].split(',')
        acqTypes = config_dict['acqTypes'].split(',')

        resultList = []
        acquisition_time = datetime.now().replace(microsecond=0)
        sample_time = acquisition_time - timedelta(seconds=self.config.get('measurement_delay_secs', 0))


        for i, item in enumerate(items):
            if item != 'x':
                values = self.buffer[instrument_key][item]
                if not values:
                    continue

                agg_method = aggregate_items[i]
                aggregated_value = None
                if formats[i] == 'f':
                    values = [float(v) for v in values if v is not None]  # Filter out None values
                    if agg_method == 'mean':
                        aggregated_value = mean(values)
                    elif agg_method == 'min':
                        aggregated_value = min(values)
                    elif agg_method == 'max':
                        aggregated_value = max(values)
                    elif agg_method == 'first':
                        aggregated_value = values[0]
                    elif agg_method == 'last':
                        aggregated_value = values[-1]
                elif formats[i] in ['s', 'h']:
                    if agg_method == 'first':
                        aggregated_value = values[0]
                    elif agg_method == 'last':
                        aggregated_value = values[-1]

                resultDict = {
                    'platform': self.config['platform'],
                    'instrument': self.config['instrument'],
                    'parameter': item,
                    'unit': units[i],
                    'acquisition_type': acqTypes[i],
                    'acquisition_time': acquisition_time,
                    'sample_time': sample_time,
                    'instrument_time': instrument_datetime,  # Assumes current time for instrument_time
                }
                if aggregated_value is not None:
                    if formats[i] == 'f':
                        resultDict['value'] = aggregated_value
                    elif formats[i] in ['s','h']:
                        resultDict['string'] = aggregated_value

                resultList.append(resultDict)

                # Clear buffer for the item
                self.buffer[instrument_key][item].clear()

        return resultList

logger = None

def open_queue(qname, maxmsgs, maxmsgsize, destroy_first=False):
    qExists = False
    queue = None
    # check if queue already exists
    try:
        queue = posixmq.Queue(qname)
        qExists = True
    except OSError as e:
        logger.debug('Queue does not yet exist')
    if qExists:
        if destroy_first:
            queue.close()
            queue.unlink()
            qExists = False
        else:
            attribs = queue.qattr()
            # if queue exists, check to make sure it is big enough
            if attribs['max_size'] < maxmsgs or attribs['max_msgbytes'] < maxmsgsize:
                # destroy the queue if it is too small
                queue.close()
                queue.unlink()
                qExists = False
    if not qExists:
        # create the queue if it doesn't exist or has been detroyed
        queue = posixmq.Queue(qname, maxsize=maxmsgs, maxmsgsize=maxmsgsize)
    return queue

class Acquirer:
    global logger
    def __init__(self, config_dict):  
        self.verbose = False  
        self.last_acquire_time = datetime.now()
        self.secs_since_last_acquire = 0
        self.measurements = []
        self.queue = None
        self.rp = RecordParser(config_dict)
        # Initialize static variables for the 'random' signal
        self.sim_previous_value = 0
        self.sim_direction = 1
        self.config = config_dict
        self.command_queue = None
        self.response_queue = None
        self.logger = logging.getLogger(self.config['logs']['logger_name'])
        logger = self.logger
        try:
            if self.config['verbose'] > 0:
                self.verbose = True
        except Exception as e:
            pass
        self.measurement_delay = 0
        try:
            self.measurement_delay = self.config['measurement_delay_secs']
        except Exception as e:
            pass
        if doqueue:
            myMaxMsgSize = self.config['queue']['max_msg_size']
            myMaxMsgs = self.config['queue']['max_msgs']
            myQname = self.config['queue']['name']
            self.queue = open_queue(myQname, myMaxMsgs, myMaxMsgSize)
        command_queue_config = self.config.get('command_queue')
        if command_queue_config:
            self.command_queue = open_queue(
                command_queue_config['name'],
                command_queue_config['max_msgs'],
                command_queue_config['max_msg_size'],
                destroy_first=True
            )
        response_queue_config = self.config.get('response_queue')
        if response_queue_config:
            self.response_queue = open_queue(
                response_queue_config['name'],
                response_queue_config['max_msgs'],
                response_queue_config['max_msg_size'],
                destroy_first=True
            )
    
    def get_command_from_queue(self):
        command = None
        if self.command_queue and self.command_queue.qsize() > 0:
            try:
                sleep(0.5)  # give time for the full message to arrive
                command = self.command_queue.get()
            except (OSError, posixmq.QueueError) as e:
                self.logger.error(f"Failed to unload queue {name}: {e}")
        return command
    
    def put_response_to_queue(self, response):
        if self.response_queue and response:
            try:
                self.response_queue.put(response)
            except Exception as e:
                self.logger.error('Error putting response to queue: '+ str(e))
        return
    
    def get_next_instrument_record(self):
        # this is always overridden
        # gets a measurement record from the instrument
        # method depnds on instrument interface 
        # returns a string in some parseable format 
        return 'not a valid record'
    
    def send_measurement_to_queue(self, measurements):
        if measurements and len(measurements) > 0:
            if doqueue:
                #self.logger.debug('queuing %s', str(measurements))
                self.queue.put(measurements)
                if self.verbose:
                    print(str(measurements))
            else:
                self.logger.debug('not queuing %s', str(measurements))
        
    def parse_simple_string_to_record(self, line, config_dict=None, item_delimiter=','):
        self.logger.debug('received data string: '+line)
        return self.rp.parse_simple_string_to_record(line, config_dict, item_delimiter)

    def apply_alarms(self, messages_in):
        if messages_in and 'alarms' in self.config:
            alarms = self.config['alarms']
            messages_out = []
            for message in messages_in:
                if message['parameter'] in alarms:
                    message_alarms = []
                    for alarm_rule in alarms[message['parameter']]:
                        for alarm_key in alarm_rule.keys():
                            alarm = {} 
                            alarm_tripped = False                           
                            if alarm_key == 'value_<':
                                if message['value'] < alarm_rule[alarm_key]['value']:
                                    alarm_tripped = True
                            if alarm_key == 'value_>':
                                if message['value'] > alarm_rule[alarm_key]['value']:
                                    alarm_tripped = True
                            if alarm_key == 'value_=':
                                if message['value'] == alarm_rule[alarm_key]['value']:
                                    alarm_tripped = True
                            if alarm_key == 'substr_is':
                                if 'string' in message and message['string']:
                                    substr = message['string'][alarm_rule[alarm_key]['substr_begin']:alarm_rule[alarm_key]['substr_end']]
                                    if substr == alarm_rule[alarm_key]['value']:
                                        alarm_tripped = True
                            if alarm_tripped:
                                alarm = {'alarm_level': alarm_rule[alarm_key]['alarm_level'], 'alarm_type': alarm_rule[alarm_key]['alarm_type'], 'alarm_message':alarm_rule[alarm_key]['alarm_message']}
                                if 'impacts_data' in alarm_rule[alarm_key] and not alarm_rule[alarm_key]['impacts_data']:
                                    alarm['data_impacted'] = False
                                else:
                                    alarm['data_impacted'] = True
                                message_alarms.append(alarm)
                                
                    if message_alarms:
                        message['alarms'] = message_alarms
                messages_out.append(message)
        else:
            messages_out = messages_in
        return messages_out        
  
    def time(self):
        # Called to give some processing time to the acquirer
        # meant to be used in polled or periodic instrument reads
        # this is always overridden
        return

    def run(self):
        # Run the acquirer operating loop.  
        # This never returns under normal conditions 
        # this is always overridden
        return
      
      
class SerialStreamAcquirer(Acquirer):
    
    def __init__(self, configdict):
        Acquirer.__init__(self,configdict)
        self.baudrate = 19200
        self.serial_port = None
        self.num_items_per_line = 0
        self.serial_open = False
        self.serial_open_error_logged = False
        self.line_buffer = []
        self.partial_line = ""
        if 'stream' in self.config:
            if 'items' in self.config['stream']:
                try:
                    self.num_items_per_line = len(self.config['stream']['items'].split(','))
                except Exception as e:
                    pass
        if 'init' in self.config:
            for key in self.config['init']:
                if self.check_serial_open():
                    self.serial_port.write(str.encode(self.config['init'][key]))
                    sleep(0.1)

    def check_serial_open(self):
        if not self.serial_open:
            try:
                self.serial_port = serial.Serial(self.config['serial']['device'],baudrate=self.config['serial']['baud'])    
                self.serial_open = True
                self.serial_open_error_logged = False
            except serial.SerialException as e:
                if not self.serial_open_error_logged:
                    self.logger.error('Error opening serial port '+self.config['serial']['device']+' :'+ str(e))
                    self.serial_open_error_logged = True
        return self.serial_open
               
    def getline(self):
        """Retrieve the next complete line, keeping incomplete lines in a buffer."""
        self.check_serial_open()

        # Read available bytes from the serial buffer
        if self.serial_port.in_waiting > 0:
            data = self.serial_port.read(self.serial_port.in_waiting).decode(errors='replace')
            # Add new data to the existing partial line
            self.partial_line += data
            
            # Split into complete lines and update the buffer
            lines = self.partial_line.split('\n')
            self.line_buffer.extend(line.strip() for line in lines[:-1])
            self.partial_line = lines[-1]  # Store incomplete line

        # Return the oldest line from the buffer if available
        if self.line_buffer:
            return self.line_buffer.pop(0)

        return None  # No complete line available
                
    def run(self):
        cycle_time = self.config['stream'].get('cycle_time',1)
        command = None
        while True:
            if self.check_serial_open():
                try:
                    #line = self.serial_port.readline().decode()
                    line = self.getline()
                except Exception as e:
                    self.logger.error('Error reading serial port '+self.config['serial']['device']+' :'+ str(e))
                    sleep(cycle_time)
                else:
                    if self.config.get('response_header'):
                        header = self.config['response_header']
                        if line and line[0:len(header)] == header:
                            self.logger.info('Received response from instrument: '+line.strip()) 
                            response = {'response': line}
                            self.put_response_to_queue(response)
                            continue
                    if line and len(line.split(self.config['stream']['item_delimiter'])) == self.num_items_per_line:
                        #print(str(line))
                        command = None
                        dataMessage = self.parse_simple_string_to_record(line,config_dict=self.config['stream'])
                        dataMessage = self.apply_alarms(dataMessage)
                        if dataMessage and len(dataMessage) > 0:
                            #print(str(dataMessage))
                            self.send_measurement_to_queue(dataMessage)
                if self.command_queue:
                    command = self.get_command_from_queue()
                    if command:
                        self.logger.info('Received command from queue: '+ str(command))
                        if 'command' in command:
                            try:
                                self.serial_port.write(str.encode(command['command']))
                            except Exception as e:
                                self.logger.error('Error writing to serial port '+self.config['serial']['device']+' :'+ str(e))
            else:
                sleep(cycle_time)

class SerialPolledAcquirer(SerialStreamAcquirer):
    def __init__(self, configdict):
        SerialStreamAcquirer.__init__(self, configdict)
        self.lastPolled =datetime.now()
        
    def run(self):
        while True:
            if (datetime.now() - self.lastPolled).total_seconds() >= self.config['data_freq_secs']:
                self.lastPolled =datetime.now()
                if self.check_serial_open():
                    if 'poll' in self.config:
                        for key in self.config['poll']:
                            self.serial_port.reset_input_buffer()
                            self.serial_port.write(str.encode(self.config['poll'][key]['request_string']))
                            sleep(0.1)
                            #self.serial_port.flushInput()
                            read = True #indicator of whether instrument is responding
                            timeout = False #timeout for the reading

                            wait_time = datetime.now()
                            while self.serial_port.inWaiting() < self.config['poll'][key]['response_len_min'] and timeout == False:  # wait for 26 bytes before reading in
                                sleep(.05)
                                if (datetime.now() - wait_time).total_seconds() >= 1:
                                    timeout = True
                                    read = False
                            
                            resp_string = ''
                            if read:
                                sleep(.01)
                                original_resp_string = self.serial_port.read_all().decode()
                                try:
                                    resp_string = original_resp_string
                                    if 'trim_response_begin' in self.config['poll'][key]:
                                        if 'trim_response_end' in self.config['poll'][key]:
                                            resp_string = resp_string[self.config['poll'][key]['trim_response_begin']:self.config['poll'][key]['trim_response_end']]
                                        else:
                                            resp_string = resp_string[self.config['poll'][key]['trim_response_begin']:]
                                    else:
                                        if 'trim_response_end' in self.config['poll'][key]:
                                            resp_string = resp_string[:self.config['poll'][key]['trim_response_end']]
                                    
                                    responses = resp_string.split(self.config['poll'][key]['item_delimiter'])                              
                                    
                                    value_string = ''
                                    if 'key_delimiter' in self.config['poll'][key]:
                                        resp_values = {}                                  
                                        for response in responses:
                                            parts = response.split(self.config['poll'][key]['key_delimiter'])
                                            resp_values[parts[0]] = parts[1]
                                        value_string = self.config['poll'][key]['item_delimiter'].join(resp_values.values())
                                    else:
                                        value_string = self.config['poll'][key]['item_delimiter'].join(responses)
                                           
                                    if value_string:                                        
                                        messages = self.parse_simple_string_to_record(value_string,config_dict=self.config['poll'][key])
                                        messages = self.apply_alarms(messages)
                                        self.send_measurement_to_queue(messages)
                                except Exception as e:
                                    self.logger.error('cannot proccess response string: '+original_resp_string+' :' + str(e))

class NetworkAcquirer(Acquirer):
    def __init__(self, configdict):
        Acquirer.__init__(self, configdict)
        self.socket = None
        self.socket_open = False
        self.conn = None
        self.addr = None

    def check_socket_open(self):
        host = self.config['network']['address']
        port = self.config['network']['port']

        if not self.socket or not self.socket_open:
            context = zmq.Context()
            self.socket = context.socket(zmq.PULL)  # response socket
            try:
                self.socket.bind('tcp://*:'+str(port))
                self.socket_open = True
            except Exception as e:
                self.socket_open = False
        return self.socket_open

    def read_message_from_socket(self):
        message = None
        # Receive data from the client
        success = False
        while  not success:
            received_data = b''
            if self.check_socket_open():
                try:
                    received_data = self.socket.recv()    
                except Exception as e:
                    self.logger.error('Error receiving message from zmq socket,'+' err:' + str(e))
                else:
                    try:
                        message_length = 0
                        message = pickle.loads(received_data)
                        message_length = len(message)
                        self.logger.debug('pickled message of length = '+ str(message_length))
                        success = True
                    except Exception as e:
                        self.logger.error('Error converting message from socket, message len='+str(message_length)+' err:' + str(e))
                        message = None
                        success = True
        return message

class NetworkStreamingAcquirer(NetworkAcquirer):
    def __init__(self, configdict):
        NetworkAcquirer.__init__(self, configdict)

    def measurement_dict_to_text_line(self, dict, keys):
        if isinstance(keys, str):
            keys = list(map(int,keys.split(',')))
        try:
            value_strings = [str(dict[k]) for k in keys]
            return ','.join(value_strings)  
        except Exception as e:
            self.logger.error('Error converting measurement dict to string, err:' + str(e))
            return None
        
    def run(self):
        while True:
            if self.check_socket_open():
                try:
                    message = self.read_message_from_socket()
                except Exception as e:
                    self.logger.error('Error reading from network socket '+int(self.config['network']['port'])+' :'+ str(e))
                else:
                    if message:
                        dicts = self.config['dictionaries'].split(',')
                        for dict in dicts:
                            if dict in message: 
                                values_dict = message[dict]
                                if 'keys' in self.config[dict]:
                                    values_string = self.measurement_dict_to_text_line(values_dict, self.config[dict]['keys'])
                                else:
                                    items = self.config[dict]['items'].split(',')
                                    try:
                                        values = [values_dict[item] for item in items]
                                        values_string = ','.join(values)
                                    except Exception as e:
                                        self.logger.error('bad message found while acquiring: {}'.format(str(dict)))
                                        values_string = None
                                if values_string: 
                                    dataMessage = self.parse_simple_string_to_record(values_string,config_dict=self.config[dict])
                                    dataMessage = self.apply_alarms(dataMessage)
                                    if len(dataMessage) > 0:
                                        self.send_measurement_to_queue(dataMessage)
            else:
                sleep(1)

class SerialNmeaGPSAcquirer(SerialStreamAcquirer):
    def __init__(self, configdict):
        SerialStreamAcquirer.__init__(self, configdict)

    def make_measurement_item(self, parameter, unit, value, string=None, timestamp=None):
        acquisition_time = datetime.now().replace(microsecond=0)
        sample_time = acquisition_time - timedelta(seconds = self.measurement_delay)

        resultDict = {
            'platform':self.config['platform'],
            'instrument':self.config['instrument'],
            'parameter':parameter,
            'unit':unit,
            'acquisition_type':'GPS',
            'acquisition_time': acquisition_time,
            'sample_time':  sample_time,
            'value':value}
        if timestamp:
            resultDict['instrument_time'] = timestamp
        if string:
            resultDict['string'] = string
        return resultDict
            

    def process_nmea_sentence(self, sentence):
        try:
            # Parse the NMEA sentence
            msg = pynmea2.parse(sentence)

            # Only process messages with position data
            messages = []
            if isinstance(msg, pynmea2.types.talker.RMC):
                timeStamp = msg.timestamp
                if isinstance(timeStamp,time):
                    n = datetime.now()
                    timeStamp = datetime(n.year,n.month,n.day,timeStamp.hour,timeStamp.minute,timeStamp.second)
                if float(msg.latitude) != 0.0:
                    messages.append(self.make_measurement_item('latitude','lat',float(msg.latitude),timestamp = timeStamp))
                if float(msg.longitude) != 0.0:
                    messages.append(self.make_measurement_item('longitude','lon',float(msg.longitude),timestamp = timeStamp))
                if msg.spd_over_grnd:
                    messages.append(self.make_measurement_item('speed','m/s',float(msg.spd_over_grnd)*0.514444,timestamp = timeStamp))
                if msg.true_course:
                    messages.append(self.make_measurement_item('direction','deg',float(msg.true_course),timestamp = timeStamp))
                return messages
        except pynmea2.ParseError as e:
            self.logger.error(f"Failed to parse NMEA sentence: {e}")
            return None

    def run(self):
        buffer = ""
        timer = datetime.now()
        while True:
            if self.check_serial_open():
                try:
                    # Read all available data from the serial port
                    data = self.serial_port.read(self.serial_port.in_waiting or 1).decode('ascii', errors='replace')
                    
                    # Append data to the buffer
                    buffer += data
                    buffer = buffer.replace('\n','')

                    # Split buffer by carriage return '\r'
                    lines = buffer.split('\r')
                    
                    # Process each complete sentence in the buffer
                    for line in lines[:-1]:
                        line = line.strip()
                        if line.startswith('$'):
                            self.logger.debug('NMEA sentence: ' + line)
                            message = self.process_nmea_sentence(line)
                            if message:
                                message = self.apply_alarms(message)
                                if (datetime.now() - timer).total_seconds() >= 1:
                                    self.send_measurement_to_queue(message)
                                    timer = datetime.now()

                    # Keep the last incomplete sentence in the buffer
                    buffer = lines[-1] if lines[-1] else ""
                except Exception as e:
                    self.logger.error('Error reading serial port ' + self.config['serial']['device'] + ' :' + str(e))

class SerialNmeaAcquirer(SerialStreamAcquirer):
    def __init__(self, configdict):
        SerialStreamAcquirer.__init__(self, configdict)

    def make_measurement_item(self, parameter, unit, value, acquisition_type='GPS', string=None, timestamp=None):
        acquisition_time = datetime.now().replace(microsecond=0)
        sample_time = acquisition_time - timedelta(seconds = self.measurement_delay)

        resultDict = {
            'platform':self.config['platform'],
            'instrument':self.config['instrument'],
            'parameter':parameter,
            'unit':unit,
            'acquisition_type': acquisition_type,
            'acquisition_time': acquisition_time,
            'sample_time':  sample_time,
            'value':value}
        if timestamp:
            resultDict['instrument_time'] = timestamp
        if string:
            resultDict['string'] = string
        return resultDict
            

    def process_nmea_sentence(self, sentence):
        try:
            # Parse the NMEA sentence
            msg = pynmea2.parse(sentence)
            msg_type = msg.sentence_type
            messages = []
            if msg_type in self.config['data']['sentence_types']:
                for item in self.config['data']['sentence_types'][msg_type].keys():
                    value = getattr(msg, item, None)
                    if value is not None:
                        parameter = self.config['data']['sentence_types'][msg_type][item]['parameter']
                        unit = self.config['data']['sentence_types'][msg_type][item]['unit']
                        aquType = self.config['data']['sentence_types'][msg_type][item]['acqType'] 
                        format = self.config['data']['sentence_types'][msg_type][item]['format']
                        if format == 'f':
                            value = float(value)
                            scaler = self.config['data']['sentence_types'][msg_type][item].get('scaler', None)
                            if scaler:
                                value = value * scaler
                        elif format == 's':
                            value = str(value)
                        # filter out lonigitudes and latitudes of zero
                        if (parameter == 'latitude' or parameter == 'longitude') and value == 0:
                            continue
                        message = self.make_measurement_item(parameter, unit, value, acquisition_type=aquType, string=(format == 's'))
                        messages.append(message)
            return messages
        except pynmea2.ParseError as e:
            self.logger.error(f"Failed to parse NMEA sentence: {e}")
            return None

    def run(self):
        timer = datetime.now()
        while True:
            if self.check_serial_open():
                try:
                    line = self.getline()
                    if line is not None and line.startswith('$'):
                        self.logger.debug('NMEA sentence: ' + line)
                        message = self.process_nmea_sentence(line)
                        if message:
                            message = self.apply_alarms(message)
                            if (datetime.now() - timer).total_seconds() >= 1:
                                self.send_measurement_to_queue(message)
                                timer = datetime.now()
                except Exception as e:
                    self.logger.error('Error reading serial port ' + self.config['serial']['device'] + ' :' + str(e))

                      
class SimulatedAcquirer(Acquirer):
    def __init__(self, configdict):
        Acquirer.__init__(self, configdict)
        self.parameters = configdict['stream']['items'].split(',')
        self.rnd_data = np.cumsum(np.random.randn(500))
        self.cycletime = 1

    def simulate_signal(self, signal_type, period, last_data_point, signal_min=0, signal_max=100):
        time = last_data_point + 1
        amplitude = signal_max - signal_min
        normalized_time = (time % period) / period
        value = 0

        if signal_type == 'sine':
            value = np.sin(2 * np.pi * normalized_time)
        elif signal_type == 'triangle':
            if normalized_time < 0.5:
                value = 4 * normalized_time - 1
            else:
                value = 3 - 4 * normalized_time
        elif signal_type == 'sawtooth':
            value = 2 * normalized_time - 1
        elif signal_type == 'square':
            value = 1 if normalized_time < 0.5 else -1
        elif signal_type == 'random':
            value = self.rnd_data[time % 500]   

        scaled_value = signal_min + (value + 1) / 2 * amplitude
        return scaled_value, time

    def make_data_line(self):
        items = []
        line = ''
        for parameter in self.parameters:
            value,self.cycletime = self.simulate_signal(self.config['simulate'][parameter]['signal'], self.config['simulate'][parameter]['period'], self.cycletime, self.config['simulate'][parameter]['min'], self.config['simulate'][parameter]['max'])
            items.append(str(value))
        return self.config['stream']['item_delimiter'].join(items)

    def run(self):
        cycle_time = datetime.now()
        cycle_interval = timedelta(seconds=self.config['simulate']['cycle_secs'])
        while True:
            line = self.make_data_line()
            record = self.parse_simple_string_to_record(line,config_dict=self.config['stream'])
            record = self.apply_alarms(record)
            print(str(record))
            self.send_measurement_to_queue(record)
            time_since_last_cycle = datetime.now() - cycle_time
            to = (cycle_interval.seconds * 1000 - time_since_last_cycle.microseconds) / 1000
            sleep(cycle_interval.total_seconds())
            cycle_time = datetime.now()

class SimulatedGPSAcquirer(SerialNmeaGPSAcquirer):
    def __init__(self, configdict):
        Acquirer.__init__(self,configdict)
        self.config = configdict
        self.cycletime = configdict['cycletime']
        self.dataframe = pd.read_csv(configdict['datafile'])
        self.location_index = 0
        self.measurement_delay = configdict.get('measurement_delay_secs', 0)


    def run(self):
        cycle_interval = int(self.config['cycletime'])
        while self.location_index < len(self.dataframe):
            lat = self.dataframe.iloc[self.location_index]['latitude']
            lon = self.dataframe.iloc[self.location_index]['longitude']
            self.location_index += 1
            n = datetime.now()
            timeStamp = datetime(n.year,n.month,n.day,n.hour,n.minute,n.second)
            lat_message = self.make_measurement_item('latitude','lat',float(lat),timestamp = timeStamp)
            lon_message = self.make_measurement_item('longitude','lon',float(lon),timestamp = timeStamp)
            self.send_measurement_to_queue([lat_message,lon_message])
            sleep(cycle_interval)

from labjack import ljm

class LabJackAcquirer(Acquirer):
    def __init__(self, config_dict):
        super().__init__(config_dict)
        self.handle = None
        self.params = config_dict['Parameters']
        self.data_freq = config_dict.get('data_freq_secs', 1)
        self.buffers = {}  # {param_name: [list of samples]}
        self.aggregate_info = {}  # {param_name: (agg_type, hz)}
        self.open_labjack()
        self.setup_buffers()

    def open_labjack(self):
        try:
            self.handle = ljm.openS(
                self.config.get('device_type', 'ANY'),
                self.config.get('connection_type', 'ANY'),
                self.config.get('identifier', 'ANY')
            )
            self.logger.info("LabJack device opened successfully.")
        except Exception as e:
            self.logger.error(f"Failed to open LabJack: {str(e)}")
            raise

    def setup_buffers(self):
        for param_entry in self.params:
            for param_name, cfg in param_entry.items():
                if cfg.get("signal_type") == "Analog" and "aggregate_hz" in cfg and "aggregate" in cfg:
                    self.buffers[param_name] = []
                    self.aggregate_info[param_name] = (cfg["aggregate"], cfg["aggregate_hz"])

    def read_analog(self, name, cfg):
        try:
            raw_voltage = ljm.eReadName(self.handle, name)
            gain = cfg.get('preamp_gain', 1.0)
            v_offset = cfg.get('v_offset', 0.0)
            v_per_unit = cfg.get('v_per_unit', 1.0)
            value = (raw_voltage - v_offset) / (v_per_unit * gain)
            return value
        except Exception as e:
            self.logger.error(f"Error reading analog channel {name}: {str(e)}")
            return None

    def read_digital(self, name):
        try:
            state = ljm.eReadName(self.handle, name)
            return int(state)
        except Exception as e:
            self.logger.error(f"Error reading digital channel {name}: {str(e)}")
            return None

    def run(self):
        aggregate_cycle_secs = self.data_freq
        next_output_time = datetime.now() + timedelta(seconds=aggregate_cycle_secs)

        while True:
            loop_start = datetime.now()
            now = datetime.now()

            results = []

            for param_entry in self.params:
                for param_name, cfg in param_entry.items():
                    signal_type = cfg.get('signal_type')
                    channel = cfg.get('channel_name')

                    is_aggregated = param_name in self.buffers

                    if signal_type == 'Analog':
                        value = self.read_analog(channel, cfg)
                        if value is not None:
                            if is_aggregated:
                                self.buffers[param_name].append(value)
                            elif now >= next_output_time:
                                record = self.make_record(param_name, value, cfg)
                                results.append(record)

                    elif signal_type == 'Digital':
                        if now >= next_output_time:
                            value = self.read_digital(channel)
                            if value is not None:
                                record = self.make_record(param_name, value, cfg)
                                results.append(record)

            if now >= next_output_time:
                for param_name, (agg_type, _) in self.aggregate_info.items():
                    samples = self.buffers.get(param_name, [])
                    if samples:
                        if agg_type == 'mean':
                            agg_value = mean(samples)
                        elif agg_type == 'max':
                            agg_value = max(samples)
                        elif agg_type == 'min':
                            agg_value = min(samples)
                        else:
                            continue
                        self.buffers[param_name] = []
                        cfg = next(entry[param_name] for entry in self.params if param_name in entry)
                        record = self.make_record(param_name, agg_value, cfg)
                        results.append(record)

                if results:
                    self.send_measurement_to_queue(self.apply_alarms(results))
                next_output_time = now + timedelta(seconds=aggregate_cycle_secs)

            # Sleep to match aggregate_hz (if any); otherwise 10 Hz default
            max_hz = max((hz for _, hz in self.aggregate_info.values()), default=10)
            sleep_time = 1.0 / max_hz
            elapsed = (datetime.now() - loop_start).total_seconds()
            sleep(max(0, sleep_time - elapsed))


    def make_record(self, param_name, value, cfg):
            now = datetime.now().replace(microsecond=0)
            sample_time = now - timedelta(seconds=self.measurement_delay)
            return {
                'platform': self.config['platform'],
                'instrument': self.config['instrument'],
                'parameter': param_name,
                'unit': cfg.get('unit', ''),
                'acquisition_type': cfg.get('aquisition_type', ''),
                'acquisition_time': now,
                'sample_time': sample_time,
                'value': value
            }


class AquirerFactory():
    
    def makeSerialAcquirer(self, config):
        acquirer = SerialStreamAcquirer(config)
        return acquirer

    def makeSimulatorAcquirer(self, config):
        acquirer = SimulatedAcquirer(config)
        return acquirer

    def makeNetworkStreamingAcquirer(self, config):
        acquirer = NetworkStreamingAcquirer(config)
        return acquirer

    def makeSerialNmeaGPSAcquirer(self, config):
        acquirer = SerialNmeaGPSAcquirer(config)
        return acquirer

    def makeSerialNmeaAcquirer(self, config):
        acquirer = SerialNmeaAcquirer(config)
        return acquirer

    def makeSerialPolledAcquirer(self, config):
        acquirer = SerialPolledAcquirer(config)
        return acquirer
    
    def makeSimulatedGPSAcquirer(self, config):
        acquirer = SimulatedGPSAcquirer(config)
        return acquirer

    def makeLabJackAcquirer(self, config):
        return LabJackAcquirer(config)


    selector = {'simpleSerial':makeSerialAcquirer, 'simulated':makeSimulatorAcquirer, 'networkStreaming':makeNetworkStreamingAcquirer, 'serial_nmea_GPS':makeSerialNmeaGPSAcquirer, 'serial_nmea':makeSerialNmeaAcquirer, 'serialPolled':makeSerialPolledAcquirer, 'simulated_GPS': makeSimulatedGPSAcquirer, 'LabJack': makeLabJackAcquirer, }

    def make(self,config):
        maker = self.selector[config['type']]
        return maker(self,config)

    

# Run the app
if __name__ == '__main__':
    configfile = open('co2simulator.yaml','r')
    config = yaml.safe_load(configfile)
    configfile.close()

    factory = AquirerFactory()
    acq = factory.make(config)
    acq.run()
    
