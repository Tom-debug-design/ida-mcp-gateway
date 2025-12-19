import os
import glob
import importlib.util
from typing import Dict, Any, Callable, Tuple, Optional

from flask import Flask, jsonify, request
from flask_cors import CORS

APP_NAME = "ida-mcp-gateway"
APP_VERSION = "1.0.0"

app = Flask(__name__)
CORS(app)

# ----------------------------
# Tool loading (AUTO)
# ----------------------------
ToolSpec = Dict[str, Any]
ToolCallFn = Callable[[Dict[str, Any]], Dict[str, Any]]

TOOLS: Dict[str, ToolSpec] = {}     # name -> spec (name, description, inputSchema)
TOOL_CALLS: Dict[str, ToolCallFn] = {}  # name -> callable(args)->result

def load_tools_from_folder(folder: str = "tools") -> Tuple[int, int]:
    """
    Loads tools from ./tools/*.py.
    Each tool file must export:
      - TOOL (dict): {"name": str, "description": str, "inputSchema": {...}}
      - call(args: dict) -> dict  (returns MCP 'content' or your own structure)
    """
    loaded = 0
    failed = 0

    if not os.path.isdir(folder):
        return (0, 0)

    for path in sorted(glob.glob(os.path.join(folder, "*.py"))):
        filename = os.path.basename(path)
        if filename.startswith("_"):
            continue

        module_name = f"tool_{os.path.splitext(filename)[0]}"

        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if not spec or not spec.loader:
                failed += 1
                continue

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore

            tool: Optional[dict] = getattr(module, "TOOL", None)
            call_fn: Optional[Callable] = getattr(module, "call", None)

            if not isinstance(tool, dict) or not callable(call_fn):
                failed += 1
                continue

            name = tool.get("name")
            desc = tool.get("description", "")
            schema = tool.get("inputSchema", {"type": "object", "properties": {}})

            if not isinstance(name, str) or not name.strip():
                failed += 1
                continue

            TOOLS[name] = {
                "name": name,
                "description": desc,
                "inputSchema": schema,
            }
            TOOL_CALLS[name] = call_fn
            loaded += 1

        except Exception:
            failed += 1

    return (loaded, failed)

# Load tools at boot
_loaded, _failed = load_tools_from_folder("tools")

# ----------------------------
# Basic endpoints
# ----------------------------
@app.get("/")
def root():
    return jsonify({
        "message": "IDA MCP Gateway alive ✅",
        "service": APP_NAME,
        "version": APP_VERSION,
        "tools_loaded": len(TOOLS)
    })

@app.get("/.well-known/mcp.json")
def mcp_manifest():
    host = request.host_url.rstrip("/")
    # Minimal manifest-like info (Agent Builder may use /mcp directly anyway)
    return jsonify({
        "name": APP_NAME,
        "version": APP_VERSION,
        "description": "Custom MCP gateway for IDA (Render hosted)",
        "transport": {"type": "http", "url": f"{host}/mcp"}
    })

# ----------------------------
# MCP JSON-RPC over HTTP
# Endpoint: POST /mcp
# ----------------------------
@app.post("/mcp")
def mcp_http():
    payload = request.get_json(silent=True) or {}

    rpc_id = payload.get("id", None)
    method = payload.get("method", "")
    params = payload.get("params", {}) or {}

    def ok(result: Any):
        return jsonify({"jsonrpc": "2.0", "id": rpc_id, "result": result})

    def err(code: int, message: str):
        # MCP/JSON-RPC clients often expect HTTP 200 even on errors
        return jsonify({"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}), 200

    if method == "initialize":
        return ok({
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": APP_NAME, "version": APP_VERSION},
            "capabilities": {"tools": {"listChanged": False}}
        })

    if method == "tools/list":
        return ok({"tools": list(TOOLS.values())})

    if method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {}) or {}

        if tool_name not in TOOL_CALLS:
            return err(-32601, f"Unknown tool: {tool_name}")

        try:
            result = TOOL_CALLS[tool_name](args)

            # MCP expects something like: {"content":[{"type":"text","text":"..."}]}
            # We'll normalize if the tool returns plain text.
            if isinstance(result, str):
                result = {"content": [{"type": "text", "text": result}]}
            elif isinstance(result, dict) and "content" not in result:
                # If tool returns dict without MCP content, wrap it.
                result = {"content": [{"type": "text", "text": jsonify(result).get_data(as_text=True)}]}

            return ok(result)
        except Exception as e:
            return err(-32000, f"Tool error: {str(e)}")

    return err(-32601, f"Method not found: {method}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
