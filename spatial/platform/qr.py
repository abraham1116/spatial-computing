"""A small QR Code encoder (ISO/IEC 18004): byte mode, error correction level M, versions 1 to 10 (up to 213 bytes).
Enough for an otpauth:// link. Output: a square matrix of booleans (True = dark) or an SVG string."""
from __future__ import annotations

# version -> (ec codewords per block, [(number of blocks, data codewords per block), ...])  for level M
EC_M = {1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]), 5: (24, [(2, 43)]), 6: (16, [(4, 27)]),
        7: (18, [(4, 31)]), 8: (22, [(2, 38), (2, 39)]), 9: (22, [(3, 36), (2, 37)]), 10: (26, [(4, 43), (1, 44)])}
ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50]}
M_BITS = 0b00                                  # level M format bits

# GF(256) with the QR primitive polynomial 0x11D
EXP, LOG = [0] * 512, [0] * 256
_x = 1
for _i in range(255):
    EXP[_i], LOG[_x] = _x, _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    EXP[_i] = EXP[_i - 255]


def _gmul(a: int, b: int) -> int:
    return 0 if a == 0 or b == 0 else EXP[LOG[a] + LOG[b]]


def _rs_generator(n: int) -> list[int]:
    g = [1]
    for i in range(n):
        ng = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            ng[j] ^= c
            ng[j + 1] ^= _gmul(c, EXP[i])
        g = ng
    return g


def _rs_remainder(data: list[int], n: int) -> list[int]:
    gen = _rs_generator(n)
    res = [0] * n
    for b in data:
        f = b ^ res[0]
        res = res[1:] + [0]
        if f:
            for i in range(n):
                res[i] ^= _gmul(gen[i + 1], f)
    return res


def _capacity(v: int) -> int:
    ec, groups = EC_M[v]
    return sum(n * d for n, d in groups)


def _bch(value: int, poly: int, deg: int) -> int:
    v = value << deg
    pl = poly.bit_length()
    while v.bit_length() >= pl:
        v ^= poly << (v.bit_length() - pl)
    return v


def _codewords(data: bytes, v: int) -> list[int]:
    cap = _capacity(v)
    bits: list[int] = []
    put = lambda val, n: bits.extend((val >> (n - 1 - i)) & 1 for i in range(n))
    put(0b0100, 4)
    put(len(data), 8 if v < 10 else 16)
    for b in data:
        put(b, 8)
    put(0, min(4, cap * 8 - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    cw = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = [0xEC, 0x11]
    while len(cw) < cap:
        cw.append(pad[(len(cw) - len(bits) // 8) % 2])
    ec, groups = EC_M[v]
    blocks, pos = [], 0
    for n, d in groups:
        for _ in range(n):
            blocks.append(cw[pos:pos + d]); pos += d
    ecs = [_rs_remainder(b, ec) for b in blocks]
    out = []
    for i in range(max(len(b) for b in blocks)):
        out += [b[i] for b in blocks if i < len(b)]
    for i in range(ec):
        out += [e[i] for e in ecs]
    return out


def _mask_fn(m: int):
    return [lambda r, c: (r + c) % 2 == 0, lambda r, c: r % 2 == 0, lambda r, c: c % 3 == 0, lambda r, c: (r + c) % 3 == 0,
            lambda r, c: (r // 2 + c // 3) % 2 == 0, lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
            lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0, lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0][m]


def _build(v: int, cw: list[int], mask: int) -> list[list[bool]]:
    n = 17 + 4 * v
    mat = [[False] * n for _ in range(n)]
    fn = [[False] * n for _ in range(n)]                          # function modules (not data)

    def setm(r, c, val, f=True):
        mat[r][c] = val
        if f:
            fn[r][c] = True
    for (r0, c0) in ((0, 0), (0, n - 7), (n - 7, 0)):             # finder patterns
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                r, c = r0 + dr, c0 + dc
                if 0 <= r < n and 0 <= c < n:
                    dark = 0 <= dr <= 6 and 0 <= dc <= 6 and (dr in (0, 6) or dc in (0, 6) or (2 <= dr <= 4 and 2 <= dc <= 4))
                    setm(r, c, dark)
    pts = ALIGN[v]
    for r in pts:                                                 # alignment patterns
        for c in pts:
            if fn[r][c]:
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    setm(r + dr, c + dc, max(abs(dr), abs(dc)) != 1)
    for i in range(8, n - 8):                                     # timing patterns
        setm(6, i, i % 2 == 0); setm(i, 6, i % 2 == 0)
    setm(n - 8, 8, True)                                          # the dark module
    fmt = ((M_BITS << 3 | mask) << 10 | _bch(M_BITS << 3 | mask, 0x537, 10)) ^ 0x5412
    for i in range(15):
        bit = (fmt >> i) & 1 == 1
        r1, c1 = (i, 8) if i < 6 else (i + 1, 8) if i < 8 else (8, 14 - i) if i < 9 else (8, 14 - i)
        if i < 6: setm(i, 8, bit)
        elif i < 8: setm(i + 1, 8, bit)
        elif i == 8: setm(8, 7, bit)
        else: setm(8, 14 - i, bit)
        if i < 8: setm(8, n - 1 - i, bit)
        else: setm(n - 15 + i, 8, bit)
    if v >= 7:                                                    # version information
        vi = v << 12 | _bch(v, 0x1F25, 12)
        for i in range(18):
            bit = (vi >> i) & 1 == 1
            setm(i // 3, n - 11 + i % 3, bit); setm(n - 11 + i % 3, i // 3, bit)
    bits = [(b >> (7 - i)) & 1 for b in cw for i in range(8)]
    k, up, c = 0, True, n - 1
    mf = _mask_fn(mask)
    while c > 0:
        if c == 6:
            c -= 1
        for step in range(n):
            r = n - 1 - step if up else step
            for cc in (c, c - 1):
                if not fn[r][cc]:
                    bit = bits[k] == 1 if k < len(bits) else False
                    k += 1
                    mat[r][cc] = bit != mf(r, cc)
        up = not up
        c -= 2
    return mat


def _penalty(mat: list[list[bool]]) -> int:
    n, score = len(mat), 0
    for rows in (mat, [list(col) for col in zip(*mat)]):          # rule 1 (runs) and rule 3 (finder-like) on rows and columns
        for row in rows:
            run = 1
            for i in range(1, n):
                if row[i] == row[i - 1]:
                    run += 1
                else:
                    score += run - 2 if run >= 5 else 0; run = 1
            score += run - 2 if run >= 5 else 0
            s = "".join("1" if x else "0" for x in row)
            score += 40 * (s.count("10111010000") + s.count("00001011101"))
    for r in range(n - 1):                                        # rule 2 (2x2 blocks)
        for c in range(n - 1):
            if mat[r][c] == mat[r][c + 1] == mat[r + 1][c] == mat[r + 1][c + 1]:
                score += 3
    dark = sum(sum(r) for r in mat)
    score += 10 * (abs(dark * 100 // (n * n) - 50) // 5)          # rule 4 (balance)
    return score


def matrix(text: str, mask: int | None = None) -> list[list[bool]]:
    data = text.encode()
    v = next((v for v in EC_M if len(data) <= _capacity(v) - (2 if v < 10 else 3)), None)
    if v is None:
        raise ValueError("text too long for this encoder (213 bytes at most)")
    cw = _codewords(data, v)
    if mask is not None:
        return _build(v, cw, mask)
    return min((_build(v, cw, m) for m in range(8)), key=_penalty)


def svg(text: str, box: int = 6, border: int = 4) -> str:
    m = matrix(text)
    n = len(m) + 2 * border
    rects = "".join(f'<rect x="{(c + border) * box}" y="{(r + border) * box}" width="{box}" height="{box}"/>' for r, row in enumerate(m) for c, d in enumerate(row) if d)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n * box} {n * box}" shape-rendering="crispEdges">'
            f'<rect width="100%" height="100%" fill="#fff"/><g fill="#000">{rects}</g></svg>')
