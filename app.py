from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import FastMCP

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

mcp = FastMCP("ida-mcp-gateway")

@mcp.tool
def ping() -> str:
    return "pong"

@app.get("/")
def root():
    return {
        "ok": True,
        "message": "IDA MCP minimal server",
        "mcp_sse": "/sse/"
    }

# ⛔️ VIKTIG: path må være ROOT /sse – ikke /mcp, ikke noe annet
app.mount("/sse", mcp.http_app(path="/sse"))
