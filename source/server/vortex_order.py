"""The order of the Vortex's event tiles (operator's request, 2026-11-10: story and limited-time events at the
top, the farming chambers at the bottom).

The client sorts the Vortex's areas itself (GateUtil::getInSessionAreaList 0x1ab6xxx -> std::sort with
SortUtil::compAreaMst 0x19ceb50): areas whose challenge limit is used up last, the rest by
AreaMst::getPriority, ascending, which is `F_AREA_MST.Z0EN6jSh` (AreaMstResponse::readParam: `Z0EN6jSh` ->
+0x8c). The order the server sends the gate rows in doesn't count. The shipped priorities are small numbers
meant for a handful of events at a time (Chamber of Supercite 2, Chamber of Experience 4, Akademeia 20), so
farming chambers came out on top. ios_tables serves `F_AREA_MST` with these priorities instead:

  1. story events, newest first (by first Global run);
  2. the other limited-time events (exchange, exploration, challenge, raid, collaboration...), newest first;
  3. ranked events in their own periods (Clash of Wills, Dark Visions);
  4. undated rotating events (Boss Rush, Cactuar Dunes, Series Boss Battle...);
  5. the permanent trial chambers (Chamber of the Fallen, of Arms, of the Vengeful, Training the Soul);
  6. the permanent farming chambers (Awakening, Experience, Riches, Crystals, Crysts, Enlightenment,
     Supercite, Blue Magic, Challenges...), those Global added later lowest (`introduced` in
     content/event_quest_dates.json, from Global's update history; they stay open from the start).

Ties and tiers 3-5 go by area id. `EXVIUS_VORTEX_ORDER=0` serves the table's own priorities.
"""
from __future__ import annotations

import os
from functools import lru_cache

TIER = 10000


def enabled() -> bool:
    return str(os.environ.get('EXVIUS_VORTEX_ORDER', '1')).strip().lower() not in ('0', 'off', 'false', 'no')


def tier(row) -> int:
    if row.get('windows'):
        return 3
    if row.get('group') == 'permanent':
        return 5 if row.get('runs') else 6
    if not (row.get('runs') or row.get('release')):
        return 4
    return 1 if 'story event' in str(row.get('kind') or '').lower() else 2


@lru_cache(maxsize=1)
def priorities() -> dict:
    """Event area id -> its F_AREA_MST priority (empty when switched off)."""
    if not enabled():
        return {}
    import event_archive
    rows = event_archive.document()['events']

    def first_run(row):
        runs = sorted(str(r) for r in (row.get('runs') or []) if r)
        return runs[0] if runs else str(row.get('release') or '')
    out = {}
    for t in range(1, 7):
        group = [r for r in rows if tier(r) == t]
        if t <= 2:
            group.sort(key=lambda r: (first_run(r), -int(r['area'])), reverse=True)
        elif t == 6:
            added = event_archive.quest_dates().get('introduced') or {}
            group.sort(key=lambda r: (added.get(str(r['area']), ''), int(r['area'])))
        else:
            group.sort(key=lambda r: int(r['area']))
        for n, row in enumerate(group):
            out.setdefault(str(row['area']), t * TIER + n)
    return out
