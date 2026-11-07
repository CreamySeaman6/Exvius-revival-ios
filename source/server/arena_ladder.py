"""Arena ladder: full rival teams, opponent ratios, a weekly leaderboard and placement rewards.

Global's last Arena (the client this server talks to): you pick an opponent from a list that changes every
10 minutes; each opponent is another player's team (up to five units, AI-controlled) with a ratio between
0.50 and 1.50; a win pays ratio x 100 ranking points (plus streak and unit bonuses), a loss 10; points
reset every week and the week's final rank pays a bracket reward (Brave Exvius wiki, "Arena", rev 313327).

Offline, the other players are the made-up accounts of friend_players.py:

  * Teams. Each player fields five units for the week: their lent unit as leader plus four more from the
    same pool (units released by this week's point in history with the replay on). The wire format is
    one ';'-separated entry per unit (UserRbVsInfoResponse::readParam 0x1928fac). Each stat is a
    `base-bonus` pair; the bonus stands in for equipment the made-up players don't have, scaled by how
    strong the player is.
  * Ratio. Their team's power over yours (party stats with equipment), clamped to the master's
    0.50-1.50 (F_RB_DEFINE_MST), in steps of 0.05. A win pays ratio x 100 before bonuses.
  * Leaderboard. Each player has a weekly target score; the strongest reaches about EXVIUS_ARENA_TOP
    (default 12000) by the end of the week. Scores grow through the week at each player's own pace, so the
    board moves while you play. Weeks follow the summon rotation (Sunday 10 PM by default).
  * Placement. At the week's end your rank among all players is placed on Global's scale (rank / players x
    300,000, Global's last bracket edge) and paid from that week's season reward table (F_RB_SS_REWARD_MST):
    with 200 players, ranks 1-2 get the top bracket (Global 1-3000), 3-20 the next, and so on.
  * Season. With the historical replay on, each week uses the Global weekly season (F_RB_SS_MST) that was
    running at the start of that week's slice of history: its banned ability types, bonus units, daily
    rewards and ranking rewards. Without the replay, the last shipped season.

Everything is derived from the player id and the week; only your own points and results are saved.
"""
from __future__ import annotations

import math
import os
import random
import time
from datetime import datetime, timezone

GLOBAL_LAST_BRACKET = 300000
REFRESH_SECONDS = 600


def _int_env(name, default):
    try:
        return max(0, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def top_score():
    return _int_env('EXVIUS_ARENA_TOP', 12000)


def list_size():
    return max(1, min(10, _int_env('EXVIUS_ARENA_RIVALS', 5)))


def enabled():
    import friend_players
    return friend_players.enabled()


# --- the week and its season ---------------------------------------------------------------------------

def week(now=None):
    """(number, start, end) of the current rotation week (gacha_rotation.week)."""
    import gacha_rotation
    return gacha_rotation.week(now)


def _mst(name, key):
    from exvius_actions import _mst as load
    return load(name, key)


def season_id(now=None):
    """The F_RB_SS_MST weekly season for this week: the replay's point in history, else the last shipped."""
    seasons = [r for k, r in _mst('F_RB_SS_MST.ndjson', '6Z9DxQFf').items() if str(k).isdigit() and int(k) > 0]
    if not seasons:
        return '0'
    seasons.sort(key=lambda r: r.get('VjJQ51uG', ''))
    try:
        import replay
        win = replay.window(now) if replay.enabled() else None
    except Exception:  # noqa: BLE001 -- no replay: the last season
        win = None
    if win and not win['finished']:
        moment = win['from'].isoformat() + ' 23:59:59'
        started = [r for r in seasons if r.get('VjJQ51uG', '') <= moment]
        return str((started[-1] if started else seasons[0])['6Z9DxQFf'])
    return str(seasons[-1]['6Z9DxQFf'])


# --- players and their teams ---------------------------------------------------------------------------

def players():
    """The made-up players (friend_players), this week's entries."""
    import friend_players
    return [friend_players.player(i) for i in range(1, friend_players._count() + 1)]


def by_id(friend_id):
    import friend_players
    return friend_players.by_id(friend_id)


def _strength(friend_id, number):
    """0..1: how strong and how active this player is this week (heavy tail: few strong players)."""
    rng = random.Random(f'arena-strength-{friend_id}-{number}')
    base = random.Random(f'arena-persona-{friend_id}').random()      # stable across weeks
    return min(1.0, max(0.0, 0.75 * base ** 1.8 + 0.25 * rng.random() ** 2))


def team(friend, number=None):
    """Five unit dicts (leader first): master_id, level, lb_level, instance_id, gear (bonus fraction)."""
    import friend_players
    from player_state import limit_burst
    number = week()[0] if number is None else number
    leader = friend['unit']
    pool = friend_players._unit_pool(int(friend.get('rank') or 1)) or [(str(leader['master_id']), leader['level'])]
    rng = random.Random(f"arena-team-{friend['friend_id']}-{number}")
    picks, seen = [], {str(leader['master_id'])}
    for uid, level in rng.sample(pool, min(len(pool), 12)):
        if uid not in seen and len(picks) < 4:
            seen.add(uid)
            picks.append((uid, level))
    gear = 0.25 + 0.35 * _strength(friend['friend_id'], number)
    units = [{'master_id': str(leader['master_id']), 'level': int(leader['level']),
              'lb_level': int(leader.get('lb_level') or 0)}]
    units += [{'master_id': uid, 'level': int(level), 'lb_level': 1 if limit_burst(uid) else 0}
              for uid, level in picks]
    for order, unit in enumerate(units):
        unit['instance_id'] = str(int(friend['friend_id']) * 10 + order + 1)
        unit['gear'] = gear
    return units


def _base(unit):
    from player_state import unit_stats
    return unit_stats(unit['master_id'], unit['level'])


def _power(stats):
    hp, mp, atk, df, mag, spr = stats
    return hp / 10 + mp / 10 + atk + df + mag + spr


def team_power(units):
    return sum(_power([round(v * (1 + u['gear'])) for v in _base(u)]) for u in units)


def own_power(party):
    """Your party: unit stats (with pots, NV EX and EX bonuses) plus equipment."""
    from player_state import owned_unit_stats
    equipment = _mst('F_EQUIP_ITEM_MST.ndjson', 'J1YX9kmM')
    tokens = ('fh31sk7B', 'PC97pWQj', '9NBV1XCS', 'Pn5w9dfh', '84FJM3PD', 'T8xMDAZ4')
    total = 0
    for unit in party:
        stats = list(owned_unit_stats(unit))
        worn = unit.get('equipment') or {}
        for iid in (worn.values() if isinstance(worn, dict) else worn):
            row = equipment.get(str(iid))
            if row:
                stats = [s + int(row.get(t) or 0) for s, t in zip(stats, tokens)]
        total += _power(stats)
    return max(1.0, total)


def ratio(units, party):
    """Hundredths, 50..150 in steps of 5 (F_RB_DEFINE_MST: XfWEsM97 50, w97U1BmN 150)."""
    value = 100 * team_power(units) / own_power(party)
    return int(min(150, max(50, round(value / 5) * 5)))


def rival_string(units):
    """UserRbVsInfo VsBattleInfo: one ':'-separated entry per unit, ';' between units (leader type 0)."""
    from player_state import limit_burst
    patterns = list(_mst('F_RB_AI_PATTERN_MST.ndjson', 'UE3vKA5y').values())
    total = sum(int(row['ixDq7yJ8']) for row in patterns)
    entries = []
    for order, unit in enumerate(units):
        draw = random.Random(f"arena-ai-{unit['instance_id']}-{time.time_ns()}").randrange(total)
        pattern = patterns[-1]['UE3vKA5y']
        for row in patterns:
            draw -= int(row['ixDq7yJ8'])
            if draw < 0:
                pattern = row['UE3vKA5y']
                break
        stats = [f'{v}-{round(v * unit["gear"])}' for v in _base(unit)]
        lb = str(max(int(unit['lb_level']), 1 if limit_burst(unit['master_id']) else 0))
        equipment = '@'.join(f'{i + 1}-0' for i in range(6))
        materia = '@'.join(f'{i + 1}-0' for i in range(4))
        entries.append(':'.join([unit['instance_id'], unit['master_id'], unit['master_id'], str(unit['level']),
                                 *stats, lb, equipment, materia, '', '', '0' if order == 0 else '1',
                                 str(order), pattern]))
    return ';'.join(entries)


# --- the weekly leaderboard ----------------------------------------------------------------------------

_TARGETS: dict = {}


def _targets(number):
    """friend id -> this week's final score; the best close to top_score(). Cached per week."""
    key = (number, top_score(), len(players()))
    if key not in _TARGETS:
        if len(_TARGETS) > 8:
            _TARGETS.clear()
        _TARGETS[key] = _compute_targets(number)
    return _TARGETS[key]


def _compute_targets(number):
    rows = players()
    raw = {}
    for friend in rows:
        rng = random.Random(f"arena-target-{friend['friend_id']}-{number}")
        raw[friend['friend_id']] = _strength(friend['friend_id'], number) ** 1.4 * rng.uniform(0.85, 1.0)
    best = max(raw.values(), default=1) or 1
    jitter = random.Random(f'arena-top-{number}').uniform(0.94, 1.0)
    return {fid: int(round(top_score() * jitter * value / best / 10) * 10) for fid, value in raw.items()}


def points(friend_id, now=None, number=None, start=None, end=None):
    """A player's score at `now`: their target times their progress through the week."""
    if number is None:
        number, start, end = week(now)
    target = _targets(number).get(friend_id, 0)
    moment = now or datetime.now(timezone.utc)
    span = max(1.0, (end - start).total_seconds())
    done = min(1.0, max(0.0, (moment - start).total_seconds() / span))
    pace = random.Random(f'arena-pace-{friend_id}-{number}').uniform(0.7, 1.4)
    return int(target * done ** pace) // 10 * 10


def standings(own_points, now=None):
    """[(points, friend or None for you)], best first; ties go to the made-up player."""
    number, start, end = week(now)
    rows = [(points(f['friend_id'], now, number, start, end), f) for f in players()]
    rows.sort(key=lambda r: (-r[0], r[1]['friend_id']))
    you = sum(1 for p, _f in rows if p >= own_points) + 1
    rows.insert(you - 1, (own_points, None))
    return rows


def rank_of(own_points, now=None):
    return next(i for i, (_p, f) in enumerate(standings(own_points, now), 1) if f is None)


def ranking_entries(own_points, user, now=None, limit=100):
    """RbRankingListInfo entries: friendId:name:unitId:unitLv:totalPoint:rank:lv:rate:emblem:frame
    (RbRankingListInfoResponse::readParam 0x197f1a4, ten fields minimum). Top `limit` and you."""
    out = []
    for rank, (pts, friend) in enumerate(standings(own_points, now), 1):
        if rank > limit and friend is not None:
            continue
        if friend is None:
            out.append(':'.join(map(str, (user['id'], _clean(user['name']), user['unit'], user['unit_level'],
                                          pts, rank, user['rank'], 100, 0, 0))))
        else:
            out.append(':'.join(map(str, (friend['friend_id'], _clean(friend['display_name']),
                                          friend['unit']['master_id'], friend['unit']['level'], pts, rank,
                                          friend['rank'], 100, friend['emblem_id'], 0))))
    return ','.join(out)


def _clean(name):
    return str(name).replace(':', ' ').replace(',', ' ').replace(';', ' ')


def candidates(own_points, party, now=None):
    """This 10-minute window's opponents: (friend, units, ratio), a spread from weaker to stronger."""
    number, start, end = week(now)
    window = int(time.time() // REFRESH_SECONDS)
    rows = players()
    rng = random.Random(f'arena-list-{number}-{window}')
    picked = rng.sample(rows, min(len(rows), list_size() * 3))
    scored = []
    for friend in picked:
        units = team(friend, number)
        scored.append((ratio(units, party), friend, units))
    scored.sort(key=lambda r: r[0])
    if len(scored) > list_size():
        step = (len(scored) - 1) / (list_size() - 1) if list_size() > 1 else 0
        scored = [scored[round(i * step)] for i in range(list_size())]
    return [(friend, units, rate) for rate, friend, units in scored]


def candidate_entries(rows, now=None):
    """RbMatchingListInfo entries, same field order as the ranking list."""
    number, start, end = week(now)
    board = standings(-1, now)
    rank = {f['friend_id']: i for i, (_p, f) in enumerate(board, 1) if f is not None}
    out = []
    for friend, _units, rate in rows:
        out.append(':'.join(map(str, (friend['friend_id'], _clean(friend['display_name']),
                                      friend['unit']['master_id'], friend['unit']['level'],
                                      points(friend['friend_id'], now, number, start, end),
                                      rank.get(friend['friend_id'], 0), friend['rank'], rate,
                                      friend['emblem_id'], 0, 0))))
    return ','.join(out)


# --- placement --------------------------------------------------------------------------------------------

def placement(final_rank, total):
    """Your rank on Global's scale: the bracket edges in F_RB_SS_REWARD_MST run to rank 300,000."""
    return max(1, math.ceil(final_rank / max(1, total) * GLOBAL_LAST_BRACKET))


def reward_row(season, global_rank):
    rows = [r for r in _mst('F_RB_SS_REWARD_MST.ndjson', None)['__rows__']
            if r['6Z9DxQFf'] == str(season) and r['vs48LZrt'] == '0']
    for row in sorted(rows, key=lambda r: int(r['ip94Nqb7'])):
        if int(row['ip94Nqb7']) <= global_rank <= int(row['XM4Ca3PF']):
            return row
    return max(rows, key=lambda r: int(r['XM4Ca3PF']), default=None)
