import os
import sys
import time
import shutil
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

def is_host_available(host, port, ssh_client, private_key, timeout=5):
    """Check if the stationary host is reachable via SSH."""
    try:
        ssh_client.connect(
            hostname=config['STATIONARY_HOST'],
            port=config['SSH_PORT'],
            username=config['USERNAME'],
            pkey=private_key
        )
        ssh_client.close()
        return True
    except Exception as e:
        print(f"An error occurred: {e}")
        return False

def transfer_files(ssh_client, private_key):
    """Transfer new files to the stationary host and archive them."""
    # Establish SFTP connection
    try:
        ssh_client.connect(
            hostname=config['STATIONARY_HOST'],
            port=config['SSH_PORT'],
            username=config['USERNAME'],
            pkey=private_key
        )
        sftp_client = ssh_client.open_sftp()

        for file in Path(config['DATA_DIR']).glob(config['SUBMIT_FILE_PATTERN']):
            if file.is_file():
                try:
                    remote_path = config['REMOTE_PATH'] +file.name # Adjust remote path as needed
                    sftp_client.put(str(file), remote_path)
                    print(f"Transferred: {file}")
                    shutil.move(str(file), os.path.join(config['ARCHIVE_DIR'], file.name))
                except Exception as e:
                    print(f"Failed to transfer {file}: {e}")
        sftp_client.close()
        ssh_client.close()
    except Exception as e:
        print(f"Error in SFTP connection: {e}")


    except Exception as e:
        print(f"Error in SFTP connection: {e}")

def main():
    """Main loop to repeatedly check network and host availability and transfer files."""
    private_key = paramiko.RSAKey.from_private_key_file(config['PRIVATE_KEY_PATH'])
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    while True:
        if is_network_available(host = config['PING_HOST']):
            print("Network is available.")
            if is_host_available(config['STATIONARY_HOST'], config['SSH_PORT'], ssh_client, private_key):
                print(f"Host {config['STATIONARY_HOST']} is reachable. Transferring files...")
                transfer_files(ssh_client, private_key)
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
