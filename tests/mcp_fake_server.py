"""
Fake MCP server used by tests/test_mcp_client.py.

Speaks JSON-RPC 2.0 over stdio using Content-Length framing (the MCP spec
framing). Run modes:

    python mcp_fake_server.py normal   # respond to initialize/tools/list/tools/call
    python mcp_fake_server.py newline  # respond using newline-delimited JSON (fallback path)
    python mcp_fake_server.py hang     # never respond (timeout path)
    python mcp_fake_server.py error    # respond with JSON-RPC errors
"""

import json
import os
import sys
import time

MODE = sys.argv[1] if len(sys.argv) > 1 else "normal"


def read_message():
    """Read one Content-Length framed (or newline) JSON message from stdin."""
    buf = b""
    while True:
        header_end = buf.find(b"\r\n\r\n")
        if header_end != -1:
            header = buf[:header_end].decode("utf-8", errors="replace")
            for line in header.split("\r\n"):
                if line.lower().startswith("content-length:"):
                    length = int(line.split(":", 1)[1].strip())
                    if len(buf) >= header_end + 4 + length:
                        body = buf[header_end + 4: header_end + 4 + length]
                        return json.loads(body.decode("utf-8"))
        # newline fallback (some clients send raw JSON lines)
        stripped = buf.lstrip()
        if stripped.startswith(b"{") and b"\n" in stripped:
            try:
                return json.loads(stripped[: stripped.index(b"\n")].decode("utf-8"))
            except json.JSONDecodeError:
                pass
        # Chunked read: frames have no trailing newline, so readline would block.
        # os.read on a pipe returns whatever is available (up to the size).
        chunk = os.read(sys.stdin.fileno(), 4096)
        if not chunk:
            return None
        buf += chunk


def send(message):
    """Send a JSON message using Content-Length framing."""
    data = json.dumps(message).encode("utf-8")
    sys.stdout.buffer.write(b"Content-Length: " + str(len(data)).encode("ascii") + b"\r\n\r\n" + data)
    sys.stdout.buffer.flush()


def send_newline(message):
    """Send a JSON message as a single newline-delimited line (fallback)."""
    sys.stdout.buffer.write(json.dumps(message).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def main():
    while True:
        msg = read_message()
        if msg is None:
            break
        method = msg.get("method")
        msg_id = msg.get("id")

        if MODE == "hang":
            time.sleep(3600)  # never respond — client must time out

        if method == "initialize":
            result = {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-mcp", "version": "1.0.0"},
            }
        elif method == "notifications/initialized":
            continue  # no response expected
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "echo_tool",
                        "description": "Echoes the text argument back",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"text": {"type": "string"}},
                            "required": ["text"],
                        },
                    }
                ]
            }
        elif method == "tools/call":
            args = msg.get("params", {}).get("arguments", {})
            if MODE == "error":
                send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32603, "message": "boom"}})
                continue
            result = {"content": [{"type": "text", "text": args.get("text", "")}]}
        else:
            send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "unknown method"}})
            continue

        if MODE == "newline":
            send_newline({"jsonrpc": "2.0", "id": msg_id, "result": result})
        else:
            send({"jsonrpc": "2.0", "id": msg_id, "result": result})


if __name__ == "__main__":
    main()
