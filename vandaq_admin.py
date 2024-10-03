import sys
import os
from glob import glob
import subprocess
import psutil

args = sys.argv
if 'python' in args[0]:
	args = args[1:]

acqDir = '/home/robin/vandaq/acquirer/'
acqLogDir = acqDir+'log/'
collDir = '/home/robin/vandaq/collector/' 
collLogDir = collDir+'log/'
processes = []

def getAcquirerProcesses():
	ps = []
	for p in psutil.process_iter():
		if p.status() != 'zombie':
			 cmdln = ' '.join(p.cmdline())
			 if 'vandaq_acquirer.py' in cmdln:
				 ps.append(p)
	return ps


def getCollectorProcesses():
	ps = []
	for p in psutil.process_iter():
		if p.status() != 'zombie':
			 cmdln = ' '.join(p.cmdline())
			 if 'vandaq_collector.py' in cmdln:
				 ps.append(p)
	return ps


def startup():
	print('starting VanDAQ processes')
	if len(args) > 2:
		basedir = args[2]
	else:
		basedir = '/home/robin/vandaq/acquirer/config/'
	
	if basedir[-1] != '/':
		basedir += '/'

	this_env = os.environ.copy()
	cmd = ['python3',collDir+'vandaq_collector.py', collDir+'vandaq_collector.yaml']
	logFileName = collLogDir + 'collector.log'
	configs = glob(basedir+'*.yaml')
	logFile = open(logFileName,'a')
	proc = subprocess.Popen(cmd, env=this_env, stdout=logFile)
	proc.wait()
	print('Started collector '+str(cmd)+'   pid='+str(proc.pid))
	processes.append({'cmd':cmd, 'pid':proc.pid})
	if len(configs) > 0:
		for config in configs:
			logFileName = acqLogDir + os.path.basename(config.replace('.yaml',''))
			logFile = open(logFileName,'a')
			cmd = ['python3',acqDir+'vandaq_acquirer.py',config]
			proc = subprocess.Popen(cmd, env=this_env, stdout=logFile)
			proc.wait()
			pid = proc.pid
			print('Started acquirer '+str(cmd)+'   pid='+str(pid))
			processes.append({'cmd':cmd, 'pid':proc.pid})

def stop():
	print('Stopping VanDAQ processes')
	ps = getAcquirerProcesses()
	for p in ps:
		p.kill()
	ps = getCollectorProcesses()
	for p in ps:
		p.kill()

commands = {'startup':startup, 'stop':stop}

if len(args) >= 2 and args[1] in commands.keys():
	command = commands[args[1]]
	command()
else:
	print('no command found')


