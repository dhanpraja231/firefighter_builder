"""Shared radio lines for Band room agents and the orchestrator film.

Keep these identical so the Band chat and the Three.js decide/speak events match.
"""

# Commander -> scout (opening beat)
SCOUT_ASSIGN_UTTERANCE = "Scout, sweep every floor and report what you find."
SCOUT_ASSIGN_REASONING = (
    "Need the full picture before committing the rescue robot anywhere."
)

# Commander -> hose + rescue (after fire confirmed)
HOSE_RESCUE_ASSIGN_UTTERANCE = (
    "Hose-1, hold the floor 3 stairwell. Rescue-1, start with the easiest extracts and work up."
)
HOSE_RESCUE_ASSIGN_REASONING = (
    "Fire is confirmed on 3. Buy time on the stairwell while rescue clears rooms floor by floor."
)

# Robot radio acks (Band replies; film can reuse the same wording in speak events)
SCOUT_ACK = "Scout-1 copies. Beginning floor sweep, bottom to top."
HOSE_ACK = "Hose-1 copies. Moving to floor 3 stairwell to hold the exit."
RESCUE_ACK = "Rescue-1 copies. Staging for easiest extracts first, then working up."

# Phrases that wake the Commander Band agent
COMMANDER_WAKE_WORDS = ("start", "deploy", "fire", "structure")
