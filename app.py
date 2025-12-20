from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import os
import time

app = Flask(__name__)
CORS(app)

# ----------------------------
# Tool registry (what MCP sees)
# ----------------------------
TOOLS = [
    {
        "name": "ping",
        "description": "Health check to verify MCP connectivity",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    },
    {
        "name": "github_whoami",
        "description": "Verify GitHub token works by returning the authenticated user login",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    }
]

# ----------------------------
# Tool execution router
# ----------------------------
def call_tool(name: str, arguments: dict) -> dict:
    # Keep these imports inside to avoid import-time crashes if file missing
    if name == "ping":
        try:
            from tools.ping import run as ping_run
            return ping_run(arguments or {})
        except Exception as e:
            return {"ok": False, "error": f"ping tool error: {str(e)}"}

    if name == "github_whoami":
        try:
            from tools.github_whoami import run as whoami_run
            return whoami_run(arguments or {})
        except Exception as e:
            return {"ok": False, "error": f"github_whoami tool error: {str(e)}"}

    return {"ok": False, "error": f"Unknown tool: {name}"}

# ----------------------------
# Basic health
# ----------------------------
@app.get("/")
def root():
    return jsonify({
        "message": "IDA MCP Gateway alive ✅",
        "service": "ida-mcp-gateway",
        "tools_loaded": len(TOOLS),
        "version": "1.2.0"
    })

# ----------------------------
# MCP over HTTP (JSON-RPC)
# ----------------------------
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
                    "version": "1.2.0"
                }
            }
        })

    # MCP tools/list
    if method == "tools/list":
        return jsonify({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {"tools": TOOLS}
        })

    # MCP tools/call
    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        result = call_tool(tool_name, arguments)
        return jsonify({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": result
        })

    # Fallback
    return jsonify({
        "jsonrpc": "2.0",
        "id": rpc_id,
        "error": {
            "code": -32601,
            "message": f"Method not found: {method}"
        }
    })

# ----------------------------
# MCP over SSE (streaming keepalive)
# ----------------------------
@app.get("/mcp/sse")
def mcp_sse():
    def stream():
        # Minimal SSE "ready" + periodic keepalive
        yield 'event: ready\ndata: {"status":"ok"}\n\n'
        while True:
            yield f'event: ping\ndata: {{"t":{int(time.time())}}}\n\n'
            time.sleep(15)

    return Response(stream(), mimetype="text/event-stream")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
