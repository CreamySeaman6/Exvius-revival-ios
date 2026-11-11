"""Recipes the story gave on Global that the server never paid (GitHub issue #3, 2026-11-11).

`content/story_recipes.json` (ios-server/devtools/build_story_recipes.py; report ios-server/research/STORY_RECIPES.md):
  * `missions`: first-clear recipes the wiki records and Global's final mission table dropped (Grandshelt Castle -
    Throne Room 1110703: the Magic Key recipe, next to its 100 Lapis);
  * `tutorial`: the crafting tutorial's Bronze Knife recipe and 3 Copper Ore (treasure 1101013), paid with the
    first clear of 1110103, Earth Shrine - Exit: a stand-in point the operator approved (2026-11-11), since nothing
    records when the tutorial ran;
  * `scripted`: Farplane's Tower of Earth gifts (Murasame, Force Armor, Killer Bow, Apollo Harp; treasures
    9001006/9001011/9001012/9001013 after missions 2000101/2000102/2000103/2000201). The map script gives them after
    each boss and the town update already pays them (exvius_field_treasures); here only the back-pay for a save that
    won the battle with no record of the treasure.

`extra(mid)` adds them to the quest's first-clear reward (first_clear.raw), so a new clear pays and shows them.
Saves that cleared those quests before get them by mail once, at login (`deliver`), leaving out recipes they
already own. Settings: EXVIUS_STORY_RECIPES (1); 0 turns both off.
"""
from __future__ import annotations

import copy
import json
import os
from functools import lru_cache
from pathlib import Path

LEDGER = "story_recipes"
TITLE = "Story Recipes"


def enabled() -> bool:
    return os.environ.get("EXVIUS_STORY_RECIPES", "1").strip() not in ("0", "off", "false", "no")


@lru_cache(maxsize=1)
def _doc() -> dict:
    try:
        return json.loads(Path(__file__).with_name("content").joinpath("story_recipes.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def extra(mid) -> str:
    """Reward entries (`kind:id:count`, comma list) this quest's first clear adds, or ''."""
    if not enabled():
        return ""
    doc = _doc()
    out = [r["reward"] for r in (doc.get("missions") or {}).get(str(mid), [])]
    out += [t["rewards"] for t in doc.get("tutorial") or [] if str(t.get("after_mission")) == str(mid)]
    return ",".join(out)


def _mark_treasures(player, ids) -> None:
    """Record treasures as received, so the phone's own report of them never pays a second time."""
    got = player.data.setdefault("exvius_field_treasures", [])
    for iid in ids:
        if str(iid) not in got:
            got.append(str(iid))


def note_paid(player, mid) -> None:
    """first_clear paid this quest's reward with its story recipes in it: nothing to mail later."""
    if extra(mid):
        led = player.data.setdefault(LEDGER, {"paid": []})
        if str(mid) not in led.setdefault("paid", []):
            led["paid"].append(str(mid))
            player.dirty = True
        _mark_treasures(player, [t["treasure"] for t in _doc().get("tutorial") or []
                                 if str(t.get("after_mission")) == str(mid)])


def _owned_recipes(player) -> set:
    owned = {str(i) for i, held in (player.data.get("exvius_craft") or {}).get("books", {}).items() if held}
    owned.update(str(it["item_id"]) for it in player._items()
                 if str(it.get("item_type")) == "60" and int(it.get("count", 0)) > 0)
    return owned


def missed(player) -> tuple[list, list, list]:
    """(quests, reward rows, treasure ids): cleared quests whose story recipes this save never got, and won
    Tower of Earth battles whose gift it has no record of."""
    from exvius_rewards import parse
    cleared = set(map(str, player.data.get("progress", {}).get("cleared_missions", [])))
    paid = set((player.data.get(LEDGER) or {}).get("paid", []))
    owned = _owned_recipes(player)
    quests, rows = [], []
    for mid in sorted(cleared - paid, key=lambda m: int(m) if m.isdigit() else 0):
        text = extra(mid)
        if not text:
            continue
        quests.append(mid)
        for row in parse(text):
            if row["kind"] == 60 and str(row["id"]) in owned:
                continue            # already in the recipe book (bought or found): only the rest
            if player._can_credit(row):
                rows.append(row)
    treasures = [t["treasure"] for t in _doc().get("tutorial") or [] if str(t.get("after_mission")) in quests]
    if enabled():
        got = set(map(str, player.data.get("exvius_field_treasures", [])))
        for gift in _doc().get("scripted") or []:
            if str(gift["after_mission"]) in cleared and str(gift["treasure"]) not in got:
                treasures.append(gift["treasure"])
                rows.extend(r for r in parse(gift["rewards"]) if player._can_credit(r))
    return quests, rows, treasures


def deliver(spec, reply_id):
    """Pipeline step (login carriers): mail the missed story recipes once per quest."""
    from ffbe_config import ANNIVERSARY_TICKET_CARRIER
    from ffbe_state import State
    player = State.player
    if (not enabled() or reply_id not in ANNIVERSARY_TICKET_CARRIER.split(",") or player is None
            or not isinstance(spec, dict) or player.mode == "frozen"):
        return spec
    quests, rows, treasures = missed(player)
    if not quests and not treasures:
        return spec
    before, dirty_before = copy.deepcopy(player.data), player.dirty
    try:
        led = player.data.setdefault(LEDGER, {"paid": []})
        if rows:
            led["mails"] = int(led.get("mails", 0)) + 1
            entry = player.deliver_mail(
                TITLE, [(r["kind"], r["id"], r["count"]) for r in rows], mail_id=str(931000000000 + led["mails"]),
                message="Story rewards you didn't receive: the crafting tutorial's Bronze Knife recipe, the Magic "
                        "Key recipe from Grandshelt Castle, and the Farplane Tower of Earth gifts.",
                icon_type=2, attach_type=1)
            if entry is None:
                raise RuntimeError("story recipe mail refused")
        led.setdefault("paid", []).extend(q for q in quests if q not in led["paid"])
        _mark_treasures(player, treasures)
        player.dirty = True
        State.state_dirty = True
    except Exception:
        player.data, player.dirty = before, dirty_before
        raise
    print(f"story recipes: {len(quests)} quest(s), {len(treasures)} gift(s), mailed "
          + (",".join(f"{r['kind']}:{r['id']}x{r['count']}" for r in rows) or "nothing (already owned)"),
          flush=True)
    return spec
