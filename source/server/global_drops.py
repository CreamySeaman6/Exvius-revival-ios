"""Enemy drop lists from Global's record (the FFBE wiki), swapped into a battle reply before its drop roll.

`content/global_drops.json` (built by ios-server/devtools/build_global_drops.py; method and counts in
ios-server/research/DROP_CHECK.md) holds, for each quest whose drops change under the operator's rules of
2026-11-10, every monster's (part id's) drop list: Japan's entries as they were plus the wiki's items Japan
lacks; for a quest that dropped nothing, the wiki's items. A wiki-only entry has three fields
(`kind:id:count`) and gets the `EXVIUS_WIKI_DROP_RATE` percent here.

`apply` rebuilds each wave's drop row (`y35YvQjZ` `9BetM2Ds`) from the monsters of the group that wave
serves (after `battle_content.roll_lottery`), the same union `battle_content.derive_mission` makes. A wave
whose monsters aren't all listed keeps its row. `EXVIUS_GLOBAL_DROPS=0` leaves every reply as it was.

EVENT CURRENCY AS ENEMY DROPS (operator, 2026-11-10): `currency` in the same file gives each event quest's
currency, Global's per-clear amount (the wiki's quest box, or Japan's own where only Japan's enemies carry it)
and the enemies that carry it. `_add_currency` puts that amount x `multiplier` on the waves holding those
enemies. Areas listed in `currency_areas` get no per-clear lump from event_currency.py. An exploration's entry
(`explore`, Orbonne Monastery Vaults' Auracite) goes on its random encounter rows instead
(`_add_encounter_currency`).

BACKSTOP (2026-11-10, Candy not arriving from Mana Mystery ELT): `_add_currency` notes each quest's placed
total (`placed`); observe_load keeps it on the attempt, and event_currency.pay credits, on a successful clear,
whatever part of it the phone's MissionEnd didn't report. `EXVIUS_CURRENCY_BACKSTOP=0` turns that off.
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "content", "global_drops.json")


def enabled() -> bool:
    return str(os.environ.get("EXVIUS_GLOBAL_DROPS", "1")).strip().lower() not in ("0", "off", "false", "no")


def wiki_rate() -> int:
    """`EXVIUS_WIKI_DROP_RATE`: percent chance for each item only the wiki lists (default 30; 0 leaves them out)."""
    try:
        return max(0, min(100, int(float(os.environ.get("EXVIUS_WIKI_DROP_RATE", "30")))))
    except ValueError:
        return 30


_DOC: dict | None = None
_PLACED: dict = {}


def placed(mid) -> dict:
    """{"20:<currency>": total} the last battle bundle for this quest put on its waves (empty when none)."""
    return dict(_PLACED.get(str(mid)) or {})


def _doc() -> dict:
    global _DOC
    if _DOC is None:
        try:
            with open(PATH, encoding="utf-8") as fh:
                _DOC = json.load(fh)
        except (OSError, ValueError) as exc:
            print(f"global drops: {PATH} not loadable ({exc!r}); serving the original drop lists", flush=True)
            _DOC = {}
    return _DOC


def missions() -> dict:
    return _doc().get("missions") or {}


def currency_for(mid) -> list:
    """The quest's event currency drops: [{item, base, carriers, placed_by}] (empty when it has none).

    A quest of a covered event area with no entry of its own (Mana Mystery's second quest set 7080106-7080110,
    and 98 more in 17 other events; HANDOFF "Event currency missing from 103 quests") drops the per-clear amount
    event_currency.py paid it before 2026-11-10, already sized (no multiplier), spread over all its waves."""
    if not enabled():
        return []
    own = (_doc().get("currency") or {}).get(str(mid))
    if own:
        return own
    try:
        from player_state import mission_row
        area = str((mission_row(str(mid)) or {}).get("uv60hgDW") or "")
        if area not in covered_areas():
            return []
        import event_currency
        n = event_currency.runs()
        found = event_currency._plan(n).get(str(mid)) if n > 0 else None
    except Exception:  # noqa: BLE001
        return []
    if not found or f"20:{found[0]}" not in covered_areas().get(area, []):
        return []
    return [{"item": f"20:{found[0]}", "base": found[1], "carriers": [], "placed_by": "per-clear amount",
             "sized": True}]


def covered_areas() -> dict:
    """Event area -> currencies its enemies now drop; event_currency.py pays no per-clear lump for those."""
    return (_doc().get("currency_areas") or {}) if enabled() else {}


def multiplier(item: str, area: str) -> float:
    """EXVIUS_EVENT_CURRENCY_RUNS as a multiplier on Global's currency drops, sized as before: the event's own
    gear, materia, units and tickets (the shop's `need`) take about that many clears of its top quest.
    Never below 1 (Global's own amounts); 1 when the runs setting is 0 or the currency has no shop to size."""
    from event_currency import runs
    n = runs()
    for ex in (_doc().get("currency_exchanges") or {}).values():
        if ex.get("currency") == item and str(area) in ex.get("areas", []):
            if n > 0 and ex.get("top") and ex.get("need"):
                return max(1.0, ex["need"] / (n * ex["top"]))
            return 1.0
    return 1.0


def apply(spec, mid):
    """A copy of `spec` with each wave's drop list from the Global lists, or `spec` itself if none apply."""
    if not enabled() or not isinstance(spec, dict) or mid is None:
        return spec
    _PLACED.pop(str(mid), None)
    lists = missions().get(str(mid)) or {}
    coins = currency_for(mid)
    explore = [c for c in coins if c.get("explore")]
    if explore and isinstance(spec.get("6v0LPiRe"), list):
        spec = _add_encounter_currency(spec, explore, mid)
    coins = [c for c in coins if not c.get("explore")]
    rows = spec.get("y35YvQjZ")
    if not (lists or coins) or not isinstance(rows, list):
        return spec
    group_of = {str(r.get("6v7y3QcJ")): str(r.get("2fY1IomW")) for r in spec.get("an6TB4WS") or []
                if isinstance(r, dict)}
    slots: dict[str, list[str]] = {}
    for g in spec.get("Bi6hVv34") or []:
        if isinstance(g, dict):
            slots.setdefault(str(g.get("2fY1IomW")), []).append(str(g.get("xqartN26")))
    rate = wiki_rate()
    out, changed = [], 0
    for row in rows:
        parts = slots.get(group_of.get(str(row.get("6v7y3QcJ")))) if isinstance(row, dict) else None
        if not lists or not parts or any(p not in lists for p in parts) or "9BetM2Ds" not in row:
            out.append(row)
            continue
        drops: list[str] = []
        for p in parts:
            for entry in lists[p].split(","):
                if not entry:
                    continue
                if entry.count(":") == 2:          # wiki-only: kind:id:count
                    if rate <= 0:
                        continue
                    entry = f"{entry}:{rate}"
                if entry not in drops:
                    drops.append(entry)
        out.append(dict(row, **{"9BetM2Ds": ",".join(drops)}))
        changed += 1
    if coins:
        out = _add_currency(out, coins, mid, group_of, slots)
        changed += 1
    if not changed:
        return spec
    spec = dict(spec)
    spec["y35YvQjZ"] = out
    return spec


def _add_encounter_currency(spec: dict, coins: list, mid) -> dict:
    """An exploration's currency (build_global_drops.SIZED_CURRENCY: Orbonne Monastery Vaults' Auracite) on its
    random encounters: the run's amount (base x multiplier) spread over the run's planned battles
    (battle_content.exploration_plans). Each encounter row drops the share rounded down or up at random (at 100%,
    so ffbe_battle._roll_items' "never empty" pick of the last entry can't add to it); the run's total holds."""
    import random
    import battle_content as bc
    from player_state import mission_row
    plan = bc.exploration_plans().get("missions", {}).get(str(mid))
    battles = sum(len(z.get("battles") or []) for z in (plan or {}).get("zones") or [])
    if not battles:
        return spec
    area = str((mission_row(str(mid)) or {}).get("uv60hgDW") or "")
    shares = [(coin["item"], coin["base"] * multiplier(coin["item"], area) / battles) for coin in coins]

    def with_currency(row):
        entries = []
        for item, per in shares:
            count = int(per) + (1 if random.random() < per - int(per) else 0)
            if count > 0:
                entries.append(f"{item}:{count}:100")
        return dict(row, **{"9BetM2Ds": ",".join(x for x in entries + [row.get("9BetM2Ds") or ""] if x)})
    spec = dict(spec)
    spec["6v0LPiRe"] = [with_currency(r) if isinstance(r, dict) else r for r in spec["6v0LPiRe"]]
    return spec


def _add_currency(rows: list, coins: list, mid, group_of: dict, slots: dict) -> list:
    """Each currency's per-clear amount (Global's base x the multiplier, +/-10%) as drops at 100% on the waves
    whose served group holds one of its carriers, split evenly; the last wave when the rolled groups hold none.
    Any entry of that currency already in a list (Japan's own) is replaced, so it never drops twice."""
    import random
    from player_state import mission_row
    area = str((mission_row(str(mid)) or {}).get("uv60hgDW") or "")
    rows = [dict(r) if isinstance(r, dict) else r for r in rows]
    _PLACED[str(mid)] = {}
    waves = [i for i, r in enumerate(rows) if isinstance(r, dict) and "9BetM2Ds" in r]
    for coin in coins:
        item = coin["item"]
        for i in waves:
            rows[i]["9BetM2Ds"] = ",".join(e for e in rows[i]["9BetM2Ds"].split(",")
                                           if e and ":".join(e.split(":")[:2]) != item)
        carriers = set(coin.get("carriers") or [])
        hit = [i for i in waves if carriers & set(slots.get(group_of.get(str(rows[i].get("6v7y3QcJ"))), []))]
        if coin.get("sized"):
            hit = waves                 # per-clear amount: every wave's enemies carry a share
        hit = hit or waves[-1:]
        scale = 1.0 if coin.get("sized") else multiplier(item, area)
        total = max(1, round(coin["base"] * scale * random.uniform(0.9, 1.1)))
        _PLACED[str(mid)][item] = total
        for n, i in enumerate(hit):
            count = total // len(hit) + (total % len(hit) if n == len(hit) - 1 else 0)
            if count > 0:
                entry = f"{item}:{count}:100"
                rows[i]["9BetM2Ds"] = rows[i]["9BetM2Ds"] + ("," if rows[i]["9BetM2Ds"] else "") + entry
    return rows
