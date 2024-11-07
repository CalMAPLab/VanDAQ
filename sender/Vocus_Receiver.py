import socket
import pickle

# Define the IP and port for the server
HOST = '0.0.0.0'  # 0.0.0.0 listens on all available interfaces
PORT = 6969      # Use any available port, just make sure it's the same on both ends
buffer_size = 16384

# Create a socket object and bind it to the IP and port
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
    server_socket.bind((HOST, PORT))
    server_socket.listen()
    print(f"Server listening on {HOST}:{PORT}")

    # Accept a connection
    conn, addr = server_socket.accept()
    with conn:
        print(f"Connected by {addr}")
        while True:
            # Receive data from the client
            length_data = conn.recv(4)
            if length_data:
                message_length = int.from_bytes(length_data, 'big')
                received_data = b""
                while len(received_data) < message_length:
                    chunk = conn.recv(1024)
                    if chunk:
                        received_data += chunk
                if len(received_data) == message_length:
                    message = pickle.loads(received_data)
                    print(f"Received from client: "+str(message))  # Decode and print data
