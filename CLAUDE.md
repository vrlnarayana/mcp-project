# CLAUDE.md — MCP Server/Client Demo

## What This Is

A two-app Python demo of the **Model Context Protocol (MCP)**:
- **App A (`mcp-server/`)** — FastAPI + SQLite + MCP SSE server with 3 tools
- **App B (`mcp-client/`)** — Streamlit + Claude SDK agent + MCP client

Remote repo: **https://github.com/vrlnarayana/mcp-project.git** (main branch)

Design spec: `docs/superpowers/specs/2026-04-18-mcp-server-client-demo-design.md`
Implementation plan: `docs/superpowers/plans/2026-04-18-mcp-server-client-demo.md`

---

## Repo Structure

```
mcp-server/
├── main.py         FastAPI app + MCP SSE mount at "/"
├── database.py     SQLite layer — init_db, db_list_jobs, db_get_job, db_search_jobs
├── tools.py        Registers 3 MCP tools on FastMCP instance
├── seed_data.py    52 Indian tech job records (JOBS list of dicts)
├── requirements.txt
├── pytest.ini      asyncio_mode = auto
└── tests/test_database.py   12 unit tests

mcp-client/
├── app.py          Streamlit split-panel UI
├── agent.py        async run(query) → (text, tool_call_log)
├── requirements.txt
├── pytest.ini      asyncio_mode = auto
└── tests/test_agent.py   3 async tests
```

---

## Local Dev Quick Start

Both apps need Python 3.11 virtualenvs. Use `python3.11` explicitly — system `python3` may be 3.7.

```bash
# App A — MCP Server (Terminal 1)
cd mcp-server
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --port 8000

# App B — MCP Client (Terminal 2)
cd mcp-client
python3.11 -m venv .venv
source .venv/bin/activate
export ANTHROPIC_API_KEY=<your-key>
streamlit run app.py
```

Open **http://localhost:8501**

Health check: `curl http://localhost:8000/health` → `{"status": "ok"}`
MCP SSE endpoint: `http://localhost:8000/sse`

---

## Key Implementation Details

### MCP Tool Registration

Tools are registered in `tools.py` using `@mcp.tool()` decorator on a `FastMCP` instance. Type hints + docstrings become the JSON Schema Claude sees. The `register_tools(mcp)` function is called from `main.py` at module level (before FastAPI app creation).

### MCP SSE Mount

```python
app.mount("/", mcp_server.sse_app())
```
FastAPI exact-match routes (`/health`) take precedence over the mount. All MCP traffic goes through root.

### Agent Tool-Use Loop

`agent.py:run()` is a `while True` loop that:
1. Sends query to Claude with dynamically-discovered tools
2. If `stop_reason == "tool_use"`: calls each tool via `session.call_tool()`, appends results, loops
3. If `stop_reason == "end_turn"`: returns final text + `tool_call_log`

Never breaks out of the loop prematurely — Claude decides when it has enough information.

### Database Connection Safety

All 4 DB functions (`init_db`, `db_list_jobs`, `db_get_job`, `db_search_jobs`) use `try/finally` to guarantee `conn.close()` even on exceptions. This was a bug in an earlier version — connections leaked on query errors.

### Streamlit Health Check Cache

`check_server()` is decorated with `@st.cache_data(ttl=10)` to prevent hitting the network on every Streamlit rerun. Without this, every keystroke in the text input triggers an HTTP request to the MCP server.

---

## Running Tests

```bash
# From mcp-server/ with venv active:
pytest tests/ -v    # 12 tests

# From mcp-client/ with venv active:
pytest tests/ -v    # 3 tests
```

### Test isolation pattern (database tests)

```python
@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    database.init_db(seed=False)
    yield
```

`monkeypatch.setattr` redirects `DB_PATH` to a temp directory — the production `jobs.db` is never touched. This is the correct pattern for testing SQLite code without mocking.

### Async test pattern (agent tests)

Agent tests use `unittest.mock.AsyncMock` to mock `sse_client` and `ClientSession` as async context managers. `asyncio_mode = auto` in `pytest.ini` removes the need for `@pytest.mark.asyncio` on every test.

---

## Known Gotchas

### `git subtree push` for pushing a subdirectory

The `mcp-project/` directory lives inside a larger home-dir git repo (`/Users/vrln`). Pushing to `vrlnarayana/mcp-project` requires:

```bash
git subtree push --prefix=mcp-project mcp-origin master:main
```

Force-push when remote has diverged (e.g. after pushing to `master` first):
```bash
git push mcp-origin $(git subtree split --prefix=mcp-project master):main --force
```

### Multiple GitHub accounts with `gh` CLI

`gh auth status` shows the active account. If `lax-t3` is active but you need to push as `vrlnarayana`:
```bash
gh auth switch --user vrlnarayana
```

Switch back after pushing:
```bash
gh auth switch --user lax-t3
```

### `git subtree push` does not support `--force`

`git subtree push` ignores `--force`. To force-push, split the subtree into a branch manually and use `git push --force`:
```bash
git push mcp-origin $(git subtree split --prefix=mcp-project master):main --force
```

### Python version

`python3` on this machine resolves to Python 3.7. Always use `python3.11` explicitly when creating venvs or running scripts.

### `.venv` directories are gitignored

Virtualenvs are not committed. After cloning, run `python3.11 -m venv .venv && pip install -r requirements.txt` in each app directory before running tests or starting the server.

### `jobs.db` is gitignored

The SQLite database file is regenerated automatically on first `uvicorn` startup via `init_db()`. Do not commit it.

---

## MCP Protocol Notes

- Client connects to `http://localhost:8000/sse` and calls `session.initialize()` before any tool calls
- `session.list_tools()` returns typed tool definitions with `name`, `description`, `inputSchema`
- `session.call_tool(name, input)` returns `CallToolResult` with a `content` list; each item has `.text`
- Tool results must be passed back to Claude as `{"type": "tool_result", "tool_use_id": ..., "content": ...}` in a user message
- The MCP session must remain open for the entire agent loop — open it as a context manager wrapping the `while True` loop

---

## Seed Data Summary

52 job records across:
- **Cities**: Bangalore, Chennai, Mumbai, Hyderabad, Pune, Delhi
- **Roles**: React, Python, Data Science, DevOps, Java, iOS, Android, PM, QA, Node.js
- **Companies**: Flipkart, Swiggy, Zepto, Razorpay, Zoho, Freshworks, Google, Amazon, Microsoft IDC, CRED, PhonePe, etc.
- **Levels**: junior, mid, senior
- **Types**: full-time, contract, remote
- 51 open (`is_open=1`), 1 closed (`is_open=0`)
