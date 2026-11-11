"""A message the phone shows instead of the action's result (2026-11-11).

Used when the server refuses an awakening: a refusal used to answer with no result row, and the phone went on to
the awakening animation, which looked up the new unit and crashed (Lightning's NV awakening, 7 times).

The phone's reply parser (`GameResponseParser::parseTag`, GL 0x190ec30) reads four top-level envelope keys:
`TEAYk6R1` (header), `t7n6cVWf` (body), `bCf65yoK` (message) and `QFUPjOcL` (signature). `MessageResponse::readParam`
(0x1982100) reads `D8aznm56` -> `MessageState::setType`, `5oHZM9zK` -> `setCmd`, `Wk1v6upb` -> the text (split on
"@"). A screen's `checkConnectResult` calls `GameScene::checkResponseMessage` (0x1e7cfc8) first: when a message
exists it shows it with `changeNoticeScene` and stops (the awakening screen then never opens the animation).
Command 6 takes the plain path (code 0: no return to the title, no maintenance or update action); type 3 is avoided
(it forces command 4). The text goes through `TextManager::getText`, which returns unknown text as it is.

`set(text)` during a request; `capture_server` puts it in the envelope and `take()` clears it.
"""
from __future__ import annotations

TAG = "bCf65yoK"
_pending: list[str] = []


def set(text: str) -> None:  # noqa: A001 - the module's one verb
    _pending[:] = [str(text).replace("@", " ")]


def take() -> dict | None:
    """The envelope's message object for this reply, or None; clears it."""
    if not _pending:
        return None
    text = _pending.pop()
    _pending.clear()
    return {"D8aznm56": "1", "5oHZM9zK": "6", "Wk1v6upb": text}


def clear() -> None:
    _pending.clear()
