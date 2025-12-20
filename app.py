from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import importlib.util
import os
import time
import traceback

APP_VERSION = "1.3.0"

app = Flask(__name__)
CORS(app)

# ---------------------------
# Tool loader
# ---------------------------

def load_tools(tools_dir: str = "tools"):
    """
    Auto-load MCP tools from tools/*.py
    Each tool file must define:
      - TOOL_SPEC: dict  (must include "name", "description", "inputSchema")
      - run(args: dict) -> dict or list or str
    """
    loaded = {}
    abs_dir = os.path.join(os.path.dirname(__file__), tools_dir)

    if not os.path.isdir(abs_dir):
        return loaded

    for fname in os.listdir(abs_dir):
        if not fname.endswith(".py"):
            continue
        if fname.startswith("_"):
            continue

        path = os.path.join(abs_dir, fname)
        mod_name = f"{tools_dir}.{fname[:-3]}"

        try:
            spec = importlib.util.spec_from_file_location(mod_name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore

            tool_spec = getattr(module, "TOOL_SPEC", None)
            tool_run = getattr(module, "run", None)

            if not isinstance(tool_spec, dict):
                continue
            if not callable(tool_run):
                continue
            if "name" not in tool_spec:
                continue

            loaded[tool_spec["name"]] = {
                "spec": tool_spec,
                "run": tool_run,
                "file": fname,
            }
        except Exception:
            # Don't crash service if one tool is broken
            print(f"[TOOL-LOAD-ERROR] {fname}\n{traceback.format_exc()}")

    return loaded


TOOLS_REGISTRY = load_tools("tools")


def tools_list():
    # MCP tools/list expects an array of tool specs
    return [TOOLS_REGISTRY[name]["spec"] for name in sorted(TOOLS_REGISTRY.keys())]


def call_tool(name: str, arguments: dict):
    tool = TOOLS_REGISTRY.get(name)
    if not tool:
        return {
            "content": [{"type": "text", "text": f"Unknown tool: {name}"}]
        }

    try:
        result = tool["run"](arguments or {})
        # Normalize result to MCP "content" format if it's not already
        if isinstance(result, dict) and "content" in result:
            return result

        if isinstance(result, (dict, list)):
            return {"content": [{"type": "text", "text": str(result)}]}

        return {"content": [{"type": "text", "text": str(result)}]}
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Tool error: {name} -> {e}"}]
        }


# ---------------------------
# Basic health
# ---------------------------

@app.get("/")
def root():
    return jsonify({
        "message": "IDA MCP Gateway alive ✅",
        "service": "ida-mcp-gateway",
        "tools_loaded": len(TOOLS_REGISTRY),
        "version": APP_VERSION
    })


# ---------------------------
# MCP over HTTP (JSON-RPC)
# ---------------------------

@app.route("/mcp", methods=["GET", "POST"])
def mcp_http():
    # Non-standard but common: clients do GET to discover tools
    if request.method == "GET":
        return jsonify(tools_list())

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
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ida-mcp-gateway", "version": APP_VERSION}
            }
        })

    if method == "tools/list":
        return jsonify({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {"tools": tools_list()}
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
        "error": {"code": -32601, "message": f"Method not found: {method}"}
    })


# ---------------------------
# MCP over SSE (basic streaming keepalive)
# ---------------------------

@app.get("/mcp/sse")
def mcp_sse():
    def stream():
        # minimal "ready" + periodic keepalive
        yield 'event: ready\ndata: {"status":"ok"}\n\n'
        while True:
            yield f'event: ping\ndata: {{"t":{int(time.time())}}}\n\n'
            time.sleep(15)

    return Response(stream(), mimetype="text/event-stream")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
