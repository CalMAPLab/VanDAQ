import paramiko
import socket
import time
from datetime import datetime

# Remote server details
REMOTE_SERVER = "169.229.157.7"
SSH_PORT = 2025  # Replace with the actual SSH port
USERNAME = "vandaq"  # Replace with the username
PRIVATE_KEY_PATH = "/home/vandaq/.ssh/vandaq_central"  # Path to your SSH private key
REMOTE_FILE = "/home/vandaq/tattle.txt"  # Remote file to append data


def log_client_info():
    try:
        # Initialize SSH key
        private_key = paramiko.RSAKey.from_private_key_file(PRIVATE_KEY_PATH)
        
        # Create an SSH client
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Connect to the remote server
        print(f"Connecting to {REMOTE_SERVER} on port {SSH_PORT}...")
        ssh_client.connect(
            hostname=REMOTE_SERVER,
            port=SSH_PORT,
            username=USERNAME,
            pkey=private_key
        )
        print("Connected successfully.")

        # Get the current timestamp
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Construct the remote command
        command = f"""
            echo '{current_time} - '$SSH_CLIENT >> {REMOTE_FILE}
        """
        print(f"Executing command: {command.strip()}")

        # Execute the command on the remote server
        stdin, stdout, stderr = ssh_client.exec_command(command)

        # Handle output and errors
        stdout_output = stdout.read().decode().strip()
        stderr_output = stderr.read().decode().strip()
        if stdout_output:
            print(f"Command output: {stdout_output}")
        if stderr_output:
            print(f"Command error: {stderr_output}")

        # Close the SSH connection
        ssh_client.close()
        print("Connection closed.")
    except Exception as e:
        print(f"An error occurred: {e}")



if __name__ == "__main__":
    while True:
        log_client_info()
        time.sleep(60)
