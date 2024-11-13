#!/usr/bin python3
from acquirers import *
import yaml
import logging
from logging.handlers import TimedRotatingFileHandler
import sys
import os


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

# Create an acquirer to match the configuration file
factory = AquirerFactory()
acq = factory.make(config)
# run the acquirer
acq.run()
