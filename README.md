# MCP Server / Client Demo

A two-app Python demo showing how the **Model Context Protocol (MCP)** connects an LLM agent to a live database through dynamically-discovered tools — no hardcoded schemas, no special API wrappers.

- **App A (`mcp-server/`)** — FastAPI + SQLite jobs database exposed as 3 MCP tools over SSE/HTTP
- **App B (`mcp-client/`)** — Streamlit UI + Claude SDK agent that discovers tools at runtime and answers natural-language queries

```
User types query → Streamlit UI → Claude agent → MCP client → SSE transport → MCP server → SQLite DB
                                               ← tool results ←              ←             ←
```

---

## What is MCP?

**Model Context Protocol** is an open standard for connecting AI models to external tools and data sources. Instead of writing custom function definitions for each integration, MCP lets servers advertise their capabilities as typed tools. Clients discover and call those tools without knowing anything about the underlying implementation.

Key properties:
- **Transport-agnostic** — works over SSE/HTTP, stdio, or WebSockets
- **Dynamic discovery** — clients call `list_tools()` at runtime; no hardcoded schemas
- **Structured I/O** — tools declare JSON Schema input/output; the LLM uses this to form correct calls
- **Session-based** — client opens a session, initialises it, then makes tool calls over the same connection

This demo uses **SSE over HTTP** (`http://localhost:8000/sse`) — App A is a long-running server process, App B connects to it over HTTP.

---

## Project Structure

```
mcp-project/
├── mcp-server/              # App A — MCP server
│   ├── main.py              # FastAPI app + MCP SSE mount
│   ├── database.py          # SQLite data layer
│   ├── tools.py             # MCP tool definitions
│   ├── seed_data.py         # 52 Indian tech job records
│   ├── requirements.txt
│   ├── pytest.ini
│   └── tests/
│       └── test_database.py # 12 database unit tests
│
├── mcp-client/              # App B — MCP client + agent
│   ├── app.py               # Streamlit split-panel UI
│   ├── agent.py             # Claude SDK + MCP client logic
│   ├── requirements.txt
│   ├── pytest.ini
│   └── tests/
│       └── test_agent.py    # 3 async agent unit tests
│
└── docs/
    └── superpowers/
        ├── specs/           # Design spec
        └── plans/           # Implementation plan
```

---

## How App A Works (MCP Server)

### Overview

App A is a FastAPI application that wraps a SQLite jobs database and exposes it as MCP tools. It uses `FastMCP` from the `mcp[cli]` Python package.

### Startup sequence

```
uvicorn starts main.py
  → lifespan() fires database.init_db()
      → creates jobs table if missing
      → seeds 52 job records if table is empty
  → FastAPI mounts MCP SSE app at "/"
  → /health endpoint available for liveness checks
```

### MCP tool registration (`tools.py`)

Tools are registered by decorating functions with `@mcp.tool()`. The decorator reads the function signature (type hints + defaults) and docstring to build the JSON Schema automatically:

```python
def register_tools(mcp) -> None:
    @mcp.tool()
    def list_jobs(
        page: int = 1,
        page_size: int = 10,
        location: Optional[str] = None,
        job_type: Optional[str] = None,
        experience_level: Optional[str] = None,
    ) -> dict:
        """List open jobs with optional filters..."""
        return database.db_list_jobs(page, page_size, location, job_type, experience_level)

    @mcp.tool()
    def get_job(job_id: int) -> dict:
        """Get a single job record by its numeric ID."""
        return database.db_get_job(job_id)

    @mcp.tool()
    def search_jobs(query: str, location: Optional[str] = None, skill: Optional[str] = None) -> list:
        """Search open jobs by keyword across title, skills, and description (max 20 results)."""
        return database.db_search_jobs(query, location, skill)
```

### SSE transport (`main.py`)

```python
mcp_server = FastMCP("jobs-mcp-server")
register_tools(mcp_server)

app = FastAPI(lifespan=lifespan)
app.mount("/", mcp_server.sse_app())
```

`sse_app()` returns an ASGI app that handles the MCP SSE handshake, session lifecycle, and message routing. Mounting it at `"/"` means all MCP traffic goes through the root path; the `/health` route still works because FastAPI routes take precedence over the mount for exact matches.

### Database layer (`database.py`)

Three query functions, all wrapped in `try/finally` for guaranteed connection cleanup:

| Function | Query | Returns |
|---|---|---|
| `db_list_jobs()` | Paginated SELECT with optional WHERE filters | `{jobs, total, page, page_size}` |
| `db_get_job(id)` | SELECT by primary key | job dict or `{"error": "..."}` |
| `db_search_jobs(query)` | LIKE on title + skills + description | list of job dicts (max 20) |

All string comparisons are lowercased on both sides to make filters case-insensitive.

### Jobs table schema

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | auto-increment |
| `title` | TEXT | e.g. "Senior React Developer" |
| `company` | TEXT | e.g. "Flipkart", "Zepto" |
| `location` | TEXT | Bangalore / Chennai / Mumbai / Hyderabad / Pune / Delhi |
| `skills` | TEXT | Comma-separated, e.g. "React, TypeScript, Redux" |
| `job_type` | TEXT | `full-time` / `contract` / `remote` |
| `experience_level` | TEXT | `junior` / `mid` / `senior` |
| `salary_min` | INTEGER | INR per annum |
| `salary_max` | INTEGER | INR per annum |
| `description` | TEXT | 2–3 sentence summary |
| `posted_at` | TEXT | ISO date string |
| `is_open` | INTEGER | 1 = open, 0 = closed |

---

## How App B Works (MCP Client + Agent)

### Overview

App B is a Streamlit application with a split-panel layout. The left panel accepts natural-language queries; the right panel shows each MCP tool call and its raw output. The core logic is in `agent.py`.

### Agent flow (`agent.py`)

```
run(query)
  1. Open SSE connection to http://localhost:8000/sse
  2. Initialize MCP session
  3. Call list_tools() → get tool definitions (name, description, inputSchema)
  4. Convert MCP tools to Anthropic tool format
  5. Send query + tools to Claude (claude-sonnet-4-6)
  6. If stop_reason == "tool_use":
       → call session.call_tool(name, input) for each tool_use block
       → append tool results to messages
       → send follow-up to Claude
       → repeat loop
  7. If stop_reason == "end_turn":
       → extract final text
       → return (text, tool_call_log)
```

### Dynamic tool discovery — the key demo point

```python
tools_result = await session.list_tools()
anthropic_tools = [
    {
        "name": t.name,
        "description": t.description or "",
        "input_schema": t.inputSchema,
    }
    for t in tools_result.tools
]
```

The agent never has hardcoded tool names or schemas. It reads them from the server at session start. If you add a new tool to App A, App B will use it automatically on the next query — no code changes needed in the client.

### Tool use loop

Claude returns `stop_reason = "tool_use"` when it wants to call a tool. The agent handles this by:

1. Extracting all `tool_use` blocks from the response
2. Calling `session.call_tool(name, input)` for each
3. Appending the assistant message (with tool_use blocks) + tool results as a new user message
4. Sending the updated conversation back to Claude
5. Repeating until `stop_reason = "end_turn"`

```python
while True:
    response = client.messages.create(model="claude-sonnet-4-6", ...)

    if response.stop_reason == "tool_use":
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tu in tool_uses:
            call_result = await session.call_tool(tu.name, tu.input)
            output = call_result.content[0].text if call_result.content else ""
            tool_call_log.append({"tool": tu.name, "input": tu.input, "output": output})
            tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": output})

        messages.append({"role": "user", "content": tool_results})
    else:
        final_text = next((b.text for b in response.content if b.type == "text"), "")
        return final_text, tool_call_log
```

### MCP Tool Inspector (right panel)

Every tool call is logged in `tool_call_log` as `{tool, input, output}` and rendered in the right panel after each query. Output longer than 600 characters is truncated. This makes the MCP communication visible — you can see exactly what Claude asked for and what the server returned.

### Health check

```python
@st.cache_data(ttl=10)
def check_server() -> bool:
    try:
        r = requests.get("http://localhost:8000/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False
```

`@st.cache_data(ttl=10)` prevents the health check from hitting the network on every Streamlit rerun (every keystroke). Result is cached for 10 seconds.

---

## Running the Demo

### Prerequisites

- Python 3.11
- `ANTHROPIC_API_KEY` environment variable set

### Setup

```bash
# App A — MCP Server
cd mcp-server
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# App B — MCP Client
cd ../mcp-client
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Start

```bash
# Terminal 1 — App A
cd mcp-server
source .venv/bin/activate
uvicorn main:app --port 8000

# Terminal 2 — App B
cd mcp-client
source .venv/bin/activate
export ANTHROPIC_API_KEY=<your-key>
streamlit run app.py
```

Open **http://localhost:8501** in a browser.

---

## Example Queries

| Query | Tools used |
|---|---|
| Show me senior React jobs in Bangalore | `search_jobs` |
| Find Python data science roles under 20 LPA | `search_jobs` |
| What remote contract jobs are in Chennai? | `search_jobs` |
| Tell me more about job #7 | `get_job` |
| List all open DevOps positions | `list_jobs` |
| How many jobs are available in Mumbai? | `list_jobs` |

---

## Running Tests

```bash
# App A tests (12 database unit tests)
cd mcp-server
source .venv/bin/activate
pytest tests/ -v

# App B tests (3 async agent tests)
cd mcp-client
source .venv/bin/activate
pytest tests/ -v
```

Tests use `asyncio_mode = auto` (configured in `pytest.ini`). Database tests use `monkeypatch` to redirect `DB_PATH` to a `tmp_path` so the production `jobs.db` is never touched.

---

## Architecture Decisions

**Why SSE over stdio?** Two separate terminal processes is closer to real-world deployment (server and client on different machines). SSE also makes the network boundary visible — you can see the HTTP traffic.

**Why FastMCP over raw MCP?** `FastMCP` handles the SSE handshake, session lifecycle, and tool schema generation from type hints. Less boilerplate, same protocol.

**Why single-turn queries?** Keeps the demo focused on the MCP tool-use pattern. Adding conversation history is straightforward — just persist `messages` in `st.session_state` between queries.

**Why SQLite?** Zero-dependency persistence. The database file (`jobs.db`) is auto-created and seeded on first run. Gitignored so it doesn't pollute the repo.

---

## Dependencies

**App A:**
```
fastapi          # HTTP server framework
uvicorn[standard]  # ASGI server
mcp[cli]         # MCP server + FastMCP
pytest           # test runner
pytest-asyncio   # async test support
```

**App B:**
```
streamlit        # UI framework
anthropic        # Claude SDK
mcp[cli]         # MCP client (sse_client, ClientSession)
requests         # health check HTTP call
pytest           # test runner
pytest-asyncio   # async test support
```
