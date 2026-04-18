import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_mcp_session():
    tool = MagicMock()
    tool.name = "search_jobs"
    tool.description = "Search jobs"
    tool.inputSchema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }
    tools_result = MagicMock()
    tools_result.tools = [tool]

    call_result = MagicMock()
    call_result.content = [MagicMock(text='[{"id": 1, "title": "React Dev", "company": "Acme"}]')]

    session = AsyncMock()
    session.list_tools.return_value = tools_result
    session.call_tool.return_value = call_result
    return session


def _make_anthropic_responses(tool_name, tool_input, final_text):
    tool_use = MagicMock()
    tool_use.type = "tool_use"
    tool_use.name = tool_name
    tool_use.id = "tu_abc123"
    tool_use.input = tool_input

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = final_text

    resp_tool = MagicMock()
    resp_tool.stop_reason = "tool_use"
    resp_tool.content = [tool_use]

    resp_final = MagicMock()
    resp_final.stop_reason = "end_turn"
    resp_final.content = [text_block]

    return [resp_tool, resp_final]


@pytest.mark.asyncio
async def test_run_returns_text_and_tool_log(mock_mcp_session):
    import agent

    anthropic_client = MagicMock()
    anthropic_client.messages.create.side_effect = _make_anthropic_responses(
        "search_jobs", {"query": "React"}, "Found 1 React job."
    )

    with patch("agent.sse_client") as mock_sse, \
         patch("agent.ClientSession") as mock_cs, \
         patch("agent.anthropic.Anthropic", return_value=anthropic_client):

        mock_sse.return_value.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
        mock_sse.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_cs.return_value.__aenter__ = AsyncMock(return_value=mock_mcp_session)
        mock_cs.return_value.__aexit__ = AsyncMock(return_value=None)

        text, log = await agent.run("Show me React jobs")

    assert text == "Found 1 React job."
    assert len(log) == 1
    assert log[0]["tool"] == "search_jobs"
    assert log[0]["input"] == {"query": "React"}
    assert "React Dev" in log[0]["output"]


@pytest.mark.asyncio
async def test_run_without_tool_use(mock_mcp_session):
    import agent

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "I can help you search for jobs."

    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [text_block]

    anthropic_client = MagicMock()
    anthropic_client.messages.create.return_value = resp

    with patch("agent.sse_client") as mock_sse, \
         patch("agent.ClientSession") as mock_cs, \
         patch("agent.anthropic.Anthropic", return_value=anthropic_client):

        mock_sse.return_value.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
        mock_sse.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_cs.return_value.__aenter__ = AsyncMock(return_value=mock_mcp_session)
        mock_cs.return_value.__aexit__ = AsyncMock(return_value=None)

        text, log = await agent.run("hello")

    assert text == "I can help you search for jobs."
    assert log == []


@pytest.mark.asyncio
async def test_run_returns_error_on_connection_failure():
    import agent

    with patch("agent.sse_client") as mock_sse:
        mock_sse.side_effect = Exception("Connection refused")
        text, log = await agent.run("Show me React jobs")

    assert text == ""
    assert len(log) == 1
    assert "error" in log[0]
    assert "Connection refused" in log[0]["error"]
