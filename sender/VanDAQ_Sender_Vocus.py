import sys
import time
import numpy as np
import socket
import pickle

sys.path.append('C:\\Users\\TofUser\\Documents\\TOFDaq API\\TofDaq_1.99r759_API_20180912\\src\\Python')
print(sys.path)
from TofDaq import *

# Define the IP and port of the server to connect to
HOST = '169.229.157.5'     # Replace with the server's IP address
PORT = 6969                # Should match the server's port

TwLoadDll()

client_socket = None
socket_open = False

def check_socket_open():
    global client_socket, socket_open
    if not client_socket or not socket_open:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            client_socket.connect((HOST, PORT))
            socket_open = True
            print('Socket opened')
        except Exception as e:
            socket_open = False
    return socket_open



while True:
    if TwTofDaqRunning() == False:
        print('TofDaq recorder application is not running')
    else:
        print('TofDaq recorder application is running')
        if TwDaqActive() == False:
            print('No active acquisition')
            time.sleep(1)
        else:
            print('Acquisition active')
            if check_socket_open():
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
                        messageDict = {'ms':msDict}
                        message = pickle.dumps(messageDict)
                        message_length = len(message)
                        print('size of message: '+str(len(message)))
                        try:
                            client_socket.sendall(message_length.to_bytes(4, 'big'))
                            client_socket.sendall(message)
                            print(str(msDict))
                        except Exception as e:
                            print('Error: socket will not send, '+str(e))
                            client_socket.close()
                            socket_open = False

            else:
                print('No socket connection with '+str(HOST)+' port '+str(PORT))
                time.sleep(1)





