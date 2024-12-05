import os
import sys
import time
import socket
import shutil
import keyring
import yaml
import paramiko
import subprocess
from pathlib import Path

config = {}

def load_config_file(filename):
	try:
		configfile = open(filename)
		config = yaml.load(configfile, Loader=yaml.FullLoader)
		configfile.close()
		return config
	except:
		print("Cannot load config file "+sys.argv[1])
		return None

def is_network_available(host = '0.0.0.0', timeout=2):
    """Check if the network is available by pinging a public server."""
    try:
        subprocess.check_call(["ping", "-c", "1", "-W", str(timeout), host],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False

def is_host_available(host, port, timeout=5):
    """Check if the stationary host is reachable via SSH."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except (socket.timeout, socket.error):
            return False

def transfer_files():
    """Transfer new files to the stationary host and archive them."""
    # Establish SFTP connection
    try:
        transport = paramiko.Transport((config['STATIONARY_HOST'], config['SSH_PORT']))
        uname = keyring.get_password(config['KEYRING_HOST_KEY'],'username')
        pw = keyring.get_password(config['KEYRING_HOST_KEY'],'password')
        transport.connect(username=uname, password=pw)
        sftp = paramiko.SFTPClient.from_transport(transport)

        for file in Path(config['DATA_DIR']).glob(config['SUBMIT_FILE_PATTERN']):
            if file.is_file():
                try:
                    remote_path = config['REMOTE_PATH'] +file.name # Adjust remote path as needed
                    sftp.put(str(file), remote_path)
                    print(f"Transferred: {file}")
                    shutil.move(str(file), os.path.join(config['ARCHIVE_DIR'], file.name))
                except Exception as e:
                    print(f"Failed to transfer {file}: {e}")
        sftp.close()
        transport.close()
    except Exception as e:
        print(f"Error in SFTP connection: {e}")

def transfer_files_2():
    """Transfer new files to the stationary host and archive them."""
    # Establish SFTP connection
    try:
        uname = keyring.get_password(config['KEYRING_HOST_KEY'],'username')
        pw = keyring.get_password(config['KEYRING_HOST_KEY'],'password')
        conn = Connection(host='hostname', user=uname, connect_kwargs={"password": pw})
 
        for file in Path(config['DATA_DIR']).glob(config['SUBMIT_FILE_PATTERN']):
            if file.is_file():
                try:
                    remote_path = config['REMOTE_PATH'] +file.name # Adjust remote path as needed
                    conn.put(str(file), remote=remote_path)
                    print(f"Transferred: {file}")
                    shutil.move(str(file), os.path.join(config['ARCHIVE_DIR'], file.name))
                except Exception as e:
                    print(f"Failed to transfer {file}: {e}")
        conn.close()

    except Exception as e:
        print(f"Error in SFTP connection: {e}")

def main():
    """Main loop to repeatedly check network and host availability and transfer files."""
    while True:
        if is_network_available(host = config['PING_HOST']):
            print("Network is available.")
            if is_host_available(config['STATIONARY_HOST'], config['SSH_PORT']):
                print(f"Host {config['STATIONARY_HOST']} is reachable. Transferring files...")
                transfer_files()
            else:
                print(f"Host {config['STATIONARY_HOST']} is not reachable.")
        else:
            print("Network is unavailable.")
        time.sleep(config['CHECK_INTERVAL'])

config_file_name = '/home/vandaq/vandaq/submitter/vandaq_submitter.yaml'


if len(sys.argv) > 1:
    config_file_name = sys.argv[1]    

config = load_config_file(config_file_name)

# Ensure archive directory exists
os.makedirs(config['ARCHIVE_DIR'], exist_ok=True)


if __name__ == "__main__":
    main()
