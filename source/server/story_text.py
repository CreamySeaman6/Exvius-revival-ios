"""Missing story lines: three scene packs whose script names a text line the pack does not have.

A story scene ("event") pack, `common_lang/sd/event/<nn>/Ver<v>_<scene>.cpk`, holds the script
(`<scene>_event.bin`) and its lines (`<scene>_event_text.txt`, `id,text`, and `<scene>_event_text_sg.txt`,
`id^text^text...` one column per language). The script names each line by id; a line the text files do not
have is drawn as its key, `MAP_TEXT_<scene><line>` (reported from the phone 2026-11-06: MAP_TEXT_111020301210134
and MAP_TEXT_111020301210135 in chapter 1).

A scan of all 1,121 shipped scenes (2026-11-07) found three with missing lines, all the same shape: the script
holds two copies of a passage (two branches), the second copy was renumbered, and the renumbered lines never
made it into the English text files. The two copies have the same commands between each line, byte for byte,
so each missing line is the line at the same place in the first copy:

- 111020301 (chapter 1, leaving with Fina): 210134 = 210096 (Lasswell), 210135 = 210023 (Rain).
- 121020102 (Ballen Passage, Lid's Mechabo): 210005 = 210015 (Lid). Here the pack has 210015 but the script
  never names it, and it sits in the text file exactly where 210005 is spoken.
- 18301010101 (event scene, Bahamut's aura): 210016-210023 = 210014, 210015, 210008-210013.

No transcript of these scenes was found to check against; the mapping comes from the scripts alone.

The server serves those packs with the lines added, under a new file version (`F_RESOURCE_MAP_VERSION_MST_LOCALIZE`,
patched in `ios_tables.py`), because the phone never fetches a `Ver<N>_` name it already holds. The built packs
are cached in the server root (`ios-cache/`).

OFF BY DEFAULT since 2026-11-07: the iPhone refuses the rebuilt pack. Its own log (client report) shows
`CRI LIB ERROR E06100301: Invalid IFF header (mismatched four_cc)` and `CPK Analyzer::Cannot possibly analyze
the CPK File` for both builds (Ver1048 and Ver1049), then "A loading error has occurred" entering Port City
Lodin. So something in `rebuild` leaves a chunk (TOC/ETOC) where the CRI loader doesn't find it; the header
size fix (BUILDER 2) wasn't it. Not found yet. `EXVIUS_STORY_TEXT_FIX=1` turns it back on for testing only.
"""
from __future__ import annotations

import glob
import os
import re
import struct
import threading

# scene -> (resource id in F_RESOURCE_MAP_MST, {missing line: line to copy})
FIXES = {
    "111020301": ("311203101", {"210134": "210096", "210135": "210023"}),
    "121020102": ("321201102", {"210005": "210015"}),
    "18301010101": ("383101001", {"210016": "210014", "210017": "210015", "210018": "210008",
                                  "210019": "210009", "210020": "210010", "210021": "210011",
                                  "210022": "210012", "210023": "210013"}),
}
BUILDER = "2"                    # change to give every fixed pack a new version (and rebuild it)
# 1 (2026-11-07) left the header's FileSize at the original size: "a loading error has occurred" entering
# Port City Lodin, whose arrival downloads 111020301. 2 sets FileSize and TotalDataSize.
VERSION_FIELD = "OzT5lSz3"       # base (common_lang) file version in F_RESOURCE_MAP_VERSION_MST_LOCALIZE
_LOCK = threading.Lock()
_PATH = re.compile(r"(^|/)common_lang/sd/event/([^/]+)/Ver(\d+)_(\d+)\.cpk$")


def enabled() -> bool:
    return os.environ.get("EXVIUS_STORY_TEXT_FIX", "0") == "1"


def table_offset() -> int:
    """Added (with the sound bump) to `F_RESOURCE_MAP_VERSION_MST_LOCALIZE`'s advertised version.

    Phones that got the broken fix hold the table at +3000+1002 (BUILDER 2). Off, the table is advertised at
    +4500 so those phones fetch it again (a table advertised lower than the phone's copy may never be fetched)
    and go back to the shipped scene packs."""
    return 3000 + (bump() if enabled() else 1500)


def bump() -> int:
    """Added to each fixed pack's file version."""
    return 1000 + int(BUILDER)


def version_sets(raw_versions: dict[str, str]) -> dict[str, dict[str, int]]:
    """{resource id: {version field: new version}} given {resource id: shipped version}."""
    if not enabled():
        return {}
    out = {}
    for rid in (r for r, _ in FIXES.values()):
        v = str(raw_versions.get(rid, ""))
        if v.isdigit() and int(v) < bump():
            out[rid] = {VERSION_FIELD: int(v) + bump()}
    return out


def resource_ids() -> set[str]:
    return {r for r, _ in FIXES.values()} if enabled() else set()


def wants(rel: str) -> bool:
    m = _PATH.search(rel)
    return bool(enabled() and m and m.group(4) in FIXES and int(m.group(3)) > bump())


# --- text -----------------------------------------------------------------------------------------------

def add_lines(text: bytes, adds: dict[str, str], sep: bytes) -> tuple[bytes, int]:
    """`text` with a copy of line `src` under id `new` after it, for each `new: src` the file lacks."""
    lines = text.split(b"\n")
    have = {ln.split(sep, 1)[0].strip().lstrip(b"\xef\xbb\xbf") for ln in lines if sep in ln}
    added = 0
    for new, src in adds.items():
        if new.encode() in have:
            continue
        for i, ln in enumerate(lines):
            if sep in ln and ln.split(sep, 1)[0].strip().lstrip(b"\xef\xbb\xbf") == src.encode():
                lines.insert(i + 1, new.encode() + sep + ln.split(sep, 1)[1])
                added += 1
                break
    return b"\n".join(lines), added


# --- the pack -------------------------------------------------------------------------------------------

def rebuild(data: bytes, scene: str) -> tuple[bytes, int]:
    """The pack with the missing lines added to both text files. Returns (pack, lines added).

    The header and TOC tables keep their layout; only fixed-width cells change (sizes, offsets), so they are
    patched in place. Files keep their order and the pack's alignment; the ETOC block moves to the new end."""
    from ios_art import _cells, _mask, _plain, _FMT
    adds = FIXES[scene][1]
    if data[:4] != b"CPK ":
        raise ValueError("not a CPK")
    hsize = struct.unpack_from("<Q", data, 8)[0]
    header = bytearray(_plain(data[16:16 + hsize]))
    hcols, hrows = _cells(bytes(header))
    h = {k: v[1] for k, v in hrows[0].items()}
    toc_off, content_off, align = h["TocOffset"], h["ContentOffset"], h.get("Align") or 2048
    if h.get("ItocOffset") or h.get("GtocOffset"):
        raise ValueError("pack has an ITOC/GTOC; not supported")
    tsize = struct.unpack_from("<Q", data, toc_off + 8)[0]
    toc = bytearray(_plain(data[toc_off + 16:toc_off + 16 + tsize]))
    tcols, trows = _cells(bytes(toc))
    tfmt = {c[0]: _FMT[c[2]] for c in tcols}
    entries = sorted(trows, key=lambda r: (r["FileOffset"][1], r["ID"][1]))
    total = 0
    blobs = []
    for row in entries:
        name, size, extract, off = (row[k][1] for k in ("FileName", "FileSize", "ExtractSize", "FileOffset"))
        blob = data[toc_off + off:toc_off + off + size]
        if name in (f"{scene}_event_text.txt", f"{scene}_event_text_sg.txt"):
            if size != extract:
                raise ValueError(f"{name} is compressed; not supported")
            blob, n = add_lines(blob, adds, b"," if name.endswith("_event_text.txt") else b"^")
            total += n
        blobs.append((row, blob))
    out = bytearray(data[:content_off])
    sum_size = 0
    for row, blob in blobs:
        if blob:
            out += b"\0" * (-len(out) % align)
        struct.pack_into(tfmt["FileOffset"], toc, row["FileOffset"][0], len(out) - toc_off)
        struct.pack_into(tfmt["FileSize"], toc, row["FileSize"][0], len(blob))
        if row["FileSize"][1] == row["ExtractSize"][1]:
            struct.pack_into(tfmt["ExtractSize"], toc, row["ExtractSize"][0], len(blob))
        out += blob
        sum_size += len(blob)
    out += b"\0" * (-len(out) % align)
    values = {"ContentSize": len(out) - content_off, "TotalDataSize": len(out) - content_off,
              "EnabledPackedSize": sum_size, "EnabledDataSize": sum_size}
    if h.get("EtocOffset"):
        values["EtocOffset"] = len(out)
        out += data[h["EtocOffset"]:h["EtocOffset"] + (h.get("EtocSize") or len(data) - h["EtocOffset"])]
    values["FileSize"] = len(out)
    hfmt = {c[0]: _FMT[c[2]] for c in hcols}
    for name, value in values.items():
        if name in hrows[0]:
            struct.pack_into(hfmt[name], header, hrows[0][name][0], value)
    out[16:16 + hsize] = _mask(bytes(header))
    out[toc_off + 16:toc_off + 16 + tsize] = _mask(bytes(toc))
    return bytes(out), total


def _source(root: str, folder: str, scene: str) -> str | None:
    hits = [p for p in glob.glob(os.path.join(root, "common_lang", "sd", "event", folder, f"Ver*_{scene}.cpk"))
            if int(re.search(r"Ver(\d+)_", os.path.basename(p)).group(1)) < bump()]
    return max(hits, key=lambda p: int(re.search(r"Ver(\d+)_", os.path.basename(p)).group(1)), default=None)


def serve(rel: str, *roots: str | None) -> tuple[bytes | None, str | None]:
    m = _PATH.search(rel)
    if not (enabled() and m and m.group(4) in FIXES):
        return None, None
    folder, version, scene = m.group(2), int(m.group(3)), m.group(4)
    for root in roots:
        if not root:
            continue
        src = _source(root, folder, scene)
        if not src:
            continue
        base = int(re.search(r"Ver(\d+)_", os.path.basename(src)).group(1))
        if version != base + bump():
            return None, None
        from ios_art import cache_dir
        path = os.path.join(cache_dir(), f"story-{scene}-v{base}-b{BUILDER}.cpk")
        with _LOCK:
            if not os.path.isfile(path):
                with open(src, "rb") as fh:
                    built, n = rebuild(fh.read(), scene)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path + ".tmp", "wb") as fh:
                    fh.write(built)
                os.replace(path + ".tmp", path)
                print(f"[story-text] built {os.path.basename(path)}: {n} line(s) added", flush=True)
        with open(path, "rb") as fh:
            return fh.read(), f"{os.path.basename(src)} with its missing story lines added"
    return None, None
