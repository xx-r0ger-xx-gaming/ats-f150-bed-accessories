"""Generate the placeholder mod icon (original artwork: pickup + bed shell silhouette at dusk).

  python scripts/make_icon.py [--output src/mod/mod_icon.jpg]

Stdlib-only baseline JPEG writer (YCbCr 4:4:4, flat quantisation, fixed-length Huffman codes
that are valid canonical JPEG tables). Size 276x162 JPG is the documented Workshop icon spec
(modding.scssoft.com Mod_manager + Workshop validation errors: ".jpg ... exactly 276x162", <= 1 MB).
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.common import make_parser, repo_path, run_main, script_args  # noqa: E402

W, H = 276, 162
ZIGZAG = [0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34,
          27, 20, 13, 6, 7, 14, 21, 28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37,
          44, 51, 58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63]
QUANT = 3  # flat quantiser: smooth artwork, small error, file stays tiny anyway

# Huffman tables: DC = 12 symbols x 4-bit codes, AC = 162 symbols x 8-bit codes (canonical order).
DC_SYMS = list(range(12))
AC_SYMS = [0x00, 0xF0] + [(r << 4) | s for r in range(16) for s in range(1, 11)]
DC_CODE = {sym: (i, 4) for i, sym in enumerate(DC_SYMS)}
AC_CODE = {sym: (i, 8) for i, sym in enumerate(AC_SYMS)}


def draw():
    """Return rows of (r, g, b) tuples."""
    px = [[None] * W for _ in range(H)]
    for y in range(H):
        t = y / (H - 1)
        sky = (int(24 + 200 * t ** 1.6), int(40 + 90 * t ** 1.4), int(90 + 40 * t))
        for x in range(W):
            px[y][x] = sky
    ground = 128

    def rect(x0, y0, x1, y1, c):
        for y in range(max(0, y0), min(H, y1)):
            for x in range(max(0, x0), min(W, x1)):
                px[y][x] = c

    def circle(cx, cy, r, c):
        for y in range(int(cy - r), int(cy + r) + 1):
            for x in range(int(cx - r), int(cx + r) + 1):
                if 0 <= x < W and 0 <= y < H and (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    px[y][x] = c

    for y in range(ground, H):  # road
        for x in range(W):
            px[y][x] = (38, 40, 46)
    rect(0, ground, W, ground + 2, (200, 170, 90))
    rect(0, 150, W, 152, (230, 230, 230))
    body, shade, glass = (196, 52, 40), (150, 36, 30), (150, 190, 215)
    # stylised pickup facing right: bed (left) + cab (right)
    rect(38, 96, 236, 124, body)                       # lower body
    rect(150, 70, 214, 98, body)                       # cab
    rect(158, 76, 206, 96, glass)                      # windows
    rect(180, 76, 183, 96, shade)                      # B pillar
    rect(228, 104, 242, 124, shade)                    # bumper
    rect(30, 118, 240, 124, shade)                     # sill
    rect(46, 56, 148, 98, body)                        # camper shell
    rect(46, 54, 148, 58, shade)                       # roof edge
    rect(62, 66, 128, 84, glass)                       # shell window
    rect(94, 66, 97, 84, shade)
    for cx in (84, 196):                               # wheels
        circle(cx, 126, 17, (18, 18, 20))
        circle(cx, 126, 8, (170, 172, 178))
    rect(232, 104, 238, 110, (255, 224, 140))          # headlight
    return px


def rgb_to_ycc(r, g, b):
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb = -0.168736 * r - 0.331264 * g + 0.5 * b + 128
    cr = 0.5 * r - 0.418688 * g - 0.081312 * b + 128
    return y, cb, cr


COS = [[math.cos((2 * x + 1) * u * math.pi / 16) for x in range(8)] for u in range(8)]


def fdct(block):
    """block: 8x8 list of floats (level-shifted). Returns zigzag-ordered quantised ints."""
    tmp = [[sum(block[y][x] * COS[u][x] for x in range(8)) for u in range(8)] for y in range(8)]
    out = [0] * 64
    for v in range(8):
        for u in range(8):
            s = sum(tmp[y][u] * COS[v][y] for y in range(8))
            cu = 1 / math.sqrt(2) if u == 0 else 1
            cv = 1 / math.sqrt(2) if v == 0 else 1
            out[v * 8 + u] = int(round(0.25 * cu * cv * s / QUANT))
    return [out[i] for i in ZIGZAG]


class BitWriter:
    def __init__(self):
        self.buf = bytearray()
        self.acc = 0
        self.n = 0

    def put(self, code, length):
        self.acc = (self.acc << length) | (code & ((1 << length) - 1))
        self.n += length
        while self.n >= 8:
            byte = (self.acc >> (self.n - 8)) & 0xFF
            self.buf.append(byte)
            if byte == 0xFF:
                self.buf.append(0x00)
            self.n -= 8
        self.acc &= (1 << self.n) - 1

    def flush(self):
        if self.n:
            self.put((1 << (8 - self.n)) - 1, 8 - self.n)


def size_bits(v):
    return abs(v).bit_length()


def amp_bits(v, s):
    return v if v >= 0 else v + (1 << s) - 1


def encode_block(bw, zz, prev_dc):
    diff = zz[0] - prev_dc
    s = size_bits(diff)
    bw.put(*DC_CODE[s])
    if s:
        bw.put(amp_bits(diff, s), s)
    run = 0
    for i in range(1, 64):
        v = zz[i]
        if v == 0:
            run += 1
            continue
        while run > 15:
            bw.put(*AC_CODE[0xF0])
            run -= 16
        s = size_bits(v)
        bw.put(*AC_CODE[(run << 4) | s])
        bw.put(amp_bits(v, s), s)
        run = 0
    if run:
        bw.put(*AC_CODE[0x00])
    return zz[0]


def segment(marker, payload):
    return b"\xff" + bytes([marker]) + (len(payload) + 2).to_bytes(2, "big") + payload


def encode_jpeg(px):
    planes = [[[0.0] * W for _ in range(H)] for _ in range(3)]
    for y in range(H):
        for x in range(W):
            planes[0][y][x], planes[1][y][x], planes[2][y][x] = rgb_to_ycc(*px[y][x])
    bw = BitWriter()
    prev = [0, 0, 0]
    for by in range(0, H, 8):
        for bx in range(0, W, 8):
            for c in range(3):
                blk = [[planes[c][min(by + j, H - 1)][min(bx + i, W - 1)] - 128 for i in range(8)]
                       for j in range(8)]
                prev[c] = encode_block(bw, fdct(blk), prev[c])
    bw.flush()

    out = bytearray(b"\xff\xd8")
    out += segment(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
    out += segment(0xDB, bytes([0]) + bytes([QUANT] * 64))
    out += segment(0xC0, bytes([8]) + H.to_bytes(2, "big") + W.to_bytes(2, "big") +
                   bytes([3, 1, 0x11, 0, 2, 0x11, 0, 3, 0x11, 0]))
    dc_bits = [0, 0, 0, 12] + [0] * 12          # twelve 4-bit codes
    ac_bits = [0] * 7 + [len(AC_SYMS)] + [0] * 8  # 162 8-bit codes
    out += segment(0xC4, bytes([0x00]) + bytes(dc_bits) + bytes(DC_SYMS) +
                   bytes([0x10]) + bytes(ac_bits) + bytes(AC_SYMS))
    out += segment(0xDA, bytes([3, 1, 0x00, 2, 0x00, 3, 0x00, 0, 63, 0]))
    out += bw.buf + b"\xff\xd9"
    return bytes(out)


def main():
    ap = make_parser("Generate placeholder 276x162 JPG mod icon")
    ap.add_argument("--output", default="src/mod/mod_icon.jpg")
    args = ap.parse_args(script_args())
    out = repo_path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = encode_jpeg(draw())
    out.write_bytes(data)
    print(f"wrote {out} ({len(data)} bytes, {W}x{H})")


if __name__ == "__main__":
    run_main(main)
