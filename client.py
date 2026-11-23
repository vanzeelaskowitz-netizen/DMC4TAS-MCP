"""One authenticated loopback request; probe batches all candidates in that request."""
import json
import os
from pathlib import Path
import socket


def call(command, **args):
    root = Path(os.environ["DMC4TAS_ROOT"])
    info = json.loads((root / "logs/tas-service.json").read_text(encoding="utf-8"))
    request = {"token": info["token"], "command": command, "args": args}
    with socket.create_connection(("127.0.0.1", info["port"]), timeout=3) as conn:
        conn.settimeout(600 if command == "probe" else 120)
        conn.sendall(json.dumps(request).encode() + b"\n")
        with conn.makefile("rb") as stream:
            line = stream.readline()
    if not line:
        raise ConnectionError(f"TAS closed {command} without replying")
    reply = json.loads(line)
    if "error" in reply:
        raise RuntimeError(reply["error"])
    return reply["result"]
