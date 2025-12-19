from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import json
import os
import time

app = Flask(__name__)
CORS(app)

# -----------------------------
# Tool registry
# -----------------------------
TOOLS = [
    {
        "name": "ping",
        "description": "Health check to verify MCP connectivity",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    }
]

def call_tool(name: str, arguments: dict):
    if name == "ping":
        return {
            "content": [
                {"type": "text", "text": "pong ✅"}
            ]
        }
    return {
        "content": [
            {"type": "text", "text": f"Unknown tool: {name}"}
        ]
    }

# -----------------------------
# Basic health
# -----------------------------
@app.get("/")
def root():
    return jsonify({
        "message": "IDA MCP Gateway alive ✅",
        "service": "ida-mcp-gateway",
        "tools_loaded": len(TOOLS),
        "version": "1.1.0"
    })

# -----------------------------
# MCP over HTTP (JSON-RPC)
# -----------------------------
@app.route("/mcp", methods=["GET", "POST"])
def mcp_http():
    # Some clients do a GET to discover tools (non-standard but common)
    if request.method == "GET":
        return jsonify({"tools": TOOLS})

    payload = request.get_json(silent=True) or {}
    method = payload.get("method")
    params = payload.get("params") or {}
    rpc_id = payload.get("id")

    # MCP init handshake (clients may call initialize first)
    if method == "initialize":
        return jsonify({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "ida-mcp-gateway",
                    "version": "1.1.0"
                }
            }
        })

    if method == "tools/list":
        return jsonify({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "tools": TOOLS
            }
        })

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        result = call_tool(name, arguments)
        return jsonify({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": result
        })

    # fallback
    return jsonify({
        "jsonrpc": "2.0",
        "id": rpc_id,
        "error": {
            "code": -32601,
            "message": f"Method not found: {method}"
        }
    })

# -----------------------------
# MCP over SSE (for clients that require streaming)
# -----------------------------
@app.get("/mcp/sse")
def mcp_sse():
    def stream():
        # Minimal SSE "hello" + periodic keepalive
        yield "event: ready\ndata: {\"status\":\"ok\"}\n\n"
        while True:
            yield "event: ping\ndata: {\"t\":%d}\n\n" % int(time.time())
            time.sleep(15)

    return Response(stream(), mimetype="text/event-stream")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
