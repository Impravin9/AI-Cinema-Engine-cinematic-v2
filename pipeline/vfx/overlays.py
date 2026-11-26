"""Documentary graphics: kinetic titles with count-ups, chapter tags, lower thirds, karaoke captions, weather/FX."""
from __future__ import annotations

import math
import random
import re

import skia

from .gfx import P, R, back, clamp, ease, eout, lg, rg, text, tw, wrap

ACCENT = {"epic": (255, 176, 58), "action": (255, 120, 64), "anger": (255, 96, 80), "suspense": (96, 205, 255),
          "mystery": (150, 190, 255), "fear": (120, 220, 200), "sad": (160, 176, 255), "calm": (255, 206, 90), "wonder": (255, 206, 90)}
_NUM = re.compile(r"^(\d[\d,.]*)(.*)$")


def accent(mood):
    return ACCENT.get(mood, (255, 196, 64))


def title_card(c, W, H, s, t, win, mood):
    """Big centred title; leading numbers count up. t = seconds since scene start, win = seconds visible."""
    if t > win:
        return
    a = ease(t / .35) * (1 - ease((t - win + .4) / .4))
    ac = accent(mood)
    m = _NUM.match(s.strip())
    head, rest = "", s.strip()
    if m:
        raw, rest = m.group(1), m.group(2)
        digits = re.sub(r"\D", "", raw)
        year = len(digits) == 4 and 1000 <= int(digits) <= 2100 and "," not in raw
        if digits and not year:
            n = int(float(raw.replace(",", "")) * eout(t / 1.3)) if "." not in raw else float(raw) * eout(t / 1.3)
            head = f"{n:,}" if "," in raw else (f"{n:.1f}" if "." in raw else str(n))
        else:
            head = raw
    size = 118 if len(s) < 14 else 92 if len(s) < 24 else 70
    while tw(head + rest, size) > W * .84 and size > 36:
        size -= 4
    c.drawRect(R(0, H * .26, W, H * .4), P(shader=lg(0, H * .26, 0, H * .66, [(0, (0, 0, 0), 0), (.5, (0, 0, 0), 150 * a), (1, (0, 0, 0), 0)])))
    sc = .86 + .14 * back(t / .5)
    c.save(); c.translate(W / 2, H * .47); c.scale(sc, sc)
    total = tw(head + rest, size, sp=2)
    x = -total / 2
    if head:
        x += text(c, head, x, 0, size, ac, 255 * a, sp=2, shadow=10)
    text(c, rest, x, 0, size, (255, 255, 255), 255 * a, sp=2, shadow=10)
    c.drawRoundRect(R(-total / 2 * eout(t / .7), size * .2, total * eout(t / .7), 7), 3, 3, P(ac, 255 * a))
    c.restore()


def tag_chip(c, W, H, s, t, win, mood):
    if t > win or not s:
        return
    a = ease(t / .3) * (1 - ease((t - win + .35) / .35))
    ac = accent(mood)
    dx = -(1 - eout(t / .45)) * 260
    year = re.fullmatch(r"[\d\s\u2013\-,A-Za-z]{4,16}", s) and any(ch.isdigit() for ch in s)
    c.save(); c.translate(dx + 56, 66)
    size = 54 if year else 28
    w = tw(s.upper(), size, sp=3 if not year else 1)
    if year:
        c.drawRect(R(0, -size * .85, 8, size * 1.05), P(ac, 255 * a))
        text(c, s.upper(), 24, 0, size, (255, 255, 255), 255 * a, sp=1, shadow=8)
    else:
        c.drawRoundRect(R(0, -34, w + 44, 52), 8, 8, P((10, 12, 18), 190 * a))
        c.drawRect(R(0, -34, 8, 52), P(ac, 255 * a))
        text(c, s.upper(), 26, 2, size, (255, 255, 255), 255 * a, sp=3)
    c.restore()


def lower_third(c, W, H, name, role, t, win, mood):
    if t > win:
        return
    a = ease(t / .3) * (1 - ease((t - win + .35) / .35))
    ac = accent(mood)
    x = 56 - (1 - eout(t / .5)) * 320
    w = max(tw(name.upper(), 36, sp=2), tw(role.upper(), 20, sp=2)) + 60
    c.drawRoundRect(R(x, H * .70, w, 86), 6, 6, P((10, 12, 18), 205 * a))
    c.drawRect(R(x, H * .70, 7, 86), P(ac, 255 * a))
    text(c, name.upper(), x + 26, H * .70 + 40, 36, (255, 255, 255), 255 * a, sp=2)
    text(c, role.upper(), x + 26, H * .70 + 70, 20, ac, 255 * a, sp=3, bold=False)


def chunks(s, n=7):
    words, out, cur = s.split(), [], []
    for w in words:
        cur.append(w)
        if len(cur) >= n or w[-1:] in ".!?;:" and len(cur) >= 3:
            out.append(cur); cur = []
    if cur:
        (out[-1].extend(cur) if out and len(cur) < 3 else out.append(cur))
    return out


def captions(c, W, H, s, t, T, mood):
    ch = chunks(s)
    if not ch:
        return
    total = sum(len(x) for x in ch)
    pos, cum = clamp(t / max(T, .1)) * total, 0
    for words in ch:
        if pos < cum + len(words) or words is ch[-1]:
            break
        cum += len(words)
    idx = int(clamp(pos - cum, 0, len(words) - 1e-6))
    size = 40
    lines, cur = [], []
    for w in words:
        if tw(" ".join(cur + [w]), size) > W * .78 and cur:
            lines.append(cur); cur = []
        cur.append(w)
    lines.append(cur)
    y = H * .905 - (len(lines) - 1) * 50
    n = 0
    ac = accent(mood)
    for ln in lines:
        lw = tw(" ".join(ln), size)
        x = (W - lw) / 2
        if ln is lines[0]:
            pad = 22
            c.drawRoundRect(R(W / 2 - max(tw(" ".join(l), size) for l in lines) / 2 - pad, y - size - 6, max(tw(" ".join(l), size) for l in lines) + pad * 2, len(lines) * 50 + 14), 16, 16, P((8, 10, 16), 150))
        for w in ln:
            text(c, w, x, y, size, ac if n == idx else (255, 255, 255), 255, shadow=4)
            x += tw(w + " ", size)
            n += 1
        y += 50


def particles(c, W, H, weather, t, seed=3):
    rnd = random.Random(seed)
    if weather == "rain":
        for _ in range(150):
            x, y, v = rnd.uniform(0, W + 200), rnd.uniform(0, H), rnd.uniform(900, 1300)
            yy = (y + t * v) % (H + 40)
            xx = (x - t * v * .22) % (W + 200) - 100
            c.drawLine(xx, yy, xx - 6, yy + 26, P((220, 232, 255), 90, stroke=1.6))
    elif weather == "snow":
        for _ in range(130):
            x, y, v, r = rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(40, 110), rnd.uniform(1.6, 5)
            c.drawCircle((x + math.sin(t * 1.3 + y) * 24 + t * 18) % W, (y + t * v) % H, r, P((255, 255, 255), 215))
    elif weather == "wind":
        for _ in range(40):
            x, y, v = rnd.uniform(0, W), rnd.uniform(0, H * .8), rnd.uniform(500, 900)
            xx = (x + t * v) % (W + 300) - 150
            c.drawLine(xx, y, xx + 120, y + 4, P((255, 255, 255), 55, stroke=1.6))
    elif weather == "fog":
        for k in range(5):
            x = (k * 380 + t * 24 * (1 + k % 2)) % (W + 700) - 350
            c.drawOval(R(x, H * (.5 + .07 * k), 700, 120), P((225, 232, 238), 60, blur=46))
    for _ in range(26):  # drifting dust motes (depth)
        x, y, r = rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(1, 2.6)
        c.drawCircle((x + t * 8 + math.sin(t + y) * 12) % W, (y - t * 6) % H, r, P((255, 255, 240), 60))


def smoke(c, W, H, gy, t):
    for k in range(9):
        x = W * (.15 + .09 * k) + math.sin(t * .4 + k) * 40
        for j in range(5):
            y = gy - 60 - ((t * 38 + j * 90 + k * 31) % 520)
            r = 40 + (gy - y) * .12
            c.drawCircle(x + math.sin(t + j) * 18, y, r, P((60, 60, 66), 38 * (1 - (gy - y) / 560), blur=22))


def confetti(c, W, H, t):
    rnd = random.Random(9)
    for _ in range(90):
        x, y, v = rnd.uniform(0, W), rnd.uniform(-H, 0), rnd.uniform(180, 380)
        colr = rnd.choice([(255, 90, 90), (255, 210, 70), (90, 200, 255), (130, 230, 140)])
        c.save(); c.translate(x + math.sin(t * 3 + y) * 30, (y + t * v) % (H + 80) - 40); c.rotate(t * 220 + x)
        c.drawRect(R(-5, -3, 10, 6), P(colr)); c.restore()


def speed_lines(c, W, H, t):
    rnd = random.Random(int(t * 24))
    for _ in range(34):
        y = rnd.uniform(0, H); x = rnd.uniform(0, W)
        c.drawLine(x, y, x + rnd.uniform(120, 360), y, P((255, 255, 255), 60, stroke=rnd.uniform(1, 3)))
