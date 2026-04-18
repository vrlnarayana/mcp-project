import asyncio
import json
import requests
import streamlit as st
from agent import run

st.set_page_config(page_title="Jobs AI Assistant", layout="wide")

MCP_HEALTH_URL = "http://localhost:8000/health"


def check_server() -> bool:
    try:
        r = requests.get(MCP_HEALTH_URL, timeout=2)
        return r.status_code == 200
    except Exception:
        return False


st.title("Jobs AI Assistant")
st.caption("Powered by Claude + MCP · Queries the jobs database via SSE tool calls")

server_ok = check_server()
if server_ok:
    st.success("🟢  MCP Server connected · localhost:8000")
else:
    st.error("🔴  MCP Server offline · start App A first: `uvicorn main:app --port 8000`")

left, right = st.columns(2, gap="large")

with left:
    st.subheader("Query")
    query = st.text_input(
        "Ask about jobs...",
        placeholder="Show me senior React jobs in Bangalore",
        disabled=not server_ok,
    )
    ask_clicked = st.button("Ask", disabled=not server_ok or not query)

    if ask_clicked and query:
        with st.spinner("Agent thinking..."):
            response_text, tool_log = asyncio.run(run(query))
        st.session_state["response_text"] = response_text
        st.session_state["tool_log"] = tool_log

    if "response_text" in st.session_state:
        st.subheader("Response")
        if st.session_state["response_text"]:
            st.markdown(st.session_state["response_text"])
        else:
            st.error("No response — see the MCP Inspector for error details.")

with right:
    st.subheader("MCP Tool Inspector")

    if not server_ok:
        st.warning("Start App A to see live tool calls here.")
    else:
        st.info("Tools are discovered dynamically from the MCP server at runtime.")

    if "tool_log" in st.session_state:
        log = st.session_state["tool_log"]
        if not log:
            st.caption("No tool calls were made for this query.")
        for entry in log:
            if "error" in entry:
                st.error(entry["error"])
            else:
                st.markdown(f"**▶ Tool Call: `{entry['tool']}`**")
                st.code(json.dumps(entry["input"], indent=2), language="json")
                st.markdown("**◀ Tool Result:**")
                output = entry["output"]
                display = output if len(output) <= 600 else output[:600] + "\n... (truncated)"
                st.code(display, language="json")
                st.divider()
