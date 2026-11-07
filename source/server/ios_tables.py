"""Tables the iPhone server serves patched.

1. THE FIRST-BATTLE CRASH. On the iPhone, the opening battle (mission 1110100) loads
`layout/timer/layout_questCounter.csv` and `spritestudio/timer_animation/Timer_animation.ssbp`
(`BattleScene::initialize`, GL 0x1e3ce70). Those files live only in the full resource packs,
`resources_common.cpk` and `resources.cpk`. `F_RESOURCE_MST` gives those two packs no download
class, so they wait in the background queue (about 340 files in) and the battle starts long before
they arrive. Missing layout -> crash on entering battle.

The client groups resource rows by their `81fTkEDP` class (`DownloadSequencePopup::requestFullDownload`,
GL 0x257a4e8): `PRE_TUTO` and `TUTO` rows are downloaded up front, in a blocking download, and every
other row in the background. Marking the two packs `TUTO` makes the blocking download fetch them (about
50 MB more), so they are on the phone before the battle.

That blocking check runs at startup, BEFORE login, from the table the phone already holds. The patched
table itself only arrives during login, so the launch that first receives it still starts the battle
without the packs; the NEXT launch downloads them up front (seen live 2026-11-05: the crash, then a
relaunch that fetched exactly these two packs first).

`EXVIUS_EARLY_RESOURCES` picks the packs (comma-separated file names), `all` moves every background
pack up front (one long first download, nothing left for later), and empty/`0` turns this off.

2. NEW SOUND FILE VERSIONS. The phone keeps every downloaded file under its `Ver<N>_` name and never fetches
that name again, so a change to how the server rewrites the Android sound banks (`sound_compat.py`) would
never reach it. The file versions come from `OzT5lSz3` in two tables: `F_RESOURCE_VERSION_MST_LOCALIZE`
(rows of `F_RESOURCE_MST`, e.g. `System.acb` -> `Ver15_`) and `F_RESOURCE_MAP_VERSION_MST_LOCALIZE` (rows of
`F_RESOURCE_MAP_MST`, most of the BGM). Every sound row gets a bump derived from
`sound_compat.ios_signature()`, so each change of setting gives the banks new names and the phone fetches
them once. `_cdn_fetch` answers any `Ver<N>_` of a sound file from the Android folder, so the new names
need no files of their own. The client's size table (`F_RESOURCE_CHECKSUM_MST`) still matches, because
the rewrites keep every bank's size.

3. MISSING ENGLISH TEXT. The localized-text index and three text tables are served by `ios_texts.py`.

4. VORTEX BANNERS. `ios_art.py` rebuilds the English Vortex banner pack; this module serves it and raises its
English version (`F_RESOURCE_VERSION_MST_LOCALIZE`) and size (`F_RESOURCE_CHECKSUM_MST`).

5. MISSING STORY LINES. Three story scene packs are served with lines their scripts name but their text files
lack (`story_text.py`); `F_RESOURCE_MAP_VERSION_MST_LOCALIZE` gives those packs new versions. Off by default
since 2026-11-07 (the iPhone can't load the rebuilt pack); the table is still served, above the versions
phones were given while it was on, so they return to the shipped packs.

6. ROWS WITH NO FILE. `F_RESOURCE_MST` rows with no version in any language are left out (`drop_unversioned`),
so the phone stops asking to download 0 KB on every start.

7. HIDDEN QUEST REWARDS (2026-11-07). Taking on a town quest whose reward is hidden ("???" until it's done)
freezes or closes the iPhone app on the quest screen. `F_QUEST_MST` is served with every reward marked shown
(`quest_rewards_shown`, `EXVIUS_IOS_QUEST_REWARDS`).

8. DROP RATES ADDRESS (2026-11-07). `F_URL_MST` is served with `GACHA_RATE_URL` as a full address on this server
(`fix_web_urls`), so the summon Drop Rates button posts its banner id to the page `gacha_rates.py` builds.
"""
from __future__ import annotations

import glob
import json
import os
import re
import zlib

# (name, token, key) of each table, from libgame's `F_NAME\0token\0key\0` triplets.
RESOURCE = ("F_RESOURCE_MST", "ZQqB38Ns", "u6q3F02d")
RESOURCE_MAP = ("F_RESOURCE_MAP_MST", "B7LnP2TH", "U0Vd7AfQ")
RESOURCE_VERSION = ("F_RESOURCE_VERSION_MST_LOCALIZE", "A1L1GlaQ", "JchlFPWK")
RESOURCE_MAP_VERSION = ("F_RESOURCE_MAP_VERSION_MST_LOCALIZE", "YIgCpDKW", "geHlpoos")
RESOURCE_CHECKSUM = ("F_RESOURCE_CHECKSUM_MST", "9Hwur83G", "92SkMNAx")
QUEST = ("F_QUEST_MST", "2Px75LpY", "20mEeKo3")
QUEST_REWARD_FIELD = "dX6cor8j"
URL = ("F_URL_MST", "9wmd4iua", "UREmi85S")
URL_KEY_FIELD = "gu8McTA6"
# The host the Drop Rates page is opened on. NOT v900 (the notice host): `WebViewCommon::showWebView`
# (GL 0x258bbf8) skips the page's posted fields (`gacha_id`) when the address contains the game setting
# P_GS_NOTICE_STATIC (`GameSettingInfo::getNoticeStaticURL`, served as https://v900-lapis.gumi.sg/), so on
# v900 the page could never learn which summon was tapped (phone, 2026-11-07 09:24). v910 is the game API
# host; the same server answers both names.
WEB_HOST = "https://v910-lapis.gumi.sg"
DROP_RATE_PATH = "/lapisProd/app/php/web/statics/probability/sg_summons_list.php"

TABLE, TOKEN, KEY = RESOURCE  # kept for older callers
CLASS_FIELD = "81fTkEDP"
FILE_FIELD = "pJ56sAEo"
PATH_FIELD = "3LHdc6Qa"
VERSION_FIELD = "OzT5lSz3"
UP_FRONT = "TUTO"

# Which id field joins each version table to its resource table.
_VERSIONS = {RESOURCE_VERSION: (RESOURCE, "9ZCEWn0z"), RESOURCE_MAP_VERSION: (RESOURCE_MAP, "Nnb20keZ")}


def setting() -> str:
    raw = str(os.environ.get("EXVIUS_EARLY_RESOURCES", "")).strip()
    return "" if raw.lower() in ("", "0", "off", "none") else raw


def _bump(value: str) -> int:
    return 1000 + zlib.crc32(value.encode()) % 1000 if value else 0


def sound_bump() -> int:
    """Added to every sound file version. 0 when the server serves the Android banks unchanged."""
    import sound_compat
    return _bump(sound_compat.ios_signature())


def _art_up_front() -> bool:
    import ios_art
    return ios_art.enabled()


def drop_unversioned() -> bool:
    """`EXVIUS_IOS_DROP_UNVERSIONED` (default on): leave out of `F_RESOURCE_MST` the rows that have no file
    version in any language (`OzT5lSz3` and `86SWOBTb` both 0 in `F_RESOURCE_VERSION_MST_LOCALIZE`).

    Seven rows: `character.cpk` (class `tuto`) and six `6th_story*.usm` movies. There is no file to download for
    them, so the phone counts them as missing on every start and asks "Download while playing tutorial?" with
    0 KB to fetch (reported 2026-11-06, long after the tutorial). Nothing can ever be loaded from them."""
    return os.environ.get("EXVIUS_IOS_DROP_UNVERSIONED", "1") == "1"


def quest_rewards_shown() -> bool:
    """`EXVIUS_IOS_QUEST_REWARDS` (default on): serve `F_QUEST_MST` with every reward marked shown.

    A quest reward is `kind:id:count:rate:shown` (`dX6cor8j`); 263 of the 285 rewards in the shipped table
    have shown = 0, which the quest screen draws as "???" until the quest is cleared.
    `QuestReportDetailScene::setLayoutWindowLow` (GL 0x23fe99c) splits the rewards, and when any has
    shown != 1 and the quest isn't cleared it takes the "unknown reward" branch (0x23ff204: text
    `NAME_UNKNOWN`, `GameUtils::setRevisedSizeItemIcon(0, 0, ...)`). On the iPhone that branch freezes or
    closes the app (2026-11-07, Port City Lodin: "Rime of the Absent Mariner" 1003008 froze, "Hello? Sailor?"
    1003003 closed the app; every quest taken without trouble so far had shown = 1). Which part of it fails
    on iOS wasn't found (no crash log); marking the rewards shown avoids the branch. The cost: rewards are
    listed when a quest is taken instead of "???"."""
    return os.environ.get("EXVIUS_IOS_QUEST_REWARDS", "1") == "1"


def show_quest_rewards(raw: bytes) -> tuple[bytes, int]:
    """`F_QUEST_MST` with each reward's fifth field set to 1. Returns (table, rewards changed)."""
    out, changed = [], 0
    for line, row, double in _rows(raw, QUEST[2]):
        entries = str(row.get(QUEST_REWARD_FIELD) or "").split(",")
        fixed = []
        for entry in entries:
            parts = entry.split(":")
            if len(parts) >= 5 and parts[4] != "1":
                parts[4] = "1"
                changed += 1
            fixed.append(":".join(parts))
        if fixed != entries:
            row[QUEST_REWARD_FIELD] = ",".join(fixed)
            line = _encrypt(QUEST[2], row, double)
        out.append(line)
    return ("\n".join(out) + "\n").encode("ascii"), changed


def fix_web_urls(raw: bytes) -> tuple[bytes, int]:
    """`F_URL_MST` with `GACHA_RATE_URL` (the summon Drop Rates page) made a full address on this server.

    The shipped rows read `<WEB>/lapisProd/.../sg_summons_list.php`; the iPhone app has no `<WEB>` entry for its
    environment (`UrlMst::getUrl` 0x1d1eb94 -> `EnvUrlMst::replaceUrlKey`), so it opened
    `/en<WEB>/lapisProd/...` as a relative GET without the posted `gacha_id` (server log 2026-11-07 08:46) and
    the page couldn't tell which summon was meant. Returns (table, rows changed)."""
    out, changed = [], 0
    for line, row, double in _rows(raw, URL[2]):
        if row.get(URL_KEY_FIELD) == "GACHA_RATE_URL":
            fixed = {k: (WEB_HOST + DROP_RATE_PATH if k not in (URL_KEY_FIELD, "G4L0YIB2") and v else v)
                     for k, v in row.items()}
            if fixed != row:
                row = fixed
                line = _encrypt(URL[2], row, double)
                changed += 1
        out.append(line)
    return ("\n".join(out) + "\n").encode("ascii"), changed


def version_bump() -> int:
    """Added to `F_RESOURCE_MST`'s advertised version, so a client holding the unpatched table fetches this
    one. Changes with the setting, so switching packs makes the client fetch again. The Vortex banner pack
    moving up front adds 1000, which keeps the number above what phones were served before it; dropping the
    unversioned rows adds 2000 more, for the same reason."""
    if not (setting() or _art_up_front() or drop_unversioned()):
        return 0
    return _bump(setting()) + (1000 if _art_up_front() else 0) + (2000 if drop_unversioned() else 0)


def _roots():
    return os.environ.get("CDN_OVERLAY"), os.environ.get("CDN_ROOT")


def art(*roots):
    """(path, version, size) of the rebuilt Vortex banner pack (ios_art.py), or None."""
    import ios_art
    try:
        return ios_art.built_pack(ios_art.cache_dir(), *(roots or _roots()))
    except Exception as exc:  # noqa: BLE001 -- without the pack the tiles stay blank, nothing else breaks
        print(f"[ios-art] banner pack not built ({exc})", flush=True)
        return None


def _art_signature(*roots) -> str:
    a = art(*roots)
    return f"art={a[1]}:{a[2]}" if a else ""


def table_bump(spec, *roots) -> int:
    import sound_compat
    if spec == RESOURCE_VERSION:
        # Kept above the sound-only bump (1000-1999) that phones may already hold: a table advertised at a
        # LOWER version than the phone's copy may never be fetched again.
        art_sig = _art_signature(*roots)
        return sound_bump() + (2000 + zlib.crc32(art_sig.encode()) % 1000 if art_sig else 0)
    if spec == RESOURCE_MAP_VERSION:
        import story_text
        # Kept above the sound-only bump (1000-1999) and the story-fix bumps that phones may already hold.
        return sound_bump() + story_text.table_offset()
    if spec == RESOURCE_CHECKSUM:
        return _bump(_art_signature(*roots))
    if spec == QUEST:
        return 1000 if quest_rewards_shown() else 0
    if spec == URL:
        return 1001     # 1000: first build (v900 address); raise it whenever the served rows change
    return 0


def version_bumps() -> dict[str, int]:
    """Table name -> amount to add to its advertised version (only tables served patched)."""
    import ios_texts
    out = {RESOURCE[0]: version_bump(), ios_texts.INDEX[0]: ios_texts.bump()}
    for spec in (RESOURCE_VERSION, RESOURCE_MAP_VERSION, RESOURCE_CHECKSUM, QUEST, URL):
        out[spec[0]] = table_bump(spec)
    return {name: bump for name, bump in out.items() if bump}


def _path(token: str):
    return re.compile(r"(^|/)mst/Ver\d+_" + token + r"\.dat$")


def wants(rel: str) -> bool:
    import ios_texts, ios_art, story_text
    return _which(rel) is not None or ios_texts.wants(rel) or ios_art.wants(rel) or story_text.wants(rel)


def _which(rel: str):
    if version_bump() and _path(RESOURCE[1]).search(rel):
        return RESOURCE
    for spec in (RESOURCE_VERSION, RESOURCE_MAP_VERSION, RESOURCE_CHECKSUM, QUEST, URL):
        if _path(spec[1]).search(rel) and table_bump(spec):
            return spec
    return None


def _chosen(row: dict, value: str) -> bool:
    if row.get(CLASS_FIELD):
        return False  # already downloaded up front
    import ios_art
    if _art_up_front() and str(row.get("9ZCEWn0z")) == ios_art.RESOURCE_ID:
        return True   # the rebuilt Vortex banner pack: the Enhance tab crashes without its art
    if value.lower() == "all":
        return True
    names = {n.strip() for n in value.split(",") if n.strip()}
    return str(row.get(FILE_FIELD, "")) in names


def source_table(*roots: str | None, token: str = RESOURCE[1]) -> str | None:
    """The newest shipped copy of a table, looked up in each data root in turn."""
    for root in roots:
        if not root:
            continue
        hits = glob.glob(os.path.join(root, "mst", f"Ver*_{token}.dat"))
        if hits:
            return max(hits, key=lambda p: int(re.search(r"Ver(\d+)_", os.path.basename(p)).group(1)))
    return None


def _rows(raw: bytes, key_text: str):
    """Yield (line, row, double_pad) for each CBC-encrypted JSON line."""
    from ffbe_crypto import cbc_decrypt, key16
    key = key16(key_text)
    for line in raw.decode("ascii").splitlines():
        line = line.strip()
        if not line:
            continue
        plain = cbc_decrypt(key, line)
        pad = plain[-1]
        double = 1 <= pad <= 16 and plain[-pad:] == bytes([pad]) * pad
        yield line, json.loads(plain[:-pad] if double else plain), double


def _encrypt(key_text: str, row: dict, double: bool) -> str:
    from ffbe_crypto import cbc_encrypt, key16
    return cbc_encrypt(key16(key_text), json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                       double_pad=double)


def unversioned_ids(raw: bytes) -> set[str]:
    """Ids of `F_RESOURCE_VERSION_MST_LOCALIZE` rows with no version in the base or English column."""
    return {str(row.get("9ZCEWn0z")) for _, row, _ in _rows(raw, RESOURCE_VERSION[2])
            if str(row.get(VERSION_FIELD) or "0") == "0" and str(row.get("86SWOBTb") or "0") == "0"}


def patch(raw: bytes, drop: set[str] | None = None) -> tuple[bytes, list[str]]:
    """`F_RESOURCE_MST` with the chosen packs moved up front and the `drop` ids left out.
    Returns (table, pack names moved)."""
    value = setting()
    out, moved = [], []
    for line, row, double in _rows(raw, RESOURCE[2]):
        if drop and str(row.get("9ZCEWn0z")) in drop:
            continue
        if _chosen(row, value):
            row[CLASS_FIELD] = UP_FRONT
            moved.append(str(row.get(FILE_FIELD)))
            line = _encrypt(RESOURCE[2], row, double)
        out.append(line)
    return ("\n".join(out) + "\n").encode("ascii"), moved


def sound_ids(raw: bytes, spec=RESOURCE, id_field: str = "9ZCEWn0z") -> set[str]:
    """Ids of the rows of a resource table that are sound files (`sound/bgm`, `sound/se`, ...)."""
    return {str(row.get(id_field)) for _, row, _ in _rows(raw, spec[2])
            if str(row.get(PATH_FIELD, "")).startswith("sound/")}


def patch_versions(raw: bytes, spec, ids: set[str], bump: int, sets=None,
                   id_field: str | None = None) -> tuple[bytes, int]:
    """A version table with every sound row's file version raised by `bump`, and `sets` ({row id: {field:
    value}}) applied. Returns (table, rows changed)."""
    id_field = id_field or _VERSIONS[spec][1]
    sets = sets or {}
    out, changed = [], 0
    for line, row, double in _rows(raw, spec[2]):
        rid = str(row.get(id_field))
        value = str(row.get(VERSION_FIELD, ""))
        touched = False
        if bump and rid in ids and value.isdigit():
            row[VERSION_FIELD] = str(int(value) + bump)
            touched = True
        for field, new in sets.get(rid, {}).items():
            if str(row.get(field)) != str(new):
                row[field] = str(new)
                touched = True
        if touched:
            line = _encrypt(spec[2], row, double)
            changed += 1
        out.append(line)
    return ("\n".join(out) + "\n").encode("ascii"), changed


def serve(rel: str, *roots: str | None) -> tuple[bytes | None, str | None]:
    """(table bytes, CDN log note) when `rel` is one of the tables served patched, else (None, None)."""
    import ios_texts, ios_art, story_text
    if ios_texts.wants(rel):
        return ios_texts.serve(rel, *roots)
    if story_text.wants(rel):
        return story_text.serve(rel, *roots)
    if ios_art.wants(rel):
        built = art(*roots)
        m = re.search(r"Ver(\d+)_", os.path.basename(rel))
        if not built or not m or int(m.group(1)) != built[1]:
            return None, None   # an older version: the shipped pack, as is
        with open(built[0], "rb") as fh:
            return fh.read(), f"Vortex banner pack {os.path.basename(built[0])} for the iPhone"
    spec = _which(rel)
    if spec is None:
        return None, None
    src = source_table(*roots, token=spec[1])
    if not src:
        return None, None
    try:
        if spec == RESOURCE:
            drop = set()
            if drop_unversioned():
                vsrc = source_table(*roots, token=RESOURCE_VERSION[1])
                drop = unversioned_ids(open(vsrc, "rb").read()) if vsrc else set()
            data, moved = patch(open(src, "rb").read(), drop)
            return data, (f"{os.path.basename(src)}, {len(moved)} pack(s) moved to the first download, "
                          f"{len(drop)} row(s) with no file left out")
        if spec == QUEST:
            data, changed = show_quest_rewards(open(src, "rb").read())
            return data, f"{os.path.basename(src)}, {changed} hidden quest reward(s) shown"
        if spec == URL:
            data, changed = fix_web_urls(open(src, "rb").read())
            return data, f"{os.path.basename(src)}, Drop Rates address set ({changed} row)"
        import ios_art
        built = art(*roots)
        if spec == RESOURCE_CHECKSUM:
            sets = {ios_art.RESOURCE_ID: {ios_art.SIZE_FIELD: built[2]}} if built else {}
            data, changed = patch_versions(open(src, "rb").read(), spec, set(), 0, sets, id_field="9ZCEWn0z")
            return data, f"{os.path.basename(src)}, Vortex banner pack size set ({changed} row)"
        sets = {}
        if spec == RESOURCE_VERSION and built:
            sets = {ios_art.RESOURCE_ID: {ios_art.VERSION_FIELD: built[1]}}
        raw = open(src, "rb").read()
        if spec == RESOURCE_MAP_VERSION:
            import story_text
            wanted = story_text.resource_ids()
            shipped = {str(row.get("Nnb20keZ")): str(row.get(VERSION_FIELD, "")) for _, row, _ in
                       _rows(raw, spec[2]) if str(row.get("Nnb20keZ")) in wanted} if wanted else {}
            sets.update(story_text.version_sets(shipped))
        base, id_field = _VERSIONS[spec]
        base_src = source_table(*roots, token=base[1])
        if not base_src:
            return None, f"{spec[0]} not patched ({base[0]} not found)"
        ids = sound_ids(open(base_src, "rb").read(), base, id_field)
        bump = sound_bump()
        data, changed = patch_versions(raw, spec, ids, bump, sets)
        art_note = spec == RESOURCE_VERSION and built
        return data, (f"{os.path.basename(src)}, {changed} row(s): sound versions +{bump}"
                      + (f", Vortex banner pack -> Ver{built[1]}" if art_note else "")
                      + (f", {len(sets)} story pack(s) with missing lines" if spec == RESOURCE_MAP_VERSION and sets
                         else ""))
    except Exception as exc:  # noqa: BLE001 -- fall back to the shipped table
        return None, f"{spec[0]} patch failed ({exc})"
