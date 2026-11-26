"""Environment props: ground vehicles/flags and floating infographic cards (maps, documents, money...)."""
from __future__ import annotations

import math
import random

import skia

from .gfx import P, R, back, clamp, lg, mix, shade, text, tw

COLORS = {"grey": (112, 118, 124), "gray": (112, 118, 124), "green": (76, 100, 70), "brown": (118, 84, 56), "red": (178, 48, 44),
          "blue": (52, 96, 170), "black": (40, 42, 48), "white": (236, 236, 232), "gold": (214, 170, 60), "yellow": (230, 196, 70),
          "silver": (176, 182, 190), "pink": (230, 150, 170), "orange": (224, 130, 50)}
FLAGS = {"british": ("uk",), "french": ([(0, 0, 1 / 3, 1, (40, 70, 160)), (1 / 3, 0, 2 / 3, 1, (240, 240, 240)), (2 / 3, 0, 1, 1, (200, 40, 50))],),
         "german": ([(0, 0, 1, 1 / 3, (30, 30, 34)), (0, 1 / 3, 1, 2 / 3, (200, 40, 40)), (0, 2 / 3, 1, 1, (230, 190, 60))],),
         "soviet": ([(0, 0, 1, 1, (190, 36, 36)), (.12, .12, .3, .32, (240, 200, 60))],),
         "polish": ([(0, 0, 1, .5, (240, 240, 240)), (0, .5, 1, 1, (210, 40, 60))],),
         "italian": ([(0, 0, 1 / 3, 1, (40, 140, 70)), (1 / 3, 0, 2 / 3, 1, (240, 240, 240)), (2 / 3, 0, 1, 1, (200, 40, 50))],),
         "american": ([(0, 0, 1, 1, (240, 240, 240))] + [(0, k / 7, 1, (k + 1) / 7, (190, 40, 50)) for k in range(0, 7, 2)] + [(0, 0, .42, .54, (40, 60, 130))],),
         "japanese": ([(0, 0, 1, 1, (240, 240, 240)), (.36, .3, .64, .7, (200, 40, 50))],)}


def kind_of(name: str) -> str:
    n = name.lower()
    for k, keys in (("tank", ("tank",)), ("truck", ("truck", "lorry", "vehicle")), ("flag", ("flag",)), ("map", ("map",)),
                    ("doc", ("document", "treaty", "paper", "speech", "letter", "contract", "newspaper")),
                    ("calendar", ("calendar",)), ("money", ("money", "cash", "mark", "banknote", "gold")),
                    ("wallet", ("wallet",)), ("book", ("book",))):
        if any(w in n for w in keys):
            return k
    return "generic"


def _warp(c, pts, x0, y0, w, h, t, color, amp=10):
    path = skia.Path()
    for i, (u, v) in enumerate(pts):
        px, py = x0 + u * w, y0 + v * h + amp * math.sin(u * 7 - t * 4.2) * u
        path.moveTo(px, py) if i == 0 else path.lineTo(px, py)
    path.close()
    c.drawPath(path, P(color))


def _rect_pts(u0, v0, u1, v1, n=10):
    top = [(u0 + (u1 - u0) * i / n, v0) for i in range(n + 1)]
    bot = [(u1 - (u1 - u0) * i / n, v1) for i in range(n + 1)]
    return top + bot


def _flag(c, name, x, gy, size, t, G, color):
    key = next((k for k in list(FLAGS) if k in name.lower()), None)
    w, h = size * .5, size * .32
    top = gy - size * 1.05
    c.drawRect(R(x - 4, top, 8, size * 1.05), P(G((150, 150, 156))))
    c.drawCircle(x, top, 7, P(G((214, 186, 90))))
    fx0, fy0 = x + 4, top + 8
    if key == "british":
        blue, white, red = G((30, 52, 120)), G((240, 240, 240)), G((190, 30, 48))
        for pts, colr in ((_rect_pts(0, 0, 1, 1), blue), ([(0, 0), (.14, 0), (1, .86), (1, 1), (.86, 1), (0, .14)], white), ([(1, 0), (.86, 0), (0, .86), (0, 1), (.14, 1), (1, .14)], white),
                          (_rect_pts(.42, 0, .58, 1), white), (_rect_pts(0, .38, 1, .62), white), (_rect_pts(.46, 0, .54, 1), red), (_rect_pts(0, .44, 1, .56), red)):
            _warp(c, pts, fx0, fy0, w, h, t, colr)
    elif key:
        for u0, v0, u1, v1, colr in FLAGS[key][0]:
            _warp(c, _rect_pts(u0, v0, u1, v1), fx0, fy0, w, h, t, G(colr))
    else:
        _warp(c, _rect_pts(0, 0, 1, 1), fx0, fy0, w, h, t, G(color))


def _tank(c, x, gy, size, t, G, color, rubber=False):
    col = G(color)
    bob = math.sin(t * 22) * 1.2
    w = size
    c.save(); c.translate(x, gy - 6 + bob)
    c.drawOval(R(-w * .55, -4, w * 1.1, 16), P((0, 0, 0), 80, blur=7))
    c.drawRoundRect(R(-w * .5, -w * .2, w, w * .2), 18, 18, P(shade(col, .55)))
    for i in range(6):
        c.drawCircle(-w * .4 + i * w * .16, -w * .1, w * .068, P(shade(col, .4))); c.drawCircle(-w * .4 + i * w * .16, -w * .1, w * .03, P(shade(col, .8)))
    c.drawRoundRect(R(-w * .46, -w * .36, w * .92, w * .2), 10, 10, P(shader=lg(0, -w * .36, 0, -w * .16, [(0, shade(col, 1.2)), (1, shade(col, .8))])))
    c.drawRoundRect(R(-w * .2, -w * .54, w * .42, w * .2), 14, 14, P(shader=lg(0, -w * .54, 0, -w * .34, [(0, shade(col, 1.25)), (1, shade(col, .85))])))
    c.drawLine(w * .2, -w * .45, w * .62, -w * .47, P(shade(col, .6), stroke=w * .045))
    if rubber:
        c.drawOval(R(-w * .3, -w * .5, w * .3, w * .08), P((255, 255, 255), 110, blur=5))
    c.restore()


def _truck(c, x, gy, size, t, G, color):
    col, w = G(color), size
    bob = math.sin(t * 18) * 1.2
    c.save(); c.translate(x, gy - 4 + bob)
    c.drawOval(R(-w * .55, -4, w * 1.1, 14), P((0, 0, 0), 80, blur=7))
    c.drawRoundRect(R(-w * .5, -w * .42, w * .66, w * .3), 8, 8, P(shade(col, .95)))
    c.drawRoundRect(R(w * .16, -w * .36, w * .3, w * .24), 10, 10, P(shade(col, 1.15)))
    c.drawRect(R(w * .27, -w * .32, w * .15, w * .1), P(G((170, 200, 220))))
    for wx in (-.34, -.1, .3):
        c.drawCircle(w * wx, -w * .06, w * .075, P((24, 24, 28))); c.drawCircle(w * wx, -w * .06, w * .03, P((150, 150, 156)))
    c.restore()


def _card(c, x, y, w, h, t, i, label, G, body, appear):
    s = back(appear)
    if s <= 0:
        return
    bob = math.sin(t * 1.5 + i * 1.7) * 7
    c.save(); c.translate(x, y + bob); c.rotate(math.sin(t * .9 + i) * 1.6); c.scale(s, s)
    c.drawRoundRect(R(-w / 2 + 6, -h / 2 + 14, w, h), 14, 14, P((0, 0, 0), 90, blur=14))
    body(c, w, h)
    if label:
        text(c, label.upper(), 0, h / 2 + 34, 24, (255, 255, 255), align="c", sp=2, shadow=5)
    c.restore()


def _paper(c, w, h, G, seal=False, lines=8):
    c.drawRoundRect(R(-w / 2, -h / 2, w, h), 10, 10, P(shader=lg(0, -h / 2, 0, h / 2, [(0, (250, 248, 240)), (1, (226, 220, 204))])))
    rnd = random.Random(int(w))
    for k in range(lines):
        y = -h / 2 + 24 + k * (h - 70) / lines
        c.drawRoundRect(R(-w / 2 + 20, y, (w - 40) * rnd.uniform(.55, 1), 6), 3, 3, P((150, 148, 140), 200))
    if seal:
        c.drawCircle(w * .22, h * .3, 22, P((170, 32, 38))); c.drawCircle(w * .22, h * .3, 13, P((205, 60, 64)))
        c.drawRect(R(w * .22 - 8, h * .3 + 14, 7, 30), P((170, 32, 38))); c.drawRect(R(w * .22 + 3, h * .3 + 14, 7, 30), P((140, 24, 30)))


def _map(c, w, h, G, name, t):
    c.drawRoundRect(R(-w / 2, -h / 2, w, h), 14, 14, P(shader=lg(0, -h / 2, 0, h / 2, [(0, (236, 224, 192)), (1, (212, 196, 160))])))
    c.drawRoundRect(R(-w / 2 + 8, -h / 2 + 8, w - 16, h - 16), 10, 10, P((120, 90, 50), 160, stroke=2))
    rnd = random.Random(sum(map(ord, name)))
    for k in range(3):
        cx, cy, r = rnd.uniform(-w * .28, w * .28), rnd.uniform(-h * .22, h * .22), rnd.uniform(h * .16, h * .28)
        pts = [(cx + math.cos(a / 9 * 6.283) * r * rnd.uniform(.7, 1.2), cy + math.sin(a / 9 * 6.283) * r * rnd.uniform(.6, 1.1)) for a in range(9)]
        p = skia.Path(); p.moveTo(*[(pts[0][i] + pts[-1][i]) / 2 for i in (0, 1)])
        for i in range(9):
            a, b = pts[i], pts[(i + 1) % 9]
            p.quadTo(a[0], a[1], (a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        c.drawPath(p, P((150, 170, 110) if k else (120, 150, 100), 255)); c.drawPath(p, P((90, 110, 70), 255, stroke=2))
    pulse = 150 + 90 * math.sin(t * 3)
    hl = skia.Path(); hl.addCircle(w * .08, -h * .02, h * .17)
    c.drawPath(hl, P((220, 60, 50), pulse)); c.drawPath(hl, P((180, 30, 30), 255, stroke=3))
    for k in range(10):
        a = k / 10
        c.drawCircle(-w * .3 + a * w * .38, h * .28 - math.sin(a * 3) * h * .3, 3.2, P((90, 60, 40), 220 if (k / 10 < (t * .35) % 1) else 90))


def _money(c, w, h, G):
    c.drawRoundRect(R(-w / 2, -h / 2, w, h * .8), 8, 8, P(shader=lg(0, -h / 2, 0, h / 2, [(0, (140, 190, 130)), (1, (92, 148, 96))])))
    c.drawCircle(0, -h * .1, h * .22, P((210, 236, 200), 220)); c.drawRoundRect(R(-w / 2 + 8, -h / 2 + 8, w - 16, h * .8 - 16), 5, 5, P((60, 110, 70), 255, stroke=2))


def draw_prop(c, prop, i, x, gy, W, H, t, G, appear):
    name, color = str(prop.get("name", "")), COLORS.get(str(prop.get("color", "")).lower(), (120, 126, 132))
    k = kind_of(name)
    x = min(max(x, 260), W - 260) if k in ("tank", "truck") else x
    if k == "tank":
        _tank(c, x, gy - 14, 330, t, G, color, "rubber" in name.lower())
    elif k == "truck":
        _truck(c, x, gy - 14, 330, t, G, color)
    elif k == "flag":
        _flag(c, name, x, gy - 18, 280, t, G, color)
    else:
        y = H * (.27 if k == "map" else .25)
        body = {"map": lambda c_, w, h: _map(c_, w, h, G, name, t), "doc": lambda c_, w, h: _paper(c_, w, h, G, "treaty" in name.lower()),
                "money": lambda c_, w, h: _money(c_, w, h, G), "calendar": lambda c_, w, h: (_paper(c_, w, h, G, False, 4), c_.drawRoundRect(R(-w / 2, -h / 2, w, 44), 10, 10, P((200, 52, 52))),
                                                                                              text(c_, "DATE", 0, 20, 26, (255, 255, 255), align="c", sp=3)),
                "wallet": lambda c_, w, h: (c_.drawRoundRect(R(-w / 2, -h * .35, w, h * .7), 16, 16, P(G((110, 76, 50)))), c_.drawRoundRect(R(-w / 2, -h * .35, w, h * .26), 14, 14, P(G((136, 98, 66))))),
                "book": lambda c_, w, h: (c_.drawRoundRect(R(-w * .4, -h / 2, w * .8, h), 8, 8, P(G((120, 44, 44)))), c_.drawRect(R(-w * .4, -h / 2, 14, h), P(G((84, 28, 30)))), c_.drawRoundRect(R(-w * .22, -h * .3, w * .5, 10), 4, 4, P(G((226, 196, 120))))),
                }.get(k, None)
        if k == "generic":
            lw = tw(name.upper(), 26, sp=2) + 64
            cx = min(max(x, lw / 2 + 30), W - lw / 2 - 30)
            s_ = back(appear)
            if s_ > 0:
                bob = math.sin(t * 1.5 + i * 1.7) * 6
                c.save(); c.translate(cx, H * .17 + i * 6 + bob); c.scale(s_, s_)
                c.drawRoundRect(R(-lw / 2, -26, lw, 52), 26, 26, P((10, 12, 18), 205)); c.drawCircle(-lw / 2 + 26, 0, 7, P((255, 196, 64)))
                text(c, name.upper(), -lw / 2 + 44, 9, 26, (255, 255, 255), sp=2)
                c.restore()
            return
        x = min(max(x, 230), W - 230)
        w, h = (360, 230) if k == "map" else (170, 215) if k in ("doc", "calendar", "book") else (230, 140)
        _card(c, x, y, w, h, t, i, name if k in ("map", "wallet", "money", "calendar") else "", G, body, appear)
