import os
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

SERVER_NAME = "ida-mcp-gateway"
SERVER_VERSION = "1.0.0"

def base_url() -> str:
    # Render setter vanligvis ikke en perfekt base-url env, så vi bygger fra request
    # når vi trenger det (i manifest-endpoint).
    return ""

@app.get("/")
def root():
    return jsonify({
        "message": "IDA MCP Gateway alive ✅",
        "service": SERVER_NAME,
        "status": "ok"
    })

@app.get("/health")
def health():
    return "ok", 200

# --- MCP Manifest (Agent Builder leter ofte etter denne) ---
@app.get("/.well-known/mcp.json")
def mcp_manifest():
    # Pek manifestet til HTTP endpointet vårt
    # (Agent Builder/klienter bruker dette for å forstå hvor MCP calls skal gå)
    host = request.host_url.rstrip("/")
    return jsonify({
        "name": SERVER_NAME,
        "version": SERVER_VERSION,
        "description": "Custom MCP gateway for IDA (Render hosted)",
        "transport": {
            "type": "http",
            "url": f"{host}/mcp"
        }
    })

# --- MCP over HTTP (JSON-RPC) ---
@app.post("/mcp")
def mcp_http():
    payload = request.get_json(silent=True) or {}

    # MCP er i praksis JSON-RPC 2.0-stil
    rpc_id = payload.get("id", None)
    method = payload.get("method", "")
    params = payload.get("params", {}) or {}

    def ok(result):
        return jsonify({"jsonrpc": "2.0", "id": rpc_id, "result": result})

    def err(code, message):
        return jsonify({"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}), 200

    if method == "initialize":
        return ok({
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "capabilities": {"tools": {}}
        })

    if method == "tools/list":
        return ok({
            "tools": [
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
        })

    if method == "tools/call":
        tool_name = params.get("name")
        if tool_name != "ping":
            return err(-32601, f"Unknown tool: {tool_name}")

        return ok({
            "content": [
                {"type": "text", "text": "pong ✅ (from ida-mcp-gateway)"}
            ]
        })

    # Hvis Agent Builder prøver noe annet først, gi tydelig feil men 200 OK (mange MCP-klienter forventer det)
    return err(-32601, f"Method not found: {method}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
