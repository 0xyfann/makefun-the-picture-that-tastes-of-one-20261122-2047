# SPDX-License-Identifier: MIT
"""A steaming bowl of ramen, top-down, rendered entirely in code.

main.py paints one 1024x1024 PNG (entry.png) with the Python standard
library only: a walnut table, a dark bowl of rich amber broth, golden
noodle nests, jammy eggs, chashu, nori, spring onion, sesame, chilli
oil and chopsticks, steam curling above the rim. One ingredient leads
the picture -- the broth -- and everything else is there to make you
taste it.

Deterministic: a single fixed seed drives every random choice, and the
PNG encoder writes no timestamps, so two runs produce byte-identical
files. No network, no files read.
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


def clamp(v, lo=0, hi=255):
    """Clamp a channel value into the 0..255 byte range."""
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    """Linear interpolation between two RGB colours, per channel."""
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def blend(dst, src, alpha):
    """Blend src over dst with the given opacity (0..1)."""
    return tuple(int(round(dst[i] + (src[i] - dst[i]) * alpha)) for i in range(3))


def shade(colour, factor):
    """Scale a colour's brightness by factor (darken < 1, lighten > 1)."""
    return tuple(clamp(int(round(c * factor))) for c in colour)


class Canvas:
    """An RGB image held as a list of bytearray rows."""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.rows = [bytearray(width * 3) for _ in range(height)]

    def set_pixel(self, x, y, colour):
        if 0 <= x < self.width and 0 <= y < self.height:
            row = self.rows[y]
            i = x * 3
            row[i] = colour[0]
            row[i + 1] = colour[1]
            row[i + 2] = colour[2]

    def blend_pixel(self, x, y, colour, alpha):
        if 0 <= x < self.width and 0 <= y < self.height and alpha > 0:
            row = self.rows[y]
            i = x * 3
            if alpha >= 1:
                row[i] = colour[0]
                row[i + 1] = colour[1]
                row[i + 2] = colour[2]
            else:
                row[i] = int(round(row[i] + (colour[0] - row[i]) * alpha))
                row[i + 1] = int(round(row[i + 1] + (colour[1] - row[i + 1]) * alpha))
                row[i + 2] = int(round(row[i + 2] + (colour[2] - row[i + 2]) * alpha))

    def fill_row_span(self, y, x0, x1, colour):
        """Fill a horizontal span of one row with a solid colour."""
        if 0 <= y < self.height:
            x0 = max(0, x0)
            x1 = min(self.width, x1)
            if x1 > x0:
                self.rows[y][x0 * 3:x1 * 3] = bytes(colour) * (x1 - x0)

    def fill_row_gradient(self, y, x0, x1, palette):
        """Fill a row span with one colour per pixel from a palette list."""
        if 0 <= y < self.height:
            x0 = max(0, x0)
            x1 = min(self.width, x1)
            row = self.rows[y]
            for x in range(x0, x1):
                c = palette[x - x0]
                i = x * 3
                row[i] = c[0]
                row[i + 1] = c[1]
                row[i + 2] = c[2]

    def _row_blend_span(self, y, x0, x1, colour, alpha):
        """Blend a colour over a horizontal span of one row."""
        if 0 <= y < self.height and alpha > 0:
            x0 = max(0, x0)
            x1 = min(self.width, x1)
            row = self.rows[y]
            for x in range(x0, x1):
                i = x * 3
                row[i] = int(round(row[i] + (colour[0] - row[i]) * alpha))
                row[i + 1] = int(round(row[i + 1] + (colour[1] - row[i + 1]) * alpha))
                row[i + 2] = int(round(row[i + 2] + (colour[2] - row[i + 2]) * alpha))

    def disc(self, cx, cy, r, colour, alpha=1.0):
        """Fill a disc, optionally translucent."""
        if r <= 0:
            return
        r2 = r * r
        y0 = max(0, int(math.floor(cy - r)))
        y1 = min(self.height - 1, int(math.ceil(cy + r)))
        for y in range(y0, y1 + 1):
            dy = y - cy
            dx = math.sqrt(max(0.0, r2 - dy * dy))
            x0 = int(math.ceil(cx - dx))
            x1 = int(math.floor(cx + dx)) + 1
            if alpha >= 1:
                self.fill_row_span(y, x0, x1, colour)
            else:
                self._row_blend_span(y, x0, x1, colour, alpha)

    def ellipse(self, cx, cy, rx, ry, colour, alpha=1.0):
        """Fill an axis-aligned ellipse, optionally translucent."""
        if rx <= 0 or ry <= 0:
            return
        y0 = max(0, int(math.floor(cy - ry)))
        y1 = min(self.height - 1, int(math.ceil(cy + ry)))
        for y in range(y0, y1 + 1):
            dy = (y - cy) / ry
            dx = rx * math.sqrt(max(0.0, 1.0 - dy * dy))
            x0 = int(math.ceil(cx - dx))
            x1 = int(math.floor(cx + dx)) + 1
            if alpha >= 1:
                self.fill_row_span(y, x0, x1, colour)
            else:
                self._row_blend_span(y, x0, x1, colour, alpha)

    def ring(self, cx, cy, r, thickness, colour, alpha=1.0):
        """Draw a ring (annulus) of the given thickness."""
        if r <= 0 or thickness <= 0:
            return
        ro = r
        ri = max(0.0, r - thickness)
        ro2 = ro * ro
        ri2 = ri * ri
        y0 = max(0, int(math.floor(cy - ro)))
        y1 = min(self.height - 1, int(math.ceil(cy + ro)))
        for y in range(y0, y1 + 1):
            dy = y - cy
            dxo = math.sqrt(max(0.0, ro2 - dy * dy))
            dxi = math.sqrt(max(0.0, ri2 - dy * dy)) if ri > 0 else 0.0
            for x0, x1 in ((int(math.ceil(cx - dxo)), int(math.floor(cx - dxi)) + 1),
                           (int(math.ceil(cx + dxi)), int(math.floor(cx + dxo)) + 1)):
                if x1 > x0:
                    if alpha >= 1:
                        self.fill_row_span(y, x0, x1, colour)
                    else:
                        self._row_blend_span(y, x0, x1, colour, alpha)

    def thick_line(self, x0, y0, x1, y1, width, colour, alpha=1.0):
        """Draw a thick line by stamping discs along the segment."""
        dx = x1 - x0
        dy = y1 - y0
        length = math.hypot(dx, dy)
        if length == 0:
            self.disc(x0, y0, width / 2.0, colour, alpha)
            return
        step = length / max(1, int(length / (width * 0.30)) + 1)
        n = max(1, int(length / step))
        for i in range(n + 1):
            t = i / n
            self.disc(x0 + dx * t, y0 + dy * t, width / 2.0, colour, alpha)

    def polyline(self, points, width, colour, alpha=1.0):
        """Draw a thick polyline through the given points."""
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            self.thick_line(x0, y0, x1, y1, width, colour, alpha)


# ---------------------------------------------------------------------------
# PNG encoder (pure stdlib, deterministic)
# ---------------------------------------------------------------------------

def _png_chunk(kind, data):
    """One PNG chunk: length + kind + data + CRC32."""
    out = struct.pack(">I", len(data))
    out += kind
    out += data
    out += struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return out


def _filter_row(ftype, row, prev):
    """Apply one PNG row filter. prev is the previous unfiltered row."""
    n = len(row)
    out = bytearray(n)
    if ftype == 0:  # None
        out[:] = row
    elif ftype == 1:  # Sub
        for i in range(n):
            a = row[i - 3] if i >= 3 else 0
            out[i] = (row[i] - a) & 0xFF
    elif ftype == 2:  # Up
        for i in range(n):
            out[i] = (row[i] - prev[i]) & 0xFF
    elif ftype == 3:  # Average
        for i in range(n):
            a = row[i - 3] if i >= 3 else 0
            out[i] = (row[i] - ((a + prev[i]) >> 1)) & 0xFF
    else:  # Paeth
        for i in range(n):
            a = row[i - 3] if i >= 3 else 0
            b = prev[i]
            c = prev[i - 3] if i >= 3 else 0
            p = a + b - c
            pa = abs(p - a)
            pb = abs(p - b)
            pc = abs(p - c)
            pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
            out[i] = (row[i] - pr) & 0xFF
    return bytes(out)


def _signed_sum(data):
    """Sum of bytes read as signed (-128..127); filter choice metric."""
    return sum(b - 256 if b >= 128 else b for b in data)


def encode_png(canvas):
    """Encode the canvas as a deterministic PNG (8-bit RGB, type 2)."""
    width, height = canvas.width, canvas.height
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = bytearray()
    prev = bytes(width * 3)
    for y in range(height):
        row = bytes(canvas.rows[y])
        best = None
        best_score = None
        for ftype in range(5):
            filtered = _filter_row(ftype, row, prev)
            score = _signed_sum(filtered)
            if best_score is None or score < best_score:
                best_score = score
                best = bytes([ftype]) + filtered
        raw += best
        prev = row
    idat = zlib.compress(bytes(raw), 9)
    png = b"\x89PNG\r\n\x1a\n"
    png += _png_chunk(b"IHDR", ihdr)
    png += _png_chunk(b"IDAT", idat)
    png += _png_chunk(b"IEND", b"")
    return png


# ---------------------------------------------------------------------------
# Palette + geometry
# ---------------------------------------------------------------------------

CX, CY = 512, 545
BOWL_R = 392
BROTH_R = 332

TABLE_TOP = (88, 58, 38)
TABLE_BOTTOM = (46, 28, 17)
TABLE_SEAM = (30, 18, 10)
TABLE_GRAIN = (110, 76, 50)

BOWL_BODY = (24, 26, 38)
BOWL_RIM = (52, 58, 84)
BOWL_RIM_LIGHT = (150, 158, 200)
BOWL_SHADOW = (10, 8, 14)

BROTH_DEEP = (146, 62, 12)
BROTH_MID = (196, 102, 22)
BROTH_LIGHT = (238, 158, 52)
BROTH_GLOSS = (252, 196, 104)

NOODLE = (232, 178, 74)
NOODLE_DARK = (196, 134, 44)
NOODLE_LIGHT = (250, 214, 130)

CHASHU = (198, 122, 88)
CHASHU_FAT = (238, 204, 172)
CHASHU_DARK = (150, 82, 56)

EGG_WHITE = (250, 244, 232)
EGG_WHITE_SHADE = (228, 218, 200)
YOLK = (232, 128, 24)
YOLK_DEEP = (198, 96, 12)
YOLK_GLOSS = (255, 190, 90)

NORI = (22, 44, 26)
NORI_SHEEN = (60, 96, 58)

ONION = (96, 178, 74)
ONION_DARK = (52, 110, 40)

CHILLI = (178, 40, 16)
SESAME = (244, 230, 200)
CHOPSTICK = (122, 74, 40)
CHOPSTICK_LIGHT = (168, 112, 66)
STEAM = (255, 250, 240)
VIGNETTE = (12, 8, 6)


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------

def draw_table(canvas, rng):
    """Walnut table: vertical gradient, plank seams, faint grain."""
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        canvas.fill_row_span(y, 0, WIDTH, lerp(TABLE_TOP, TABLE_BOTTOM, t))
    for base_y, phase in ((250, 0.0), (512, 1.7), (774, 3.1)):
        points = []
        for x in range(0, WIDTH + 1, 32):
            points.append((x, base_y + 3.0 * math.sin(x / 90.0 + phase)))
        canvas.polyline(points, 2.5, TABLE_SEAM, alpha=0.5)
    for _ in range(26):
        x0 = rng.uniform(0, WIDTH - 200)
        y = rng.uniform(0, HEIGHT)
        length = rng.uniform(60, 220)
        canvas.thick_line(x0, y, x0 + length, y + rng.uniform(-4, 4),
                          rng.uniform(1.0, 2.0), TABLE_GRAIN, alpha=0.35)


def draw_bowl_shadow(canvas):
    """Soft stacked shadow under the bowl."""
    for i in range(5):
        r = 430 - i * 12
        alpha = 0.10 + i * 0.02
        canvas.disc(CX + 6, CY + 12, r, BOWL_SHADOW, alpha=alpha)


def draw_bowl(canvas):
    """Dark bowl body, rim ring, rim light and speckles."""
    canvas.disc(CX, CY, BOWL_R, BOWL_BODY)
    canvas.ring(CX, CY, BOWL_R - 14, 26, BOWL_RIM)
    # Bright rim-light arc, upper-left (angles 150..330 degrees).
    for deg in range(150, 331, 4):
        a = math.radians(deg)
        x = CX + (BOWL_R - 14) * math.cos(a)
        y = CY + (BOWL_R - 14) * math.sin(a)
        canvas.disc(x, y, 9, BOWL_RIM_LIGHT, alpha=0.75)
    # Rim speckles from their own generator so the main stream is untouched.
    speck = random.Random(SEED + 7)
    for _ in range(90):
        a = speck.uniform(0, 2 * math.pi)
        r = speck.uniform(BOWL_R - 40, BOWL_R - 2)
        x = CX + r * math.cos(a)
        y = CY + r * math.sin(a)
        canvas.disc(x, y, speck.uniform(1.0, 2.5),
                    shade(BOWL_RIM, speck.uniform(1.2, 1.8)), alpha=0.5)


def draw_broth(canvas):
    """Amber broth: radial gradient, gloss, chilli-oil arcs."""
    lx, ly = CX - 90, CY - 110
    for y in range(CY - BROTH_R, CY + BROTH_R + 1):
        dy = y - CY
        dx = math.sqrt(max(0.0, BROTH_R * BROTH_R - dy * dy))
        x0 = int(math.ceil(CX - dx))
        x1 = int(math.floor(CX + dx)) + 1
        palette = []
        for x in range(x0, x1):
            d = math.hypot(x - CX, y - CY) / BROTH_R
            dl = math.hypot(x - lx, y - ly) / BROTH_R
            t = min(1.0, d * 0.75 + dl * 0.45)
            palette.append(lerp(BROTH_LIGHT, BROTH_DEEP, t))
        canvas.fill_row_gradient(y, x0, x1, palette)
    # Gloss highlights near the light point.
    for (gx, gy, grx, gry, ga) in ((CX - 130, CY - 140, 120, 46, 0.30),
                                   (CX - 40, CY - 170, 80, 30, 0.22),
                                   (CX + 90, CY - 60, 60, 24, 0.18),
                                   (CX - 190, CY + 40, 70, 28, 0.20)):
        canvas.ellipse(gx, gy, grx, gry, BROTH_GLOSS, alpha=ga)
    # Chilli-oil arcs floating on the broth.
    for (r, a0, a1) in ((282, 20, 150), (297, 200, 320), (312, 300, 40)):
        points = []
        a = a0
        while True:
            rad = math.radians(a)
            points.append((CX + r * math.cos(rad), CY + r * math.sin(rad)))
            a += 5
            if (a1 > a0 and a > a1) or (a1 <= a0 and a > a1 + 360):
                break
        canvas.polyline(points, 7, CHILLI, alpha=0.8)


def draw_noodles(canvas, rng):
    """52 golden noodle nests, each strand drawn in three passes."""
    for _ in range(52):
        r = rng.uniform(38, 318)
        a0 = rng.uniform(0, 360)
        span = rng.uniform(40, 260)
        width = rng.uniform(9, 15)
        base = rng.uniform(0, 2 * math.pi)
        tint = rng.uniform(0, 1)
        strand_col = lerp(NOODLE_DARK, NOODLE, tint)
        points = []
        steps = max(8, int(span / 4))
        for i in range(steps + 1):
            deg = a0 + span * i / steps
            rad = math.radians(deg)
            rr = r + 11 * math.sin(deg / 34.0 + base) + 4 * math.sin(deg / 9.0)
            points.append((CX + rr * math.cos(rad), CY + rr * math.sin(rad)))
        # Dark under-strand, golden strand, light top edge.
        canvas.polyline(points, width + 3, NOODLE_DARK, alpha=0.85)
        canvas.polyline(points, width, strand_col)
        top = [(x, y - width * 0.22) for (x, y) in points]
        canvas.polyline(top, width * 0.45, NOODLE_LIGHT, alpha=0.9)
    # 12 short lifted cross-strands near the centre.
    for _ in range(12):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(0, 90)
        x0 = CX + d * math.cos(a)
        y0 = CY + d * math.sin(a)
        length = rng.uniform(40, 110)
        ang = rng.uniform(0, 2 * math.pi)
        x1 = x0 + length * math.cos(ang)
        y1 = y0 + length * math.sin(ang)
        w = rng.uniform(8, 12)
        canvas.thick_line(x0, y0, x1, y1, w + 3, NOODLE_DARK, alpha=0.85)
        canvas.thick_line(x0, y0, x1, y1, w, lerp(NOODLE_DARK, NOODLE, rng.uniform(0, 1)))


def draw_nori(canvas):
    """Wavy vertical nori sheet on the left of the bowl."""
    for y in range(470, 661):
        wob = 8.0 * math.sin(y / 40.0)
        x0 = int(196 + wob)
        x1 = int(268 + 8.0 * math.sin(y / 40.0 + 1.0))
        canvas.fill_row_span(y, x0, x1, NORI)
    for sx in (215, 232, 250):
        points = [(sx + 6.0 * math.sin(y / 45.0), y) for y in range(480, 651, 12)]
        canvas.polyline(points, 2.0, NORI_SHEEN, alpha=0.5)


def draw_chashu(canvas, cx, cy, r, rot):
    """One chashu slice: dark edge, fat ring, meat, inner fat, gloss."""
    canvas.disc(cx, cy, r, CHASHU_DARK)
    canvas.ring(cx, cy, r * 0.85, r * 0.18, CHASHU_FAT)
    mx, my = cx + r * 0.08, cy + r * 0.06
    canvas.disc(mx, my, r * 0.78, CHASHU)
    canvas.disc(mx, my, r * 0.35, CHASHU_FAT)
    gx = mx + r * 0.35 * math.cos(rot)
    gy = my + r * 0.35 * math.sin(rot)
    canvas.ellipse(gx, gy, r * 0.28, r * 0.16, BROTH_GLOSS, alpha=0.3)


def draw_egg(canvas, cx, cy, rx, ry, rot):
    """One jammy egg: white, deep yolk, bright yolk, gloss dot."""
    canvas.ellipse(cx, cy + 3, rx + 3, ry + 3, EGG_WHITE_SHADE)
    canvas.ellipse(cx, cy, rx, ry, EGG_WHITE)
    yx = cx + rx * 0.15 * math.cos(rot)
    yy = cy + ry * 0.15 * math.sin(rot)
    canvas.ellipse(yx, yy, rx * 0.55, ry * 0.55, YOLK_DEEP)
    canvas.ellipse(yx, yy, rx * 0.48, ry * 0.48, YOLK)
    canvas.disc(yx - rx * 0.18, yy - ry * 0.2, rx * 0.12, YOLK_GLOSS, alpha=0.9)


def draw_onions(canvas, rng):
    """52 spring-onion rings scattered over the broth."""
    for _ in range(52):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(30, 305)
        x = CX + d * math.cos(a)
        y = CY + d * math.sin(a)
        r = rng.uniform(6, 11)
        canvas.ring(x, y, r, rng.uniform(3.5, 5.5), ONION)
        canvas.disc(x, y, 2.0, ONION_DARK)


def draw_sesame(canvas, rng):
    """70 tiny sesame seeds over the broth."""
    for _ in range(70):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(0, 320)
        x = CX + d * math.cos(a)
        y = CY + d * math.sin(a)
        if rng.random() < 0.5:
            canvas.ellipse(x, y, 4.5, 2.6, SESAME)
        else:
            canvas.ellipse(x, y, 2.6, 4.5, SESAME)


def draw_chopsticks(canvas):
    """Two chopsticks resting diagonally over the bowl's right edge."""
    for (sx, sy, tx, ty) in ((1004, 452, 742, 288), (1004, 482, 742, 318)):
        canvas.thick_line(sx, sy, tx, ty, 20, CHOPSTICK)
        canvas.thick_line(sx, sy - 4, tx, ty - 4, 7, CHOPSTICK_LIGHT, alpha=0.9)
        canvas.disc(tx, ty, 7, CHOPSTICK)
        canvas.disc(tx, ty, 3.5, CHOPSTICK_LIGHT)


def draw_steam(canvas, rng):
    """Three steam columns rising above the bowl -- never below the rim."""
    top_edge = CY - BOWL_R  # 153: the bowl's top rim
    for col, phase in ((430, 0.0), (512, 2.1), (596, 4.2)):
        for band in range(3):
            width = 26 - band * 6
            y = top_edge
            prev = None
            while y > 28:
                y_next = max(28, y - 10)
                ym = (y + y_next) / 2.0
                t = (top_edge - ym) / (top_edge - 28)
                alpha = 0.14 * (1.0 - t * 0.75) - band * 0.03
                if alpha > 0:
                    x0 = col + 12.0 * math.sin((top_edge - y) / 45.0 + phase)
                    x1 = col + 12.0 * math.sin((top_edge - y_next) / 45.0 + phase)
                    canvas.thick_line(x0, y, x1, y_next, width, STEAM, alpha=alpha)
                y = y_next


def draw_vignette(canvas):
    """Very faint corner darkening -- keep it subtle."""
    for (cx, cy) in ((0, 0), (WIDTH, 0), (0, HEIGHT), (WIDTH, HEIGHT)):
        canvas.disc(cx, cy, 430, VIGNETTE, alpha=0.05)
        canvas.disc(cx, cy, 360, VIGNETTE, alpha=0.05)


# ---------------------------------------------------------------------------
# Build + entry point
# ---------------------------------------------------------------------------

def build_image():
    """Draw the whole scene in fixed order and return the canvas."""
    rng = random.Random(SEED)
    canvas = Canvas(WIDTH, HEIGHT)
    draw_table(canvas, rng)
    draw_bowl_shadow(canvas)
    draw_bowl(canvas)
    draw_broth(canvas)
    draw_noodles(canvas, rng)
    draw_nori(canvas)
    draw_chashu(canvas, 600, 430, 78, 0.6)
    draw_chashu(canvas, 668, 520, 66, 2.4)
    draw_egg(canvas, 398, 468, 62, 50, 0.9)
    draw_egg(canvas, 470, 668, 58, 47, 2.8)
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
        print(f"error: entry.png is {len(png)} bytes, over the {MAX_BYTES} limit",
              file=sys.stderr)
        return 1
    path = os.path.join(out_dir, "entry.png")
    with open(path, "wb") as f:
        f.write(png)
    print(f"wrote {path} ({len(png)} bytes, 1024x1024)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
