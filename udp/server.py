import socket
import struct
import sys

talk = "-v" in sys.argv
port = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] != "-v" else 5000

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("0.0.0.0", port))
print(f"Echo server listening on UDP port {port}", flush=True)

while True:
    data, addr = s.recvfrom(2048)
    if talk and len(data) >= 12:
        seq, _ = struct.unpack("!Id", data[:12])
        print(f"probe seq={seq} from {addr[0]}:{addr[1]}", flush=True)
    s.sendto(data, addr)