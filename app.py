from flask import Flask, request, jsonify, make_response

app = Flask(__name__)

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

def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    resp.headers["Access-Control-Max-Age"] = "86400"
    return resp

@app.route("/", methods=["GET"])
def root():
    resp = jsonify({
        "message": "IDA MCP Gateway alive ✅",
        "service": "ida-mcp-gateway",
        "tools_loaded": len(TOOLS),
        "version": "1.0.0"
    })
    return add_cors(resp)

@app.route("/health", methods=["GET"])
def health():
    resp = jsonify({"ok": True, "tools_loaded": len(TOOLS)})
    return add_cors(resp)

@app.route("/mcp", methods=["GET", "POST", "OPTIONS"])
def mcp():
    # Preflight
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    # Tool discovery
    if request.method == "GET":
        resp = jsonify({"tools": TOOLS})
        return add_cors(resp)

    # JSON-RPC tool calling
    payload = request.get_json(silent=True) or {}
    rpc_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}

    if method == "tools/list":
        resp = jsonify({"jsonrpc": "2.0", "id": rpc_id, "result": {"tools": TOOLS}})
        return add_cors(resp)

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}

        if name == "ping":
            result = {"content": [{"type": "text", "text": "pong ✅"}]}
            resp = jsonify({"jsonrpc": "2.0", "id": rpc_id, "result": result})
            return add_cors(resp)

        resp = jsonify({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32601, "message": f"Unknown tool: {name}"}
        })
        return add_cors(resp), 200

    # Fallback for unknown methods
    resp = jsonify({
        "jsonrpc": "2.0",
        "id": rpc_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"}
    })
    return add_cors(resp), 200

if __name__ == "__main__":
    # Render uses PORT env var; fallback to 10000 for local
    import os
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
