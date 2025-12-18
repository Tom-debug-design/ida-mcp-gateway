from flask import Flask, jsonify
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)

# -------------------------------------------------
# Root health check
# -------------------------------------------------
@app.route("/", methods=["GET"])
def root():
    return jsonify({
        "message": "IDA MCP Gateway alive 🟢",
        "service": "ida-mcp-gateway",
        "status": "ok"
    })

# -------------------------------------------------
# SSE endpoint (Agent Builder needs this)
# -------------------------------------------------
@app.route("/sse", methods=["GET"])
def sse():
    def stream():
        yield "event: ready\ndata: ok\n\n"
    return app.response_class(stream(), mimetype="text/event-stream")

# -------------------------------------------------
# MCP manifest
# -------------------------------------------------
@app.route("/.well-known/mcp.json", methods=["GET"])
def mcp_manifest():
    return jsonify({
        "name": "ida-mcp-gateway",
        "version": "1.0.0",
        "description": "Custom MCP gateway for IDA (Render hosted)",
        "tools": {
            "ping": {
                "description": "Health check to verify IDA MCP connectivity",
                "input_schema": {
                    "type": "object",
                    "properties": {}
                }
            }
        }
    })

# -------------------------------------------------
# MCP tool: ping
# -------------------------------------------------
@app.route("/mcp/ping", methods=["POST"])
def mcp_ping():
    return jsonify({
        "ok": True,
        "tool": "ping",
        "message": "Ping received by IDA MCP Gateway",
        "service": "ida-mcp-gateway"
    })

# -------------------------------------------------
# Render entrypoint
# -------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
