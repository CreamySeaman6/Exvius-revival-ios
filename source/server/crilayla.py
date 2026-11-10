"""CRILAYLA decompression (CRI's LZ format used for compressed files inside CPK archives).

    from crilayla import decompress
    data = decompress(blob)   # blob starts with b"CRILAYLA"; returns blob unchanged otherwise

Layout: "CRILAYLA", u32 uncompressed size (minus the 0x100-byte prefix), u32 compressed size, the
compressed stream (read backwards, bit by bit, from its end), then the 0x100-byte uncompressed prefix.

A copy of ios-server/devtools/crilayla.py for the server (captain_menu.py reads the Farplane's map.bin), since
only source/server goes into the container.
"""
from __future__ import annotations

import struct


def decompress(blob: bytes) -> bytes:
    if blob[:8] != b'CRILAYLA':
        return blob
    usize, csize = struct.unpack_from('<II', blob, 8)
    prefix = blob[16 + csize:16 + csize + 0x100]
    out = bytearray(usize + 0x100)
    out[:0x100] = prefix
    src = memoryview(blob)[16:16 + csize]

    pos = csize - 1          # byte index, reading backwards
    bits_left = 0
    cur = 0

    def bits(n: int) -> int:
        nonlocal pos, bits_left, cur
        v = 0
        while n:
            if bits_left == 0:
                cur = src[pos]
                pos -= 1
                bits_left = 8
            take = min(bits_left, n)
            v = (v << take) | ((cur >> (bits_left - take)) & ((1 << take) - 1))
            bits_left -= take
            n -= take
        return v

    end = 0x100
    w = len(out) - 1         # write backwards from the end
    while w >= end:
        if bits(1):
            offset = bits(13) + 3
            length = 3
            levels = (2, 3, 5, 8)
            for n in levels:
                v = bits(n)
                length += v
                if v != (1 << n) - 1:
                    break
            else:
                while True:
                    v = bits(8)
                    length += v
                    if v != 0xFF:
                        break
            for _ in range(length):
                if w < end:
                    break
                out[w] = out[w + offset]
                w -= 1
        else:
            out[w] = bits(8)
            w -= 1
    return bytes(out)
