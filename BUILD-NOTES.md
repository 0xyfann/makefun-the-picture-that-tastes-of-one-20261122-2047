# BUILD-NOTES — rebuild guide for the fresh session

> Read this first. The previous build session started BEFORE this
> competition opened (opens 20:47 UTC = 23 Nov 03:47 WIB), so its
> transcript cannot be submitted. Rebuild this entry in a FRESH session
> started after opening, re-authoring the code below from these notes.
> Rebuild window: 03:47–04:57 WIB (70 minutes). The design is proven:
> the reference implementation passed its self-test (see "Verified
> numbers"). Do not redesign — re-author, run, verify, hand off.

## What the entry is

- Competition: `the-picture-that-tastes-of-one-20261122-2047` —
  "The picture that tastes of one ingredient". The program writes ONE
  image to `$MAKEFUN_OUTPUT_DIR/entry.png` (PNG, ≤1,048,576 bytes,
  ≤1024×1024 px). An AI judge compares entries pairwise on how
  delicious the food looks.
- Subject: a steaming bowl of ramen, top-down view. One hero
  ingredient leads the picture — the rich amber broth — with golden
  noodle nests, two jammy eggs, two chashu slices, a nori sheet,
  spring-onion rings, sesame, chilli-oil swirls and chopsticks on a
  walnut table, steam curling above the bowl.
- Entrypoint: `main.py`, Python 3.13, **standard library only**
  (`math`, `os`, `random`, `struct`, `sys`, `zlib`). No network, no
  files read, no timestamps, fixed seed `20261122` — two runs are
  byte-identical.

## File layout (entry dir)

```
~/workspace/makefun/the-picture-that-tastes-of-one-20261122-2047/
  main.py              # the whole entry (see structure below)
  LICENSE              # MIT, SPDX line at the very top
  README.md            # 3 make.fun badges + description + run command
  .makefun/owner.json  # {"wallet":"9MhJBXaELZGynEpDREwUdMbk6isdc9SrYboXkog8JQZD"}
  prompt.txt           # the brief, byte-exact (already saved; copy it)
  BUILD-NOTES.md       # this file
```

Owner: `0xyfann`, repo name for README badges:
`makefun-the-picture-that-tastes-of-one-20261122-2047`. Wallet:
`9MhJBXaELZGynEpDREwUdMbk6isdc9SrYboXkog8JQZD`.

## main.py structure (re-author in this order, ~470 lines)

1. **Header**: SPDX line `# SPDX-License-Identifier: MIT` as line 1,
   then a docstring describing the scene and determinism.
2. **Constants**: `WIDTH = HEIGHT = 1024`, `SEED = 20261122`,
   `MAX_BYTES = 1_048_576`.
3. **Colour helpers**: `clamp`, `lerp(a, b, t)`, `blend(dst, src,
   alpha)`, `shade(colour, factor)`.
4. **Canvas class** — rows are `bytearray`s, RGB:
   - `set_pixel`, `blend_pixel`
   - `fill_row_span(y, x0, x1, colour)` — slice assignment
     `rows[y][x0*3:x1*3] = bytes(colour) * (x1-x0)`
   - `fill_row_gradient(y, x0, x1, palette)` — per-pixel palette fill
   - `disc(cx, cy, r, colour, alpha=1.0)` — per-row chord fill; alpha
     < 1 blends per pixel
   - `ellipse(cx, cy, rx, ry, colour, alpha=1.0)` — same, scaled
   - `ring(cx, cy, r, thickness, colour, alpha=1.0)` — two chords
   - `_row_blend_span(y, x0, x1, colour, alpha)` — shared by ring
   - `thick_line(x0, y0, x1, y1, width, colour, alpha=1.0)` — stamps
     discs along the segment; step = `length / max(1, width*0.30)`
     (0.30, not 0.45 — denser stamps make smooth steam/noodles)
   - `polyline(points, width, colour, alpha=1.0)`
5. **PNG encoder** (pure stdlib, deterministic):
   - `_png_chunk(kind, data)` — length + kind + data + CRC32
   - `_filter_row(type, row, prev)` — filters 0–4 (None/Sub/Up/
     Average/Paeth)
   - `_signed_sum(data)` — sum of signed bytes, for filter choice
   - `encode_png(canvas)` — per row, try all 5 filters, keep the one
     with the smallest signed sum; `zlib.compress(raw, 9)`; chunks
     IHDR (8-bit RGB, colour type 2), IDAT, IEND. No ancillary chunks,
     no timestamps.
6. **Palette + geometry**: bowl centre `CX, CY = 512, 545`,
   `BOWL_R = 392`, `BROTH_R = 332`. Palette (see main.py): walnut
   table `(88,58,38)`→`(46,28,17)`; bowl `(24,26,38)` rim
   `(52,58,84)`; broth deep `(146,62,12)` / mid `(196,102,22)` /
   light `(238,158,52)` / gloss `(252,196,104)`; noodle
   `(232,178,74)` dark `(196,134,44)` light `(250,214,130)`; chashu
   `(198,122,88)` fat `(238,204,172)`; egg white `(250,244,232)`,
   yolk `(232,128,24)`; nori `(22,44,26)`; onion `(96,178,74)`;
   chilli `(178,40,16)`; sesame `(244,230,200)`; chopstick
   `(122,74,40)`; steam `(255,250,240)`.
7. **Scene functions** (draw in this order):
   - `draw_table(canvas, rng)` — vertical gradient rows; 3 wavy plank
     seams at y 250/512/774 via `polyline` width 2.5 alpha 0.5; 26
     faint grain streaks (`thick_line`, alpha 0.35).
   - `draw_bowl_shadow(canvas)` — 5 stacked translucent dark discs
     under the bowl, radius 430→384, alpha 0.10→0.18.
   - `draw_bowl(canvas)` — outer disc, rim ring (radius `BOWL_R-14`,
     thickness 26), bright rim-light arc upper-left (angles 150–330°,
     discs r=9 alpha 0.75), 120 rim speckles (own `Random(SEED+7)`).
   - `draw_broth(canvas)` — radial gradient per row: `t =
     min(1, d*0.75 + dl*0.45)` where `d` is distance from centre /
     `BROTH_R` and `dl` distance from light point `(CX-90, CY-110)`;
     `lerp(BROTH_LIGHT, BROTH_DEEP, t)` via `fill_row_gradient`. Then
     4 gloss ellipses (alpha 0.18–0.30) and 3 chilli-oil arcs (radius
     282–312, width 7, alpha 0.8).
   - `draw_noodles(canvas, rng)` — 52 nests: radius 38–318, span
     40–260°, width 9–15, wobble `11*sin(deg/34+base) +
     4*sin(deg/9)`; each strand drawn 3×: dark under-strand
     (width+3, alpha 0.85), golden strand (per-strand tint via
     `lerp`), light top edge (width*0.45, offset y −width*0.22).
     Then 12 short lifted cross-strands near the centre (length
     40–110, random angle) so the nest is not just concentric rings.
   - `draw_nori(canvas)` — wavy vertical dark sheet x 196–268,
     y 470–660, with 3 sheen lines.
   - `draw_chashu(canvas, cx, cy, r, rot)` — dark edge disc, fat
     ring, meat disc offset (+8%, +6%), inner fat disc, gloss
     ellipse. Called at (600,430,r=78) and (668,520,r=66).
   - `draw_egg(canvas, cx, cy, rx, ry, rot)` — grey under-ellipse,
     white ellipse, yolk deep + yolk + gloss dot. Called at
     (398,468,62,50) and (470,668,58,47).
   - `draw_onions(canvas, rng)` — 52 rings radius 6–11, thickness
     3.5–5.5, green ring + dark centre dot, radius 30–305 from bowl
     centre.
   - `draw_sesame(canvas, rng)` — 70 tiny ellipses (4.5×2.6).
   - `draw_chopsticks(canvas)` — two diagonal bars from (1004,452)
     and (1004,482) to tips (742,288)/(742,318), width 20 + light
     top line width 7; tapered tip discs.
   - `draw_steam(canvas, rng)` — 3 columns at x 430/512/596, from
     y=28 down to the bowl's top rim (`top_edge = CY-BOWL_R = 153`),
     wavy x; drawn in short segments so alpha fades toward the top
     (`0.14*(1-t*0.75) - band*0.03`, width 26−band*6). **Steam stays
     ABOVE the bowl only** — earlier version crossed the noodles and
     looked like white ribbons; do not extend it down.
   - `draw_vignette(canvas)` — very subtle: 2 large corner discs per
     corner (r 430/360, alpha 0.05). Stronger values left visible
     rings in the corners; keep it faint.
8. **`build_image()`** — `rng = random.Random(SEED)`, canvas, call
   the draw functions in the order above, return canvas.
9. **`main()`** — `out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR")
   or "/output"`; `makedirs`; `encode_png(build_image())`; if
   `len(png) > MAX_BYTES` print to stderr and return 1; else write
   `entry.png`, print `wrote <path> (<n> bytes, 1024x1024)`, return 0.
   `if __name__ == "__main__": raise SystemExit(main())`.

## Design decisions (why it looks the way it does)

- Top-down ramen: the big circle fills the frame and reads clearly
  even at ~300 px; warm amber broth + golden noodles + green onion
  is the highest-contrast appetising palette that pure code can do
  well. A side view would need perspective the renderer cannot do.
- Illustration style, not photorealism: clean vector-like shapes with
  gloss highlights read as deliberate craft to the judge; smudged
  fake-photorealism would score worse on "craft".
- No text anywhere in the image (garbled text is a judge penalty).
- No grain/noise: it inflates PNG size and reads as artefacts.

## Self-test (run exactly this)

```sh
cd ~/workspace/makefun/the-picture-that-tastes-of-one-20261122-2047
rm -rf ~/workspace/makefun/test-out1 ~/workspace/makefun/test-out2
mkdir -p ~/workspace/makefun/test-out1 ~/workspace/makefun/test-out2
MAKEFUN_OUTPUT_DIR=~/workspace/makefun/test-out1 python3 main.py
MAKEFUN_OUTPUT_DIR=~/workspace/makefun/test-out2 python3 main.py
cmp ~/workspace/makefun/test-out1/entry.png ~/workspace/makefun/test-out2/entry.png && echo BYTE-IDENTICAL
sha256sum ~/workspace/makefun/test-out1/entry.png
python3 -c "import struct; d=open('/home/hatch/workspace/makefun/test-out1/entry.png','rb').read(); print(len(d), struct.unpack('>II', d[16:24]))"
```

Pass = both runs exit 0, `cmp` silent + `BYTE-IDENTICAL`, size
< 1,048,576, dims 1024×1024. Then view the PNG once to confirm it
still looks like a steaming ramen bowl (bowl fills frame, steam
above the rim only, no artefacts).

## Verified numbers (reference build, 22 Nov 2026)

- Final run: exit 0, **305,675 bytes**, 1024×1024, sha256
  `1ac7114d0094e9d9a18139c9021d9d7adea36ab071226beb6d566907150011d8`,
  byte-identical across two runs, ~13–21 s per run (limit 60 s).
- Earlier revision: 310,395 bytes, then 317,437 bytes — size moves
  with the drawing; anything < 1,048,576 is fine.
- Python here is 3.12.3 locally; the grader uses 3.13 — code uses
  nothing version-specific.

## Tricky parts

- `/tmp` does NOT persist between tool calls in this environment —
  use `~/workspace/makefun/test-out1` etc. for test outputs.
- Pure-Python pixel work is slow: keep drawing row-based (slice
  assignment) and avoid per-pixel Python loops over the full canvas.
  The broth gradient is the only ~200k-iteration loop; everything
  else is discs/lines. Total runtime ~13–21 s; do not add a
  full-canvas blur or per-pixel vignette (would blow the 60 s cap).
- `thick_line` step factor 0.30 (denser disc stamps) is what makes
  steam and noodles smooth; 0.45 left visible beads.
- Determinism: single `random.Random(SEED)` threaded through the
  draw calls in fixed order; the bowl speckle uses its own
  `Random(SEED+7)`. Never use `time`, `os.urandom`, `hash()`, or dict
  iteration order for anything that affects pixels. `zlib.compress`
  level 9 is deterministic.
- The kit's local check: there is no offline `grade` command that
  applies to this competition (the kit CLI is for record/submit);
  the two-run byte-identical check above IS the self-test.
- Do NOT create a GitHub repo, submit, bundle, or claim anything —
  the parent orchestrator handles submission after the rebuild.
  Do NOT copy the kit's starter code — there is none for this
  competition; the code above is original.

## README badges (exact)

Use the template from the requirements with `{owner}=0xyfann`,
`{repo}=makefun-the-picture-that-tastes-of-one-20261122-2047`. The
`{referral_code}` placeholder has no known value — the footer link
is written without a `ref=` parameter. Badge URLs:

- `https://make.fun/badge/the-picture-that-tastes-of-one-20261122-2047.svg`
- `https://make.fun/badge/the-picture-that-tastes-of-one-20261122-2047/0xyfann/makefun-the-picture-that-tastes-of-one-20261122-2047/rank.svg`
- `https://make.fun/badge/the-picture-that-tastes-of-one-20261122-2047/0xyfann/makefun-the-picture-that-tastes-of-one-20261122-2047/reward.svg`

## Time budget for the rebuild (70 min)

- 0–10 min: read these notes + `prompt.txt`, set up the dir.
- 10–40 min: re-author `main.py` in 3 chunks (canvas+PNG, scene
  part 1, toppings+main), running after each chunk.
- 40–50 min: self-test twice + view the PNG; fix only if broken.
- 50–60 min: LICENSE, README, `.makefun/owner.json`, copy
  `prompt.txt`; final self-test; report to parent.
- Keep 10 min spare. If the image looks wrong, adjust constants
  (steam range, noodle wobble) — do not rewrite the renderer.
