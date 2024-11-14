import sys
import serial
import socket
import yaml
import numpy as np
import logging
import pickle
import random
from datetime import datetime, timedelta
from time import sleep
import pynmea2

doqueue = True
if doqueue:
    from  ipcqueue import posixmq

class Acquirer:
    def __init__(self, config_dict):  
        self.verbose = False  
        self.last_acquire_time = datetime.now()
        self.secs_since_last_acquire = 0
        self.measurements = []
        self.queue = None
        # Initialize static variables for the 'random' signal
        self.sim_previous_value = 0
        self.sim_direction = 1
        self.config = config_dict
        self.logger = logging.getLogger(self.config['logs']['logger_name'])
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
            self.open_queue()

    def open_queue(self):
        myMaxMsgSize = self.config['queue']['max_msg_size']
        myMaxMsgs = self.config['queue']['max_msgs']
        myQname = self.config['queue']['name']
        qExists = False
        # check if queue already exists
        try:
            queue = posixmq.Queue(myQname)
            qExists = True
        except OSError as e:
            self.logger.debug('Queue does not yet exist')
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
        self.queue = queue


    def get_next_instrument_record(self):
        # this is always overridden
        # gets a measurement record from the instrument
        # method depnds on instrument interface 
        # returns a string in some parseable format 
        return 'not a valid record'
    
    def send_measurement_to_queue(self, measurements):
        if len(measurements) > 0:
            if doqueue:
                #self.logger.debug('queuing %s', str(measurements))
                self.queue.put(measurements)
                if self.verbose:
                    print(str(measurements))
            else:
                self.logger.debug('not queuing %s', str(measurements))
        
    def parse_simple_string_to_record(self,line,config_dict=None, item_delimiter = ','):
        # parses a string record as acquared from the instrument
        # and returns a list fo dictionaries, one dict for each parameter
        # read by the instrument
        # this clearly needs a rewrite 
        if not config_dict:
            config_dict = self.config['stream']
        if 'item_delimiter' in config_dict:
            item_delimiter = config_dict['item_delimiter']
        parts = line.strip().split(item_delimiter)
        items = config_dict['items'].split(',')
        resultList = []

        if len(parts) == len(items):
            formats = config_dict['formats'].split(',')
            units = config_dict['units'].split(',')
            acqTypes = config_dict['acqTypes'].split(',')
            res_values = []
            res_parameters = []
            res_units = []
            res_acqTypes = []
            time = None
            date = None
            instTime = None
            next_day = False
            for i in range(0,len(parts)):
                 if items[i] != 'x':
                    if formats[i] in 'fh':
                        part = parts[i]
                        try:
                            if formats[i] == 'h':
                                if '0x' not in part.lower():
                                    part = '0x'+part
                                fl = float(int(part,0))
                            else:
                                fl = float(part)
                        except:
                            self.logger.error('bad item '+items[i]+'='+parts[i]+' in line \"'+line+'\"')
                        else:
                            res_values.append(fl)
                            res_parameters.append(items[i])
                            res_units.append(units[i])
                            res_acqTypes.append(acqTypes[i])
                    elif items[i] == 'inst_date':
                        parsed = datetime.strptime(parts[i], formats[i])
                        date = parsed.date()
                    elif items[i] == 'inst_time':
                        # BUG HERE: some instruments deliver 24:00:00, python doesn't handle
                        if parts[i][0:3] == '24:':
                            parts[i][0:3] = '00:'
                            next_day = True
                        parsed = datetime.strptime(parts[i], formats[i])
                        time = parsed.time()
                    elif items[i] == 'inst_datetime':
                        if ' 24:' in parts[i]:
                            parts[i].replace(' 24:', ' 00:')
                            parsed = datetime.strptime(parts[i], formats[i]) + timedelta(days=1)
                        else:
                            parsed = datetime.strptime(parts[i], formats[i])
                        instTime = parsed
                    if time and date:
                        if next_day:
                            date += timedelta(days=1)
                        instTime = datetime.combine(date, time)
            
            acquisition_time = datetime.now().replace(microsecond=0)
            sample_time = acquisition_time - timedelta(seconds = self.measurement_delay)

            for i in range(0,len(res_values)):		
                resultDict = {
                    'platform':self.config['platform'],
                    'instrument':self.config['instrument'],
                    'parameter':res_parameters[i],
                    'unit':res_units[i],
                    'acquisition_type':res_acqTypes[i],
                    'acquisition_time':acquisition_time,
                    'sample_time':sample_time,
                    'instrument_time':instTime,
                    'value':res_values[i]} 
                resultList.append(resultDict)
        return resultList 



  
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
    baudrate = 19200
    serial_port = None
    num_items_per_line = 0
    serial_open = False
    serial_open_error_logged = False
    
    def __init__(self, configdict):
        Acquirer.__init__(self,configdict)
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
               
                
    def run(self):
        while True:
            if self.check_serial_open():
                try:
                    line = self.serial_port.readline().decode()
                except Exception as e:
                    self.logger.error('Error reading serial port '+config['serial']['device']+' :'+ e)
                else:
                    if len(line.split(self.config['stream']['item_delimiter'])) == self.num_items_per_line:
                        dataMessage = self.parse_simple_string_to_record(line,config_dict=self.config['stream'])
                        if len(dataMessage) > 0:
                            self.send_measurement_to_queue(dataMessage)
            else:
                sleep(1)

class SerialPolledAcquirer(SerialStreamAcquirer):
    def __init__(self, configdict):
        SerialStreamAcquirer.__init__(self, configdict)
        self.lastPolled =datetime.now()
        
    def run(self):
        while True:
            if (datetime.now() - self.lastPolled).total_seconds() >= self.config['data_freq_secs']:
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
                                        self.send_measurement_to_queue(messages)
                                        self.lastPolled =datetime.now()
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
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                self.socket.bind((host, port))
                self.socket.listen()
                # Accept a connection
                self.conn, self.addr = self.socket.accept()
                self.socket_open = True
            except Exception as e:
                self.socket_open = False
        return self.socket_open

    def read_message_from_socket(self):
        message = None
        # Receive data from the client
        success = False
        while  not success:
            self.logger.debug('About to recieve length from network socket '+str(self.config['network']['port']))
            length_data = self.conn.recv(1024)
            if len(length_data) != 4:
                self.logger.error('Error receiving message length, len = '+str(len(length_data)))
                continue
            self.logger.debug('received length = '+ str(int.from_bytes(length_data, 'big')))
            if length_data:
                message_length = int.from_bytes(length_data, 'big')
                received_data = b""
                while len(received_data) < message_length:
                    chunk = self.conn.recv(1024)
                    self.logger.debug('received chunk of length = '+ str(len(chunk)))
                    if chunk:
                        if len(chunk) == 4 and len(received_data) + len(chunk) != message_length:
                            # We've slipped a frame, restart with this data chunk as length
                            message_length = int.from_bytes(chunk, 'big')
                            continue
                        else:
                            received_data += chunk
                if len(received_data) >= message_length:
                    try:
                        message = pickle.loads(received_data)
                        self.logger.debug('pickled message of length = '+ str(len(received_data)))
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
        value_strings = [str(dict[k]) for k in keys]
        return ','.join(value_strings)                
        
    def run(self):
        while True:
            if self.check_socket_open():
                try:
                    message = self.read_message_from_socket()
                except Exception as e:
                    self.logger.error('Error reading from network socket '+int(self.config['network']['port'])+' :'+ e)
                else:
                    if message:
                        dicts = self.config['dictionaries'].split(',')
                        for dict in dicts:
                            values_dict = message[dict]
                            values_string = self.measurement_dict_to_text_line(values_dict, self.config[dict]['keys'])
                            dataMessage = self.parse_simple_string_to_record(values_string,config_dict=self.config[dict])
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
                messages.append(self.make_measurement_item('latitude','lat',float(msg.latitude),timestamp = timeStamp))
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
        while True:
            if self.check_serial_open():
                try:
                    # Read all available data from the serial port
                    data = self.serial_port.read(self.serial_port.in_waiting or 1).decode('ascii', errors='replace')
                    
                    # Append data to the buffer
                    buffer += data

                    # Split buffer by carriage return '\r'
                    lines = buffer.split('\r')
                    
                    # Process each complete sentence in the buffer
                    for line in lines[:-1]:
                        line = line.strip()
                        if line.startswith('$'):
                            message = self.process_nmea_sentence(line)
                            if message:
                                self.send_measurement_to_queue(message)

                    # Keep the last incomplete sentence in the buffer
                    buffer = lines[-1] if lines[-1] else ""
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
            self.send_measurement_to_queue(record)
            time_since_last_cycle = datetime.now() - cycle_time
            to = (cycle_interval.seconds * 1000 - time_since_last_cycle.microseconds) / 1000
            sleep(cycle_interval.seconds)
            cycle_time = datetime.now()

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
    
    def makeSerialPolledAcquirer(self, config):
        acquirer = SerialPolledAcquirer(config)
        return acquirer
    
    selector = {'simpleSerial':makeSerialAcquirer, 'simulated':makeSimulatorAcquirer, 'networkStreaming':makeNetworkStreamingAcquirer, 'serial_nmea_GPS':makeSerialNmeaGPSAcquirer, 'serialPolled':makeSerialPolledAcquirer}

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
    
