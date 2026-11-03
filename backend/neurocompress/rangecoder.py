"""Byte-oriented range coder (LZMA-style carry handling) with 16-bit frequency totals.

The encoder/decoder operate on *cumulative frequency rows*: ``row[u]`` is the cumulative
frequency below symbol ``u`` and ``row[256] == 65536``. Rows are plain Python lists so the
per-symbol loop stays fast.
"""
from bisect import bisect_right

TOP = 1 << 24
TOTAL_BITS = 16
MASK32 = 0xFFFFFFFF


class RangeDecodeError(Exception):
    """Raised when the compressed stream is truncated or inconsistent."""


class RangeEncoder:
    def __init__(self):
        self.low = 0
        self.range = MASK32
        self.cache = 0
        self.cache_size = 1
        self.out = bytearray()

    def encode_many(self, rows, row_idx, symbols):
        low, rng, cache, csize, out = self.low, self.range, self.cache, self.cache_size, self.out
        for ri, u in zip(row_idx, symbols):
            row = rows[ri]
            c = row[u]
            f = row[u + 1] - c
            r = rng >> TOTAL_BITS
            low += r * c
            rng = r * f
            while rng < TOP:
                rng <<= 8
                if low < 0xFF000000 or low > MASK32:
                    carry = low >> 32
                    temp = cache
                    while True:
                        out.append((temp + carry) & 0xFF)
                        temp = 0xFF
                        csize -= 1
                        if csize == 0:
                            break
                    cache = (low >> 24) & 0xFF
                csize += 1
                low = (low & 0x00FFFFFF) << 8
        self.low, self.range, self.cache, self.cache_size = low, rng, cache, csize

    def finish(self) -> bytes:
        low, cache, csize, out = self.low, self.cache, self.cache_size, self.out
        for _ in range(5):
            if low < 0xFF000000 or low > MASK32:
                carry = low >> 32
                temp = cache
                while True:
                    out.append((temp + carry) & 0xFF)
                    temp = 0xFF
                    csize -= 1
                    if csize == 0:
                        break
                cache = (low >> 24) & 0xFF
            csize += 1
            low = (low & 0x00FFFFFF) << 8
        self.low, self.cache, self.cache_size = low, cache, csize
        # The first emitted byte is always the initial zero cache byte; drop it.
        return bytes(out[1:])


class RangeDecoder:
    def __init__(self, data: bytes):
        if len(data) < 4:
            raise RangeDecodeError("compressed payload too short")
        self.data = data
        self.pos = 4
        self.code = int.from_bytes(data[:4], "big")
        self.range = MASK32

    def decode_many(self, rows, row_idx):
        data, pos, code, rng = self.data, self.pos, self.code, self.range
        n = len(data)
        res = []
        append = res.append
        for ri in row_idx:
            row = rows[ri]
            r = rng >> TOTAL_BITS
            t = code // r
            if t > 65535:
                t = 65535
            u = bisect_right(row, t) - 1
            c = row[u]
            code -= r * c
            rng = r * (row[u + 1] - c)
            if code < 0 or code >= rng:
                raise RangeDecodeError("corrupt range-coded stream")
            while rng < TOP:
                if pos < n:
                    code = (code << 8) | data[pos]
                elif pos < n + 8:  # a few implicit zero bytes are legal at the very end
                    code = code << 8
                else:
                    raise RangeDecodeError("compressed stream truncated")
                pos += 1
                rng <<= 8
            append(u)
        self.pos, self.code, self.range = pos, code, rng
        return res
