"""Layered, periodic (scroll-able) painted backgrounds with atmospheric perspective."""
from __future__ import annotations

import math
import random

import skia

from .gfx import P, R, hx, lg, mix, rg, shade, surface

ALIAS = {"home": "office", "interior": "office", "studio": "studio", "water": "beach", "landscape": "sky"}
SKY = {"day": ("#3d8fd1", "#cfe9f7"), "sunrise": ("#34407a", "#ffb37a"), "sunset": ("#3b3470", "#ff8b4a"),
       "dusk": ("#1b2552", "#c46d78"), "night": ("#040816", "#17264d")}
GROUND_Y = {"city": .72, "office": .78, "hall": .76, "beach": .70, "snow": .72, "tunnel": .76, "forest": .76, "sky": .80,
            "castle": .76, "village": .74, "battlefield": .74, "mountain": .74, "studio": .80}


def _wrapx(L, x, w):
    return [x, x - L] if x + w > L else [x]


def _hills(c, L, H, base, amp, color, seed, n=3):
    rnd = random.Random(seed)
    ph = [rnd.uniform(0, 6.28) for _ in range(n)]
    p = skia.Path()
    p.moveTo(0, H)
    for x in range(0, int(L) + 8, 8):
        y = base - sum(amp / (i + 1) * math.sin(2 * math.pi * (i + 1) * x / L + ph[i]) for i in range(n))
        p.lineTo(x, y)
    p.lineTo(L, H)
    p.close()
    c.drawPath(p, P(color))


def _glowband(c, L, y0, y1, color, a=120):
    c.drawRect(R(0, y0, L, y1 - y0), P(shader=lg(0, y0, 0, y1, [(0, color, 0), (1, color, a)])))


def _buildings(c, L, base, hmin, hmax, wmin, wmax, color, rnd, lights, wincol, detail=True):
    x = rnd.uniform(-20, 0)
    while x < L:
        w, h = rnd.uniform(wmin, wmax), rnd.uniform(hmin, hmax)
        for dx in _wrapx(L, x, w):
            c.drawRect(R(dx, base - h, w, h + 400), P(color))
            if rnd.random() < .35:
                c.drawRect(R(dx + w * .2, base - h - h * .12, w * .6, h * .12), P(shade(color, .92)))
            if detail:
                gx, gy = max(10, w / 6), max(14, wmin / 4)
                yy = base - h + gy
                while yy < base - gy:
                    xx = dx + gx * .6
                    while xx < dx + w - gx:
                        on = lights and rnd.random() < .42
                        c.drawRect(R(xx, yy, gx * .55, gy * .55), P(wincol if on else shade(color, 1.12 if not lights else .8), 230 if on else 120))
                        xx += gx * 1.2
                    yy += gy * 1.15
        x += w + rnd.uniform(0, 14)


def _pines(c, L, base, n, hmin, hmax, color, rnd, snow=False):
    for _ in range(n):
        x, h = rnd.uniform(0, L), rnd.uniform(hmin, hmax)
        w = h * .36
        for dx in _wrapx(L, x - w, w * 2):
            dx += w
            c.drawRect(R(dx - 3, base - h * .12, 6, h * .14 + 400), P(shade(color, .7)))
            for k in range(4):
                yk = base - h * (.12 + k * .22)
                wk = w * (1 - k * .2)
                p = skia.Path()
                p.moveTo(dx - wk, yk)
                p.lineTo(dx, yk - h * .32)
                p.lineTo(dx + wk, yk)
                p.close()
                c.drawPath(p, P(color))
                if snow:
                    q = skia.Path()
                    q.moveTo(dx - wk * .55, yk - h * .13)
                    q.lineTo(dx, yk - h * .32)
                    q.lineTo(dx + wk * .55, yk - h * .13)
                    q.close()
                    c.drawPath(q, P((240, 246, 255), 235))


def _clouds(c, L, H, rnd, color, n=7, ymax=.4):
    for _ in range(n):
        x, y, s = rnd.uniform(0, L), rnd.uniform(H * .05, H * ymax), rnd.uniform(80, 190)
        for dx in _wrapx(L, x - s, s * 2.4):
            for k in range(5):
                c.drawOval(R(dx + k * s * .38 + s, y + rnd.uniform(-8, 8), s * rnd.uniform(.8, 1.3), s * .42),
                           P(color, 120, blur=14))


def _col_arch(c, x, y0, y1, w, color):
    c.drawRect(R(x - w / 2, y0, w, y1 - y0), P(lg(x - w / 2, 0, x + w / 2, 0, [(0, shade(color, 1.15)), (.5, color), (1, shade(color, .7))]) and color, 255, shader=lg(x - w / 2, 0, x + w / 2, 0, [(0, shade(color, 1.18)), (.55, color), (1, shade(color, .68))])))
    c.drawRect(R(x - w * .68, y0 - 16, w * 1.36, 16), P(shade(color, 1.1)))
    c.drawRect(R(x - w * .68, y1 - 12, w * 1.36, 12), P(shade(color, .9)))


def _sky(c, L, H, tod, rnd, weather):
    top, bot = (hx(h) for h in SKY.get(tod, SKY["day"]))
    c.drawRect(R(0, 0, L, H), P(shader=lg(0, 0, 0, H * .78, [(0, top), (1, bot)])))
    sx, sy = L * .62, H * (.2 if tod == "day" else .43 if tod in ("sunrise", "sunset") else .3)
    if tod == "night":
        for _ in range(170):
            c.drawCircle(rnd.uniform(0, L), rnd.uniform(0, H * .5), rnd.uniform(.6, 1.7), P((255, 255, 235), rnd.randint(90, 230)))
        c.drawCircle(sx, sy, 150, P(shader=rg(sx, sy, 150, [(0, (190, 210, 255), 90), (1, (190, 210, 255), 0)])))
        c.drawCircle(sx, sy, 34, P((236, 240, 255)))
        c.drawCircle(sx + 12, sy - 6, 31, P(mix(top, (20, 30, 60), .3)))
    else:
        warm = (255, 244, 200) if tod == "day" else (255, 190, 120)
        c.drawCircle(sx, sy, 300, P(shader=rg(sx, sy, 300, [(0, warm, 150), (1, warm, 0)])))
        c.drawCircle(sx, sy, 40, P((255, 250, 225)))
    _clouds(c, L, H, rnd, (255, 255, 255) if tod == "day" else mix((255, 255, 255), bot, .55) if tod != "night" else (60, 76, 120),
            n=4 if weather == "none" else 9)
    if weather in ("rain", "fog"):
        c.drawRect(R(0, 0, L, H), P((90, 98, 110), 90))


def build(kind, tod, weather, W, H, grade, seed=1):
    """Returns {'layers': [(Image, parallax)], 'fore': Image|None, 'ground': y_px}."""
    kind = ALIAS.get(kind, kind)
    if kind not in GROUND_Y:
        kind = "sky"
    ss, L = 1.25, int(W * 1.5)
    gy = int(H * GROUND_Y[kind])
    rnd = random.Random(seed + sum(map(ord, kind)))
    G = grade.c
    night = tod == "night"

    def layer(fn, par):
        s = surface(L * ss, H * ss)
        cv = s.getCanvas()
        cv.scale(ss, ss)
        fn(cv)
        return (s.makeImageSnapshot(), par)

    layers = []
    indoor = kind in ("office", "hall", "tunnel", "studio")
    if not indoor:
        layers.append(layer(lambda c: _sky(c, L, H, tod, rnd, weather), .08))
    haze = G(mix(hx(SKY.get(tod, SKY["day"])[1]), (255, 255, 255), .1))
    wall = {"office": "#7b5a3a", "hall": "#8a8478", "tunnel": "#3a3d40", "studio": "#10141c"}.get(kind, "#7b7b7b")

    if kind == "city":
        layers.append(layer(lambda c: (_buildings(c, L, gy, 120, 330, 60, 120, mix(G((90, 110, 140)), haze, .55), rnd, night, (255, 214, 130)), _glowband(c, L, gy - 200, gy, haze, 120)), .22))
        layers.append(layer(lambda c: (_buildings(c, L, gy, 160, 430, 90, 170, mix(G((70, 84, 112)), haze, .3), rnd, night, (255, 205, 110)), _glowband(c, L, gy - 120, gy, haze, 90)), .45))
    elif kind == "village":
        layers.append(layer(lambda c: (_hills(c, L, H, gy - 150, 55, mix(G((110, 150, 120)), haze, .5), seed), _pines(c, L, gy - 40, 22, 90, 160, mix(G((60, 100, 80)), haze, .4), rnd)), .22))
        def houses(c):
            x = 30
            while x < L:
                w, h = rnd.uniform(110, 170), rnd.uniform(70, 110)
                for dx in _wrapx(L, x, w):
                    c.drawRect(R(dx, gy - h, w, h + 300), P(G(rnd.choice([(196, 160, 120), (210, 188, 150), (170, 130, 100)]))))
                    p = skia.Path(); p.moveTo(dx - 10, gy - h); p.lineTo(dx + w / 2, gy - h - 60); p.lineTo(dx + w + 10, gy - h); p.close()
                    c.drawPath(p, P(G((130, 62, 48))))
                    c.drawRect(R(dx + w * .4, gy - h * .55, w * .2, h * .55), P(G((80, 56, 40))))
                    c.drawRect(R(dx + w * .12, gy - h * .75, w * .18, h * .25), P((255, 214, 130) if night else G((150, 190, 210))))
                x += w + rnd.uniform(40, 120)
        layers.append(layer(houses, .5))
    elif kind in ("forest", "snow"):
        snow = kind == "snow"
        base_c = (214, 226, 240) if snow else (70, 110, 86)
        layers.append(layer(lambda c: (_hills(c, L, H, gy - 140, 50, mix(G((210, 222, 240) if snow else (120, 160, 130)), haze, .55), seed), _pines(c, L, gy - 60, 26, 110, 190, mix(G((90, 120, 140) if snow else (60, 100, 80)), haze, .5), rnd, snow)), .2))
        layers.append(layer(lambda c: (_hills(c, L, H, gy - 60, 36, G((230, 238, 250) if snow else (70, 100, 70)), seed + 1), _pines(c, L, gy - 10, 16, 220, 360, mix(G((50, 80, 70) if snow else (30, 66, 48)), haze, .2), rnd, snow), _glowband(c, L, gy - 260, gy, haze, 110)), .5))
    elif kind in ("mountain", "castle"):
        def peaks(c, col_, hh, n, k):
            for i in range(n):
                x, h = i * L / n + rnd.uniform(-60, 60), rnd.uniform(hh * .6, hh)
                for dx in _wrapx(L, x - h * .8, h * 1.6):
                    dx += h * .8
                    p = skia.Path(); p.moveTo(dx - h * .85, gy); p.lineTo(dx, gy - h); p.lineTo(dx + h * .85, gy); p.close()
                    c.drawPath(p, P(col_))
                    q = skia.Path(); q.moveTo(dx, gy - h); q.lineTo(dx + h * .85, gy); q.lineTo(dx + h * .1, gy); q.close()
                    c.drawPath(q, P(shade(col_, .8)))
        layers.append(layer(lambda c: peaks(c, mix(G((120, 140, 170)), haze, .5), 330, 6, 1), .15))
        layers.append(layer(lambda c: peaks(c, mix(G((80, 100, 130)), haze, .3), 250, 5, 2), .3))
        if kind == "castle":
            def castle(c):
                x0, col_ = L * .5, G((88, 84, 94))
                c.drawRect(R(x0 - 180, gy - 200, 360, 300), P(col_))
                for tx in (-200, 200):
                    c.drawRect(R(x0 + tx - 40, gy - 320, 80, 420), P(shade(col_, 1.08)))
                    p = skia.Path(); p.moveTo(x0 + tx - 52, gy - 320); p.lineTo(x0 + tx, gy - 410); p.lineTo(x0 + tx + 52, gy - 320); p.close()
                    c.drawPath(p, P(G((120, 56, 52))))
                for i in range(9):
                    c.drawRect(R(x0 - 180 + i * 42, gy - 222, 24, 22), P(col_))
                c.drawRect(R(x0 - 34, gy - 120, 68, 120), P(shade(col_, .5)))
            layers.append(layer(castle, .45))
    elif kind == "beach":
        def sea(c):
            c.drawRect(R(0, gy - 150, L, 150), P(shader=lg(0, gy - 150, 0, gy, [(0, G((60, 140, 190))), (1, G((20, 100, 150)))])))
            for i in range(60):
                y = gy - 150 + (i / 60) ** 1.6 * 150
                x = rnd.uniform(0, L)
                for dx in _wrapx(L, x, 90):
                    c.drawLine(dx, y, dx + rnd.uniform(30, 90), y, P((255, 255, 255), 60 + i, stroke=1.5 + i / 30))
            c.drawRect(R(0, gy - 152, L, 3), P(haze, 190))
        layers.append(layer(sea, .25))
    elif kind == "battlefield":
        layers.append(layer(lambda c: (_hills(c, L, H, gy - 110, 40, mix(G((90, 86, 80)), haze, .5), seed), _buildings(c, L, gy - 10, 60, 190, 50, 100, mix(G((60, 56, 56)), haze, .4), rnd, False, (255, 150, 60), False), c.drawRect(R(0, 0, L, H), P(G((120, 70, 40)), 50))), .3))
    elif kind in ("hall", "tunnel"):
        def hall(c):
            c.drawRect(R(0, 0, L, H), P(shader=lg(0, 0, 0, H, [(0, G(hx(wall))), (1, G(shade(hx(wall), .6)))])))
            n = 9 if kind == "hall" else 5
            for i in range(n):
                x = (i + .5) * L / n
                if kind == "hall":
                    _col_arch(c, x, 60, gy, 66, G((176, 170, 158)))
                    c.drawRect(R(x + L / n * .12, 190, L / n * .26, gy - 290), P(shader=lg(0, 190, 0, gy - 100, [(0, G((255, 226, 150)), 70), (1, G((255, 226, 150)), 0)])))
                else:
                    w = L / n
                    c.drawRect(R(x - w * .45, 70, w * .9, gy - 70), P(G((54, 58, 62)), 255, stroke=0, shader=lg(0, 70, 0, gy, [(0, G((70, 74, 78))), (1, G((38, 40, 44)))])))
                    c.drawRect(R(x - 6, 80, 12, 26), P((255, 226, 160)))
        layers.append(layer(hall, .35))
    elif kind in ("office", "studio"):
        def room(c):
            c.drawRect(R(0, 0, L, H), P(shader=lg(0, 0, 0, H, [(0, G(hx(wall))), (1, G(shade(hx(wall), .55)))])))
            if kind == "studio":
                c.drawCircle(L / 2, gy - 120, 460, P(shader=rg(L / 2, gy - 120, 460, [(0, (255, 255, 255), 70), (1, (255, 255, 255), 0)])))
                return
            c.drawRect(R(0, gy - 150, L, 150), P(G((92, 62, 40)), 80))
            for i in range(3):
                x = (i + .5) * L / 3
                wx, wy, ww, wh = x - 110, 90, 220, 270
                c.drawRect(R(wx - 12, wy - 12, ww + 24, wh + 24), P(G((60, 42, 30))))
                c.drawRect(R(wx, wy, ww, wh), P(shader=lg(0, wy, 0, wy + wh, [(0, G(hx(SKY.get(tod, SKY["day"])[0]))), (1, G(hx(SKY.get(tod, SKY["day"])[1])))])))
                c.drawRect(R(wx + ww / 2 - 3, wy, 6, wh), P(G((60, 42, 30)))); c.drawRect(R(wx, wy + wh / 2 - 3, ww, 6), P(G((60, 42, 30))))
                p = skia.Path(); p.moveTo(wx, wy + wh); p.lineTo(wx + ww, wy + wh); p.lineTo(wx + ww + 160, gy); p.lineTo(wx - 160, gy); p.close()
                c.drawPath(p, P((255, 240, 200), 28 if not night else 10))
        layers.append(layer(room, .3))
    # ground plane (parallax 1, scrolls with the character)
    gcol = {"city": (74, 76, 84), "office": (78, 52, 34), "hall": (108, 96, 82), "beach": (222, 200, 150), "snow": (232, 240, 250),
            "tunnel": (62, 64, 66), "forest": (52, 84, 58), "sky": (86, 118, 80), "castle": (84, 116, 74), "village": (110, 132, 82),
            "battlefield": (84, 70, 54), "mountain": (92, 104, 84), "studio": (24, 28, 36)}[kind]

    def ground(c):
        c.drawRect(R(0, gy, L, H - gy + 4), P(shader=lg(0, gy, 0, H, [(0, G(shade(gcol, 1.1))), (1, G(shade(gcol, .62)))])))
        c.drawRect(R(0, gy - 2, L, 5), P(G(shade(gcol, 1.3)), 160))
        for i in range(0, int(L), 120):
            c.drawLine(i, gy + 4, i - 90 - (i % 5) * 10, H, P(shade(gcol, .8), 70, stroke=2))
        for k in range(1, 4):
            y = gy + (H - gy) * (k / 4) ** 1.5
            c.drawLine(0, y, L, y, P(shade(gcol, .75), 55, stroke=1.5))
    layers.append(layer(ground, 1.0))

    def fore(c):  # blurred foreground silhouettes: depth cue drawn in front of actors
        col_ = G(shade(gcol, .25))
        for _ in range(7):
            x = rnd.uniform(0, L)
            for dx in _wrapx(L, x, 160):
                if kind in ("forest", "snow", "village", "sky", "castle", "mountain"):
                    for k in range(6):
                        p = skia.Path(); p.moveTo(dx + k * 14, H + 10); p.quadTo(dx + k * 14 + rnd.uniform(-30, 30), H - rnd.uniform(70, 150), dx + k * 14 + rnd.uniform(-40, 40), H - rnd.uniform(110, 190)); p.quadTo(dx + k * 14 + 12, H - 60, dx + k * 14 + 22, H + 10)
                        c.drawPath(p, P(col_, 235, blur=5))
                elif kind in ("office", "studio", "hall", "tunnel"):
                    c.drawRect(R(dx, H - rnd.uniform(26, 60), 140, 80), P(col_, 220, blur=6))
                else:
                    c.drawRect(R(dx, H - rnd.uniform(18, 46), 70, 80), P(col_, 210, blur=6))
    layers.append(layer(fore, 1.35))
    return {"layers": layers, "ground": gy, "L": L, "ss": ss, "kind": kind}
