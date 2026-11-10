"""Event currency on every clear: the battle drops Global's exchange events paid, sized to a number of runs.

On Global, King Mog style events paid their currency mostly as battle drops (the wiki's Battle Infobox `drop`:
Mana Mystery ELT about 210 Candy per clear, a 2019 LGD about 680). Those drop lists were server-side and are
lost: no battle served here drops any event currency (HANDOFF.md, "Event audit"). Operator's choice
(2026-11-09): pay it again on every clear, sized so the event's own gear, materia, units and tickets in its
exchange (`farm.need`: their cost minus what first clears and challenges pay; bulk materials not counted)
take about EXVIUS_EVENT_CURRENCY_RUNS clears of the event's top quest, and never less than Global's own drop.

Per clear: top amount T = max(wiki top drop, need / runs); a quest pays T x its energy / the event's highest
quest energy (Global's drops scaled with energy too), +/-10%. Paid once per loaded attempt on a successful
clear (same rule as first-clear rewards), credited server-side and listed with the battle's drops
(`xF9Sr1a6`), the way raid coins are. Data: content/event_exchanges.json (`farm`), built by
ios-server/devtools/build_event_exchanges.py.

Settings: EXVIUS_EVENT_CURRENCY_RUNS (30) top-quest clears for the event's exclusive stock; 0 turns it off.

SINCE 2026-11-10 (operator): the currency drops from the event's enemies, like Global (global_drops.py), and
EXVIUS_EVENT_CURRENCY_RUNS sizes a multiplier on those drops instead. This lump is paid only for events where
neither Japan's battle data nor the wiki says which quests drop it (`_dropped` is False); the list is in
ios-server/research/DROP_CHECK.md.
"""
from __future__ import annotations

import json
import math
import os
import random
from functools import lru_cache
from pathlib import Path

LEDGER = "event_currency"


def runs() -> int:
    try:
        return max(0, int(os.environ.get("EXVIUS_EVENT_CURRENCY_RUNS", "30")))
    except ValueError:
        return 30


@lru_cache(maxsize=4)
def _plan(n_runs: int) -> dict:
    """mission id -> (currency item id, base amount per clear)."""
    path = Path(__file__).with_name("content").joinpath("event_exchanges.json")
    try:
        exchanges = json.loads(path.read_text(encoding="utf-8"))["exchanges"]
    except (OSError, ValueError, KeyError):
        return {}
    from player_state import _load_ndjson
    missions = _load_ndjson("F_MISSION_MST.ndjson", "qo3PECw6")
    by_area: dict[str, list] = {}
    for mid, row in missions.items():
        by_area.setdefault(str(row.get("uv60hgDW")), []).append((mid, row))
    plan = {}
    for ex in exchanges:
        farm = ex.get("farm") or {}
        areas = farm.get("areas") or []
        top = max(int(farm.get("wiki_top_drop") or 0), math.ceil(int(farm.get("need") or 0) / n_runs))
        if not areas or top <= 0:
            continue
        quests = [(mid, int(row.get("B6kyCQ9M") or 0)) for area in areas for mid, row in by_area.get(area, [])]
        peak = max((energy for _mid, energy in quests), default=0)
        if peak <= 0:
            continue
        for mid, energy in quests:
            amount = round(top * energy / peak)
            if amount > 0:
                plan[mid] = (str(ex["currency"]), amount)
    return plan


def _dropped(mid, currency: str) -> bool:
    """True when this quest's event drops the currency from enemies (global_drops.py): no lump then."""
    import global_drops
    from player_state import mission_row
    area = str((mission_row(str(mid)) or {}).get("uv60hgDW") or "")
    return f"20:{currency}" in global_drops.covered_areas().get(area, [])


def amount_for(mid) -> tuple[str, int] | None:
    n = runs()
    found = _plan(n).get(str(mid)) if n > 0 else None
    if found and _dropped(mid, found[0]):
        return None
    return found


def pay(spec, mid, plaintext):
    """Pipeline step (MissionEnd reply): credit this clear's event currency and list it with the drops."""
    from ffbe_config import RESULT_TAG
    from ffbe_state import State
    player = State.player
    if (player is None or player.mode == "frozen" or not mid or not isinstance(spec, dict)
            or RESULT_TAG not in spec):
        return spec
    found = amount_for(mid)
    if not found:
        return spec
    from first_clear import _succeeded
    attempt = player.data.get("exvius_repeat", {}).get("attempt", {})
    mark = [str(mid), attempt.get("sequence")]
    led = player.data.get(LEDGER) or {}
    if led.get("last") == mark or not _succeeded(player, str(mid), plaintext):
        return spec
    currency, base = found
    count = max(1, round(base * random.uniform(0.9, 1.1)))
    row = {"kind": 20, "id": int(currency), "count": count}
    if not player._can_credit(row) or player._grant_items([row]) != [row]:
        print(f"event-currency: mission {mid}: 20:{currency} could not be credited", flush=True)
        return spec
    player.data[LEDGER] = dict(led, last=mark)
    player.dirty = True
    State.state_dirty = True
    print(f"event-currency: mission {mid} paid 20:{currency}x{count}", flush=True)
    import copy
    spec = copy.deepcopy(spec)
    for result in spec.get(RESULT_TAG, []):
        if isinstance(result, dict):
            drops = str(result.get("xF9Sr1a6") or "")
            result["xF9Sr1a6"] = drops + ("," if drops else "") + f"20:{currency}:{count}"
    return spec
