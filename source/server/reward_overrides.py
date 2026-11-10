"""Quest rewards taken from the FFBE wiki where the operator chose it over Global's final data (2026-11-10).

`content/reward_overrides.json` (built by ios-server/devtools/build_reward_overrides.py; list in
ios-server/research/REWARD_OVERRIDES.md):
  * `missions`: per quest, the wiki's first-clear reward (`first_clear`, F_MISSION_MST `1x4bG2J8` shape) and
    challenge rewards (`challenges`: challenge id -> F_CHALLENGE_MST `dX6cor8j` shape). `first_run_only`
    quests (events Global ran twice; the wiki records the first run) use them only while the replay shows
    their first run, and the final data during the later run;
  * `added_challenges`: challenge rows Global's final data dropped (Chamber of Supercite's esper trials,
    Sprouts of Devouring, Esper of Destruction, The Fighting Pits), with the wiki's conditions and rewards.
Read by first_clear.raw, ffbe_battle.challenge_table and exvius_repeat.repeat_challenge_rewards, and served in
the client's challenge and mission tables (ios_tables.py), so what is shown is what is paid.
`EXVIUS_WIKI_REWARDS=0` turns all of it off.
"""
from __future__ import annotations

import json
import os
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "content", "reward_overrides.json")
_DOC: dict | None = None


def enabled() -> bool:
    return str(os.environ.get("EXVIUS_WIKI_REWARDS", "1")).strip().lower() not in ("0", "off", "false", "no")


def _doc() -> dict:
    global _DOC
    if _DOC is None:
        try:
            with open(PATH, encoding="utf-8") as fh:
                _DOC = json.load(fh)
        except (OSError, ValueError):
            _DOC = {}
    return _DOC


def _first_run_now(area: str) -> bool:
    """True while the replay's history is still in the event's first Global run (before its next run)."""
    import event_archive
    runs = next((e.get("runs") or [] for e in event_archive.document()["events"] if str(e["area"]) == str(area)), [])
    if len(runs) < 2:
        return True
    try:
        import replay
        win = replay.window() if replay.enabled() else None
    except Exception:  # noqa: BLE001 - no replay: the latest run
        win = None
    if not win or win.get("finished"):
        return False
    upto = win["to"].isoformat() if isinstance(win["to"], date) else str(win["to"])
    return not any(run < upto for run in runs[1:])


def for_mission(mid) -> dict | None:
    """The active override for this quest, or None."""
    if not enabled():
        return None
    entry = (_doc().get("missions") or {}).get(str(mid))
    if not entry:
        return None
    if entry.get("first_run_only") and not _first_run_now(entry.get("area", "")):
        return None
    return entry


def first_clear(mid, value: str) -> str:
    entry = for_mission(mid)
    return entry["first_clear"] if entry and entry.get("first_clear") is not None else value


def added_challenges() -> list:
    return list(_doc().get("added_challenges") or []) if enabled() else []


def challenge_rows(rows):
    """F_CHALLENGE_MST rows with the active overrides applied, then the restored challenges."""
    cache: dict = {}
    for row in rows:
        mid = str(row.get("qo3PECw6"))
        if mid not in cache:
            cache[mid] = for_mission(mid)
        entry = cache[mid]
        cid = str(row.get("V36ygRYs"))
        if entry and cid in (entry.get("challenges") or {}):
            row = dict(row, dX6cor8j=entry["challenges"][cid])
        yield row
    for row in added_challenges():
        yield {k: v for k, v in row.items() if k not in ("name", "page")}


_SIG: tuple[float, str] | None = None


def signature() -> str:
    """Changes whenever what the client should be shown changes (a first-run-only override switching).
    Recomputed at most once a minute."""
    global _SIG
    import time
    if not enabled():
        return "off"
    if _SIG and time.monotonic() - _SIG[0] < 60:
        return _SIG[1]
    active = sorted(m for m, e in (_doc().get("missions") or {}).items() if for_mission(m) is not None)
    import zlib
    value = f"{len(active)}:{zlib.crc32(','.join(active).encode()) & 0xffff}"
    _SIG = (time.monotonic(), value)
    return value
