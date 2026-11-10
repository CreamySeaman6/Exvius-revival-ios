"""Story units join when the story reaches them (operator's report, 2026-11-10).

Global's story handed these units over at fixed points; this server never did, so they only ever came from
summons (now stopped, summon_exclusions.py). Where each joins is the FFBE wiki's (unit pages' Trivia, saved in
ios-server/research/wiki/units/; Runda from the "General Quests" page and his quest's own row in
`F_SP_CHALLENGE_MST`, 9908205 `15:14010503` -> `10:100037407`, a quest group this server doesn't offer).
The others are in no shipped reward column. Rain and Lasswell are the starting roster (player_state).

A unit joins once per save, the first time a user-state or quest-end reply finds one of its trigger quests in
the save's cleared list, so saves already past the point get it at their next login. The roster projection
in the same reply shows it. `EXVIUS_STORY_UNITS=0` turns it off.
"""
from __future__ import annotations

import os

LEDGER = "story_units"

# unit id, trigger missions (any one), level it joins at, where the wiki says it joins
JOINS = (
    ("100000302", ("1120704",), 20, "Fina: after Lechios Hills (Bandit's Hideout), Lanzelt; joins at level 20"),
    ("100000503", ("1220505",), 1, "Lid: after Galebreak (Beast in the Storm), Dirnado"),
    ("100000403", ("1320905",), 1, "Nichol: after the Water Shrine (Will of the Ferocious), Olderion"),
    ("100000703", ("1420606",), 1, "Jake: after Invincible Interior (Conclusion), Zoldaad"),
    ("100000603", ("1510506",), 1, "Sakura: after Magic Library - Showdown of Destiny, Mysidia"),
    ("100025705", ("11810702", "11810703"), 1,
     "Blue Mage Fina: the Season 3 opening, Our Tomorrow - Starting on a New Journey, Paladia"),
    ("100037407", ("14010503",), 1, "Runda: Season 4, clear Trail to Yorte - Underground Nest (General Quest)"),
)


def enabled() -> bool:
    return str(os.environ.get("EXVIUS_STORY_UNITS", "1")).strip().lower() not in ("0", "off", "false", "no")


def due(player) -> list:
    """The JOINS rows whose trigger is cleared and that this save hasn't been given yet."""
    cleared = set(map(str, player.data.get("progress", {}).get("cleared_missions", [])))
    joined = set((player.data.get(LEDGER) or {}).get("joined", []))
    return [j for j in JOINS if j[0] not in joined and cleared.intersection(j[1])]


def grant(spec, reply_id=None):
    """Pipeline step: add every story unit that is due to the roster, once per save."""
    from ffbe_config import RESULT_TAG, USER_STATE_GROUPS
    from ffbe_state import State
    player = State.player
    if (not enabled() or player is None or player.mode == "frozen" or not isinstance(spec, dict)
            or not (RESULT_TAG in spec or any(tag in spec for tag in USER_STATE_GROUPS))):
        return spec
    for uid, _missions, level, where in due(player):
        unit = player.grant_unit(uid)
        if unit is None:
            return spec
        if level > 1:
            player.set_unit_level(unit["instance_id"], level)
        led = player.data.setdefault(LEDGER, {})
        led.setdefault("joined", []).append(uid)
        player.dirty = True
        State.state_dirty = True
        print(f"story units: {where.split(':')[0]} joined ({uid}, level {level})", flush=True)
    return spec
