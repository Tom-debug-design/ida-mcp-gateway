from .loader import load_tools

TOOL_RUNNERS, TOOL_SPECS = load_tools()

def dispatch(tool_name: str, args: dict | None = None) -> dict:
    if args is None:
        args = {}

    if tool_name not in TOOL_RUNNERS:
        return {"ok": False, "error": f"Unknown tool: {tool_name}"}

    try:
        return TOOL_RUNNERS[tool_name](args)
    except Exception as e:
        return {"ok": False, "error": str(e)}

