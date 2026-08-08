from __future__ import annotations

import os

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import FastMCP

from execution_gateway import receive_execution
from execution_worker import process_next_execution

app = FastAPI(title="IDA MCP Gateway", version="2.0.0")

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
def root() -> dict[str, object]:
    allowed = {
        item.strip()
        for item in os.getenv("IDA2_ALLOWED_ACTION_TYPES", "").split(",")
        if item.strip()
    }
    return {
        "ok": True,
        "message": "IDA MCP gateway",
        "mcp_sse": "/sse/",
        "execution_receiver": {
            "enabled": bool(os.getenv("IDA2_EXECUTION_GATEWAY_SECRET", "").strip()),
            "allowed_action_type_count": len(allowed),
        },
    }


@app.post("/execute")
async def execute(
    request: Request,
    x_ida2_signature: str = Header(default=""),
    idempotency_key: str = Header(default=""),
) -> dict[str, object]:
    body = await request.body()
    try:
        receipt = receive_execution(body, x_ida2_signature, idempotency_key)
        if receipt["duplicate"]:
            return receipt
        return {**receipt, "worker": process_next_execution()}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        code = str(exc)
        if code in {"invalid_signature", "invalid_signature_format"}:
            status = 401
        elif code == "action_type_not_allowed":
            status = 403
        elif code == "idempotency_conflict":
            status = 409
        else:
            status = 422
        raise HTTPException(status_code=status, detail=code) from exc


app.mount("/sse", mcp.http_app(path="/sse"))
