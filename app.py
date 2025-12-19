from flask import Flask, request, jsonify

app = Flask(__name__)

# ---------------------------
# MCP TOOL REGISTRY
# ---------------------------
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

# ---------------------------
# TOOL EXECUTION
# ---------------------------
def call_tool(name: str, arguments: dict):
    if name == "ping":
        return {
            "content": [
                {"type": "text", "text": "pong 🟢 MCP alive"}
            ]
        }

    return {
        "content": [
            {"type": "text", "text": f"Unknown tool: {name}"}
        ]
    }

# ---------------------------
# MCP DISCOVERY (BUILDER NEEDS THIS)
# ---------------------------
@app.get("/mcp")
def mcp_discovery():
    return jsonify({
        "tools": TOOLS
    })

# ---------------------------
# MCP RPC ENDPOINT
# ---------------------------
@app.post("/mcp")
def mcp_rpc():
    payload = request.get_json(force=True)
    rpc_id = payload.get("id")
    method = payload.get("method")

    if method == "tools/list":
        return jsonify({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "tools": TOOLS
            }
        })

    if method == "tools/call":
        params = payload.get("params", {})
        name = params.get("name")
        arguments = params.get("arguments", {})
        result = call_tool(name, arguments)

        return jsonify({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": result
        })

    return jsonify({
        "jsonrpc": "2.0",
        "id": rpc_id,
        "error": {
            "code": -32601,
            "message": f"Method not found: {method}"
        }
    })

# ---------------------------
# HEALTH ROOT
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
# BOOT
# ---------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
