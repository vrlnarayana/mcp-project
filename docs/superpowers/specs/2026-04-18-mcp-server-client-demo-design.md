# MCP Server/Client Demo — Design Spec

**Date:** 2026-04-18  
**Status:** Approved

---

## Overview

Two separate Python applications communicating through a well-defined MCP (Model Context Protocol) tool contract over SSE/HTTP transport.

- **App A (`mcp-server/`)** — FastAPI + SQLite + MCP server. Owns a jobs database and exposes it as three MCP tools.
- **App B (`mcp-client/`)** — Streamlit + Claude SDK + MCPClient. Connects to App A, discovers tools dynamically, and runs a Claude agent that answers natural-language job queries.

**Key demo point:** the agent never has a hardcoded schema — it reads tool signatures dynamically from the MCP server at runtime.

---

## Project Structure

Two sibling directories at the same level (not nested):

```
mcp-server/          # App A
├── main.py
├── database.py
├── tools.py
├── seed_data.py
└── requirements.txt

mcp-client/          # App B
├── app.py
├── agent.py
└── requirements.txt
```

---

## Transport

**SSE over HTTP.** App A listens on `http://localhost:8000/sse`. App B connects to that URL via `mcp.ClientSession`. Two separate terminal processes.

- Local dev: `uvicorn main:app --port 8000` for App A, `streamlit run app.py` for App B.
- No auth on the MCP endpoint (demo only).

---

## App A — MCP Server

### `database.py`

- Initialises a SQLite database (`jobs.db`) on startup.
- Creates the `jobs` table if it doesn't exist.
- Imports `seed_data` and calls `seed_db()` to insert 50+ records on first run (skips if table already has rows).
- Exposes three query helpers: `db_list_jobs`, `db_get_job`, `db_search_jobs`.

### Jobs Table Schema

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | auto-increment |
| `title` | TEXT | e.g. "Senior React Developer" |
| `company` | TEXT | e.g. "Flipkart", "Zepto", "Infosys" |
| `location` | TEXT | City — Bangalore, Chennai, Mumbai, Hyderabad, Pune, Delhi |
| `skills` | TEXT | Comma-separated — "React, TypeScript, Redux" |
| `job_type` | TEXT | full-time / contract / remote |
| `experience_level` | TEXT | junior / mid / senior |
| `salary_min` | INTEGER | INR per annum |
| `salary_max` | INTEGER | INR per annum |
| `description` | TEXT | 2–3 sentence role summary |
| `posted_at` | TEXT | ISO date string |
| `is_open` | INTEGER | 1 = open, 0 = closed |

### Seed Data

50+ realistic Indian tech job records spanning:
- **Cities:** Bangalore, Chennai, Mumbai, Hyderabad, Pune, Delhi
- **Roles:** React, Python, Data Science, DevOps, Java, iOS, Android, Product Management, QA, Node.js
- **Companies:** recognisable Indian tech companies and startups
- **Levels:** junior, mid, senior mix
- **Types:** full-time, contract, remote mix

### `tools.py`

Three MCP tools registered on the server:

**`list_jobs`**
```
Parameters (all optional):
  page: int = 1
  page_size: int = 10
  location: str | None
  job_type: str | None
  experience_level: str | None

Returns: { jobs: [...], total: int, page: int, page_size: int }
```

**`get_job`**
```
Parameters:
  job_id: int  (required)

Returns: full job record dict, or error if not found
```

**`search_jobs`**
```
Parameters:
  query: str       (required) — searched in title + skills + description via LIKE
  location: str | None
  skill: str | None

Returns: list of matching job records (max 20)
```

### `main.py`

- FastAPI app.
- Initialises DB on startup (`database.init_db()`).
- Mounts the MCP server using `mcp` Python library's SSE transport on the `/sse` route.
- Health check endpoint `GET /health` returns `{"status": "ok"}`.

---

## App B — MCP Client + Agent

### `agent.py`

Single async function `run(query: str) -> tuple[str, list[dict]]` that:

1. Opens an `mcp.ClientSession` connected to `http://localhost:8000/sse`.
2. Calls `list_tools()` to discover available tools dynamically — no hardcoded schemas.
3. Sends a single-turn `anthropic.messages.create()` call with:
   - Model: `claude-sonnet-4-6`
   - Tools: the dynamically discovered MCP tools
   - System prompt: "You are a job search assistant. Use the available tools to answer the user's query about jobs."
   - Message: the user's query
4. Handles `tool_use` blocks: calls `client.call_tool()` for each, appends result as a `tool_result` message, sends follow-up to Claude.
5. Returns `(final_text, tool_call_log)` where `tool_call_log` is a list of `{tool, input, output}` dicts for the inspector panel.

Error handling:
- If MCP server is unreachable, returns `("", [{"error": "MCP server offline at localhost:8000"}])`.
- If a tool returns no results, Claude responds naturally ("No jobs found matching...").

### `app.py`

Streamlit app with split panel layout:

**Left panel — Query & Response:**
- Text input: "Ask about jobs..."
- Submit button: "Ask"
- Status indicator: green dot "MCP Server connected" / red "MCP Server offline"
- Agent response rendered as markdown below the input

**Right panel — MCP Tool Inspector:**
- Header: "MCP Tool Inspector"
- On session start: shows connection status and discovered tool names
- Per query: for each tool call in `tool_call_log`, renders:
  - Tool name (orange label)
  - Input JSON (formatted code block)
  - Output JSON (formatted code block, truncated to 500 chars if large)
- All inspector output is append-only within a single query run

Flow: `app.py` calls `asyncio.run(agent.run(query))`, unpacks `(response, log)`, renders both panels.

---

## Example Queries

The demo works well with:
- "Show me senior React jobs in Bangalore"
- "Find Python data science roles under 20 LPA"
- "What remote contract jobs are available in Chennai?"
- "Tell me more about job #7" (exercises `get_job`)
- "List all open DevOps positions" (exercises `list_jobs`)

---

## Dependencies

**App A (`mcp-server/requirements.txt`):**
```
fastapi
uvicorn[standard]
mcp[cli]
```

**App B (`mcp-client/requirements.txt`):**
```
streamlit
anthropic
mcp[cli]
```

---

## Running the Demo

```bash
# Terminal 1 — App A
cd mcp-server
pip install -r requirements.txt
uvicorn main:app --port 8000

# Terminal 2 — App B
cd mcp-client
pip install -r requirements.txt
export ANTHROPIC_API_KEY=<your-key>
streamlit run app.py
```

Open http://localhost:8501 in a browser.
