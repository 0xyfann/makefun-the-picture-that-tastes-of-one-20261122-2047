# SPDX-License-Identifier: MIT
"""A steaming bowl of ramen, top-down, rendered entirely in code.

One ingredient leads the picture — the rich amber broth — with golden
noodle nests, two jammy eggs, two chashu slices, a nori sheet, spring
onion rings, sesame, chilli-oil swirls and chopsticks on a walnut
table, steam curling above the bowl. Pure Python standard library,
fixed seed, fully deterministic: two runs write byte-identical PNGs.
"""

import math
import os
import random
import struct
import sys
import zlib

WIDTH = HEIGHT = 1024
SEED = 20261122
MAX_BYTES = 1_048_576


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def blend(dst, src, alpha):
    return tuple(int(round(dst[i] + (src[i] - dst[i]) * alpha)) for i in range(3))


def shade(colour, factor):
    return tuple(clamp(int(round(c * factor)), 0, 255) for c in colour)


class Canvas:
    """An RGB image held as rows of bytearrays, drawn row by row."""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.rows = [bytearray(width * 3) for _ in range(height)]

    def set_pixel(self, x, y, colour):
        if 0 <= x < self.width and 0 <= y < self.height:
            row = self.rows[y]
            row[x * 3:x * 3 + 3] = bytes(colour)

    def blend_pixel(self, x, y, colour, alpha):
        if 0 <= x < self.width and 0 <= y < self.height:
            row = self.rows[y]
            i = x * 3
            row[i:i + 3] = bytes(blend(tuple(row[i:i + 3]), colour, alpha))

    def fill_row_span(self, y, x0, x1, colour):
        if 0 <= y < self.height:
            x0 = clamp(x0, 0, self.width)
            x1 = clamp(x1, 0, self.width)
            if x1 > x0:
                self.rows[y][x0 * 3:x1 * 3] = bytes(colour) * (x1 - x0)

    def fill_row_gradient(self, y, x0, x1, palette):
        if 0 <= y < self.height:
            x0 = clamp(x0, 0, self.width)
            x1 = clamp(x1, 0, self.width)
            if x1 > x0:
                row = self.rows[y]
                n = x1 - x0
                for i in range(n):
                    t = i / max(1, n - 1)
                    c = palette(t)
                    row[(x0 + i) * 3:(x0 + i) * 3 + 3] = bytes(c)

    def _row_blend_span(self, y, x0, x1, colour, alpha):
        if 0 <= y < self.height:
            x0 = clamp(x0, 0, self.width)
            x1 = clamp(x1, 0, self.width)
            if x1 > x0:
                row = self.rows[y]
                for x in range(x0, x1):
                    i = x * 3
                    row[i:i + 3] = bytes(blend(tuple(row[i:i + 3]), colour, alpha))

    def disc(self, cx, cy, r, colour, alpha=1.0):
        r = int(round(r))
        for y in range(cy - r, cy + r + 1):
            dy = y - cy
            half = int(round(math.sqrt(max(0, r * r - dy * dy))))
            if alpha >= 1.0:
                self.fill_row_span(y, cx - half, cx + half + 1, colour)
            else:
                self._row_blend_span(y, cx - half, cx + half + 1, colour, alpha)

    def ellipse(self, cx, cy, rx, ry, colour, alpha=1.0):
        rx = int(round(rx))
        ry = int(round(ry))
        for y in range(cy - ry, cy + ry + 1):
            dy = (y - cy) / ry if ry else 0.0
            half = int(round(rx * math.sqrt(max(0.0, 1.0 - dy * dy))))
            if alpha >= 1.0:
                self.fill_row_span(y, cx - half, cx + half + 1, colour)
            else:
                self._row_blend_span(y, cx - half, cx + half + 1, colour, alpha)

    def ring(self, cx, cy, r, thickness, colour, alpha=1.0):
        r = int(round(r))
        t = int(round(thickness))
        for y in range(cy - r, cy + r + 1):
            dy = y - cy
            outer = int(round(math.sqrt(max(0, r * r - dy * dy))))
            inner = int(round(math.sqrt(max(0, (r - t) * (r - t) - dy * dy)))) if r - t > 0 else 0
            if alpha >= 1.0:
                self.fill_row_span(y, cx - outer, cx - inner, colour)
                self.fill_row_span(y, cx + inner, cx + outer + 1, colour)
            else:
                self._row_blend_span(y, cx - outer, cx - inner, colour, alpha)
                self._row_blend_span(y, cx + inner, cx + outer + 1, colour, alpha)

    def thick_line(self, x0, y0, x1, y1, width, colour, alpha=1.0):
        dx = x1 - x0
        dy = y1 - y0
        length = math.hypot(dx, dy)
        if length == 0:
            self.disc(int(round(x0)), int(round(y0)), width / 2, colour, alpha)
            return
        steps = max(1, int(length / max(1.0, width * 0.30)))
        for i in range(steps + 1):
            t = i / steps
            self.disc(int(round(x0 + dx * t)), int(round(y0 + dy * t)),
                      width / 2, colour, alpha)

    def polyline(self, points, width, colour, alpha=1.0):
        for a, b in zip(points, points[1:]):
            self.thick_line(a[0], a[1], b[0], b[1], width, colour, alpha)


# ---------------------------------------------------------------- PNG encoder

def _png_chunk(kind, data):
    chunk = kind + data
    return struct.pack(">I", len(data)) + chunk + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)


def _filter_row(type_, row, prev):
    if type_ == 0:
        return bytes(row)
    out = bytearray(len(row))
    if type_ == 1:
        for i, b in enumerate(row):
            out[i] = (b - (row[i - 3] if i >= 3 else 0)) & 0xFF
    elif type_ == 2:
        for i, b in enumerate(row):
            out[i] = (b - prev[i]) & 0xFF
    elif type_ == 3:
        for i, b in enumerate(row):
            left = row[i - 3] if i >= 3 else 0
            out[i] = (b - ((left + prev[i]) // 2)) & 0xFF
    else:
        for i, b in enumerate(row):
            a = row[i - 3] if i >= 3 else 0
            b_ = prev[i]
            c = prev[i - 3] if i >= 3 else 0
            p = a + b_ - c
            pa, pb, pc = abs(p - a), abs(p - b_), abs(p - c)
            pred = a if (pa <= pb and pa <= pc) else (b_ if pb <= pc else c)
            out[i] = (b - pred) & 0xFF
    return bytes(out)


def _signed_sum(data):
    return sum(b if b < 128 else b - 256 for b in data)


def encode_png(canvas):
    raw = bytearray()
    prev = bytes(canvas.width * 3)
    for row in canvas.rows:
        best = None
        best_sum = None
        for f in range(5):
            cand = _filter_row(f, row, prev)
            s = _signed_sum(cand)
            if best_sum is None or s < best_sum:
                best_sum = s
                best = bytes([f]) + cand
        raw += best
        prev = bytes(row)
    ihdr = struct.pack(">IIBBBBB", canvas.width, canvas.height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IHDR", ihdr)
            + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + _png_chunk(b"IEND", b""))


# ---------------------------------------------------------------- palette + geometry

CX, CY = 512, 545
BOWL_R = 392
BROTH_R = 332

WALNUT_LIGHT = (88, 58, 38)
WALNUT_DEEP = (46, 28, 17)
BOWL = (24, 26, 38)
BOWL_RIM = (52, 58, 84)
BROTH_DEEP = (146, 62, 12)
BROTH_MID = (196, 102, 22)
BROTH_LIGHT = (238, 158, 52)
BROTH_GLOSS = (252, 196, 104)
NOODLE = (232, 178, 74)
NOODLE_DARK = (196, 134, 44)
NOODLE_LIGHT = (250, 214, 130)
CHASHU = (198, 122, 88)
CHASHU_FAT = (238, 204, 172)
EGG_WHITE = (250, 244, 232)
YOLK = (232, 128, 24)
YOLK_DEEP = (196, 92, 12)
NORI = (22, 44, 26)
ONION = (96, 178, 74)
CHILLI = (178, 40, 16)
SESAME = (244, 230, 200)
CHOPSTICK = (122, 74, 40)
STEAM = (255, 250, 240)
SHADOW = (10, 8, 6)


# ---------------------------------------------------------------- scene

def draw_table(canvas, rng):
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        canvas.fill_row_gradient(y, 0, WIDTH, lambda u, t=t: lerp(WALNUT_LIGHT, WALNUT_DEEP, t))
    for seam_y in (250, 512, 774):
        pts = [(x, seam_y + int(round(3 * math.sin(x / 97.0 + seam_y)))) for x in range(0, WIDTH + 1, 32)]
        canvas.polyline(pts, 2.5, (30, 18, 10), 0.5)
    for _ in range(26):
        x0 = rng.randint(0, WIDTH - 1)
        y0 = rng.randint(0, HEIGHT - 1)
        x1 = x0 + rng.randint(-160, 160)
        y1 = y0 + rng.randint(-40, 40)
        canvas.thick_line(x0, y0, x1, y1, 1.5, (120, 84, 52), 0.35)


def draw_bowl_shadow(canvas):
    for r, a in ((430, 0.10), (420, 0.12), (408, 0.14), (396, 0.16), (384, 0.18)):
        canvas.disc(CX + 14, CY + 22, r, SHADOW, a)


def draw_bowl(canvas):
    canvas.disc(CX, CY, BOWL_R, BOWL)
    canvas.ring(CX, CY, BOWL_R - 14, 26, BOWL_RIM)
    # bright rim-light arc, upper-left
    for deg in range(150, 331, 3):
        rad = math.radians(deg)
        x = CX + int(round((BOWL_R - 14) * math.cos(rad)))
        y = CY + int(round((BOWL_R - 14) * math.sin(rad)))
        canvas.disc(x, y, 9, (120, 130, 180), 0.75)
    speckle = random.Random(SEED + 7)
    for _ in range(120):
        deg = speckle.uniform(0, 2 * math.pi)
        rr = speckle.uniform(BOWL_R - 40, BOWL_R - 2)
        x = CX + int(round(rr * math.cos(deg)))
        y = CY + int(round(rr * math.sin(deg)))
        canvas.disc(x, y, speckle.uniform(1.0, 2.5), (70, 76, 104), 0.5)


def draw_broth(canvas):
    lx, ly = CX - 90, CY - 110
    for y in range(CY - BROTH_R, CY + BROTH_R + 1):
        dy = y - CY
        half = int(round(math.sqrt(max(0, BROTH_R * BROTH_R - dy * dy))))
        x0, x1 = CX - half, CX + half + 1

        def palette(t, y=y, x0=x0, x1=x1):
            x = x0 + t * (x1 - x0)
            d = math.hypot(x - CX, y - CY) / BROTH_R
            dl = math.hypot(x - lx, y - ly) / BROTH_R
            tt = min(1.0, d * 0.75 + dl * 0.45)
            return lerp(BROTH_LIGHT, BROTH_DEEP, tt)

        canvas.fill_row_gradient(y, x0, x1, palette)
    for (ex, ey, erx, ery, a) in ((430, 430, 150, 60, 0.30),
                                   (640, 660, 170, 70, 0.22),
                                   (560, 380, 110, 45, 0.18),
                                   (380, 620, 90, 40, 0.25)):
        canvas.ellipse(ex, ey, erx, ery, BROTH_GLOSS, a)
    for r in (282, 297, 312):
        for deg in range(0, 360, 4):
            rad = math.radians(deg)
            x = CX + int(round(r * math.cos(rad)))
            y = CY + int(round(r * math.sin(rad)))
            canvas.disc(x, y, 4, CHILLI, 0.8)


def draw_noodles(canvas, rng):
    for _ in range(52):
        r = rng.uniform(38, 318)
        start = rng.uniform(0, 360)
        span = rng.uniform(40, 260)
        width = rng.uniform(9, 15)
        base = rng.uniform(0, 2 * math.pi)
        tint = rng.uniform(0, 1)
        col = lerp(NOODLE_DARK, NOODLE_LIGHT, tint)
        pts = []
        steps = max(8, int(span / 4))
        for i in range(steps + 1):
            deg = math.radians(start + span * i / steps)
            wob = 11 * math.sin(deg / 34 + base) + 4 * math.sin(deg / 9)
            rr = r + wob
            pts.append((CX + rr * math.cos(deg), CY + rr * math.sin(deg)))
        # dark under-strand, golden strand, light top edge
        canvas.polyline(pts, width + 3, NOODLE_DARK, 0.85)
        canvas.polyline(pts, width, col)
        top = [(x, y - width * 0.22) for x, y in pts]
        canvas.polyline(top, width * 0.45, NOODLE_LIGHT, 0.9)
    for _ in range(12):
        cx = CX + rng.uniform(-60, 60)
        cy = CY + rng.uniform(-60, 60)
        ang = rng.uniform(0, 2 * math.pi)
        ln = rng.uniform(40, 110)
        x1 = cx + ln * math.cos(ang)
        y1 = cy + ln * math.sin(ang)
        canvas.thick_line(cx, cy, x1, y1, rng.uniform(8, 12), NOODLE, 0.95)


def draw_nori(canvas):
    for y in range(470, 661):
        wob = int(round(6 * math.sin(y / 41.0)))
        x0 = 196 + wob
        x1 = 268 + wob
        canvas.fill_row_span(y, x0, x1, NORI)
    for x in (214, 232, 250):
        pts = [(x + int(round(4 * math.sin(y / 37.0))), y) for y in range(480, 651, 8)]
        canvas.polyline(pts, 2.0, (60, 96, 60), 0.6)


def draw_chashu(canvas, cx, cy, r, rot):
    canvas.disc(cx, cy, r, shade(CHASHU, 0.75))
    canvas.ring(cx, cy, r - 2, 10, CHASHU_FAT)
    mx = cx + int(round(r * 0.08))
    my = cy + int(round(r * 0.06))
    canvas.disc(mx, my, int(round(r * 0.82)), CHASHU)
    canvas.disc(mx, my, int(round(r * 0.45)), CHASHU_FAT, 0.9)
    canvas.ellipse(cx - int(r * 0.25), cy - int(r * 0.3), r * 0.35, r * 0.18,
                   (240, 170, 140), 0.5)


def draw_egg(canvas, cx, cy, rx, ry, rot):
    canvas.ellipse(cx + 3, cy + 4, rx, ry, (120, 110, 100), 0.5)
    canvas.ellipse(cx, cy, rx, ry, EGG_WHITE)
    canvas.ellipse(cx, cy, int(rx * 0.55), int(ry * 0.55), YOLK_DEEP)
    canvas.ellipse(cx, cy, int(rx * 0.48), int(ry * 0.48), YOLK)
    canvas.disc(cx - int(rx * 0.18), cy - int(ry * 0.2), 6, (255, 200, 120), 0.8)


def draw_onions(canvas, rng):
    for _ in range(52):
        deg = rng.uniform(0, 2 * math.pi)
        rr = rng.uniform(30, 305)
        x = CX + int(round(rr * math.cos(deg)))
        y = CY + int(round(rr * math.sin(deg)))
        r = rng.uniform(6, 11)
        canvas.ring(x, y, r, rng.uniform(3.5, 5.5), ONION, 0.95)
        canvas.disc(x, y, 2, (40, 90, 30), 0.9)


def draw_sesame(canvas, rng):
    for _ in range(70):
        deg = rng.uniform(0, 2 * math.pi)
        rr = rng.uniform(30, 310)
        x = CX + int(round(rr * math.cos(deg)))
        y = CY + int(round(rr * math.sin(deg)))
        canvas.ellipse(x, y, 4.5, 2.6, SESAME, 0.9)


def draw_chopsticks(canvas):
    for (y0, y1) in ((452, 288), (482, 318)):
        canvas.thick_line(1004, y0, 742, y1, 20, CHOPSTICK)
        canvas.thick_line(1004, y0 - 4, 742, y1 - 4, 7, (170, 120, 80), 0.8)
        canvas.disc(742, y1, 10, CHOPSTICK)
        canvas.disc(1004, y0, 10, CHOPSTICK)


def draw_steam(canvas, rng):
    top_edge = CY - BOWL_R  # 153
    for col_x in (430, 512, 596):
        base = rng.uniform(0, 2 * math.pi)
        y = 28
        while y <= top_edge:
            t = (top_edge - y) / (top_edge - 28)
            width = 26 - 22 * t
            alpha = max(0.02, 0.14 * (1 - t * 0.75))
            x = col_x + 10 * math.sin(y / 47.0 + base)
            canvas.disc(int(round(x)), y, width / 2, STEAM, alpha)
            y += 3


def draw_vignette(canvas):
    for (cx, cy) in ((0, 0), (WIDTH, 0), (0, HEIGHT), (WIDTH, HEIGHT)):
        canvas.disc(cx, cy, 430, SHADOW, 0.05)
        canvas.disc(cx, cy, 360, SHADOW, 0.05)


def build_image():
    rng = random.Random(SEED)
    canvas = Canvas(WIDTH, HEIGHT)
    draw_table(canvas, rng)
    draw_bowl_shadow(canvas)
    draw_bowl(canvas)
    draw_broth(canvas)
    draw_noodles(canvas, rng)
    draw_nori(canvas)
    draw_chashu(canvas, 600, 430, 78, 0)
    draw_chashu(canvas, 668, 520, 66, 0)
    draw_egg(canvas, 398, 468, 62, 50, 0)
    draw_egg(canvas, 470, 668, 58, 47, 0)
    draw_onions(canvas, rng)
    draw_sesame(canvas, rng)
    draw_chopsticks(canvas)
    draw_steam(canvas, rng)
    draw_vignette(canvas)
    return canvas


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    os.makedirs(out_dir, exist_ok=True)
    png = encode_png(build_image())
    if len(png) > MAX_BYTES:
        print(f"entry.png is {len(png)} bytes, over the {MAX_BYTES} limit", file=sys.stderr)
        return 1
    path = os.path.join(out_dir, "entry.png")
    with open(path, "wb") as fh:
        fh.write(png)
    print(f"wrote {path} ({len(png)} bytes, 1024x1024)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
