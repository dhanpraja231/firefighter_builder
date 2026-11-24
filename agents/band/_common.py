"""Shared LangGraph helpers for no-model Band agents."""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Awaitable

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph

from band import Agent, configure_logging
from band.adapters import LangGraphAdapter
from band.runtime.formatters import strip_leading_mentions

SENDER = re.compile(r"^\[(?P<sender>[^\]]+)\]:\s*(?P<text>.*)$", re.DOTALL)

Handler = Callable[[str, str, list[Any]], Awaitable[None]]


def tool_by_name(band_tools: list[Any], name: str) -> Any:
    return next(t for t in band_tools if t.name == name)


def parse_incoming(content: str) -> tuple[str, str]:
    match = SENDER.match(content)
    if match:
        sender = match.group("sender")
        text = strip_leading_mentions(match.group("text")).strip()
        return sender, text
    return "there", strip_leading_mentions(content).strip()


def peer_matches(peer: dict[str, Any], *needles: str) -> bool:
    blob = " ".join(
        str(peer.get(k) or "")
        for k in ("name", "display_name", "handle", "description", "agent_name")
    ).lower()
    return any(n.lower() in blob for n in needles)


def peer_id(peer: dict[str, Any]) -> str | None:
    for key in ("id", "agent_id", "participant_id", "user_id"):
        val = peer.get(key)
        if val:
            return str(val)
    handle = peer.get("handle")
    return str(handle) if handle else None


def peer_mention(peer: dict[str, Any]) -> str:
    handle = peer.get("handle")
    if handle:
        h = str(handle)
        return h if h.startswith("@") else f"@{h}"
    pid = peer_id(peer)
    return pid or "@unknown"


async def list_peer_rows(lookup_peers: Any) -> list[dict[str, Any]]:
    raw = await lookup_peers.ainvoke({"page": 1, "page_size": 50})
    if isinstance(raw, dict):
        for key in ("peers", "data", "items", "results"):
            rows = raw.get(key)
            if isinstance(rows, list):
                return [r for r in rows if isinstance(r, dict)]
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    return []


def make_graph_factory(handler: Handler):
    checkpointer = InMemorySaver()

    def graph_factory(band_tools: list[Any]):
        async def reply(state: MessagesState) -> dict[str, list[Any]]:
            if not state["messages"]:
                return {"messages": []}
            content = str(state["messages"][-1].content)
            sender, text = parse_incoming(content)
            await handler(sender, text, band_tools)
            return {"messages": []}

        builder = StateGraph(MessagesState)
        builder.add_node("reply", reply)
        builder.add_edge(START, "reply")
        builder.add_edge("reply", END)
        return builder.compile(checkpointer=checkpointer)

    return graph_factory


async def run_agent(config_key: str, handler: Handler) -> None:
    configure_logging(logging.INFO)
    adapter = LangGraphAdapter(graph_factory=make_graph_factory(handler))
    agent = Agent.from_config(config_key, adapter=adapter)
    await agent.run()
