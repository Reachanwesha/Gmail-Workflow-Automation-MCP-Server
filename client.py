import socket

host= '127.0.0.1'
port= 8000

with socket.create_connection((host,port)) as sock:
    sock.sendall(b"get_emails")
    response= sock.recv(10000)
    print("Received: \n", response.decode())