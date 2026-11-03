import math
import random
import unittest

from neurocompress.rangecoder import RangeDecodeError, RangeDecoder, RangeEncoder


def make_row(freqs):
    row = [0]
    for f in freqs:
        row.append(row[-1] + f)
    assert row[-1] == 65536
    return row


def random_row(rng, skew):
    w = [rng.random() ** skew + 1e-9 for _ in range(256)]
    s = sum(w)
    f = [1 + int(x / s * (65536 - 256)) for x in w]
    f[f.index(max(f))] += 65536 - sum(f)
    return make_row(f)


class RangeCoderTests(unittest.TestCase):
    def roundtrip(self, rows, idx, syms):
        enc = RangeEncoder()
        enc.encode_many(rows, idx, syms)
        data = enc.finish()
        dec = RangeDecoder(data)
        out = dec.decode_many(rows, idx)
        self.assertEqual(out, syms)
        return data

    def test_random_distributions(self):
        rng = random.Random(1)
        rows = [random_row(rng, s) for s in (1, 4, 12, 40)]
        idx = [rng.randrange(4) for _ in range(30000)]
        syms = []
        for i in idx:
            row = rows[i]
            t = rng.randrange(65536)  # sample according to the model
            lo, hi = 0, 255
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if row[mid] <= t:
                    lo = mid
                else:
                    hi = mid - 1
            syms.append(lo)
        data = self.roundtrip(rows, idx, syms)
        ideal = sum(-math.log2((rows[i][s + 1] - rows[i][s]) / 65536) for i, s in zip(idx, syms)) / 8
        self.assertLess(len(data), ideal * 1.01 + 16)  # within ~1% of the entropy bound

    def test_extreme_probabilities_and_carries(self):
        f = [1] * 256
        f[0] = 65536 - 255
        row = make_row(f)
        rng = random.Random(2)
        syms = [0 if rng.random() < 0.98 else rng.randrange(1, 256) for _ in range(50000)]
        self.roundtrip([row], [0] * len(syms), syms)
        syms = [255] * 5000 + [0] * 5000 + [255, 0] * 3000  # rare-symbol runs stress carry propagation
        self.roundtrip([row], [0] * len(syms), syms)

    def test_empty_and_single(self):
        row = make_row([256] * 256)
        self.roundtrip([row], [], [])
        self.roundtrip([row], [0], [17])

    def test_truncated_stream_raises(self):
        rng = random.Random(3)
        rows = [random_row(rng, 2)]
        syms = [rng.randrange(256) for _ in range(5000)]
        enc = RangeEncoder()
        enc.encode_many(rows, [0] * len(syms), syms)
        data = enc.finish()
        with self.assertRaises(RangeDecodeError):
            RangeDecoder(data[: len(data) // 2]).decode_many(rows, [0] * len(syms))
        with self.assertRaises(RangeDecodeError):
            RangeDecoder(b"\x00")


if __name__ == "__main__":
    unittest.main()
