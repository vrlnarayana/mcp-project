from contextlib import asynccontextmanager
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
import database
from tools import register_tools

mcp_server = FastMCP("jobs-mcp-server")
register_tools(mcp_server)


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


app.mount("/", mcp_server.sse_app())
