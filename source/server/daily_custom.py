"""Custom daily quests (operator's request, 2026-11-07): more kinds of quest and higher, varying rewards.

The quests are `daily_quests_custom.json`. `ffbe_player.daily_quest_catalogue` merges them into the shipped
catalogue, `_daily_quest_plan` adds their pools, and `_daily_quest_pick` draws `EXVIUS_DAILY_QUEST_COUNT`
quests a day from the pools in a day-shuffled order, one per pool, so each day is a different mix. The
iPhone gets their text from `ios_texts.py` (F_TEXT_DAILY_QUEST_NAME / _DETAIL).

Rewards: each quest names a tier; the day's reward is one entry of the tier's list, picked from
(day, quest id), so it changes from day to day but not within a day. `show` is what the row draws
(kind:id:count, Lapis after the multiplier); `grant` is what the claim pays (the same, plus a Trust
Moogle's trust metadata).

Settings:
  EXVIUS_DAILY_CUSTOM (default 1)       0 = only the shipped daily quests, as before.
  EXVIUS_DAILY_QUEST_COUNT (default 5)  quests a day while the custom ones are on.
"""
from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_DOC: dict | None = None


def enabled() -> bool:
    return os.environ.get('EXVIUS_DAILY_CUSTOM', '1').strip() not in ('0', 'false', 'off', '')


def count() -> int:
    try:
        return max(1, int(os.environ.get('EXVIUS_DAILY_QUEST_COUNT', '5')))
    except ValueError:
        return 5


def doc() -> dict:
    global _DOC
    if _DOC is None:
        try:
            with open(os.path.join(_HERE, 'daily_quests_custom.json'), encoding='utf-8') as fh:
                _DOC = json.load(fh)
        except (OSError, ValueError):
            _DOC = {}
    return _DOC


def quests() -> list:
    out = []
    for q in doc().get('quests') or []:
        row = dict(q, custom=True)
        row.setdefault('name_key', 'MST_DAILY_QUEST_NAME_' + str(q['id']))
        row.setdefault('detail_key', 'MST_DAILY_QUEST_DETAIL_' + str(q['id']))
        out.append(row)
    return out


def pools() -> dict:
    return dict(doc().get('pools') or {})


def _seed(*parts) -> int:
    return int(hashlib.sha256('|'.join(map(str, parts)).encode()).hexdigest()[:8], 16)


def reward(quest: dict, day: str) -> str:
    """The day's reward string for a custom quest (full form, metadata included)."""
    options = (doc().get('tiers') or {}).get(str(quest.get('tier') or 1)) or []
    if not options:
        return ''
    return str(options[_seed(day, quest.get('id')) % len(options)])


def show(text: str) -> str:
    """What the row draws: kind:id:count only, Lapis after the multiplier (that is what is paid)."""
    from lapis_economy import earned
    out = []
    for part in filter(None, str(text).split(',')):
        f = part.split(':')
        if f[0] == '50' and len(f) >= 3:
            f = ['50', f[1], str(earned(int(f[2])))]
        out.append(':'.join(f[:3]))
    return ','.join(out)


def grant(text: str) -> list:
    """The claim's reward rows, Lapis after the multiplier (granted with the multiplier skipped)."""
    from exvius_rewards import parse
    from lapis_economy import earned
    rows = parse(text)
    for row in rows:
        if row['kind'] == 50:
            row['count'] = earned(row['count'])
    return rows
