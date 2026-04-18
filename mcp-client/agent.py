import anthropic
from mcp.client.sse import sse_client
from mcp import ClientSession

MCP_SERVER_URL = "http://localhost:8000/sse"
SYSTEM_PROMPT = (
    "You are a job search assistant. Use the available tools to answer the user's "
    "query about jobs. Be concise and format results in a readable list."
)


async def run(query: str) -> tuple[str, list[dict]]:
    tool_call_log: list[dict] = []
    try:
        async with sse_client(MCP_SERVER_URL) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools_result = await session.list_tools()
                anthropic_tools = [
                    {
                        "name": t.name,
                        "description": t.description or "",
                        "input_schema": t.inputSchema,
                    }
                    for t in tools_result.tools
                ]

                client = anthropic.Anthropic()
                messages: list[dict] = [{"role": "user", "content": query}]

                while True:
                    response = client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=4096,
                        system=SYSTEM_PROMPT,
                        tools=anthropic_tools,
                        messages=messages,
                    )

                    if response.stop_reason == "tool_use":
                        tool_uses = [b for b in response.content if b.type == "tool_use"]
                        messages.append({"role": "assistant", "content": response.content})

                        tool_results = []
                        for tu in tool_uses:
                            call_result = await session.call_tool(tu.name, tu.input)
                            output = (
                                call_result.content[0].text
                                if call_result.content
                                else ""
                            )
                            tool_call_log.append(
                                {"tool": tu.name, "input": tu.input, "output": output}
                            )
                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": tu.id,
                                    "content": output,
                                }
                            )
                        messages.append({"role": "user", "content": tool_results})

                    else:
                        final_text = next(
                            (b.text for b in response.content if b.type == "text"),
                            "No response generated.",
                        )
                        return final_text, tool_call_log

    except Exception as exc:
        return "", [{"error": f"MCP server offline or error: {exc}"}]
