"""Unit pictures for the Drop Rates and News pages, from the game's own files (operator, 2026-11-10).

The pages used to fetch each unit's sprite from the FFBE wiki, guessing the file name from the unit's name and
stars; for Neo Vision and many 7★ units the guess missed (Sol -Neo Vision-, Summoner Yuna, Sora (KHIII)...), and
the operator doesn't want the pages to depend on the wiki. The unit packs every install already has
(`native/common_lang/sd/unit/Ver<N>_unit<k>[_sg]_common.cpk`, from the data download) hold one standing picture
per unit form, `unit_ills_<unit id>.png` (a small pixel sprite, about 100x100), next to its battle sheets.

* At startup (`start`, from ios-server/serve.py) a background thread reads every unit pack's file table once and
  saves each `unit_ills_<id>.png` into `ios-cache/notice-art/` (files already there are skipped; the old wiki
  downloads there are removed). About 3,700 pictures, 10 MB.
* `/exvius/notice-art/unit/<id>.png` (capture_server) answers `picture(id)`: the cached file; before the scan
  gets to it, straight from the one pack that holds it. A form with no picture of its own takes another form
  of the same unit (`F_UNIT_MST.woghJa61`, its base form; a Neo Vision unit's shift form, `JPW8Vs40`), nearest
  rarity first. None at all: 404, and the page leaves the space blank.
* A unit in several packs (`unit2_common` and `unit2_sg_common`, `unit22` and `unit22_common`) is read from the
  `_sg` pack first, then the newest version. `Ver0_unit22.cpk` holds 77 pictures that aren't PNGs (encrypted
  or damaged); those are skipped and the copies in `unit22_common` used.

`EXVIUS_NOTICE_ART=0` turns the pictures off (no scan; the pages show names only).
"""
from __future__ import annotations

import glob
import os
import re
import struct
import threading

PACK_DIRS = (("common_lang", "sd", "unit"), ("en", "sd", "unit"))
_NAME = re.compile(r"unit_ills_(\d+)\.png")
_PNG = b"\x89PNG\r\n\x1a\n"
_LOCK = threading.Lock()
_INDEX: dict | None = None
_STARTED = False


def enabled() -> bool:
    return str(os.environ.get("EXVIUS_NOTICE_ART", "1")).strip().lower() not in ("0", "off", "false", "no")


def art_dir() -> str:
    try:
        import ios_art
        base = ios_art.cache_dir()
    except Exception:  # noqa: BLE001
        base = os.path.join(os.environ.get("FFBE_SERVER_ROOT", "."), "ios-cache")
    path = os.path.join(base, "notice-art")
    os.makedirs(path, exist_ok=True)
    return path


def _roots(roots=None) -> list:
    if roots is None:
        try:
            from ffbe_state import State
            roots = (State.cdn_overlay, State.cdn_root)
        except Exception:  # noqa: BLE001
            roots = ()
        roots = tuple(roots) + (os.environ.get("CDN_OVERLAY"), os.environ.get("CDN_ROOT"))
    return list(dict.fromkeys(os.path.abspath(r) for r in roots if r))


def _rank(path: str):
    """`_sg` (Global) packs first, then the newest version."""
    name = os.path.basename(path)
    m = re.match(r"Ver(\d+)_", name)
    return ("_sg" in name, int(m.group(1)) if m else 0)


def packs(roots=None) -> list:
    found = {}
    for root in _roots(roots):
        for parts in PACK_DIRS:
            for path in glob.glob(os.path.join(root, *parts, "Ver*_*.cpk")):
                found.setdefault(os.path.basename(path), path)
    return sorted(found.values(), key=_rank, reverse=True)


def _pictures(path: str) -> list:
    """[(unit id, absolute offset, stored size, extracted size)] of a pack's unit pictures (reads its file table)."""
    from ios_art import _cells, _plain
    with open(path, "rb") as fh:
        head = fh.read(16)
        if head[:4] != b"CPK ":
            return []
        header = {k: v[1] for k, v in _cells(_plain(fh.read(struct.unpack_from("<Q", head, 8)[0])))[1][0].items()}
        toc = header.get("TocOffset") or 0
        fh.seek(toc)
        toc_head = fh.read(16)
        if toc_head[:4] != b"TOC ":
            return []
        rows = _cells(_plain(fh.read(struct.unpack_from("<Q", toc_head, 8)[0])))[1]
    out = []
    for row in rows:
        m = _NAME.fullmatch(str(row["FileName"][1]))
        if m:
            out.append((m.group(1), toc + row["FileOffset"][1], row["FileSize"][1], row["ExtractSize"][1]))
    return out


def index(roots=None) -> dict:
    """unit id -> [(pack, offset, size, extracted size)], best pack first. Built once (file tables only)."""
    global _INDEX
    with _LOCK:
        if _INDEX is None:
            out: dict = {}
            for path in packs(roots):
                try:
                    for uid, off, size, extract in _pictures(path):
                        out.setdefault(uid, []).append((path, off, size, extract))
                except Exception as exc:  # noqa: BLE001 -- a damaged pack: the others still count
                    print(f"[unit-art] {os.path.basename(path)} not read ({exc!r})", flush=True)
            if not out:
                return out      # no packs found (data folders not known yet): look again next time
            _INDEX = out
        return _INDEX


def _extract(entry) -> bytes | None:
    path, off, size, extract = entry
    with open(path, "rb") as fh:
        fh.seek(off)
        data = fh.read(size)
    if size != extract:
        from crilayla import decompress
        data = decompress(data)
    return data if data[:8] == _PNG else None


def _cached(uid: str) -> str:
    return os.path.join(art_dir(), f"unit_ills_{uid}.png")


def own_picture(uid: str, roots=None) -> bytes | None:
    """This form's own picture: from the cache, else from its pack (and then cached)."""
    path = _cached(uid)
    if os.path.isfile(path):
        with open(path, "rb") as fh:
            return fh.read()
    for entry in index(roots).get(uid, []):
        try:
            data = _extract(entry)
        except Exception:  # noqa: BLE001
            data = None
        if data:
            tmp = path + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, path)
            return data
    return None


def forms(uid: str) -> list:
    """The unit's other forms: same base form (`woghJa61`) or its Neo Vision shift (`JPW8Vs40`), nearest
    rarity first."""
    from player_state import _load_ndjson
    rows = _load_ndjson("F_UNIT_MST.ndjson").get("__rows__", [])
    by_id = {str(r.get("3HriTp6B")): r for r in rows}
    me = by_id.get(uid)
    if not me:
        return []
    base = str(me.get("woghJa61") or uid)
    linked = {str(me.get("JPW8Vs40") or "")} | {str(r.get("3HriTp6B")) for r in rows
                                                if str(r.get("JPW8Vs40") or "") == uid}
    family = [i for i, r in by_id.items() if i != uid and (str(r.get("woghJa61")) == base or i in linked)]

    def rarity(i):
        try:
            return int(by_id[i].get("9fW0TePj") or 0)
        except ValueError:
            return 0
    mine = rarity(uid)
    return sorted(family, key=lambda i: (abs(rarity(i) - mine), -rarity(i), i))


def picture(uid, roots=None) -> bytes | None:
    """PNG bytes for a unit form's page picture, or None (the page leaves the space blank)."""
    uid = str(uid)
    if not enabled() or not uid.isdigit():
        return None
    data = own_picture(uid, roots)
    if data:
        return data
    for other in forms(uid):
        data = own_picture(other, roots)
        if data:
            return data
    return None


def warm(roots=None) -> dict:
    """Save every unit picture into the cache (skipping those already there). Returns counts."""
    folder = art_dir()
    for old in glob.glob(os.path.join(folder, "unit-*")):   # the wiki downloads this replaces
        try:
            os.remove(old)
        except OSError:
            pass
    saved = had = unreadable = 0
    for uid in index(roots):
        if os.path.isfile(_cached(uid)):
            had += 1
        elif own_picture(uid, roots):
            saved += 1
        else:
            unreadable += 1
    size = sum(os.path.getsize(p) for p in glob.glob(os.path.join(folder, "unit_ills_*.png")))
    return {"saved": saved, "already": had, "unreadable": unreadable, "bytes": size}


def start(*roots) -> None:
    """Fill the cache in the background (server start)."""
    global _STARTED
    if not enabled() or _STARTED:
        return
    _STARTED = True
    roots = list(roots) or None

    def run():
        try:
            info = warm(roots)
            print(f"[unit-art] notice art cache: {info['saved']} saved, {info['already']} already there, "
                  f"{info['unreadable']} unreadable, {info['bytes'] // 1024} KB", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[unit-art] cache not filled ({exc!r}); pictures are read from the packs as asked", flush=True)
    threading.Thread(target=run, name="unit-art", daemon=True).start()
