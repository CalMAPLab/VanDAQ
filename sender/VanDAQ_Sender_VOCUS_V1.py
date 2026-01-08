"""

VanDAQ
Mobile Atmospheric Data Acquisition System

Author: Robert Jay (Robin) Weber
Affiliation: University of California, Berkeley

Copyright (c) 2025 The Regents of the University of California
Released under the BSD 3-Clause License.
"""

import sys
import numpy as np
import zmq
import pickle
import requests
import asyncio
import aiohttp
import time
from datetime import datetime
import json

sys.path.append('C:\\Users\\TofUser\\Documents\\TOFDaq API\\TofDaq_1.99r759_API_20180912\\src\\Python')
print(sys.path)
from TofDaq import *

response_list = []
eng_codes = [{'name':'Interlock', "ID": "INTERLOCK_MON", "CAN": "3020070901"},
        {'name':'Zero_Valve', "ID": "VALVE_MON", "CAN": "1920070701"},
        {'name':'Cal_valve', "ID": "VALVE1_MON", "CAN": "1920080701"},
        {'name':'H2O_MFC', "ID": "MFCEXT_MON",   "CAN": "0E20030407"},
        {'name':'Ion_source current',"ID":"PTRCUR_MON","CAN":"6020021406"},
        {'name':'MCP_V', "ID": "HVA0_MON", "CAN": "5120011406"},
        {'name':'TOF_pressure', "ID": "PRESSA6_MON", "CAN": "1D20061707"},
        {'name':'VOCUS_pressure', "ID": "PRESSA3_MON", "CAN": "1D20031707"},
        {'name':'Turbo_speed', "ID": "PFEIFFER_ACTSPEED_MON", "CAN": "1320030803"},
        {'name':'Turbo_power', "ID": "PFEIFFER_DRVPOWER_MON", "CAN": "1320030F03"},
        {'name':'Turbo_T', "ID": "PFEIFFER_TMOTOR_MON", "CAN": "1320031503"}]

# Define the IP and port of the server to connect to
HOST = '169.229.157.5'     # Replace with the server's IP address
PORT = 6969                # Should match the server's port

TwLoadDll()

client_socket = None
socket_open = False

def check_socket_open():
    global client_socket, socket_open
    if not client_socket or not socket_open:
        context = zmq.Context()
        client_socket = context.socket(zmq.PUSH)  # Request socket
        open_str = 'tcp://'+HOST+':'+str(PORT)
        try:
            client_socket.connect(open_str)
            socket_open = True
            print('Socket opened')
        except Exception as e:
            socket_open = False
    return socket_open


def process_engineering_codes(codes):
    urls = []
    cans = {}
    for code in codes:
        urls.append('http://localhost/cgi-bin/readsdo?' + code['CAN'])
        cans[code['CAN']] = code['name']
    return urls, cans

def get_MS_from_VOCUS():
    msDict = {}
    smd = TSharedMemoryDesc()
    smp = TSharedMemoryPointer()
    timeout = 2000 # ms
    retval = TwWaitForNewData(timeout, smd, smp, True)
    if retval == TwSuccess:
        spectrum = np.zeros(shape = (smd.nbrPeaks),dtype = np.float32)
        masses = np.zeros(shape = (smd.nbrPeaks),dtype = np.float32)
        segmentIndex = np.int64(0)  # There is only one segment in our configuration
        segmentEndIndex = np.int64(0) 
        bufIndex  = np.int64((smd.totalBufsProcessed - 1) % smd.nbrBufs)
        retval == TwGetStickSpectrumFromShMem(spectrum, masses, segmentIndex, segmentEndIndex, bufIndex)
        if retval == TwSuccess:
            msDict = {float(mass): float(intensity) for mass, intensity in zip(masses, spectrum)}
    return msDict
    
async def get(url, session):
    try:
        async with session.get(url) as response:
            if response.status == 200:
                text = await response.text()
                print(f"Successfully got url {url} with resp of length {len(text)}.")
                return json.loads(text)
            else:
                print(f"Failed to get url {url} with status {response.status}.")
                return None
    except Exception as e:
        print("Unable to get url {} due to {}: {}.".format(url, e.__class__, str(e)))
        return None
    
async def main(urls,cans):
    eng_working = False
    replies = []
    async with aiohttp.ClientSession() as session:
        while True:
            if TwTofDaqRunning() == False:
                print('TofDaq recorder application is not running')
            else:
                print('TofDaq recorder application is running')
                if TwDaqActive() == False:
                    print('No active acquisition')
                    time.sleep(1)
                else:
                    eng_vals = {}
                    ms = {}
                    start = time.time()
                    if check_socket_open():
                        if not eng_working:
                            tasks = [asyncio.create_task(get(url, session)) for url in urls]
                            eng_working = True
                            replies = []
                        await asyncio.sleep(0.5)
                        ms = get_MS_from_VOCUS()
                        #async with aiohttp.ClientSession() as session:
                        #    ret = await asyncio.gather(*(get(url, session) for url in urls))
                        for task in tasks[:]:
                            if task.done():
                                try:
                                    result = task.result()
                                    if result:
                                        print(f"Task completed with result of length {len(result)}.")
                                        replies.append(result)
                                    else:
                                        print("Task completed with no result.")
                                except Exception as e:
                                    print(f"Task failed with exception: {e}")
                                tasks.remove(task)
                        if not tasks:
                            eng_working = False
                        messageDict = {'ms':ms}
                        if not eng_working:
                            for reply in replies:
                                if reply:
                                    eng_vals[cans[reply[0]['CAN']]] = reply[0]['VAL']
                            if eng_vals:
                                messageDict['eng'] = eng_vals
                            replies = []
                        message = pickle.dumps(messageDict)
                        try:
                            client_socket.send(message)
                            print(str(messageDict))
                        except Exception as e:
                            print('Error: socket will not send, '+str(e))
                            client_socket.close()
                            socket_open = False
                    else:
                        print('No socket connection with '+str(HOST)+' port '+str(PORT))
                        time.sleep(1)
                end = time.time()
                print("Took {} seconds to pull {} websites and get mass spec.".format(end - start, len(eng_codes)))

urls,cans = process_engineering_codes(eng_codes)

asyncio.run(main(urls,cans))


