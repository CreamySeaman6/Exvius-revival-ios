"""Bonuses printed on the summon banners: paid even where the banner data left them out.

Global's banner art advertised extras on top of the units: "free 4★ Trust Moogles with every 10+1", "get 1
FFBE Heroes Coin for every 10+1", and from October 2020 "a guaranteed 5★/NV unit and a Summon Coin with
every 11 summon". Most of the archived banners carry the units and rates but not those extras.
banner_deals.json lists them per banner id, read by hand from each banner's art (2026-11-05):

  * `ten_plus_one`: goes into the banner's 10+1 offer (`secondary_offer`): `bonus_rewards` (paid on every
    10+1), `bonus_choice` (one of the listed rewards, by weight, on every 10+1) and `guarantee`
    (`{"rarity": 5}` = at least one 5★ base or NV unit in the 11).
  * `every_pull`: `bonus_rewards` paid on every summon, single or 10+1.

Data the banner already has always wins: a reward list or choice it already carries is kept, and a guarantee
is only raised, never lowered. Trust Moogles use the shapes player_state already pays: a moogle for any
unit (`affinity_points` only) or for one unit's Trust Master reward (`affinity_info` = that unit's own
trust reward string). Coins are the ones the summon screen's exchange shops take.

EXVIUS_BANNER_DEALS=0 turns this off.
"""
from __future__ import annotations

import copy
import json
import os
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))


def enabled() -> bool:
    return os.environ.get("EXVIUS_BANNER_DEALS", "1") == "1"


@lru_cache(maxsize=1)
def deals() -> dict:
    try:
        with open(os.path.join(HERE, "banner_deals.json"), encoding="utf-8") as fh:
            return json.load(fh).get("banners", {})
    except (OSError, ValueError):
        return {}


def _rarity(guarantee) -> int:
    try:
        return int((guarantee or {}).get("rarity") or 0)
    except (TypeError, ValueError):
        return 0


def apply(banner: dict) -> dict:
    """The banner with its printed bonuses added (a copy), or the banner itself when it has none."""
    if not enabled():
        return banner
    deal = deals().get(str(banner.get("id")))
    if not deal:
        return banner
    out = dict(banner)
    ten = deal.get("ten_plus_one") or {}
    offer = out.get("secondary_offer")
    if ten and isinstance(offer, dict) and offer:
        offer = dict(offer)
        for key in ("bonus_rewards", "bonus_choice"):
            if ten.get(key) and not offer.get(key):
                offer[key] = copy.deepcopy(ten[key])
        want = ten.get("guarantee")
        if want and _rarity(want) > _rarity(offer.get("guarantee")):
            # The pool the old guarantee drew from was filtered for its own rarity; let the new one draw from
            # the banner's pool (everything at or above the new rarity, by rate).
            offer["guarantee"] = copy.deepcopy(want)
        out["secondary_offer"] = offer
    every = deal.get("every_pull") or {}
    if every.get("bonus_rewards") and not out.get("bonus_rewards"):
        out["bonus_rewards"] = copy.deepcopy(every["bonus_rewards"])
    return out
