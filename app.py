from flask import Flask, request, jsonify
import importlib
import pkgutil

app = Flask(__name__)

TOOLS = {}         # name -> module
TOOL_SPECS = []    # list of {"name","description","inputSchema"}


def load_tools():
    global TOOLS, TOOL_SPECS
    TOOLS = {}
    TOOL_SPECS = []

    # Auto-discover: ida_mcp_gateway/tools/*.py  (eller bare tools/*.py)
    # Vi prøver begge for å være robust uten mer drama.
    candidates = ["tools", "ida_mcp_gateway.tools"]

    for pkg_name in candidates:
        try:
            pkg = importlib.import_module(pkg_name)
        except Exception:
            continue

        for m in pkgutil.iter_modules(pkg.__path__):
            if m.ispkg:
                continue
            mod_name = f"{pkg_name}.{m.name}"
            try:
                mod = importlib.import_module(mod_name)
            except Exception:
                continue

            # Støtter begge varianter:
            # A) TOOL = {"name","description","inputSchema"} + call(args)
            # B) TOOL_NAME + TOOL_SPEC + run(args)
            name = None
            spec = None
            runner = None

            if hasattr(mod, "TOOL") and isinstance(getattr(mod, "TOOL"), dict):
                spec = getattr(mod, "TOOL")
                name = spec.get("name")
                runner = getattr(mod, "call", None)
            elif hasattr(mod, "TOOL_NAME") and hasattr(mod, "TOOL_SPEC"):
                name = getattr(mod, "TOOL_NAME")
                ts = getattr(mod, "TOOL_SPEC", {})
                spec = {
                    "name": name,
                    "description": ts.get("description", ""),
                    "inputSchema": ts.get("input_schema", {"type": "object", "properties": {}})
                }
                runner = getattr(mod, "run", None)

            if name and spec and callable(runner):
                TOOLS[name] = mod
                TOOL_SPECS.append({
                    "name": spec.get("name", name),
                    "description": spec.get("description", ""),
                    "inputSchema": spec.get("inputSchema", {"type": "object", "properties": {}})
                })


load_tools()


@app.get("/")
def health():
    return jsonify({
        "message": "IDA MCP Gateway alive ✅",
        "service": "ida-mcp-gateway",
        "tools_loaded": len(TOOLS),
        "version": "1.0.0"
    })


@app.post("/mcp")
def mcp_rpc():
    payload = request.get_json(silent=True) or {}
    method = payload.get("method")
    rpc_id = payload.get("id")

    try:
        if method == "tools/list":
            return jsonify({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {"tools": TOOL_SPECS}
            })

        if method == "tools/call":
            params = payload.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}

            mod = TOOLS.get(name)
            if not mod:
                raise ValueError(f"Unknown tool: {name}")

            # Kjør riktig runner (call eller run)
            if hasattr(mod, "call") and callable(getattr(mod, "call")):
                out = mod.call(arguments)
            else:
                out = mod.run(arguments)

            # MCP forventer {"content":[...]}
            if isinstance(out, dict) and "content" in out:
                result = out
            else:
                # fallback hvis tool returnerer {"ok":True,"message":"..."}
                msg = out.get("message") if isinstance(out, dict) else str(out)
                result = {"content": [{"type": "text", "text": msg}]}

            return jsonify({"jsonrpc": "2.0", "id": rpc_id, "result": result})

        # ukjent metode
        return jsonify({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }), 400

    except Exception as e:
        return jsonify({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32000, "message": str(e)}
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
