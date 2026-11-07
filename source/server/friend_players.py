"""Other players: 200 made-up accounts you can find, add as friends, borrow units from and remove again.

friends.yaml holds the hand-picked friends. This module adds a crowd around them, so the friend screens,
the companion list and the "send gifts to N friends" daily quests have people in them:

  * EXVIUS_PLAYERS (default 200) accounts with gaming/anime handles, ids 910000001 and up, a Rank each;
  * each one lends a different unit every week (Sunday rollover, same week as the summon rotation). With
    the historical replay on, only units already released by then are lent (replay.released_by);
  * Friend > Suggestions shows EXVIUS_PLAYER_SUGGESTIONS (default 10) of them, changing daily; Friend >
    Search finds any of them by id;
  * a friend request is accepted at once (no one is on the other end to accept it), and Remove works.
    Who you have added or removed is kept in your save (player.data["exvius_friends"]).
  * EXVIUS_START_FRIENDS (default 15) of them are already your friends in a new save, so the gift
    quests can be done from day one. Remove any you don't want.

Everything is derived from the friend id, the week and the day, so nothing about the crowd is stored
except your own adds and removals. EXVIUS_PLAYERS=0 turns the crowd off.
"""
from __future__ import annotations

import os
import random
import time

ID_BASE = 910000000

_PARTS_A = [
    "Moogle", "Chocobo", "Cactuar", "Tonberry", "Kupo", "Mako", "Lapis", "Limit", "Esper", "Mithril",
    "Phoenix", "Crystal", "Ultima", "Omega", "Zodiac", "Behemoth", "Malboro", "Bomb", "Ahriman", "Coeurl",
    "Senpai", "Kaiju", "Shonen", "Sakura", "Kitsune", "Ronin", "Shinobi", "Mecha", "Neko", "Oni",
    "Tsundere", "Isekai", "Ramen", "Bento", "Mochi", "Tanuki", "Kawaii", "Sensei", "Chibi", "Yokai",
    "Pixel", "Turbo", "Combo", "Critical", "Rare", "Rainbow", "Gacha", "Speedrun", "Respawn", "Loot",
]
_PARTS_B = [
    "Main", "Slayer", "Knight", "Sage", "Blade", "Hunter", "Dreamer", "Kun", "Chan", "Sama",
    "Prime", "Zero", "Rising", "Breaker", "Lord", "Rider", "Mage", "Ninja", "Bard", "Tamer",
    "Whale", "Fan", "Pilot", "Smith", "Fist", "Storm", "Fang", "Heart", "Soul", "Star",
]
_HANDLES = [
    "LimitBreakLu", "ChainItAll", "PullForNoctis", "XxDarkFinaxX", "RainbowRain", "TrustMeBro",
    "NoLapisNoLife", "SummonAddict", "KupoKupoKupo", "MogKingFan", "OnlyChains", "DualcastDan",
    "GilSnapper", "BraveShifter", "TMRhunter", "VortexVet", "ArenaAce", "ExpeditionEd",
    "OneMorePull", "SaltyRNG", "PityTimer", "GuaranteedGG", "WhaleWatcher", "F2Pforever",
    "MasterTrust", "SevenStarSam", "SoulCrystal", "MegacrystalM", "AwakenedAmy", "PrismPrince",
    "CrystalChaser", "ElementalEli", "KillerChains", "MultiCaster", "TankNTaunt", "CoverGod",
    "StopKillers", "BreakerBob", "AilmentAndy", "EvokerEve", "BlueMageBo", "BardicBella",
    "SamuraiSoul", "DragoonDash", "JumpingJin", "NinjaNoodle", "MonkMode", "PaladinPam",
    "DarkKnightDK", "SpellbladeSi", "ChemistKai", "ThiefTaro", "TimeMageTia", "GeomancerGo",
    "OtakuOracle", "ShonenJump", "MechaPilot", "IsekaiIvy", "KawaiiKaiju", "SenpaiNotice",
    "RamenRonin", "NekoNinja", "ChibiChamp", "AnimeAlex", "MangaMax", "CosplayCam",
    "PixelPaladin", "RetroRyu", "SpeedrunSol", "ComboCarl", "FrameDataFi", "HitboxHana",
]


def enabled() -> bool:
    return _count() > 0


def _count() -> int:
    try:
        return max(0, min(999, int(os.environ.get("EXVIUS_PLAYERS", "200"))))
    except ValueError:
        return 200


def _int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def names(count: int | None = None) -> list[str]:
    """`count` unique handles of at most 12 characters, the same every time."""
    count = _count() if count is None else count
    out, seen = [], set()
    for name in _HANDLES:
        if len(name) <= 12 and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    rng = random.Random("exvius-players")
    combos = [a + b for a in _PARTS_A for b in _PARTS_B if len(a + b) <= 12]
    rng.shuffle(combos)
    for name in combos:
        if len(out) >= count:
            break
        if rng.random() < 0.25:
            name += str(rng.randint(1, 99))
            if len(name) > 12:
                continue
        if name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    order = list(range(len(out)))
    random.Random("exvius-players-order").shuffle(order)
    return [out[i] for i in order][:count]


def _week() -> int:
    try:
        import gacha_rotation
        return gacha_rotation.week()[0]
    except Exception:  # noqa: BLE001 -- ISO week as a fallback
        return int(time.strftime("%G%V"))


def _unit_pool(rank: int) -> list[tuple[str, int]]:
    """(unit id, level) choices for a player of this rank: base forms with an English name, released by
    this week's point in history when the replay is on."""
    from player_state import named_unit_ids, unit_roots_by_rarity
    cutoff = None
    try:
        import replay
        cutoff = replay.pool_cutoff()
    except Exception:  # noqa: BLE001
        cutoff = None
    named = named_unit_ids()
    roots = unit_roots_by_rarity()
    levels = {"4": 60, "5": 80, "7": 99}
    rarities = ["5", "7"] if rank >= 100 else ["4", "5"] if rank < 40 else ["4", "5", "7"]
    out = []
    for rarity in rarities:
        for uid in roots.get(rarity, []):
            if uid.startswith("9") or (named and uid not in named):
                continue
            if cutoff is not None:
                import replay
                if not replay.released_by(uid, cutoff):
                    continue
            out.append((uid, levels[rarity]))
    return out


_POOLS: dict = {}


_PLAYERS: dict = {}


def player(index: int) -> dict:
    """Player `index` (1-based) as a friends.yaml-style entry, with this week's unit. Cached per week."""
    week = _week()
    key = (index, week)
    if key not in _PLAYERS:
        if len(_PLAYERS) > 4 * _count():
            _PLAYERS.clear()
        _PLAYERS[key] = _player(index, week)
    return _PLAYERS[key]


def _player(index: int, week: int) -> dict:
    from ffbe_friends import _entry
    rng = random.Random(f"exvius-player-{index}")
    rank = rng.choice([rng.randint(8, 40), rng.randint(40, 120), rng.randint(120, 250), rng.randint(60, 180)])
    pool_key = (week, min(rank // 40, 3))
    if pool_key not in _POOLS:
        _POOLS.clear() if len(_POOLS) > 8 else None
        _POOLS[pool_key] = _unit_pool(rank)
    pool = _POOLS[pool_key] or [("100000102", 1)]
    uid, level = random.Random(f"exvius-player-{index}-week-{week}").choice(pool)
    raw = {"display_name": names()[index - 1], "friend_id": ID_BASE + index, "rank": rank, "emblem_id": 0,
           "unit": {"master_id": uid, "level": level}}
    try:
        return _entry(index, raw)
    except ValueError:
        raw["unit"]["level"] = 1  # a form whose cap is lower than the rarity's usual one
        return _entry(index, raw)


def all_ids() -> list[int]:
    return [ID_BASE + i for i in range(1, _count() + 1)]


def by_id(friend_id) -> dict | None:
    try:
        index = int(friend_id) - ID_BASE
    except (TypeError, ValueError):
        return None
    if 1 <= index <= _count():
        return player(index)
    return None


def _state(player_state) -> dict:
    return player_state.data.setdefault("exvius_friends", {}) if player_state is not None else {}


def friend_ids(player_state) -> list[int]:
    """The generated players who are your friends: the starting set plus your adds, minus removals."""
    if not enabled():
        return []
    state = _state(player_state)
    if "players_added" not in state and player_state is not None:
        start = _int_env("EXVIUS_START_FRIENDS", 15)
        picks = random.Random("exvius-start-friends").sample(all_ids(), min(start, _count()))
        state["players_added"] = sorted(picks)
        player_state.dirty = True
    added = [int(x) for x in state.get("players_added", [])]
    return [x for x in added if ID_BASE < x <= ID_BASE + _count()]


def suggestions(player_state) -> list[dict]:
    """Today's suggested players: not already your friends, changing every day."""
    if not enabled():
        return []
    mine = set(friend_ids(player_state))
    others = [x for x in all_ids() if x not in mine]
    count = min(_int_env("EXVIUS_PLAYER_SUGGESTIONS", 10), len(others))
    picks = random.Random("exvius-suggest-" + time.strftime("%Y-%m-%d")).sample(others, count)
    return [by_id(x) for x in picks]


def add(player_state, friend_id) -> bool:
    if by_id(friend_id) is None or player_state is None:
        return False
    current = friend_ids(player_state)
    if int(friend_id) not in current:
        _state(player_state)["players_added"] = sorted(current + [int(friend_id)])
        player_state.dirty = True
    return True


def remove(player_state, friend_id) -> bool:
    if player_state is None:
        return False
    current = friend_ids(player_state)
    if int(friend_id) in current:
        _state(player_state)["players_added"] = [x for x in current if x != int(friend_id)]
        player_state.dirty = True
        return True
    return False
