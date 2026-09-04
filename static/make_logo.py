"""Generate the Trader Tools app logo.

Concept: "The Breakout" — a rising candlestick sequence whose final candle pierces a dashed
resistance line. Chosen because it stays readable at 32px (four bodies, one line, one glow)
while meaning something specific to a trader rather than being generic chart decoration.

Everything is drawn at SS x scale and downsampled with LANCZOS: PIL has no antialiased
shape drawing, so supersampling is what keeps the wicks and rounded corners from crawling.

Run: python static/make_logo.py
"""
import os

from PIL import Image, ImageDraw, ImageFilter

SS = 4                       # supersample factor
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
SIZES = (1024, 512, 256, 128, 64, 32)

# Palette — deep "terminal at night" navy, gains green, one loss red, amber resistance.
BG_TOP = (11, 17, 32)
BG_BOT = (30, 42, 74)
GREEN = (34, 197, 94)
GREEN_HOT = (74, 222, 128)
RED = (239, 68, 68)
AMBER = (245, 158, 11)
GRID = (255, 255, 255, 16)

# (value_low, value_high, value_open, value_close, colour)
# Value space: 0 = bottom of the plot, 1 = top. A rising trend with one honest pullback,
# then the breakout — a straight ramp would look like clip art, not a market.
CANDLES = [
    (0.16, 0.34, 0.20, 0.31, GREEN),
    (0.25, 0.45, 0.42, 0.28, RED),
    (0.27, 0.53, 0.31, 0.50, GREEN),
    (0.41, 0.63, 0.45, 0.60, GREEN),
    (0.54, 0.94, 0.57, 0.88, GREEN_HOT),   # breaks through resistance
]
RESISTANCE = 0.74

# Pulled in on the right so the breakout candle's bloom has room to breathe instead of
# bleeding into the tile rim.
PLOT_L, PLOT_R = 0.170, 0.800     # plot area as a fraction of the tile
PLOT_T, PLOT_B = 0.140, 0.845


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def build(size):
    S = size * SS
    body_w = S * 0.088
    wick_w = max(2, round(S * 0.020))
    radius = round(S * 0.225)          # squircle-ish app-tile corner

    def px(v):   # value space -> pixel y
        return (PLOT_B - (PLOT_B - PLOT_T) * v) * S

    # ---- gradient ground -------------------------------------------------------------
    base = Image.new('RGB', (S, S), BG_TOP)
    d = ImageDraw.Draw(base)
    for y in range(S):
        d.line([(0, y), (S, y)], fill=lerp(BG_TOP, BG_BOT, y / max(1, S - 1)))

    img = base.convert('RGBA')

    # ---- faint grid, so the tile reads as a chart surface ------------------------------
    grid = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    for i in range(1, 6):
        y = PLOT_T * S + (PLOT_B - PLOT_T) * S * i / 6.0
        gd.line([(PLOT_L * S, y), (PLOT_R * S, y)], fill=GRID, width=max(1, round(S * 0.004)))
    img = Image.alpha_composite(img, grid)

    # ---- dashed resistance line --------------------------------------------------------
    res = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    rd = ImageDraw.Draw(res)
    y = px(RESISTANCE)
    dash, gap = S * 0.052, S * 0.030
    x = PLOT_L * S
    while x < PLOT_R * S:
        rd.line([(x, y), (min(x + dash, PLOT_R * S), y)],
                fill=AMBER + (170,), width=max(2, round(S * 0.011)))
        x += dash + gap
    img = Image.alpha_composite(img, res)

    # ---- candles, drawn on their own layer so the breakout can be glowed ---------------
    def draw_candles(layer, only_last=False):
        dd = ImageDraw.Draw(layer)
        n = len(CANDLES)
        span = (PLOT_R - PLOT_L) * S
        for i, (lo, hi, op, cl, colour) in enumerate(CANDLES):
            if only_last and i != n - 1:
                continue
            cx = PLOT_L * S + span * ((i + 0.5) / n)
            # wick
            dd.rounded_rectangle(
                [cx - wick_w / 2, px(hi), cx + wick_w / 2, px(lo)],
                radius=wick_w / 2, fill=colour + (255,))
            # body — always at least a thin slab so a doji never vanishes
            top, bot = px(max(op, cl)), px(min(op, cl))
            if bot - top < S * 0.03:
                mid = (top + bot) / 2
                top, bot = mid - S * 0.015, mid + S * 0.015
            dd.rounded_rectangle(
                [cx - body_w / 2, top, cx + body_w / 2, bot],
                radius=S * 0.016, fill=colour + (255,))

    glow = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    draw_candles(glow, only_last=True)
    glow = glow.filter(ImageFilter.GaussianBlur(S * 0.024))
    img = Image.alpha_composite(img, glow)
    img = Image.alpha_composite(img, glow)      # twice: a real bloom, not a smudge

    candles = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    draw_candles(candles)
    img = Image.alpha_composite(img, candles)

    # ---- top sheen, for a little tile depth --------------------------------------------
    sheen = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sheen)
    for i in range(round(S * 0.42)):
        a = round(16 * (1 - i / (S * 0.42)))
        sd.line([(0, i), (S, i)], fill=(255, 255, 255, a))
    img = Image.alpha_composite(img, sheen)

    # ---- squircle mask + hairline rim ---------------------------------------------------
    mask = Image.new('L', (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=radius, fill=255)
    out = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)

    rim = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(rim).rounded_rectangle(
        [0, 0, S - 1, S - 1], radius=radius, outline=(255, 255, 255, 28),
        width=max(2, round(S * 0.006)))
    out = Image.alpha_composite(out, Image.composite(
        rim, Image.new('RGBA', (S, S), (0, 0, 0, 0)), mask))

    return out.resize((size, size), Image.LANCZOS)


def _font(px):
    from PIL import ImageFont
    for path in (r'C:\Windows\Fonts\segoeuib.ttf', r'C:\Windows\Fonts\arialbd.ttf',
                 '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'):
        if os.path.exists(path):
            return ImageFont.truetype(path, px)
    return None


def wordmark(on_dark=False):
    """Tile + "Trader Tools" lockup on a transparent ground.

    Two variants, because a transparent PNG has no idea what it will be dropped onto: the
    light build uses near-black text that dies on a dark README, the dark build uses
    near-white text that dies on a light one. Shipping one of them guarantees it is
    illegible half the time.
    """
    TILE = 220
    PAD = 28
    tile = build(TILE)
    font = _font(108)
    probe = ImageDraw.Draw(Image.new('RGBA', (10, 10)))

    a, b = 'Trader ', 'Tools'
    if font:
        wa = probe.textlength(a, font=font)
        wb = probe.textlength(b, font=font)
        top = font.getbbox('Trader Tools')[1]
        text_h = font.getbbox('Trader Tools')[3] - top
    else:
        wa = wb = 220
        top, text_h = 0, 80

    gap = 44
    W = round(PAD + TILE + gap + wa + wb + PAD)
    H = TILE + PAD * 2
    mark = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    mark.paste(tile, (PAD, PAD), tile)

    if font:
        d = ImageDraw.Draw(mark)
        x = PAD + TILE + gap
        y = (H - text_h) // 2 - top
        primary = (237, 242, 255, 255) if on_dark else (15, 23, 42, 255)
        accent = (74, 222, 128, 255) if on_dark else (22, 163, 74, 255)
        d.text((x, y), a, font=font, fill=primary)
        d.text((x + wa, y), b, font=font, fill=accent)
    return mark


def main():
    master = build(1024)
    master.save(os.path.join(OUT_DIR, 'logo.png'))
    for s in SIZES:
        if s == 1024:
            continue
        build(s).save(os.path.join(OUT_DIR, 'logo-%d.png' % s))

    for on_dark in (False, True):
        wm = wordmark(on_dark)
        wm.save(os.path.join(OUT_DIR,
                             'logo-wordmark-dark.png' if on_dark else 'logo-wordmark.png'))

    print('wrote:')
    for f in sorted(os.listdir(OUT_DIR)):
        if f.startswith('logo') and f.endswith('.png'):
            p = os.path.join(OUT_DIR, f)
            print('  static/%-22s %6.1f KB' % (f, os.path.getsize(p) / 1024))


if __name__ == '__main__':
    main()
