from flask import Flask, request, jsonify

app = Flask(__name__)

# --- Minimal tool registry (start med 1 tool: ping) ---
TOOLS = [
    {
        "name": "ping",
        "description": "Health check to verify MCP connectivity",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        },
    }
]

def call_tool(name: str, arguments: dict):
    if name == "ping":
        return {
            "content": [
                {"type": "text", "text": "pong ✅ (from ida-mcp-gateway)"}
            ]
        }
    return {
        "content": [
            {"type": "text", "text": f"Unknown tool: {name}"}
        ]
    }

@app.get("/")
def root():
    return jsonify({
        "message": "IDA MCP Gateway alive ✅",
        "service": "ida-mcp-gateway",
        "tools_loaded": len(TOOLS),
        "version": "1.0.0"
    })

# --- MCP endpoint (JSON-RPC) ---
@app.post("/mcp")
@app.post("/mcp/")  # tåler begge
def mcp():
    payload = request.get_json(silent=True) or {}
    method = payload.get("method")
    rpc_id = payload.get("id")

    # tools/list
    if method == "tools/list":
        return jsonify({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {"tools": TOOLS}
        })

    # tools/call
    if method == "tools/call":
        params = payload.get("params") or {}
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
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
