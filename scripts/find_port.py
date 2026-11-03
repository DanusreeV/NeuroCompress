"""Print the first free TCP port >= the given start port (default 8000)."""
import socket
import sys

start = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
for port in range(start, start + 200):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            continue
        print(port)
        break
else:
    sys.exit("no free port found")
