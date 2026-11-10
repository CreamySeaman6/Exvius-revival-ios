"""Collection points in explorations (operator's report, 2026-11-10: none could be found in Dalnakya Cavern).

How the client handles them (GL9 libgame):
  * A collection point is a map event of type 14 (採取). It is drawn and can be touched only while the
    point id is in `HarvestDetailInfoList` and has not been collected this run
    (`MapEventData::isEventEnable` 0x1fc5b5c, `checkPage` 0x1fc58a4). That list is filled from the reply
    group `vM21k0do` (`GameResponseFactory` -> `HarvestDetailInfoResponse::readParam` 0x1977bd0):
    `N3hB0CwE` point id, `9GIvAQC2` a number (unused by the map), `1Fa7rL5R` rewards `kind:id:count,...`.
    Nothing served it, so no point ever showed.
  * Touching one (`MapScriptData::doScript` opcode 0x50, 0x1fcc9c8) gives every reward listed for that
    point: shown on the map and added to the result with source 6, which the mission-end request reports
    in `09HRWXDf` as `EWmQy52k` / `XMgu7qE0` / `1Z2TD5ai` / `7rA9WGQe` (kinds 20 / 21 / 22 / 23,
    `MissionResultInfoBase::getItemCsv(kind, 6)`); the result reply reads the same four.

So: the exploration's load reply gets one row per point with that run's reward, rolled from
content/collection_points.json (ios-server/devtools/build_collection_points.py, Global's lists from the
FFBE wiki) and kept on the loaded attempt; the mission end pays what the request reports, up to what was
rolled for that attempt, once, and lists it on the result screen. Explorations whose points have no record
get an empty group (which also clears the previous exploration's points: maps reuse ids).
`EXVIUS_COLLECTION_POINTS=0` serves nothing (no points, as before).
"""
from __future__ import annotations

import copy
import json
import os
import random

from ffbe_state import State, _note

GROUP = 'vM21k0do'
POINT, NUMBER, REWARDS = 'N3hB0CwE', '9GIvAQC2', '1Fa7rL5R'
RESULT = '09HRWXDf'
CHANNELS = {20: 'EWmQy52k', 21: 'XMgu7qE0', 22: '1Z2TD5ai', 23: '7rA9WGQe'}
PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'content', 'collection_points.json')
_DOC: dict | None = None


def enabled() -> bool:
    return str(os.environ.get('EXVIUS_COLLECTION_POINTS', '1')).strip().lower() not in ('0', 'off', 'false', 'no')


def _doc() -> dict:
    global _DOC
    if _DOC is None:
        try:
            with open(PATH, encoding='utf-8') as fh:
                _DOC = json.load(fh)
        except (OSError, ValueError) as exc:
            print(f'collection points: {PATH} not loadable ({exc!r}); none served', flush=True)
            _DOC = {}
    return _DOC


def _is_exploration(mid) -> bool:
    from player_state import mission_row
    return str((mission_row(mid) or {}).get('Y4VoF8yu')) == '2'


def roll(mid, rng=random) -> dict:
    """point id -> 'kind:id:count' for one run of this exploration."""
    doc = _doc()
    out = {}
    for pid, key in doc.get('missions', {}).get(str(mid), []):
        items = (doc.get('pools', {}).get(key) or {}).get('items') or []
        if not items:
            continue
        kind, iid, _, lo, hi = rng.choices(items, weights=[i[2] for i in items])[0]
        out[str(pid)] = f'{kind}:{iid}:{rng.randint(int(lo), int(hi))}'
    return out


def serve(spec, mid, is_battle_bundle):
    """Pipeline step on an exploration's load reply: the run's points and what each gives."""
    if (not enabled() or not is_battle_bundle or not isinstance(spec, dict) or RESULT in spec
            or State.player is None or not mid or not _is_exploration(mid)):
        return spec
    attempt = State.player.data.get('exvius_repeat', {}).get('attempt', {})
    if attempt.get('mid') != str(mid):
        return spec
    rolled = attempt.get('collection')
    if not isinstance(rolled, dict):
        rolled = roll(mid)
        if State.player.mode != 'frozen':
            attempt['collection'] = rolled
            State.player.dirty = True
            State.state_dirty = True
    out = dict(spec)
    out[GROUP] = [{POINT: pid, NUMBER: '1', REWARDS: reward} for pid, reward in rolled.items()]
    if rolled:
        print(f'collection points: {mid} {len(rolled)} point(s) ' + ' '.join(f'{p}={r}' for p, r in rolled.items()),
              flush=True)
    return out


def _reported(request) -> dict:
    """(kind, id) -> count the mission-end request reports as collected."""
    rows = request.get(RESULT) if isinstance(request, dict) else None
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return {}
    out = {}
    for kind, channel in CHANNELS.items():
        for entry in str(rows[0].get(channel) or '').split(','):
            f = entry.split(':')
            if len(f) >= 3 and all(x.isdigit() for x in f[:3]) and int(f[0]) == kind and int(f[2]) > 0:
                out[(kind, int(f[1]))] = out.get((kind, int(f[1])), 0) + int(f[2])
    return out


def pay(spec, mid, plaintext):
    """Pipeline step on the mission end: pay what was collected, once per loaded run, and list it."""
    if (not enabled() or not isinstance(spec, dict) or RESULT not in spec or not plaintext or not mid
            or State.player is None or State.player.mode == 'frozen'):
        return spec
    attempt = State.player.data.get('exvius_repeat', {}).get('attempt', {})
    rolled = attempt.get('collection')
    # Same receipt as the chests: the loaded run, completed, its normal rewards recorded.
    if (attempt.get('mid') != str(mid) or not isinstance(rolled, dict) or attempt.get('status') != 'completed'
            or not attempt.get('normal_rewards_recorded')):
        return spec
    paid = attempt.get('collection_paid')
    if paid is None:
        try:
            request = json.JSONDecoder().raw_decode(plaintext)[0]
        except (ValueError, TypeError):
            return spec
        served = {}
        for reward in rolled.values():
            kind, iid, count = map(int, reward.split(':'))
            served[(kind, iid)] = served.get((kind, iid), 0) + count
        reported = _reported(request)
        grants = [{'kind': k, 'id': i, 'count': min(n, served[(k, i)])}
                  for (k, i), n in sorted(reported.items()) if (k, i) in served]
        extra = {key: n for key, n in reported.items() if key not in served or n > served[key]}
        if extra:
            _note(f'collection points: {mid} reported more than was served, not paid: {extra}')
        player = State.player
        before, dirty_before = copy.deepcopy(player.data), player.dirty
        try:
            if grants and player._grant_items(grants) != grants:
                raise RuntimeError('partial collection point grant')
        except Exception:
            player.data, player.dirty = before, dirty_before
            raise
        attempt = player.data['exvius_repeat']['attempt']
        paid = attempt['collection_paid'] = [f"{g['kind']}:{g['id']}:{g['count']}" for g in grants]
        player.dirty = True
        State.state_dirty = True
        if paid:
            print(f'collection points: {mid} paid ' + ','.join(paid), flush=True)
    if not paid:
        return spec
    # A retried request lists the same result again; it is paid only once.
    out = copy.deepcopy(spec)
    for row in out.get(RESULT, []):
        if isinstance(row, dict):
            for kind, channel in CHANNELS.items():
                entries = [e for e in paid if int(e.split(':')[0]) == kind]
                if entries:
                    row[channel] = ','.join(entries)
    return out
