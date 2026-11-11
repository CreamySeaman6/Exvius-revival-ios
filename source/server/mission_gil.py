"""A quest's clear Gil (`F_MISSION_MST.7UR4J2SE`), paid on each successful clear (player report, 2026-11-11: "Running
the Gil chamber quest x10 on auto did not give any Gil").

The phone adds up only the Gil its monsters carry (`MissionEndRequest.Wdi3MAs2`, from the parts rows' `7UR4J2SE`);
its mission rows have no Gil field at all (GL `MissionMst` has no Gil getter), so a quest's own clear Gil can only
come from the server, and this server never paid it. Most quests carry a few Gil there (Earth Shrine - Entrance:
12), but the Chamber of Riches pays almost everything there: BGN 1,500, INT 3,200, ADV 5,000, PRO 10,000, ELT 85,000,
with monsters worth 0 Gil (Global's wiki: PRO 10,356 and ELT 85,000 per run; its rank EXP 60-100 is the same
table's `B6H34Mea`).

`pay` (pipeline step after `pay_event_currency`): once per loaded attempt (`exvius_mission_gil.last`), only on a
successful clear (`first_clear._succeeded`), credits the Gil and adds it to the result screen's Gil (`16LQuC5r`).
EXVIUS_MISSION_GIL=0 turns it off.
"""
from __future__ import annotations

import os

LEDGER = "exvius_mission_gil"


def enabled() -> bool:
    return os.environ.get("EXVIUS_MISSION_GIL", "1").strip().lower() not in ("0", "off", "false", "no")


def amount(mid) -> int:
    from player_state import _load_ndjson
    row = _load_ndjson("F_MISSION_MST.ndjson", "qo3PECw6").get(str(mid)) or {}
    try:
        return max(0, int(row.get("7UR4J2SE") or 0))
    except (TypeError, ValueError):
        return 0


def pay(spec, mid, plaintext):
    from ffbe_config import RESULT_TAG
    from ffbe_state import State
    player = State.player
    if (not enabled() or player is None or player.mode == "frozen" or not mid or not isinstance(spec, dict)
            or RESULT_TAG not in spec):
        return spec
    gil = amount(mid)
    if gil <= 0:
        return spec
    from first_clear import _succeeded
    attempt = player.data.get("exvius_repeat", {}).get("attempt", {})
    if attempt.get("mid") != str(mid):
        attempt = {}
    mark = [str(mid), attempt.get("sequence")]
    led = player.data.get(LEDGER) or {}
    if led.get("last") == mark or not _succeeded(player, str(mid), plaintext):
        return spec
    before = int(player.currencies.get("gil", 0))
    if player.add_currency("gil", gil) == before:
        return spec
    player.data[LEDGER] = dict(led, last=mark)
    player.dirty = True
    State.state_dirty = True
    print(f"mission-gil: mission {mid} paid {gil} clear gil", flush=True)
    import copy
    spec = copy.deepcopy(spec)
    for result in spec.get(RESULT_TAG, []):
        if isinstance(result, dict):
            shown = str(result.get("16LQuC5r") or "0")
            result["16LQuC5r"] = str((int(shown) if shown.isdigit() else 0) + gil)
    return spec
