from flask import Flask, request, jsonify, make_response

app = Flask(__name__)

# ---------------------------
# TOOL REGISTRY (keep simple)
# ---------------------------
TOOLS = [
    {
        "name": "ping",
        "description": "Health check to verify MCP connectivity",
        # Builder/clients varierer litt på key-navn, så vi gir begge:
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    }
]

# ---------------------------
# CORS (THIS IS THE USUAL CULPRIT)
# ---------------------------
@app.after_request
def add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Max-Age"] = "86400"
    return resp

def ok_no_content():
    return ("", 204)

# ---------------------------
# TOOL EXECUTION
# ---------------------------
def call_tool(name: str, arguments: dict):
    if name == "ping":
        return {"content": [{"type": "text", "text": "pong 🟢 MCP alive"}]}
    return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}]}

# ---------------------------
# ROOT HEALTH
# ---------------------------
@app.get("/")
def root():
    return jsonify({
        "message": "IDA MCP Gateway alive ✅",
        "service": "ida-mcp-gateway",
        "tools_loaded": len(TOOLS),
        "version": "1.0.0"
    })

# ---------------------------
# DISCOVERY (some clients use this)
# ---------------------------
@app.route("/.well-known/mcp.json", methods=["GET", "OPTIONS"])
def well_known_mcp():
    if request.method == "OPTIONS":
        return ok_no_content()
    return jsonify({"tools": TOOLS})

@app.route("/mcp", methods=["GET", "POST", "OPTIONS"])
def mcp():
    # Preflight
    if request.method == "OPTIONS":
        return ok_no_content()

    # Discovery via GET
    if request.method == "GET":
        return jsonify({"tools": TOOLS})

    # JSON-RPC via POST
    payload = request.get_json(force=True, silent=True) or {}
    rpc_id = payload.get("id")
    method = payload.get("method")

    # tools/list
    if method in ("tools/list", "list_tools"):
        return jsonify({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {"tools": TOOLS}
        })

    # tools/call
    if method in ("tools/call", "call_tool"):
        params = payload.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        result = call_tool(name, arguments)

        return jsonify({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": result
        })

    # Fallback
    return jsonify({
        "jsonrpc": "2.0",
        "id": rpc_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"}
    })

# ---------------------------
# BOOT
# ---------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
