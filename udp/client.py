import socket
import struct
import sys
import time

if len(sys.argv) < 3:
    print("usage: client.py <dest_ip> <port> [count] [timeout_s]")
    sys.exit(1)

dest = (sys.argv[1], int(sys.argv[2]))
count = int(sys.argv[3]) if len(sys.argv) > 3 else 20
timeout = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(timeout)

FMT = "!Id" 
SIZE = struct.calcsize(FMT)
rtts = []
lost = 0

for seq in range(count):
    sent_at = time.perf_counter()
    s.sendto(struct.pack(FMT, seq, sent_at), dest)
    try:
        while True:
            data, _ = s.recvfrom(2048)
            rseq, _ = struct.unpack(FMT, data[:SIZE])
            if rseq == seq: 
                break
        rtt_ms = (time.perf_counter() - sent_at) * 1000
        rtts.append(rtt_ms)
        print(f"seq={seq} rtt={rtt_ms:.3f} ms")
    except socket.timeout:
        lost += 1
        print(f"seq={seq} LOST")
    time.sleep(0.1)

s.close()

print("\n--- summary ---")
print(f"sent={count} received={len(rtts)} loss={100 * lost / count:.1f}%")
if rtts:
    print(f"rtt min/avg/max = {min(rtts):.3f}/{sum(rtts)/len(rtts):.3f}/{max(rtts):.3f} ms")
