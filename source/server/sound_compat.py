"""Make the preserved Android sound banks playable by the iPhone client.

The preserved data only has the Android sound banks (`common_lang/sound/*/android/*.acb`). Their
waveforms are HCA, but most are flagged as HCA-MX (CRI encode type 6), which plays through a separate
HCA-MX mixer that each platform build sets up for its own banks. The iPhone client played them as noise
and crashed on entering battle. HCA-MX audio is ordinary HCA data (with stricter encoder settings), so
re-flagging those waveforms as plain HCA (encode type 2) lets the regular HCA voices play the same bytes.

Only the ACB's @UTF waveform table changes; the audio itself is untouched.

That alone did not fix the noise. `plain_bank()` (below) also removes the banks' HCA cipher, and
`apply_ios()` runs whichever of the two are switched on.
"""
from __future__ import annotations

import os
import struct

HCA = 2
HCA_MX = 6

_SIZES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 8, 7: 8, 8: 4, 0xA: 4, 0xB: 8}
_ZERO, _CONST, _ROW = 0x10, 0x30, 0x50


class UtfError(ValueError):
    pass


def _table(buf: bytes, base: int):
    """Parse the @UTF table at `base`; return (columns, row positions) with absolute byte offsets."""
    if buf[base:base + 4] != b'@UTF':
        raise UtfError('not a @UTF table')
    size = struct.unpack_from('>I', buf, base + 4)[0]
    start = base + 8
    if start + size > len(buf):
        raise UtfError('truncated @UTF table')
    rows_off, str_off, data_off, _name_off = struct.unpack_from('>HIII', buf, start + 2)
    ncols, row_len, nrows = struct.unpack_from('>HHI', buf, start + 16)

    def cstr(offset):
        p = start + str_off + offset
        end = buf.index(b'\0', p)
        return buf[p:end].decode('utf-8', 'replace')
    columns = []
    p = start + 24
    for _ in range(ncols):
        flags = buf[p]
        name = cstr(struct.unpack_from('>I', buf, p + 1)[0])
        p += 5
        storage, typ = flags & 0xF0, flags & 0x0F
        if typ not in _SIZES:
            raise UtfError(f'unknown column type {typ:#x}')
        const_at = None
        if storage == _CONST:
            const_at = p
            p += _SIZES[typ]
        columns.append({'name': name, 'storage': storage, 'type': typ, 'const_at': const_at})
    rows = []
    for r in range(nrows):
        q = start + rows_off + r * row_len
        cells = {}
        for col in columns:
            if col['storage'] == _ROW:
                cells[col['name']] = q
                q += _SIZES[col['type']]
        rows.append(cells)

    def blob(cell_at):
        off, length = struct.unpack_from('>II', buf, cell_at)
        return start + data_off + off, length
    return columns, rows, blob


def hcamx_to_hca(data: bytes) -> tuple[bytes, int]:
    """Return (patched bank, number of waveforms re-flagged). Raises UtfError on a bank it cannot read."""
    columns, rows, blob = _table(data, 0)
    wave_col = next((c for c in columns if c['name'] == 'WaveformTable'), None)
    if wave_col is None or wave_col['type'] != 0xB or not rows:
        return data, 0
    at = rows[0].get('WaveformTable') if wave_col['storage'] == _ROW else wave_col['const_at']
    if at is None:
        return data, 0
    wave_base, length = blob(at)
    if length == 0:
        return data, 0
    wcols, wrows, _ = _table(data, wave_base)
    enc = next((c for c in wcols if c['name'] == 'EncodeType'), None)
    if enc is None or enc['type'] not in (0, 1):
        return data, 0
    out = bytearray(data)
    changed = 0
    if enc['storage'] == _CONST:
        if out[enc['const_at']] == HCA_MX:
            out[enc['const_at']] = HCA
            changed = len(wrows)
    elif enc['storage'] == _ROW:
        for row in wrows:
            at = row['EncodeType']
            if out[at] == HCA_MX:
                out[at] = HCA
                changed += 1
    return bytes(out), changed


# --- HCA cipher ---------------------------------------------------------------------------------------------
# Every waveform in the Android banks (BGM and SE, downloaded and built in) is HCA cipher type 1: CRI's fixed,
# keyless byte table. The re-flag above did not stop the noise on the iPhone. A decoder that skips the type-1
# table produces exactly that noise: FFmpeg 6.1 does (full-scale, clipping), while vgmstream, which applies
# the table, decodes the same bytes cleanly. So `plain_bank()` removes the cipher instead: it decrypts every
# frame, sets the header to cipher type 0 (none) and rewrites the header and frame checksums. The audio and
# the file size are unchanged, so the client's size table (F_RESOURCE_CHECKSUM_MST) still matches.

def _crc_table():
    table = []
    for i in range(256):
        c = i << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x8005) if c & 0x8000 else (c << 1)
        table.append(c & 0xFFFF)
    return table


_CRC = _crc_table()


def _crc16(data, start: int, end: int) -> int:
    crc, table = 0, _CRC
    for b in data[start:end]:
        crc = ((crc << 8) & 0xFFFF) ^ table[(crc >> 8) ^ b]
    return crc


def _type1_table() -> bytes:
    table, v = bytearray(256), 0
    for i in range(1, 255):
        v = (v * 13 + 11) & 0xFF
        if v in (0, 0xFF):
            v = (v * 13 + 11) & 0xFF
        table[i] = v
    table[0xFF] = 0xFF
    return bytes(table)


_TYPE1 = _type1_table()


def _hca_layout(buf, at: int, end: int):
    """(header size, frame size, frame count, offset of the ciph value) of the HCA at `at`, or None."""
    if end - at < 8 or struct.unpack_from('>I', buf, at)[0] & 0x7F7F7F7F != 0x48434100:
        return None
    header = struct.unpack_from('>H', buf, at + 6)[0]
    if at + header > end or _crc16(buf, at, at + header) != 0:
        return None
    p, frames, frame, ciph = at + 8, None, None, None
    while p + 4 <= at + header - 2:
        name = bytes(c & 0x7F for c in buf[p:p + 4])
        if name == b'fmt\0':
            frames = struct.unpack_from('>I', buf, p + 8)[0]
            p += 16
        elif name == b'comp':
            frame = struct.unpack_from('>H', buf, p + 4)[0]
            p += 16
        elif name == b'dec\0':
            frame = struct.unpack_from('>H', buf, p + 4)[0]
            p += 12
        elif name == b'vbr\0':
            p += 8
        elif name == b'ath\0':
            p += 6
        elif name == b'loop':
            p += 16
        elif name == b'ciph':
            ciph = p + 4
            p += 6
        elif name == b'rva\0':
            p += 8
        else:  # comm / pad end the chunk list
            break
    if not frames or not frame:
        return None
    return header, frame, frames, ciph


def decrypt_hca(buf: bytearray, at: int, end: int) -> bool:
    """Decrypt the type-1 HCA at buf[at:end] in place. False (untouched) for anything else."""
    layout = _hca_layout(buf, at, end)
    if layout is None:
        return False
    header, frame, frames, ciph = layout
    if ciph is None or struct.unpack_from('>H', buf, ciph)[0] != 1:
        return False
    first = at + header
    if first + frame * frames > end:
        return False
    for i in range(frames):
        a = first + i * frame
        if _crc16(buf, a, a + frame) != 0:
            return False  # not a type-1 stream we understand; leave the whole file alone
    for i in range(frames):
        a = first + i * frame
        buf[a:a + frame - 2] = bytes(buf[a:a + frame - 2]).translate(_TYPE1)
        struct.pack_into('>H', buf, a + frame - 2, _crc16(buf, a, a + frame - 2))
    struct.pack_into('>H', buf, ciph, 0)
    struct.pack_into('>H', buf, at + header - 2, _crc16(buf, at, at + header - 2))
    return True


def _afs2_entries(buf, base: int, length: int):
    """(start, end) of each file in the AFS2 archive at buf[base:base+length]."""
    if buf[base:base + 4] != b'AFS2':
        return []
    offsize, idsize = buf[base + 5], struct.unpack_from('<H', buf, base + 6)[0]
    count, align = struct.unpack_from('<II', buf, base + 8)
    align &= 0xFFFF  # the high half is the AWB subkey
    fmt = {2: '<H', 4: '<I', 8: '<Q'}.get(offsize)
    if fmt is None or not align:
        return []
    table = base + 16 + count * idsize
    offs = [struct.unpack_from(fmt, buf, table + i * offsize)[0] for i in range(count + 1)]
    spans = []
    for i in range(count):
        start = base + -(-offs[i] // align) * align
        spans.append((start, min(base + offs[i + 1], base + length)))
    return spans


def plain_bank(data: bytes) -> tuple[bytes, int]:
    """Return (bank, number of HCA waveforms decrypted) for an ACB (embedded AWB) or an AWB file."""
    if data[:4] == b'AFS2':
        base, length = 0, len(data)
    else:
        columns, rows, blob = _table(data, 0)
        col = next((c for c in columns if c['name'] == 'AwbFile'), None)
        if col is None or col['type'] != 0xB or not rows:
            return data, 0
        at = rows[0].get('AwbFile') if col['storage'] == _ROW else col['const_at']
        if at is None:
            return data, 0
        base, length = blob(at)
        if length == 0:
            return data, 0
    out = bytearray(data)
    done = sum(decrypt_hca(out, start, end) for start, end in _afs2_entries(out, base, length))
    return (bytes(out), done) if done else (data, 0)


# --- what the iPhone server applies ----------------------------------------------------------------------------

def ios_transforms() -> list[str]:
    """The transforms switched on for Android banks served to the iPhone, in the order they run."""
    out = []
    if os.environ.get("EXVIUS_IOS_HCA_PLAIN") == "1":
        out.append("plain")
    if os.environ.get("EXVIUS_IOS_HCA") == "1":
        out.append("hcamx")
    return out


def ios_signature() -> str:
    """Changes whenever the served bytes would change. `ios_tables` turns it into new sound file versions, so
    the phone downloads the banks again instead of keeping copies made under an older setting.
    `EXVIUS_IOS_SOUND_REFETCH` is part of it: give it any new value to make the phone fetch them once more."""
    parts = ios_transforms()
    refetch = str(os.environ.get("EXVIUS_IOS_SOUND_REFETCH", "")).strip()
    if refetch:
        parts.append("refetch=" + refetch)
    return "+".join(parts)


def apply_ios(data: bytes) -> tuple[bytes, str]:
    """Run the switched-on transforms over one ACB/AWB. Returns (bytes, note for the CDN log line)."""
    notes = []
    for name in ios_transforms():
        try:
            if name == "plain":
                data, n = plain_bank(data)
                notes.append(f"{n} HCA decrypted")
            elif name == "hcamx":
                data, n = hcamx_to_hca(data)
                notes.append(f"{n} HCA-MX->HCA")
        except Exception as exc:  # noqa: BLE001 -- an unreadable bank is still served
            notes.append(f"{name} skipped ({exc})")
    return data, ", ".join(notes)
