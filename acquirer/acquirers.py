import sys
import serial
import yaml
import numpy as np
import logging
import random
from datetime import datetime, timedelta
from time import sleep

doqueue = True
if doqueue:
    from  ipcqueue import posixmq

class Acquirer:
    def __init__(self, config_dict):    
        self.last_acquire_time = datetime.now()
        self.secs_since_last_acquire = 0
        self.measurements = []
        self.queue = None
        # Initialize static variables for the 'random' signal
        self.sim_previous_value = 0
        self.sim_direction = 1
        self.config = config_dict
        self.logger = logging.getLogger(self.config['logs']['logger_name'])
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
                self.logger.debug('queuing %s', str(measurements))
                self.queue.put(measurements)
            else:
                self.logger.debug('not queuing %s', str(measurements))
        
    def parse_simple_string_to_record(self,line):
        # parses a string record as acquared from the instrument
        # and returns a list fo dictionaries, one dict for each parameter
        # read by the instrument
        # this clearly needs a rewrite        
        parts = line.strip().split(self.config['stream']['item_delimiter'])
        items = self.config['stream']['items'].split(',')
        resultList = []

        if len(parts) == len(items):
            formats = self.config['stream']['formats'].split(',')
            units = self.config['stream']['units'].split(',')
            acqTypes = self.config['stream']['acqTypes'].split(',')
            res_values = []
            res_parameters = []
            res_units = []
            res_acqTypes = []
            time = None
            date = None
            instTime = None
            for i in range(0,len(parts)):
                value = None
                if items[i] != 'x':
                    if formats[i] == 'f':
                        try:
                            fl = float(parts[i])
                        except:
                            self.logger.error('bad item '+items[i]+'='+parts[i]+' in line \"'+line+'\"')
                        else:
                            res_values.append(float(parts[i]))
                            res_parameters.append(items[i])
                            res_units.append(units[i])
                            res_acqTypes.append(acqTypes[i])
                    elif items[i] == 'inst_date':
                        parsed = datetime.strptime(parts[i], formats[i])
                        date = parsed.date()
                    elif items[i] == 'inst_time':
                        parsed = datetime.strptime(parts[i], formats[i])
                        time = parsed.time()
                    elif items[i] == 'inst_datetime':
                        parsed = datetime.strptime(parts[i], formats[i])
                        instTime = parsed
                    if time and date:
                        instTime = datetime.combine(date, time)

            for i in range(0,len(res_values)):		
                resultDict = {
                    'platform':self.config['platform'],
                    'instrument':self.config['instrument'],
                    'parameter':res_parameters[i],
                    'unit':res_units[i],
                    'acquisition_type':res_acqTypes[i],
                    'acquisition_time':datetime.now(),
                    'sample_time':datetime.now(),
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
        self.num_items_per_line = len(self.config['stream']['items'].split(','))
     
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
                        dataMessage = self.parse_simple_string_to_record(line)
                        if len(dataMessage) > 0:
                            self.send_measurement_to_queue(dataMessage)
            else:
                sleep(1)
            
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
            record = self.parse_simple_string_to_record(line)
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
    
    selector = {'simpleSerial':makeSerialAcquirer, 'simulated':makeSimulatorAcquirer }

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