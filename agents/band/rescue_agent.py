"""Rescue-1 Band agent — radio ack on Commander assign."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import _paths  # noqa: F401
from _common import run_agent, tool_by_name
from dotenv import load_dotenv

from assignments import HOSE_RESCUE_ASSIGN_UTTERANCE, RESCUE_ACK

logger = logging.getLogger(__name__)


async def on_message(sender: str, text: str, band_tools: list[Any]) -> None:
    send_message = tool_by_name(band_tools, "band_send_message")
    no_reply = tool_by_name(band_tools, "band_no_reply")
    lowered = text.lower()

    if (
        "rescue" not in lowered
        and "extract" not in lowered
        and HOSE_RESCUE_ASSIGN_UTTERANCE.lower() not in lowered
    ):
        await no_reply.ainvoke({"reason": "Not a rescue assignment."})
        return

    await send_message.ainvoke({"content": RESCUE_ACK, "mentions": [sender]})


async def main() -> None:
    load_dotenv()
    logger.info("Rescue-1 online")
    await run_agent("rescue", on_message)


if __name__ == "__main__":
    asyncio.run(main())
