"""Engine 9 Commander — delegates to Scout, Hose, and Rescue over Band.

No LLM: rule-based LangGraph adapter. Wake with a mention containing
start / deploy / fire / structure.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import _paths  # noqa: F401 — puts agents/ on sys.path
from _common import (
    list_peer_rows,
    peer_id,
    peer_matches,
    peer_mention,
    run_agent,
    tool_by_name,
)
from dotenv import load_dotenv

from assignments import (
    COMMANDER_WAKE_WORDS,
    HOSE_RESCUE_ASSIGN_UTTERANCE,
    SCOUT_ASSIGN_UTTERANCE,
)

logger = logging.getLogger(__name__)


def _glasser_line() -> str | None:
    try:
        from tools.glasser_briefing import load, summarize

        return summarize(
            load("apartment-3f"),
            floors=3,
            scenario_kind="multifamily walkup",
        )
    except Exception:  # fixture optional for Band demo
        return None


async def _find_robots(lookup_peers: Any) -> dict[str, dict[str, Any]]:
    rows = await list_peer_rows(lookup_peers)
    found: dict[str, dict[str, Any]] = {}
    for row in rows:
        if "scout" not in found and peer_matches(row, "scout"):
            found["scout"] = row
        elif "hose" not in found and peer_matches(row, "hose"):
            found["hose"] = row
        elif "rescue" not in found and peer_matches(row, "rescue"):
            found["rescue"] = row
    return found


async def on_message(sender: str, text: str, band_tools: list[Any]) -> None:
    send_message = tool_by_name(band_tools, "band_send_message")
    no_reply = tool_by_name(band_tools, "band_no_reply")
    lookup_peers = tool_by_name(band_tools, "band_lookup_peers")
    add_participant = tool_by_name(band_tools, "band_add_participant")

    lowered = text.lower()
    if not any(w in lowered for w in COMMANDER_WAKE_WORDS):
        await no_reply.ainvoke(
            {"reason": "Not a deploy order; waiting for start/deploy/fire/structure."}
        )
        return

    robots = await _find_robots(lookup_peers)
    for role, peer in robots.items():
        pid = peer_id(peer)
        if not pid:
            continue
        try:
            await add_participant.ainvoke({"identifier": pid, "role": "member"})
            logger.info("Added %s (%s) to room", role, pid)
        except Exception as exc:  # already in room is fine
            logger.info("add_participant %s: %s", role, exc)

    glasser = _glasser_line()
    open_lines = [
        f"@{sender} Engine 9 copies. Structure fire response for apartment-3f.",
    ]
    if glasser:
        open_lines.append(glasser)
    open_lines.append("Delegating over Band now.")
    await send_message.ainvoke({"content": "\n".join(open_lines), "mentions": [sender]})

    scout = robots.get("scout")
    if scout:
        mention = peer_mention(scout)
        await send_message.ainvoke(
            {
                "content": f"{mention} {SCOUT_ASSIGN_UTTERANCE}",
                "mentions": [mention],
            }
        )
    else:
        logger.warning("Scout peer not found via band_lookup_peers")

    hose = robots.get("hose")
    rescue = robots.get("rescue")
    targets: list[str] = []
    parts: list[str] = []
    if hose:
        targets.append(peer_mention(hose))
        parts.append(peer_mention(hose))
    if rescue:
        targets.append(peer_mention(rescue))
        parts.append(peer_mention(rescue))
    if targets:
        # Keep the film's exact assignment text; prefix mentions so Band routes it.
        content = f"{' '.join(parts)} {HOSE_RESCUE_ASSIGN_UTTERANCE}"
        await send_message.ainvoke({"content": content, "mentions": targets})
    else:
        logger.warning("Hose/Rescue peers not found via band_lookup_peers")


async def main() -> None:
    load_dotenv()
    logger.info("Commander online — mention with start/deploy/fire to assign robots")
    await run_agent("commander", on_message)


if __name__ == "__main__":
    asyncio.run(main())
