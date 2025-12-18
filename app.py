from flask import Flask, jsonify, request
import os

app = Flask(__name__)

# =========================================================
# Basic health check (browser / Render sanity check)
# =========================================================
@app.route("/", methods=["GET"])
def root():
    return jsonify({
        "message": "IDA is alive 🟢",
        "service": "ida-mcp-gateway",
        "status": "ok"
    })


# =========================================================
# MCP MANIFEST
# This is what Agent Builder / MCP looks for
# =========================================================
@app.route("/.well-known/mcp.json", methods=["GET"])
def mcp_manifest():
    return jsonify({
        "name": "ida-mcp-gateway",
        "description": "Custom MCP gateway for IDA (Render hosted)",
        "version": "1.0.0",
        "tools": {
            "ping": {
                "description": "Health check to verify IDA ↔ MCP connectivity",
                "input_schema": {
                    "type": "object",
                    "properties": {}
                }
            }
        }
    })


# =========================================================
# MCP TOOL: ping
# =========================================================
@app.route("/mcp/ping", methods=["POST"])
def mcp_ping():
    return jsonify({
        "ok": True,
        "tool": "ping",
        "message": "Ping received by IDA MCP Gateway",
        "service": "ida-mcp-gateway"
    })


# =========================================================
# Render entrypoint
# =========================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
