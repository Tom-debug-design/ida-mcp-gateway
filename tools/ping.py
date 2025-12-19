TOOL = {
    "name": "ping",
    "description": "Health check to verify MCP connectivity",
    "inputSchema": {
        "type": "object",
        "properties": {},
        "additionalProperties": False
    }
}

def call(args: dict) -> dict:
    return {
        "content": [
            {"type": "text", "text": "pong ✅ (from ida-mcp-gateway)"}
        ]
    }
