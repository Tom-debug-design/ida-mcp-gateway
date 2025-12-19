TOOL_NAME = "ping"

TOOL_SPEC = {
    "description": "Health check to verify MCP connectivity",
    "input_schema": {
        "type": "object",
        "properties": {},
        "additionalProperties": False
    },
}

def run(args: dict) -> dict:
    return {
        "ok": True,
        "message": "pong ✅ (from ida-mcp-gateway)"
    }
