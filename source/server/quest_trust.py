"""Trust from clearing quests (operator's request, 2026-11-07).

Global's rule, as the community recorded it (exvius.fandom.com "Best places to farm", GameFAQs "Trust farming
101"): on every successful clear, each unit of the player's own party rolls separately, about a 10% chance of
+0.1% trust (1 point; 1000 = 100%). The quest's type, energy cost, length and difficulty don't matter; the
friend's unit gains nothing; an exploration rolls once, at its end, not per encounter. Japan's guides (Altema)
give a different rule for JP: a 30% chance of +1% (10 points). The game's tables hold no trust-gain value: it
was decided by the original server.

Settings:

  EXVIUS_QUEST_TRUST (default 1)          0 turns quest trust off.
  EXVIUS_QUEST_TRUST_CHANCE (default 30)  percent chance per party unit per clear (0-100, decimals allowed).
  EXVIUS_QUEST_TRUST_POINTS (default 10)  trust added on a hit, in tenths of a percent (1 = 0.1%, 10 = 1%).
  EXVIUS_QUEST_TRUST_BIG_CHANCE (default 5)   percent of hits that are a big hit instead (operator's request,
                                              2026-11-07: a low chance of +5%). 0 = none.
  EXVIUS_QUEST_TRUST_BIG_POINTS (default 50)  trust added on a big hit (50 = 5%).

Every unit rolls on its own. With the defaults a unit's chance per clear is 28.5% for +1% and 1.5% for +5%,
about 0.36% expected, so roughly 280 clears for 100%.

The defaults are JP's rule (operator's choice, 2026-11-07: Global's is far too slow next to this server's Lapis
income). Global's is CHANCE=10, POINTS=1. Expected gain per unit per clear = CHANCE/100 x POINTS/10 percent:
0.3% with the defaults (about 330 clears for 100%), 0.01% with Global's (about 10,000).

Where it runs: `ffbe_battle._credit_mission_rewards`, once per loaded attempt and only when the end report says
the mission was cleared. The before/after values go out in the result's `Qic38SuC` rows (field 9, the client's
param 27, which `ResultUnitExpScene::setTrustExp` and `MissionResultUnitInfo::addAffinityPoint` animate,
including the Trust Master reward pop-up), and the reward is credited by `PlayerState.gain_trust`.
"""
from __future__ import annotations

import os
import secrets


def enabled() -> bool:
    return os.environ.get('EXVIUS_QUEST_TRUST', '1').strip() not in ('0', 'false', 'off', '')


def chance() -> float:
    try:
        return min(100.0, max(0.0, float(os.environ.get('EXVIUS_QUEST_TRUST_CHANCE', '30'))))
    except ValueError:
        return 30.0


def points() -> int:
    try:
        return max(0, int(os.environ.get('EXVIUS_QUEST_TRUST_POINTS', '10')))
    except ValueError:
        return 10


def big_chance() -> float:
    try:
        return min(100.0, max(0.0, float(os.environ.get('EXVIUS_QUEST_TRUST_BIG_CHANCE', '5'))))
    except ValueError:
        return 5.0


def big_points() -> int:
    try:
        return max(0, int(os.environ.get('EXVIUS_QUEST_TRUST_BIG_POINTS', '50')))
    except ValueError:
        return 50


def _hit(percent: float) -> bool:
    # Hundredths of a percent, so 0.5 or 12.5 work.
    return secrets.randbelow(10000) < round(percent * 100)


def roll(player, instance_ids) -> dict:
    """Roll trust for each party unit and credit the hits. Returns {instance id: (before, after)} for every
    unit that has a trust channel (unchanged ones as (n, n)), plus key '_rewards' with the Trust Master
    rewards granted."""
    out = {'_rewards': []}
    if player is None or not enabled():
        return out
    amount, percent = points(), chance()
    for iid in instance_ids:
        unit = player.roster_row(iid)
        if unit is None:
            continue
        current = (list(unit.get('affinity_points') or ['']) + [''])[0]
        current = int(current) if str(current).isdigit() else 0
        out[str(iid)] = (current, current)
        if amount <= 0 or not _hit(percent):
            continue
        result = player.gain_trust(iid, big_points() if big_points() and _hit(big_chance()) else amount)
        if result:
            before, after, rewards = result
            out[str(iid)] = (before, after)
            out['_rewards'] += rewards
    return out
