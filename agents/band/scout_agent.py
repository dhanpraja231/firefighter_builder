"""Scout-1 Band agent — radio ack on Commander assign."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import _paths  # noqa: F401
from _common import run_agent, tool_by_name
from dotenv import load_dotenv

from assignments import SCOUT_ACK, SCOUT_ASSIGN_UTTERANCE

logger = logging.getLogger(__name__)


async def on_message(sender: str, text: str, band_tools: list[Any]) -> None:
    send_message = tool_by_name(band_tools, "band_send_message")
    no_reply = tool_by_name(band_tools, "band_no_reply")

    lowered = text.lower()
    if not any(k in lowered for k in ("sweep", "scout", "assign", SCOUT_ASSIGN_UTTERANCE.lower())):
        await no_reply.ainvoke({"reason": "Not a scout assignment."})
        return

    await send_message.ainvoke({"content": SCOUT_ACK, "mentions": [sender]})


async def main() -> None:
    load_dotenv()
    logger.info("Scout-1 online")
    await run_agent("scout", on_message)


if __name__ == "__main__":
    asyncio.run(main())
