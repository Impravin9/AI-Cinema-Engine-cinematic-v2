#!/usr/bin/env python3
"""
LEGO DIRECTOR v3 - script text -> auto-planned mp4. Sits ON TOP of lego_engine_v2.py (engine logic untouched).
  python lego_director.py story.txt out.mp4 [--genre news|sports|doc|story] [--title T] [--fast] [--tts edge] [--voice narr.wav] [--pool]
Pool: 11 new backgrounds + 14 world cities/landmarks, 5 times of day, 6 weather FX, 12 animals, 35 objects,
cinematic letterbox, karaoke narration captions, location tags, auto cast / actions / faces / sfx / music / camera / transitions.
"""
import re, sys, math, random, os, subprocess, wave, argparse, hashlib
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import lego_engine_v2 as E
from lego_engine_v2 import clamp, lerp, rnd, shd, mixc, sky, clouds, birds, flag_wave, font, sm

OL = E.OL
# ---------------------------------------------------------------- primitive DSL (design units, y up = negative)
def prims(r, cx, cy, k, pr, flip=False):
    d = r.d; fx = -1 if flip else 1; lw = max(1, int(k))
    for p in pr:
        o = p[0]
        if o == 'e': _, x, y, rx, ry, c = p; d.ellipse([cx + (fx * x - rx) * k, cy + (y - ry) * k, cx + (fx * x + rx) * k, cy + (y + ry) * k], fill=c, outline=OL, width=lw)
        elif o == 'p': d.polygon([(cx + fx * x * k, cy + y * k) for x, y in p[1]], fill=p[2], outline=OL)
        elif o == 'r': _, x0, y0, x1, y1, c = p; a, b = cx + fx * x0 * k, cx + fx * x1 * k; d.rectangle([min(a, b), cy + y0 * k, max(a, b), cy + y1 * k], fill=c, outline=OL, width=lw)
        elif o == 'l': d.line([(cx + fx * x * k, cy + y * k) for x, y in p[1]], fill=p[2], width=max(1, int(p[3] * k)), joint='curve')
        elif o == 't': d.text((cx + fx * p[1] * k, cy + p[2] * k), p[4], font=font(p[3] * k), fill=p[5], anchor='mm')
        elif o == 'g': r.glow((cx + fx * p[1] * k) / E.K, (cy + p[2] * k) / E.K, p[3] * k / E.K, p[4], p[5], scr=True)
GR, DK, WH = (130, 130, 140), (40, 40, 50), (245, 245, 245)
def quad(t, walk, body, sx=1.0, lh=20, hx=38, hy=-12, hs=1.0, ear='pt', tail=1, extra=(), dark=None, bh=18):
    dark = dark or shd(body, .7); by = -(lh + bh * .7); sw = (9 if walk else 2) ; P = []
    for i, lx in enumerate((-24, -10, 10, 24)):
        a = math.sin(t * 9 + (0 if i % 3 == 0 else 3.1)) * sw; P.append(('l', [(lx * sx, by + 8), (lx * sx + a, 0)], dark, 7))
    P.append(('l', [(-30 * sx, by - 4), (-44 * sx + math.sin(t * 7) * 5, by - 14 * tail), (-48 * sx, by - 26 * tail)], dark, 5))
    P.append(('e', 0, by, 34 * sx, bh, body))
    P.append(('l', [(24 * sx, by - 6), (hx - 6, by + hy)], body, 14))
    P.append(('e', hx, by + hy, 14 * hs, 12 * hs, body))
    if ear == 'pt': P.append(('p', [(hx - 9, by + hy - 8), (hx - 6, by + hy - 22), (hx, by + hy - 10)], dark))
    elif ear == 'fl': P.append(('e', hx - 8, by + hy + 2, 5, 10, dark))
    elif ear == 'long': P += [('e', hx - 4, by + hy - 26, 4, 15, body), ('e', hx + 4, by + hy - 26, 4, 15, body)]
    P.append(('e', hx + 5, by + hy - 3, 2.2, 2.2, DK)); P.append(('e', hx + 12, by + hy + 3, 3.5, 3, DK))
    return P + list(extra)
def animal(kind):
    def f(t, c, walk):
        if kind == 'dog': return quad(t, walk, (190, 140, 80), .9, 16, 34, -10, .9, 'fl')
        if kind == 'cat': return quad(t, walk, (230, 150, 70), .7, 14, 28, -9, .8, 'pt', 2.2)
        if kind == 'horse': return quad(t, walk, (140, 90, 55), 1.3, 34, 50, -36, 1.1, 'pt', 1, [('l', [(40, -88), (30, -62)], (40, 25, 15), 6)], bh=20)
        if kind == 'cow': return quad(t, walk, (245, 245, 245), 1.2, 24, 44, -6, 1.1, 'fl', 1, [('e', -10, -42, 9, 7, DK), ('e', 12, -38, 7, 5, DK), ('p', [(40, -56), (36, -66), (44, -58)], (230, 220, 190))], bh=22)
        if kind == 'lion': return quad(t, walk, (225, 170, 70), 1.1, 24, 40, -10, 1.0, 'none', 1, [('e', 40, -44, 20, 20, (150, 80, 30)), ('e', 42, -42, 12, 11, (225, 170, 70)), ('e', 47, -42, 2, 2, DK)])
        if kind == 'tiger': return quad(t, walk, (240, 140, 40), 1.15, 22, 42, -8, 1.0, 'pt', 1, [('l', [(i, -48), (i + 4, -30)], DK, 3) for i in (-18, -6, 6, 18)])
        if kind == 'rabbit': return quad(t, walk, (235, 235, 240), .55, 10, 22, -8, .8, 'long', 1)
        if kind == 'elephant': return quad(t, walk, (150, 155, 170), 1.5, 38, 56, -8, 1.5, 'none', 1, [('e', 46, -62, 16, 20, (170, 175, 190)), ('l', [(66, -62), (76, -40), (70, -22)], (150, 155, 170), 9), ('p', [(64, -52), (80, -44), (66, -46)], WH)], bh=28)
        if kind == 'camel': return quad(t, walk, (210, 170, 100), 1.3, 34, 50, -34, 1.0, 'pt', 1, [('e', -10, -76, 11, 12, (200, 158, 90)), ('e', 12, -74, 11, 11, (200, 158, 90))], bh=20)
        if kind == 'bird': w = math.sin(t * 14) * 12; return [('p', [(-6, 0), (-22, -w - 8), (6, -4)], c), ('p', [(0, 0), (14, -w - 8), (12, -4)], shd(c, .8)), ('e', 0, -2, 12, 6, c), ('e', 11, -6, 5, 5, c), ('p', [(15, -6), (22, -5), (15, -3)], (250, 190, 40))]
        if kind == 'fish': w = math.sin(t * 8) * 6; return [('p', [(-20, 0), (-34, -10 + w), (-34, 10 + w)], shd(c, .8)), ('e', 0, 0, 22, 12, c), ('e', 12, -3, 2.5, 2.5, DK)]
        return []
    return f
ANIMALS = ['dog', 'cat', 'horse', 'cow', 'lion', 'tiger', 'rabbit', 'elephant', 'camel', 'bird', 'fish']
def obj(kind):
    def f(t, c, walk):
        fl = (255, 190 + int(40 * math.sin(t * 20)), 60)
        d = dict(
          car=[('r', -42, -30, 42, -12, c), ('p', [(-22, -30), (-10, -46), (18, -46), (30, -30)], shd(c, .85)), ('p', [(-16, -31), (-8, -43), (6, -43), (6, -31)], (170, 215, 240)), ('e', -24, -10, 10, 10, DK), ('e', 24, -10, 10, 10, DK)],
          bus=[('r', -64, -56, 64, -10, c), ('r', -56, -48, 56, -32, (170, 215, 240)), ('e', -38, -8, 10, 10, DK), ('e', 38, -8, 10, 10, DK)],
          plane=[('p', [(-10, -10), (-34, -36), (-22, -36), (8, -10)], GR), ('e', 0, -8, 50, 10, WH), ('p', [(-44, -10), (-52, -28), (-38, -12)], c), ('e', 30, -10, 6, 4, (110, 170, 230))],
          boat=[('p', [(-50, 4), (50, 4), (36, 22), (-36, 22)], (130, 80, 50)), ('l', [(0, 4), (0, -60)], (90, 60, 40), 3), ('p', [(2, -58), (40, -6), (2, -6)], WH)],
          house=[('r', -44, -52, 44, 0, (235, 215, 180)), ('p', [(-54, -52), (0, -92), (54, -52)], (190, 70, 60)), ('r', -9, -28, 9, 0, (110, 70, 45)), ('r', 18, -40, 34, -24, (170, 215, 240))],
          tv=[('r', -34, -48, 34, -10, DK), ('r', -30, -44, 30, -14, mixc((60, 90, 180), (230, 230, 120), .5 + .5 * math.sin(t * 5))), ('r', -12, -10, 12, 0, GR)],
          laptop=[('p', [(-26, -34), (26, -34), (22, -8), (-22, -8)], DK), ('p', [(-22, -31), (22, -31), (19, -11), (-19, -11)], (110, 170, 240)), ('r', -32, -8, 32, -3, GR)],
          phone=[('r', -8, -30, 8, 0, DK), ('r', -6, -27, 6, -4, (120, 200, 255)), ('g', 0, -16, 30, (140, 210, 255), .35)],
          book=[('r', -18, -8, 18, 0, c), ('r', -16, -8, 16, -3, WH)], camera=[('r', -20, -26, 20, -6, DK), ('e', 0, -16, 9, 9, GR), ('e', 0, -16, 5, 5, (80, 140, 220))],
          sword=[('l', [(0, 0), (0, -60)], (210, 215, 225), 6), ('l', [(-12, -14), (12, -14)], (200, 160, 50), 5)], gift=[('r', -16, -28, 16, 0, c), ('r', -3, -28, 3, 0, (250, 230, 80)), ('r', -16, -17, 16, -12, (250, 230, 80))],
          cake=[('r', -26, -18, 26, 0, (240, 190, 200)), ('r', -18, -34, 18, -18, (250, 235, 215)), ('r', -2, -46, 2, -34, (80, 160, 230)), ('e', 0, -50, 3, 5, fl)],
          guitar=[('e', 0, -18, 16, 18, (180, 110, 50)), ('l', [(0, -30), (0, -80)], (90, 60, 40), 5), ('e', 0, -18, 5, 5, DK)],
          umbrella=[('p', [(math.cos(a) * 34, -50 - math.sin(a) * 28) for a in np.linspace(0, math.pi, 9)], c), ('l', [(0, -50), (0, 0), (6, 4)], DK, 3)],
          chair=[('r', -14, -22, 14, -16, (150, 100, 60)), ('r', -14, -50, -10, -16, (150, 100, 60)), ('l', [(-12, -16), (-12, 0)], (110, 70, 40), 4), ('l', [(12, -16), (12, 0)], (110, 70, 40), 4)],
          table=[('r', -36, -30, 36, -24, (160, 110, 70)), ('l', [(-30, -24), (-30, 0)], (110, 70, 40), 5), ('l', [(30, -24), (30, 0)], (110, 70, 40), 5)],
          lamp=[('l', [(0, 0), (0, -64)], GR, 4), ('p', [(-16, -64), (16, -64), (10, -84), (-10, -84)], (250, 230, 150)), ('g', 0, -76, 90, (255, 230, 150), .45)],
          rocket=[('e', 0, -40, 14, 40, WH), ('p', [(-14, -60), (0, -92), (14, -60)], c), ('p', [(-14, -14), (-26, 4), (-14, -4)], c), ('p', [(14, -14), (26, 4), (14, -4)], c), ('p', [(-7, 0), (0, 22 + 8 * math.sin(t * 30)), (7, 0)], fl)],
          clock=[('e', 0, -24, 22, 22, WH), ('l', [(0, -24), (0, -42)], DK, 3), ('l', [(0, -24), (14 * math.cos(t * 1.2), -24 + 14 * math.sin(t * 1.2))], DK, 3)],
          money=[('e', -10, -6, 12, 5, (240, 200, 50)), ('e', 10, -6, 12, 5, (240, 200, 50)), ('e', 0, -13, 12, 5, (250, 215, 70)), ('r', -22, -34, 22, -20, (110, 200, 130))],
          shield=[('p', [(-20, -48), (20, -48), (20, -22), (0, 0), (-20, -22)], c), ('l', [(0, -46), (0, -6)], WH, 4)], bench=[('r', -40, -26, 40, -18, (150, 100, 60)), ('r', -40, -44, 40, -34, (150, 100, 60)), ('l', [(-34, -18), (-34, 0)], DK, 5), ('l', [(34, -18), (34, 0)], DK, 5)],
          tree=[('r', -8, -60, 8, 0, (110, 75, 45)), ('e', 0, -80, 36, 32, (60, 150, 70)), ('e', -22, -66, 24, 20, (50, 135, 62)), ('e', 22, -66, 24, 20, (50, 135, 62))],
          flower=[('l', [(0, 0), (0, -26)], (60, 150, 60), 3), ('e', 0, -30, 8, 8, c), ('e', 0, -30, 3, 3, (250, 220, 60)), ('l', [(14, 0), (14, -20)], (60, 150, 60), 3), ('e', 14, -24, 7, 7, shd(c, 1.1))],
          tent=[('p', [(-44, 0), (0, -60), (44, 0)], c), ('p', [(-10, 0), (0, -26), (10, 0)], DK)],
          campfire=[('l', [(-18, 0), (18, -6)], (100, 65, 40), 6), ('l', [(-18, -6), (18, 0)], (100, 65, 40), 6), ('p', [(-12, -6), (0, -44 - 8 * math.sin(t * 13)), (12, -6)], (255, 130, 30)), ('p', [(-6, -6), (0, -26 - 5 * math.sin(t * 17)), (6, -6)], (255, 220, 80)), ('g', 0, -22, 110, (255, 160, 70), .5)],
          lantern=[('l', [(0, -84), (0, -64)], DK, 2), ('e', 0, -52, 13, 17, (240, 80, 50)), ('g', 0, -52, 70, (255, 190, 90), .5)],
          diya=[('p', [(-14, -8), (14, -8), (8, 0), (-8, 0)], (190, 110, 60)), ('p', [(-3, -8), (0, -22 - 3 * math.sin(t * 15)), (3, -8)], fl), ('g', 0, -14, 70, (255, 190, 90), .5)],
          kite=[('p', [(0, -90 + 4 * math.sin(t * 3)), (16, -70), (0, -46), (-16, -70)], c), ('l', [(0, -46), (-6, -28), (4, -14), (0, 0)], DK, 2)],
          crown=[('p', [(-16, 0), (-16, -22), (-8, -12), (0, -26), (8, -12), (16, -22), (16, 0)], (245, 195, 40))],
          bicycle=[('e', -22, -14, 14, 14, WH), ('e', 22, -14, 14, 14, WH), ('l', [(-22, -14), (-4, -34), (22, -14)], c, 4), ('l', [(-4, -34), (12, -34)], DK, 4)],
          drum=[('r', -18, -26, 18, 0, c), ('e', 0, -26, 18, 6, (240, 230, 210))], bell=[('p', [(-14, 0), (-8, -26), (8, -26), (14, 0)], (240, 190, 50)), ('e', 0, 0, 4, 4, DK)],
          mountain=[('p', [(-80, 0), (0, -100), (80, 0)], (110, 120, 140)), ('p', [(-22, -78), (0, -100), (22, -78), (8, -70), (-8, -76)], WH)],
          statue=[('r', -16, -14, 16, 0, GR), ('r', -9, -60, 9, -14, (170, 190, 175)), ('e', 0, -68, 9, 9, (170, 190, 175)), ('l', [(9, -56), (20, -84)], (170, 190, 175), 6), ('p', [(16, -84), (24, -84), (20, -98)], (255, 200, 60))])
        return d.get(kind, [])
    return f
OBJECTS = ['car', 'bus', 'plane', 'boat', 'house', 'tv', 'laptop', 'phone', 'book', 'camera', 'sword', 'gift', 'cake', 'guitar', 'umbrella', 'chair', 'table', 'lamp', 'rocket', 'clock', 'money', 'shield', 'bench', 'tree', 'flower', 'tent', 'campfire', 'lantern', 'diya', 'kite', 'crown', 'bicycle', 'drum', 'bell', 'mountain', 'statue']
POOL_PROPS = {k: animal(k) for k in ANIMALS}; POOL_PROPS.update({k: obj(k) for k in OBJECTS})
_dp = E.draw_prop
def draw_prop2(r, kind, X, Y, z, size, t, spin=0.0, col=(230, 50, 50), txt=''):
    if kind not in POOL_PROPS: return _dp(r, kind, X, Y, z, size, t, spin, col, txt)
    s = (0.55 + clamp((Y - 380) / 340) * .75) * size; k = r.Z() * s * (1.1 if kind in ANIMALS else .95); cx, cy = r.X(X), r.Y(Y) - z * k
    if z < 20: r.sshade(X, Y + 2, 34 * s, 7 * s, 70)
    prims(r, cx, cy, k, POOL_PROPS[kind](t, col, 'walk' in txt), flip=txt.startswith('L'))
E.draw_prop = draw_prop2

# ---------------------------------------------------------------- new backgrounds
def ground(r, y, c1, c2=None, n=0):
    r.rect(-900, y, 2300, 900, c1, 1)
    for k in range(n): r.rect(-900, y + k ** 1.6 * 6, 2300, y + k ** 1.6 * 6 + 3, c2, 1)
def bg_beach(r, t, o):
    sky(r, (90, 170, 240), (210, 238, 250), 400); clouds(r, t, .1, 40, 5); birds(r, t, .2, 4, 100); r.ell(900, 120, 44, 44, (255, 240, 150), .05)
    r.rect(-900, 330, 2300, 450, (40, 130, 200), .6)
    for i in range(16): y = 345 + i * 7; r.line([(x, y + math.sin(t * 2 + x / 40 + i) * 3) for x in range(-300, 1700, 60)], (150, 210, 240), 2, .6)
    for i in range(3): bx = (i * 520 + t * 12) % 1900 - 300; r.poly([(bx, 350), (bx + 50, 350), (bx + 38, 362), (bx + 8, 362)], (120, 80, 50), .6); r.poly([(bx + 24, 350), (bx + 24, 318), (bx + 46, 350)], WH if False else (245, 245, 245), .6)
    ground(r, 450, (240, 220, 160), (226, 204, 146), 8); r.line([(x, 452 + math.sin(t * 1.5 + x / 80) * 4) for x in range(-300, 1700, 40)], (255, 255, 255), 5, 1)
    for i in range(-2, 6):
        x = i * 360 + 100; r.line([(x, 470), (x + 12, 380), (x + 4, 300)], (120, 80, 50), 12, .85)
        for a in range(7): ang = -2.4 + a * .62 + math.sin(t * 1.5 + i) * .08; r.line([(x + 4, 300), (x + 4 + 64 * math.cos(ang), 300 + 44 * math.sin(ang) + 22)], (50, 150, 70), 7, .85)
def bg_desert(r, t, o):
    sky(r, (120, 170, 235), (250, 215, 160), 400); r.glow(900, 150, 260, (255, 220, 140), .6, .05); r.ell(900, 150, 54, 54, (255, 240, 170), .05)
    for i in range(4): x = i * 700 - 100; r.poly([(x, 430), (x + 160, 300), (x + 320, 430)], (214, 176, 120), .25) if i % 2 == 0 else None
    for p, base, c in ((.3, 420, (226, 184, 120)), (.55, 450, (236, 196, 130))):
        r.poly([(x, base - 36 * math.sin(x / 150 + p * 7) - 12 * math.sin(x / 47)) for x in range(-600, 2300, 40)] + [(2300, 800), (-600, 800)], c, p)
    ground(r, 470, (240, 205, 140), (226, 188, 124), 8)
    for i in range(-2, 6): x = i * 330 + 80; r.rect(x - 5, 410, x + 5, 480, (60, 130, 70), .9); r.rect(x - 18, 430, x - 10, 450, (60, 130, 70), .9); r.rect(x + 10, 420, x + 18, 440, (60, 130, 70), .9)
    for i in range(20): y = 380 + i * 9; r.line([(x, y + math.sin(t * 3 + x / 30 + i) * 1.5) for x in range(0, 1280, 80)], (255, 235, 190), 1, .3)
def bg_snow(r, t, o):
    sky(r, (150, 190, 230), (235, 245, 255), 480); clouds(r, t, .1, 50, 4, (250, 250, 255))
    for p, base, h, c in ((.2, 420, 260, (150, 165, 195)), (.4, 450, 200, (120, 138, 170))):
        for i in range(-2, 8):
            x = i * 420 * (1 if p < .3 else .8) + 50; r.poly([(x - 220, base), (x, base - h), (x + 220, base)], c, p); r.poly([(x - 60, base - h + 80), (x, base - h), (x + 60, base - h + 80), (x + 20, base - h + 62), (x - 10, base - h + 76)], (250, 252, 255), p)
    ground(r, 460, (240, 246, 255), (222, 232, 248), 8)
    for i in range(-3, 10): x = i * 210 + 40 + rnd(i, 2) * 60; y = 470 + rnd(i, 3) * 60; r.poly([(x - 28, y), (x, y - 90), (x + 28, y)], (40, 110, 80), .9); r.poly([(x - 20, y - 36), (x, y - 90), (x + 20, y - 36)], WH, .9) if False else r.poly([(x - 14, y - 60), (x, y - 90), (x + 14, y - 60)], (250, 252, 255), .9)
def bg_forest(r, t, o):
    sky(r, (30, 80, 60), (110, 170, 110), 540)
    for p, base, n, c in ((.25, 440, 12, (30, 90, 60)), (.5, 470, 9, (36, 110, 66)), (.8, 520, 6, (44, 130, 70))):
        for i in range(-3, n):
            x = i * 2400 / n + rnd(i, int(p * 10)) * 60; r.rect(x - 12, base - 220, x + 12, base, (80, 56, 36), p); sw = math.sin(t * 1.4 + i) * 4
            for dx, dy, rr in ((0, -230, 62), (-40, -190, 48), (40, -190, 48)): r.ell(x + dx + sw, base + dy, rr, rr * .8, c, p)
    for i in range(6): x = 200 + i * 220; r.poly([(x, 0), (x + 40, 0), (x + 200, 500), (x + 120, 500)], (150, 190, 120), .3); r.glow(x + 20, 0, 160, (255, 250, 190), .25, .3)
    ground(r, 520, (60, 130, 60), (50, 112, 52), 7)
    for i in range(14): x = (i * 97 + math.sin(t * .8 + i) * 30) % 1280; y = 400 + (i * 53) % 200 + math.sin(t * 1.3 + i) * 12; r.glow(x, y, 14, (255, 250, 120), .5 + .4 * math.sin(t * 5 + i), 1)
def bg_space(r, t, o):
    sky(r, (2, 4, 16), (18, 14, 44), 520)
    for i in range(140): r.ell(rnd(i, 1) * 2400 - 300, rnd(i, 2) * 480, 1.4, 1.4, mixc((120, 120, 140), (255, 255, 255), .5 + .5 * math.sin(t * 3 + i)), .06)
    r.glow(300, 160, 380, (110, 60, 190), .3, .1); r.glow(980, 220, 300, (40, 110, 200), .3, .1)
    r.ell(980, 150, 90, 90, (80, 140, 230), .15); r.ell(960, 140, 40, 28, (90, 190, 120), .15); r.ell(1030, 180, 36, 22, (90, 190, 120), .15)
    r.ell(330, 200, 52, 52, (210, 120, 70), .12); r.d.arc([r.X(240, .12), r.Y(180, .12), r.X(420, .12), r.Y(224, .12)], 180, 360, fill=(240, 200, 150), width=int(3 * r.Z(.12)))
    ground(r, 470, (120, 120, 132), (104, 104, 116), 8)
    for i in range(10): x = i * 190 + 40; r.ell(x, 520 + (i * 37) % 120, 40 + (i % 3) * 14, 9, (98, 98, 110), 1)
def bg_home(r, t, o):
    r.rect(-900, 0, 2300, 470, (236, 214, 184), .5); [r.rect(i * 80 - 900, 0, i * 80 - 897, 470, (224, 200, 168), .5) for i in range(40)]
    r.rect(80, 60, 360, 330, (255, 255, 255), .6); sky(r, (0, 0, 0), (0, 0, 0), 1) if False else r.rect(92, 72, 348, 318, (150, 205, 245), .6); r.line([(220, 72), (220, 318)], WH, 6, .6); r.line([(92, 195), (348, 195)], WH, 6, .6)
    r.poly([(60, 40), (130, 40), (110, 340), (60, 340)], (200, 80, 90), .6); r.poly([(310, 40), (380, 40), (380, 340), (330, 340)], (200, 80, 90), .6)
    for x, y in ((520, 90), (660, 70), (790, 100)): r.rect(x, y, x + 100, y + 80, (110, 80, 55), .6); r.rect(x + 8, y + 8, x + 92, y + 72, [(120, 170, 210), (210, 170, 120), (160, 200, 150)][int(x) % 3], .6)
    r.ell(1100, 140, 46, 46, WH, .6); r.line([(1100, 140), (1100 + 24 * math.cos(t * .5), 140 + 24 * math.sin(t * .5))], DK if False else (40, 40, 50), 4, .6)
    ground(r, 470, (150, 110, 76), (130, 94, 64), 9); r.poly([(300, 600), (980, 600), (1060, 700), (220, 700)], (190, 70, 80), 1)
    r.rect(700, 360, 1060, 470, (80, 110, 160), .9); r.rect(700, 330, 1060, 372, (96, 128, 180), .9); r.glow(1150, 200, 200, (255, 225, 160), .35, .9)
def bg_office(r, t, o):
    r.rect(-900, 0, 2300, 470, (214, 222, 232), .5); r.rect(200, 40, 1080, 330, (150, 200, 240), .5)
    for i in range(10): h = 60 + rnd(i, 3) * 160; r.rect(210 + i * 86, 330 - h, 290 + i * 86, 330, (110, 140, 180), .45)
    for x in (340, 640, 940): r.line([(x, 40), (x, 330)], (230, 235, 240), 6, .5)
    ground(r, 470, (96, 110, 130), (84, 96, 116), 8)
    for x in (260, 640, 1020): r.rect(x - 90, 420, x + 90, 440, (170, 130, 90), .9); r.rect(x - 80, 440, x - 70, 500, (120, 90, 64), .9); r.rect(x - 28, 370, x + 28, 420, DK if False else (40, 40, 50), .9); r.rect(x - 24, 374, x + 24, 414, mixc((70, 120, 200), (120, 200, 255), .5 + .5 * math.sin(t * 2 + x)), .9)
    r.rect(1100, 280, 1260, 400, WH, .8); r.line([(1110, 300), (1240, 300)], (220, 60, 60), 3, .8); r.ell(80, 420, 30, 40, (50, 140, 70), .9)
def bg_castle(r, t, o):
    sky(r, (80, 120, 200), (230, 200, 190), 480); clouds(r, t, .1, 60, 4); birds(r, t, .2, 3, 130)
    for x, h in ((300, 260), (640, 340), (980, 280)): r.rect(x - 60, 470 - h, x + 60, 470, (150, 148, 160), .5); [r.rect(x - 60 + j * 26, 470 - h - 18, x - 44 + j * 26, 470 - h, (150, 148, 160), .5) for j in range(5)]; r.poly([(x - 70, 470 - h - 18), (x, 470 - h - 100), (x + 70, 470 - h - 18)], (170, 50, 60), .5); r.rect(x - 10, 470 - h + 60, x + 10, 470 - h + 110, (50, 50, 70), .5)
    r.rect(250, 380, 1030, 470, (140, 138, 150), .55); r.poly([(560, 470), (720, 470), (720, 380), (640, 330), (560, 380)], (60, 50, 60), .55); flag_wave(r, 640, 160, 60, 36, [(200, 40, 50), (245, 200, 60)], t, .5)
    ground(r, 470, (126, 122, 130), (110, 106, 116), 8)
    for x in (140, 1140): r.rect(x - 4, 340, x + 4, 470, (70, 50, 40), .9); r.ell(x, 332, 9, 14, (255, 170 + int(40 * math.sin(t * 12)), 50), .9); r.glow(x, 332, 120, (255, 170, 70), .5, .9)
def bg_underwater(r, t, o):
    sky(r, (20, 120, 190), (6, 40, 100), 560)
    for i in range(7): x = 100 + i * 190 + math.sin(t * .6 + i) * 20; r.poly([(x, 0), (x + 50, 0), (x + 230, 560), (x + 120, 560)], (120, 200, 240), .3); r.glow(x + 20, 0, 150, (150, 220, 255), .2, .3)
    for i in range(3): [r.ell((j * 211 + i * 83 + t * (30 + i * 12)) % 1500 - 100, 160 + i * 90 + math.sin(t + j) * 16, 14, 7, [(250, 150, 60), (250, 220, 60), (230, 90, 130)][i], .35 + i * .1) for j in range(5)]
    ground(r, 520, (226, 206, 150), (206, 186, 134), 6)
    for i in range(-2, 10): x = i * 160 + 30; r.line([(x, 560), (x + math.sin(t * 1.5 + i) * 14, 490), (x + math.sin(t * 1.5 + i) * 24, 430)], (40, 160, 90), 8, .9); r.ell(x + 60, 540, 22, 16, [(230, 90, 120), (250, 150, 60), (160, 90, 200)][i % 3], .9)
    for i in range(24): x = (i * 71) % 1280; y = (700 - (t * (40 + i % 5 * 15) + i * 90) % 760); r.d.ellipse([r.X(x) - 3 * K_(), r.Y(y) - 3 * K_(), r.X(x) + 3 * K_(), r.Y(y) + 3 * K_()], outline=(220, 245, 255))
def K_(): return E.K
def bg_market(r, t, o):
    sky(r, (120, 190, 240), (250, 230, 190), 400)
    for i in range(-1, 6):
        x = i * 280 + 20; c = [(230, 70, 60), (60, 160, 220), (250, 190, 50), (60, 170, 100), (200, 90, 180)][i % 5]
        r.rect(x, 200, x + 250, 400, (220, 196, 160), .5); r.poly([(x - 10, 200), (x + 260, 200), (x + 240, 250), (x + 10, 250)], c, .5)
        for j in range(8): r.rect(x + 10 + j * 30, 250, x + 24 + j * 30, 262, shd(c, .8 + .1 * (j % 2)), .5)
        for j in range(5): r.ell(x + 40 + j * 42, 392, 16, 10, [(230, 60, 50), (250, 190, 50), (80, 170, 70)][(i + j) % 3], .5)
    for i in range(-2, 24): x = i * 70; r.line([(x, 120 + math.sin(i) * 6), (x + 70, 126 + math.sin(i + 1) * 6)], (60, 50, 40), 2, .8); r.poly([(x + 28, 122), (x + 44, 122), (x + 36, 146 + math.sin(t * 3 + i) * 3)], [(240, 80, 60), (250, 200, 60), (70, 170, 220)][i % 3], .8)
    ground(r, 470, (190, 150, 110), (170, 132, 96), 8)
    for x in (300, 700, 1000): r.glow(x, 150, 110, (255, 200, 100), .35, .8)
def lm(r, c, t, night):
    p = .3; col = (46, 52, 84) if night else (90, 104, 134); x = 880
    if c == 'paris': r.poly([(x - 70, 430), (x - 12, 200), (x + 12, 200), (x + 70, 430), (x + 40, 430), (x, 300), (x - 40, 430)], col, p); r.rect(x - 3, 130, x + 3, 200, col, p); r.rect(x - 56, 330, x + 56, 342, col, p)
    elif c == 'dubai': [r.poly([(x - 30 + j * 6, 430 - j * 62), (x + 30 - j * 6, 430 - j * 62), (x + 24 - j * 6, 368 - j * 62), (x - 24 + j * 6, 368 - j * 62)], col, p) for j in range(6)]; r.rect(x - 2, 20, x + 2, 70, col, p)
    elif c == 'agra': r.ell(x, 300, 56, 62, (240, 238, 232), p); r.rect(x - 90, 330, x + 90, 430, (240, 238, 232), p); [r.rect(x + s * 120 - 9, 240, x + s * 120 + 9, 430, (240, 238, 232), p) for s in (-1, 1)]; r.line([(x, 240), (x, 210)], (220, 190, 80), 3, p)
    elif c == 'london': r.rect(x - 30, 220, x + 30, 430, (200, 180, 130) if not night else col, p); r.poly([(x - 34, 220), (x, 130), (x + 34, 220)], col, p); r.ell(x, 258, 22, 22, WH, p); r.line([(x, 258), (x + 12 * math.cos(t * .5), 258 + 12 * math.sin(t * .5))], DK if False else (40, 40, 50), 3, p)
    elif c == 'tokyo': r.poly([(x - 56, 430), (x - 6, 160), (x + 6, 160), (x + 56, 430)], (230, 70, 60), p); r.rect(x - 3, 90, x + 3, 160, (230, 70, 60), p); r.rect(x - 40, 330, x + 40, 344, (245, 245, 245), p)
    elif c == 'mumbai': r.rect(x - 90, 330, x + 90, 430, (214, 176, 120), p); r.rect(x - 30, 350, x + 30, 430, (70, 50, 40), p); r.ell(x, 350, 30, 30, (70, 50, 40), p); [r.ell(x + s * 70, 316, 18, 22, (200, 160, 100), p) for s in (-1, 0, 1)]
    elif c == 'cairo': [r.poly([(x + dx - 110 * s, 430), (x + dx, 430 - 150 * s), (x + dx + 110 * s, 430)], (214, 180, 120), p) for dx, s in ((-80, 1), (80, .7))]
    elif c == 'newyork': r.rect(x - 20, 330, x + 20, 430, (150, 190, 160), p); r.poly([(x - 20, 330), (x, 290), (x + 20, 330)], (150, 190, 160), p); r.line([(x + 14, 330), (x + 36, 270)], (150, 190, 160), 6, p); r.ell(x + 36, 262, 7, 9, (255, 190, 60), p)
    elif c == 'sydney': [r.poly([(x - 90 + j * 56, 430), (x - 40 + j * 56, 330 - j * 10), (x + j * 56 - 20, 430)], (245, 245, 240), p) for j in range(3)]
    elif c == 'rome': r.ell(x, 330, 60, 38, (200, 190, 170), p); r.rect(x - 90, 350, x + 90, 430, (200, 190, 170), p); [r.rect(x - 80 + j * 28, 360, x - 68 + j * 28, 430, (60, 55, 50), p) for j in range(6)]
    elif c == 'beijing': r.rect(x - 80, 350, x + 80, 430, (190, 50, 50), p); r.poly([(x - 110, 350), (x, 290), (x + 110, 350)], (230, 190, 70), p)
    elif c == 'rio': r.poly([(x - 60, 430), (x - 20, 200), (x + 20, 200), (x + 60, 430)], (110, 130, 120), p); r.rect(x - 56, 214, x + 56, 226, (240, 240, 240), p); r.rect(x - 4, 190, x + 4, 260, (240, 240, 240), p)
    elif c == 'moscow': [r.poly([(x + j * 44 - 20, 430), (x + j * 44 - 20, 330), (x + j * 44, 270 - j % 2 * 30), (x + j * 44 + 20, 330), (x + j * 44 + 20, 430)], [(200, 50, 60), (60, 140, 200), (240, 190, 60)][j % 3], p) for j in range(-2, 3)]
CITIES = ['paris', 'dubai', 'agra', 'london', 'tokyo', 'mumbai', 'cairo', 'newyork', 'sydney', 'rome', 'beijing', 'rio', 'moscow']
def bg_metro(r, t, o):
    E.bg_city(r, t, o); lm(r, o.get('city', 'paris'), t, o.get('time') == 'night')
BGP = dict(beach=bg_beach, desert=bg_desert, snow=bg_snow, forest=bg_forest, space=bg_space, home=bg_home, office=bg_office, castle=bg_castle, underwater=bg_underwater, market=bg_market, metro=bg_metro)
E.BGS.update(BGP)
AUDIO_ALIAS = dict(beach='village', desert='village', snow='village', forest='village', space='studio', home='locker', office='locker', castle='hall', underwater='tunnel', market='city', metro='city')

# ---------------------------------------------------------------- time of day / weather / overlays (post-process)
TINT = dict(sunrise=((1.06, .94, .84), (26, 8, 0), (255, 150, 110)), sunset=((1.1, .84, .66), (30, 4, -6), (255, 110, 60)), night=((.42, .52, .9), (0, 2, 12), None), overcast=((.8, .84, .9), (0, 0, 0), None), dusk=((.8, .66, .9), (14, 0, 22), (200, 100, 160)))
def post(im, sc, i):
    t = i / E.FPS; tod = sc.get('tod'); wx = sc.get('wx')
    if tod in TINT or wx in ('storm', 'fog', 'dust'):
        m, a, g = TINT.get(tod, ((1, 1, 1), (0, 0, 0), None)); arr = np.asarray(im, np.float32) * np.array(m, np.float32) + np.array(a, np.float32)
        if wx == 'storm': arr *= .72
        if g:
            gl = np.exp(-((np.arange(H_) / H_ - .5) / .26) ** 2)[:, None, None] * np.array(g, np.float32) * .30; arr = arr + gl
        im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    ov = Image.new('RGBA', im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    if wx in ('rain', 'storm'):
        n = 340 if wx == 'storm' else 200
        for j in range(n):
            x = (rnd(j, 1) * (W_ + 200) - t * 160) % (W_ + 200) - 100; y = (rnd(j, 2) * H_ + t * (1100 + rnd(j, 3) * 500)) % H_; d.line([(x, y), (x - 9, y + 26)], fill=(205, 220, 240, 150), width=1)
        for j in range(26):
            x = rnd(j, 5) * W_; y = 420 + rnd(j, 6) * 280; ph = (t * 3 + rnd(j, 7)) % 1; d.ellipse([x - 12 * ph, y - 4 * ph, x + 12 * ph, y + 4 * ph], outline=(220, 235, 250, int(180 * (1 - ph))))
        if wx == 'storm' and (t * 1.0) % 5.3 < .18:
            fl = 1 - ((t) % 5.3) / .18; d.rectangle([0, 0, W_, H_], fill=(255, 255, 255, int(150 * fl)))
            rr = random.Random(int(t * 7)); x = 400 + rr.random() * 500; pts = [(x, 0)]
            for s in range(7): x += rr.uniform(-40, 40); pts.append((x, (s + 1) * 60))
            d.line(pts, fill=(255, 255, 240, int(255 * fl)), width=4)
    elif wx == 'snow':
        for j in range(170): x = (rnd(j, 1) * W_ + math.sin(t * 1.3 + j) * 24 + t * 24) % W_; y = (rnd(j, 2) * H_ + t * (50 + rnd(j, 3) * 90)) % H_; q = 1.5 + rnd(j, 4) * 3.2; d.ellipse([x - q, y - q, x + q, y + q], fill=(255, 255, 255, 215))
    elif wx == 'fog':
        d.rectangle([0, 0, W_, H_], fill=(205, 212, 222, 70))
        for j in range(7): x = (rnd(j, 1) * W_ * 1.4 + t * 18 * (1 + j % 3)) % (W_ * 1.4) - 150; d.ellipse([x - 260, 330 + rnd(j, 2) * 240, x + 260, 400 + rnd(j, 2) * 240 + 70], fill=(225, 230, 238, 60))
    elif wx == 'wind':
        for j in range(46): x = (rnd(j, 1) * W_ + t * (420 + rnd(j, 2) * 300)) % (W_ + 100) - 50; y = rnd(j, 3) * H_ * .8 + 80 + math.sin(t * 5 + j) * 18; d.ellipse([x - 5, y - 2.5, x + 5, y + 2.5], fill=[(110, 160, 60, 230), (200, 140, 60, 230), (230, 110, 120, 230)][j % 3]); d.line([(x - 60, y), (x - 8, y)], fill=(255, 255, 255, 60), width=1)
    elif wx == 'dust':
        for j in range(70): x = (rnd(j, 1) * W_ + t * 600) % (W_ + 200) - 100; y = rnd(j, 2) * H_; d.line([(x, y), (x - 60, y + 3)], fill=(235, 205, 150, 120), width=2)
    if sc.get('letter'): bh = int(H_ * .085); d.rectangle([0, 0, W_, bh], fill=(0, 0, 0, 255)); d.rectangle([0, H_ - bh, W_, H_], fill=(0, 0, 0, 255))
    if sc.get('tag') and t < 2.4:
        al = int(225 * min(1, t / .25) * (1 - sm((t - 2.0) / .4))); f_ = font(22); tw = d.textlength(sc['tag'], font=f_); x1 = W_ - 30; y0 = int(H_ * .085) + 56 if sc.get('letter') else 36
        d.rounded_rectangle([x1 - tw - 52, y0, x1, y0 + 40], 10, fill=(12, 14, 24, al)); d.text((x1 - tw - 14, y0 + 20), sc['tag'], font=f_, fill=(255, 255, 255, al), anchor='lm'); d.ellipse([x1 - tw - 40, y0 + 12, x1 - tw - 24, y0 + 28], fill=(230, 60, 60, al))
    if sc.get('kar'):
        for (t0, t1, ws, em) in sc['kar']:
            if t0 <= t <= t1:
                f_ = font(34); fb = font(37); sp = d.textlength(' ', font=f_); lines = [[]]; wl = 0
                for w in ws:
                    wd = d.textlength(w[0], font=f_)
                    if wl + wd > 880 and lines[-1]: lines.append([]); wl = 0
                    lines[-1].append((w, wd)); wl += wd + sp
                bw = max(sum(x[1] for x in l) + sp * (len(l) - 1) for l in lines) + 120; bh2 = len(lines) * 46 + 26; cx = W_ / 2; y1 = H_ - (int(H_ * .085) + 20 if sc.get('letter') else 24); y0 = y1 - bh2
                u = sm((t - t0) / .15); d.rounded_rectangle([cx - bw / 2, y0 + (1 - u) * 16, cx + bw / 2, y1 + (1 - u) * 16], 16, fill=(8, 10, 18, int(190 * u)))
                class Sh: pass
                s_ = Sh(); s_.d = d; E.icon(s_, em, cx - bw / 2 + 40, (y0 + y1) / 2, 20)
                for li, l in enumerate(lines):
                    x = cx - (sum(x[1] for x in l) + sp * (len(l) - 1)) / 2 + 36
                    for (w, wd) in l:
                        on = w[1] <= t <= w[2]; done = t > w[2]; d.text((x, y0 + 13 + li * 46 + 23), w[0], font=f_, fill=(255, 224, 60, 255) if on else ((255, 255, 255, 255) if done else (200, 205, 215, 255)), anchor='lm'); x += wd + sp
                break
    return Image.alpha_composite(im.convert('RGBA'), ov).convert('RGB')
W_, H_ = E.W, E.H
_rf = E.render_frame
def render2(sc, i, h, pop): return post(mood(_rf(sc, i, h, pop), sc, i), sc, i)
E.render_frame = render2
_au = E.audio
def audio2(scenes, total, path):
    for sc in scenes:
        if sc['bg'] in AUDIO_ALIAS: sc['_bg'] = sc['bg']; sc['bg'] = AUDIO_ALIAS[sc['bg']]
    try: _au(scenes, total, path)
    finally:
        for sc in scenes:
            if '_bg' in sc: sc['bg'] = sc.pop('_bg')
    nar = [(sc['t0'] + .1, sc['voice']) for sc in scenes if sc.get('voice')]
    if nar:
        w = wave.open(path); n = w.getnframes(); a = np.frombuffer(w.readframes(n), np.int16).reshape(-1, 2).astype(np.float32) / 32768; w.close(); g = np.ones(n, np.float32); v = np.zeros((n, 2), np.float32)
        for t0, p in nar:
            with wave.open(p) as q: x = np.frombuffer(q.readframes(q.getnframes()), np.int16).astype(np.float32) / 32768
            o = int(t0 * E.SR); x = x[:max(0, n - o)]; v[o:o + len(x), 0] += x; v[o:o + len(x), 1] += x; g[max(0, o - 2000):o + len(x) + 2000] = .55
        g = np.convolve(g, np.ones(2205) / 2205, 'same'); m = a * g[:, None] + v * .95; m *= .92 / max(abs(m).max(), 1e-6)
        with wave.open(path, 'wb') as o_: o_.setnchannels(2); o_.setsampwidth(2); o_.setframerate(E.SR); o_.writeframes((m * 32767).astype(np.int16).tobytes())
E.audio = audio2

# ---------------------------------------------------------------- lexicons
def lex(d):
    o = {}
    for k, ws in d.items():
        for w in ws.split(): o[w] = k
    return o
BGL = lex(dict(stadium='stadium match goal football penalty referee pitch striker goalkeeper league', tunnel='tunnel', hall='parliament senate congress assembly minister election',
  studio='studio anchor headline', village='village temple farmer farm', beach='beach sea ocean shore island wave sail lighthouse harbor', desert='desert sand pyramid oasis camel',
  snow='snow mountain winter glacier himalaya ice', forest='forest jungle woods safari', space='space rocket moon planet galaxy astronaut', home='home kitchen bedroom family',
  office='office company meeting boss startup', castle='castle king queen prince palace knight throne', underwater='underwater coral submarine', market='market bazaar shop festival',
  locker='locker dressing', city='city street traffic town'))
CITYL = lex(dict(paris='paris france', dubai='dubai uae', agra='agra', london='london britain england', tokyo='tokyo japan', mumbai='mumbai delhi kolkata chennai bangalore india', cairo='cairo egypt',
  newyork='york america usa', sydney='sydney australia', rome='rome italy', beijing='beijing china', rio='rio brazil', moscow='moscow russia'))
TODL = lex(dict(sunrise='sunrise dawn morning', sunset='sunset evening', dusk='dusk twilight', night='night midnight moonlit', clear='noon afternoon sunny'))
WXL = lex(dict(rain='rain rainy raining drizzle monsoon', storm='storm thunder lightning cyclone', snow='snowfall blizzard snowing', fog='fog mist foggy', wind='wind windy breeze', dust='sandstorm dust', clear='clear sunny calm'))
EML = lex(dict(shock='suddenly shocked surprise stunned gasp unexpected', panic='fear scared afraid danger escape chased panic', angry='angry furious rage shout protest fight argue', joy='win won victory champion celebrate cheer happy glad success triumph scored goal',
  laugh='laugh funny joke', sad='sad cry lost defeat died death tears mourn sorrow fail', awe='amazing beautiful magnificent discover wonder', love='love wedding romance', think='think plan idea mystery', proud='proud hero brave determined courage', tired='tired exhausted sleep weary'))
EM = dict(shock=('shock', 'worried', 'shock', 'gasp_s', 'shock', 'tense'), panic=('panic', 'shock', 'run', 'gasp_s', 'alert', 'tense'), angry=('angry', 'determined', 'angry', 'growl', 'angry', 'tense'),
  joy=('joy', 'laugh', 'celebrate', 'cheer_s', 'party', 'epic'), laugh=('laugh', 'happy', 'dance', 'laugh_s', 'laugh', 'up'), sad=('sad', 'cry', 'sad', 'sigh', 'sad', 'sad'), awe=('awe', 'happy', 'point', '', 'star', None),
  love=('happy', 'proud', 'namaste', '', 'heart', None), think=('worried', 'determined', 'think', '', 'think', None), proud=('proud', 'smug', 'wave', '', 'star', 'up'), tired=('tired', 'sad', 'sad', 'sigh', 'sad', 'sad'), neutral=('neutral', 'happy', 'talk', '', 'star', None))
PRI = ['shock', 'panic', 'angry', 'joy', 'sad', 'awe', 'laugh', 'love', 'think', 'proud', 'tired']
ACTL = lex(dict(run='run rush chase race', kick='kick shoot shot', jump='jump leap', fall='fall fell slip trip', dance='dance', wave='wave greet hello', namaste='pray bow namaste thank', point='point show',
  talk='say said speak spoke announce tell told ask asked', walk='walk arrive travel enter march', shrug='shrug', celebrate='celebrate'))
SFXL = lex(dict(whistle='whistle referee', applause='applause clap', cheer_s='crowd fans cheer', thud='thunder door gate knock', ding='bell', drumroll='drum', horn='horn', sting='crash explosion explode blast', chirp='birds bird'))
PROPL = {}
for w, k in dict(dog='dog', puppy='dog', cat='cat', horse='horse', cow='cow', lion='lion', tiger='tiger', rabbit='rabbit', elephant='elephant', camel='camel', bird='bird', eagle='bird', fish='fish', shark='fish',
  car='car', bus='bus', plane='plane', aircraft='plane', boat='boat', ship='boat', house='house', tv='tv', television='tv', laptop='laptop', computer='laptop', phone='phone', book='book', camera='camera',
  sword='sword', gift='gift', cake='cake', guitar='guitar', umbrella='umbrella', chair='chair', table='table', lamp='lamp', rocket='rocket', clock='clock', money='money', cash='money', coin='money', shield='shield',
  bench='bench', tree='tree', flower='flower', tent='tent', campfire='campfire', fire='campfire', lantern='lantern', diya='diya', kite='kite', crown='crown', bicycle='bicycle', bike='bicycle', drum='drum',
  bell='bell', mountain='mountain', statue='statue', trophy='trophy', cup='trophy', flag='flag', balloon='balloon', newspaper='paper', letter='paper', microphone='mic').items(): PROPL[w] = k
FLY = {'plane': 70, 'bird': 190, 'kite': 150, 'rocket': 60, 'balloon': 120}; MOVE = {'car', 'bus', 'boat', 'plane', 'bird', 'kite', 'bicycle'} | set(ANIMALS)
ROLES = dict(king=dict(outfit='robe', hair='crown', shirt=(150, 30, 70), acc=['beard']), queen=dict(outfit='dress', hair='crown', shirt=(120, 40, 160)), prince=dict(outfit='robe', hair='short', shirt=(40, 80, 170)),
  princess=dict(outfit='dress', hair='long', shirt=(230, 110, 170)), coach=dict(outfit='suit', hair='short', acc=['glasses'], hc=(140, 140, 140)), farmer=dict(outfit='casual', hair='cap', shirt=(60, 140, 70)),
  reporter=dict(outfit='suit', hair='short', shirt=(60, 70, 120)), anchor=dict(outfit='suit', hair='short', shirt=(30, 40, 90)), doctor=dict(outfit='casual', hair='short', shirt=(245, 245, 250), acc=['glasses']),
  soldier=dict(outfit='casual', hair='cap', shirt=(80, 110, 70), hat=(80, 110, 70)), teacher=dict(outfit='suit', hair='bun', acc=['glasses'], shirt=(110, 60, 90)), child=dict(outfit='casual', hair='short', shirt=(250, 190, 40), size=.8),
  boy=dict(outfit='casual', hair='short', shirt=(60, 150, 230), size=.85), girl=dict(outfit='dress', hair='long', shirt=(240, 110, 150), size=.85), mother=dict(outfit='dress', hair='bun', shirt=(200, 80, 90)),
  father=dict(outfit='casual', hair='short', shirt=(70, 100, 150), acc=['beard']), villager=dict(outfit='robe', hair='turban', shirt=(220, 150, 50), hat=(220, 150, 50)), president=dict(outfit='suit', hair='short', shirt=(30, 40, 90)),
  minister=dict(outfit='suit', hair='short', shirt=(40, 50, 70)), referee=dict(outfit='kit', hair='short', shirt=(30, 30, 35), shorts=(30, 30, 35), socks=(30, 30, 35)), captain=dict(outfit='kit', hair='spiky', shirt=(205, 30, 40)),
  thief=dict(outfit='casual', hair='cap', shirt=(40, 40, 50), hat=(40, 40, 50)), police=dict(outfit='suit', hair='cap', shirt=(40, 70, 150), hat=(40, 70, 150)), merchant=dict(outfit='robe', hair='turban', shirt=(60, 150, 140), hat=(200, 60, 60)),
  monk=dict(outfit='robe', hair='bald', shirt=(240, 130, 30)), scientist=dict(outfit='casual', hair='spiky', shirt=(245, 245, 250), acc=['glasses']), astronaut=dict(outfit='casual', hair='bald', shirt=(240, 240, 245)),
  player=dict(outfit='kit', hair='spiky', shirt=(205, 30, 40)), fan=dict(outfit='casual', hair='curly', shirt=(220, 60, 60)), man=dict(outfit='casual', hair='short', shirt=(70, 120, 190)), woman=dict(outfit='dress', hair='long', shirt=(190, 80, 140)),
  narrator=dict(outfit='suit', hair='short', shirt=(40, 50, 80), acc=['glasses']))
STOP = set('The A An In On At Of And But Then When While After Before As It He She They We I You His Her Their Its This That There Here What Who Why How If So Suddenly Finally Meanwhile Today Yesterday Tomorrow Once Every Some Many One Two Three Soon Later Now Still Even Just Only Also With Without From Into For To By Not No Yes Each All Both Another Another Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March April May June July August September October November December Breaking'.split())
PAL = [(205, 30, 40), (40, 90, 220), (40, 170, 90), (240, 130, 30), (150, 60, 170), (30, 160, 170), (230, 190, 40), (220, 80, 140), (90, 90, 100), (110, 70, 40)]
HAIR = ['short', 'spiky', 'curly', 'long', 'bun', 'short', 'spiky']; HCOL = [(25, 20, 20), (70, 45, 30), (110, 70, 40), (200, 160, 70), (140, 140, 140), (40, 30, 25)]; SK = ['light', 'tan', 'brown', 'dark', 'tan']
def hsh(s): return int(hashlib.md5(s.encode()).hexdigest(), 16)
def stems(w):
    w = w.lower(); o = [w]
    for suf in ('s', 'es', 'ed', 'd', 'ing', 'ly'):
        if w.endswith(suf) and len(w) - len(suf) > 2: o.append(w[:-len(suf)]); o.append(w[:-len(suf)] + 'e')
    return o
def look(lx, toks):
    for t in toks:
        for s in stems(t):
            if s in lx: return lx[s]
def looks(lx, toks):
    o = []
    for t in toks:
        for s in stems(t):
            if s in lx: o.append(lx[s]); break
    return o

# ---------------------------------------------------------------- analyzer / planner
def split_sentences(text):
    out = []
    text = re.sub(r'(?<![.!?:"”])[ \t]*\r?\n(?!\s*\r?\n)', ' ', text.strip())
    for s in re.split(r'(?<=[.!?])\s+|\n\s*\n', text):
        s = s.strip()
        if not s: continue
        while len(s.split()) > 24:
            m = [x.end() for x in re.finditer(r',\s|;\s|\sand\s|\sbut\s', s) if 8 <= len(s[:x.end()].split()) <= 20]
            if not m: break
            out.append(s[:m[0]].strip(' ,;')); s = s[m[0]:].strip()
        out.append(s)
    return out
def genre_of(text):
    t = set(w.lower() for w in re.findall(r"[A-Za-z]+", text)); sc = dict(sports=len(t & set('football stadium striker penalty league referee goalkeeper scored tournament'.split())) + .5 * len(t & set('goal match score'.split())), news=len(t & set('reported according minister announced breaking officials police government election'.split())) * 1.3,
        doc=len(t & set('species history scientists years ancient discovered nature wildlife centuries'.split())))
    g = max(sc, key=sc.get); return g if sc[g] >= 2 else 'story'
def make_char(name, role=None):
    h = hsh(name); kw = dict(shirt=PAL[h % 10], shorts=(245, 245, 245), skin=SK[(h >> 3) % 5], hair=HAIR[(h >> 5) % 7], hc=HCOL[(h >> 7) % 6], num=(h % 98) + 1, outfit='casual')
    if role in ROLES: kw.update(ROLES[role]);
    if role in ROLES and ROLES[role].get('outfit') != 'kit': kw['num'] = None
    return E.char(name, **kw)

# ================================================================ SEMANTIC SEGMENTER (punctuation-independent)
SEMANTIC = True
CUES = set('meanwhile suddenly later then soon finally next once afterwards eventually however but yet while until'.split())
CUE2 = [('that', 'night'), ('the', 'next'), ('at', 'last'), ('one', 'day'), ('after', 'that'), ('a', 'moment'), ('years', 'later'), ('in', 'a'), ('by', 'the'), ('as', 'the')]
STOPW = set('that from they were have this their there been would about which when what into over after before while with were also than them then very just only'.split())
def _clean(w): return re.sub(r"[^a-z']", '', w.lower())
def _st(ws, last):
    low = [_clean(w) for w in ws]; pick = (lambda lx: (looks(lx, low) or [None])[-1]) if last else (lambda lx: look(lx, low))
    emos = looks(EML, low)
    return dict(bg=pick(BGL), city=pick(CITYL), tod=pick(TODL), wx=pick(WXL), emo=next((e for e in PRI if e in emos), None),
                cast={re.sub(r'[^A-Za-z]', '', w) for w in ws if w[:1].isupper() and re.sub(r'[^A-Za-z]', '', w) not in STOP} | {l for l in low if l in ROLES},
                bag={l for l in low if len(l) > 3 and l not in STOPW})
FUNC = set('a an the his her their its my our your this that these those of to in at on by with from near across over through into onto as and or but who which whom whose was were is are had has have be been being would will could should can may might not no for about under above beside behind between among toward towards up down off out very so such than too more most some any each every many much'.split())
OPEN = set('he she they it we i you the a an his her their its my our this that there here at in on after before during as when while then but suddenly meanwhile later soon finally once next one every each some many all both another'.split())
def segment(text, minw=9, maxw=26, thr=1.1):
    toks = []; para = set()
    for pi, p in enumerate(re.split(r'\n\s*\n', text.strip())):
        if toks: para.add(len(toks))
        toks += p.split()
    n = len(toks); low = [_clean(t) for t in toks]; inq = []; q = 0
    for t in toks: q += len(re.findall(r'["“”]', t)); inq.append(q % 2 == 1)
    sc = [0.0] * (n + 1)
    for i in range(minw - 1, n - minw + 2):
        if inq[i - 1] and i < n and inq[i]: continue
        if i < n and (low[i - 1] in FUNC or not (low[i] in OPEN or low[i] in CUES or toks[i][:1].isupper())): continue
        L, Rr = toks[max(0, i - 10):i], toks[i:i + 10]; a, b = _st(L, True), _st(Rr, False); s = 0.0
        for k, wt in (('bg', .9), ('city', .6), ('tod', .7), ('wx', .5)):
            if b[k] and a[k] != b[k]: s += wt * (1 if a[k] else .6)
        if b['emo'] and b['emo'] != a['emo']: s += .6
        if b['cast'] - a['cast']: s += .5
        BL, BR = _st(toks[max(0, i - 20):i], True)['bag'], _st(toks[i:i + 20], False)['bag']
        if BL and BR: s += .3 * (1 - len(BL & BR) / math.sqrt(len(BL) * len(BR)))
        if low[i] in CUES: s += .9
        if any(low[i] == c[0] and i + 1 < n and low[i + 1] == c[1] for c in CUE2): s += .55
        pv = toks[i - 1]
        if re.search(r'[.!?]["”]?$', pv): s += .45
        elif re.search(r'[,;:]$', pv): s += .2
        if i in para: s += .8
        if low[i] in ('the', 'a', 'an', 'his', 'her', 'their', 'its', 'this') and not re.search(r'[.!?]"?$', pv): s -= .3
        sc[i] = s
    for i in range(n, 0, -1):
        if sc[i] > 0 and any(sc[j] >= .75 * sc[i] for j in range(max(0, i - 3), i)): sc[i] = 0
    cuts = []
    for i in sorted(range(n + 1), key=lambda j: -sc[j]):
        if sc[i] < thr: break
        if i >= minw and n - i >= minw and all(abs(i - c) >= minw for c in cuts): cuts.append(i)
    cuts = sorted(cuts); done = False
    while not done:
        done = True; ed = [0] + cuts + [n]
        for a_, b_ in zip(ed, ed[1:]):
            if b_ - a_ > maxw:
                lo, hi = a_ + minw, b_ - minw; mid = (a_ + b_) / 2
                if hi >= lo: cuts.append(max(range(lo, hi + 1), key=lambda j: (sc[j] > 0) * sc[j] - abs(j - mid) * .02)); cuts.sort(); done = False; break
    ed = [0] + cuts + [n]; segs = [toks[a_:b_] for a_, b_ in zip(ed, ed[1:])]
    if len(segs) > 1 and len(segs[-1]) < minw - 1: segs[-2] += segs.pop()
    return [(' '.join(s)[:1].upper() + ' '.join(s)[1:]) for s in segs if s]

BEATS_ON = True
def plan(text, genre=None, title=None, tts=None, wpm=2.5):
    sents = segment(text) if SEMANTIC else [b for s_ in split_sentences(text) for b in (beats(s_) if BEATS_ON else [s_])]; genre = genre or genre_of(text); title = title or ' '.join(sents[0].split()[:6]).rstrip('.,')
    # cast
    first = {}; cnt = {}
    for s in sents:
        toks = re.findall(r"[A-Za-z']+", s)
        for j, w in enumerate(toks):
            lw = w.lower()
            if w[0].isupper() and w not in STOP and lw not in BGL and lw not in CITYL and lw not in ROLES and lw not in PROPL and not lw.endswith('ly') and len(w) > 2 and not (j == 0 and lw in EML) and not (j == 0 and lw in ACTL):
                cnt[w] = cnt.get(w, 0) + 1; first.setdefault(w, len(first))
            elif lw in ROLES: cnt[lw] = cnt.get(lw, 0) + 1; first.setdefault(lw, len(first))
    cast = sorted(sorted(cnt, key=lambda k: -cnt[k])[:6], key=lambda k: first[k])
    for n in cast: make_char(n.capitalize() if n.lower() in ROLES else n, n.lower() if n.lower() in ROLES else None)
    CN = {n.lower(): (n.capitalize() if n.lower() in ROLES else n) for n in cast}
    if not cast: make_char('Narrator', 'narrator'); CN['narrator'] = 'Narrator'
    make_char('Anchor', 'anchor')
    scenes = []; bg = 'village'; cur = None; tod = None; wx = None; last = [list(CN.values())[0]]; hud_on = False; hud_s = [0, 0]; seenbg = None; nsc = 0; lastm = [None, 0]
    tm = re.search(r'\b([A-Z][a-z]+)\s+(?:vs?\.?|against)\s+([A-Z][a-z]+)', text); ta, tb = (tm.group(1)[:3].upper(), tm.group(2)[:3].upper()) if tm else ('RED', 'BLU')
    for si, s in enumerate(sents):
        toks = re.findall(r"[A-Za-z']+", s); low = [t.lower() for t in toks]; words = s.split()
        d = clamp(len(words) / wpm + .6, 2.6, 7.0)
        voice = None
        if tts: voice, vd = tts(s, si); d = max(2.6, vd + .45)
        # location / time / weather (persist)
        nb = look(BGL, low); cty = look(CITYL, low) if not ('york' in low and 'new' not in low) else None
        if cty and not nb: nb = 'metro'
        if nb == 'stadium' and genre != 'sports' and not (set(low) & {'stadium', 'football', 'referee', 'striker', 'goalkeeper'}): nb = None
        nbg = nb or bg; ntod = look(TODL, low); nwx = look(WXL, low)
        if nb and nb != bg and not ntod: tod = None
        if ntod: tod = None if ntod == 'clear' else ntod
        wxa = globals().setdefault('_WXA', [0]); wxa[0] = 0 if nwx else wxa[0] + 1
        if nwx: wx = None if nwx == 'clear' else nwx
        elif wxa[0] > 2: wx = None
        if nbg != bg and nb: wx = nwx if nwx and nwx != 'clear' else None
        bg = nbg; city = cty or (cur if bg == 'metro' else None) or 'paris'
        if bg == 'metro': cur = city
        if bg == 'stadium' and genre == 'sports' or (genre == 'sports' and bg == 'village'): bg = 'stadium'
        bo = {}; t2 = None
        if bg in ('city', 'metro', 'village'): bo['time'] = {'night': 'night', 'sunset': 'dusk', 'dusk': 'dusk', 'sunrise': 'dusk'}.get(tod, 'day')
        if bg == 'stadium' and tod == 'night': bo['night'] = True
        if bg == 'metro': bo['city'] = city
        if bg == 'village' and re.search(r'temple|diya|pray', s.lower()): bo['temple'] = True
        INT = ('stadium', 'locker', 'tunnel', 'hall', 'studio', 'office', 'home'); NAT = ('city', 'metro', 'village')
        tint = None if (bg in INT and tod != 'night') or (bg == 'stadium') or (bg in NAT and tod in ('night', 'sunset', 'dusk')) else tod
        if bg in INT and bg not in ('stadium',): tint = None
        # emotion / action
        ems = looks(EML, low); emo = next((e for e in PRI if e in ems), 'neutral')
        if genre != 'sports' and 'goal' in low: emo = 'neutral'
        f0, f1, act, sfx, em, mus = EM[emo]; v = look(ACTL, low)
        if v: act = v
        if re.search(r'["“”]', s) and not v: act = 'talk'
        mw = look(MOODL, low); mk = mw or EMOOD[emo]
        if emo == 'neutral' and not mw and lastm[0] and lastm[1] < 1: mk = lastm[0]; lastm[1] += 1
        elif emo != 'neutral' or mw: lastm[:] = [mk, 0]
        else: lastm[0] = None
        mus = mus or MOODS[mk][6]
        # actors
        named = [CN[t] for t in low if t in CN] + [CN[w.lower()] for w in toks if w.lower() in CN]
        seen = []
        for n in named:
            if n not in seen: seen.append(n)
        if seen: last = seen[:3]
        ac = list(seen[:3] or last[:1] or list(CN.values())[:1]); n = len(ac)
        xs = {1: [640], 2: [470, 810], 3: [380, 640, 900]}[n]; run = act == 'run'; walk = act == 'walk'
        actors = []; ps = []
        for i, nm in enumerate(ac):
            x = xs[i]; sd = 1 if x <= 640 else -1; y = 560 + (i % 2) * 26
            if run: path = [(0, 150 if sd > 0 else 1130, y), (d, 1130 if sd > 0 else 150, y)]
            elif walk: path = [(0, x - sd * 260, y), (d * .7, x, y), (d, x + sd * 26, y)]
            else: path = [(0, x - sd * 150, y), (d * .4, x, y), (d, x + sd * 30, y)]
            a_i = act if i == 0 else {'joy': 'cheer', 'sad': 'sad', 'angry': 'shock', 'shock': 'shock'}.get(emo, 'auto')
            fc = [(0, f0 if i == 0 else {'joy': 'happy', 'sad': 'sad', 'angry': 'worried', 'shock': 'shock'}.get(emo, 'neutral')), (d * .55, f1 if i == 0 else 'neutral')]
            acts = [(d * .35, a_i)] if a_i in ('kick', 'jump', 'fall', 'wave', 'shrug', 'point') else ([(.5, a_i)] if a_i not in ('auto', 'run', 'walk') else [])
            if a_i in ('kick', 'jump', 'fall', 'wave', 'shrug', 'point') and a_i in ONE_ or False: pass
            actors.append(E.actor(nm, path, act=acts, face=fc, say=[(.3, d - .3)] if (a_i == 'talk' or (act == 'talk' and i == 0)) else [], fdir=[(d * .4, sd)], look=None))
            ps.append(x)
        # props
        pr = []; pl = []; used = set()
        for pk, ccol in find_objs(low):
            if pk in used or len(pr) >= 3: continue
            used.add(pk); col = ccol or PAL[hsh(pk + s) % 10]; k = len(pr)
            fh, mv, sz = ginfo(pk)
            if fh: pr.append(E.prop(pk, path=[(0, 100, 540, fh), (d, 1180, 540, fh + 40)], size=sz, col=col, txt='R'))
            elif mv:
                dr = 1 if k % 2 == 0 else -1; yy = 520 + 40 * (k % 3); pr.append(E.prop(pk, path=[(0, 120 if dr > 0 else 1160, yy, 0), (d, 1160 if dr > 0 else 120, yy, 0)], size=sz, col=col, txt=('R' if dr > 0 else 'L') + ' walk'))
            else: pr.append(E.prop(pk, path=[(0, [160, 1100, 330, 960][k], 480 + 30 * k, 0)], size=sz, col=col))
        if mk == 'joy' and len(pr) < 3 and 'balloon' not in used: pr += [E.prop('balloon', path=[(0, 260 + 640 * q, 560, 60), (d, 270 + 640 * q, 560, 170)], col=PAL[(si + q) % 10]) for q in (0, 1)]
        sports = genre == 'sports' and re.search(r'goal|ball|kick|shot|score|penalty|pass', s.lower())
        if sports and actors:
            x0 = ps[0]; kt = d * .35; sd = 1 if x0 <= 640 else -1; actors[0]['act'] = [(kt, 'kick')]; scored = re.search(r'goal|scor', s.lower())
            gx = 1130 if sd > 0 else 150
            pr.append(E.prop('ball', path=[(0, x0 + 34 * sd, 564, 0), (kt, x0 + 34 * sd, 564, 2), (kt + .35, (x0 + gx) / 2, 530, 55), (kt + .7, gx, 492, 40 if scored else 10), (d, gx + 5 * sd, 496, 0)]))
        sf = []; ev = look(SFXL, low)
        for q in looks(SFXL, low)[:2]: sf.append((.4, q, .8))
        if sfx and emo != 'neutral': sf.append((.5, sfx, .7))
        if sports and re.search(r'goal|scor', s.lower()): sf += [(d * .35 + .6, 'net', 1.0), (d * .35 + .65, 'roar', 1.0)]
        if sports and si == 0: sf.append((.2, 'whistle', .9))
        if mk == 'fear': sf += [(.3 + q * .9, 'thud', .35) for q in range(int(d / .9))]
        if mk in ('magic', 'wonder'): sf.append((.5, 'ding', .3))
        fxs = []
        if re.search(r'win|won|champion|victory|trophy|celebrat', s.lower()) or (sports and re.search(r'goal|scor', s.lower())): fxs.append(E.fx(d * .4, 'confetti', d=3.0))
        if sports and re.search(r'goal|scor', s.lower()): fxs += [E.fx(d * .45, 'burst', text='GOAL!', x=640, y=200), E.fx(d * .45, 'shake', amp=14)]
        if emo in ('shock', 'panic') or look(SFXL, low) == 'sting': fxs.append(E.fx(.3, 'shake', amp=11))
        if look(SFXL, low) == 'sting': fxs.append(E.fx(.3, 'flash', a=.7))
        if si == 0: fxs.append(E.fx(.4, 'title', text=title.upper(), d=min(2.2, d - 1.0), size=int(min(100, 1500 / max(len(title), 1))), y=250))
        if si == len(sents) - 1: fxs.append(E.fx(max(.5, d - 2.0), 'title', text='THE END', d=1.6, size=100, y=300))
        if mk == 'action': fxs.append(E.fx(.3, 'speed', d=min(1.2, d - .4)))
        # score HUD
        scm = re.search(r'(\d+)\s*[-–]\s*(\d+)', s)
        if genre == 'sports' and (scm or not hud_on):
            if scm: hud_s = [int(scm.group(1)), int(scm.group(2))]
            mn = re.search(r'(\d+)(?:st|nd|rd|th)?\s*minute', s.lower()); hud_on = True; hd = E.hud(ta, tb, hud_s[0], hud_s[1], f"{mn.group(1)}'" if mn else ('FT' if 'full time' in s.lower() else "1'"))
        else: hd = None
        # camera / transition / music
        ci = nsc % 4; a0 = ac[0]
        cam = [dict(follow=a0, z=(1.05, 1.3), lead=40), dict(x=(560, 720), z=1.08), dict(follow=a0, z=(1.3, 1.0), lead=20), dict(x=(720, 560), z=(1.0, 1.12))][ci]
        if run: cam = dict(follow=a0, z=(1.15, 1.25), lead=90)
        tr = 'cut' if nsc == 0 else ('fade' if (bg != seenbg or tint != scenes[-1].get('tod')) else ('whip' if act in ('run', 'kick', 'fall') or emo in ('shock', 'panic') else ('flash' if emo == 'joy' else 'cut')))
        music = mus or {'sports': 'up', 'news': 'up', 'doc': 'sad', 'story': 'sad'}[genre]; crowd = (.5, .8) if sports else ((.3, .9) if emo == 'joy' else (.25, .35))
        # anchor scene for news
        if genre == 'news' and si % 4 == 0:
            bg2 = 'studio'; hl = ' '.join(words[:4]).upper().rstrip('.,'); sc = E.scene(d, 'studio', dict(screen=hl), [E.actor('Anchor', [(0, 640, 560), (d, 650, 566)], act=[(.3, 'talk')], face=[(0, 'neutral'), (d * .5, 'determined')], say=[(.3, d - .3)])], cam=dict(z=(1.0, 1.2)), crowd=.2, music='up', tr=tr if nsc else 'cut', fx=fxs, sfx=[(.2, 'ding', .5)] if nsc == 0 else [])
            sc['tod'] = None; seenbg = 'studio'
        else:
            sc = E.scene(d, bg, bo, actors, pr, cam, fxs, sf, None, em, crowd, music, tr, hd); sc['tod'] = tint
        sc['mood'] = mk; sc['wx'] = wx; sc['voice'] = voice; sc['letter'] = genre in ('story', 'doc'); sc['em'] = emo; sc['text'] = s
        if bg != seenbg and sc['bg'] != 'studio': sc['tag'] = (city.upper() if bg == 'metro' else bg.upper()); seenbg = bg
        # karaoke chunks
        ch = [words[i:i + 8] for i in range(0, len(words), 8)]; tot = sum(len(w) + 2 for w in words); tt = .2; span = d - .45; kar = []
        for c in ch:
            ws = []
            for w in c: dt = (len(w) + 2) / tot * span; ws.append((w, tt, tt + dt)); tt += dt
            kar.append([ws[0][1] - .05, ws[-1][2] + .08, ws, em])
        for k in range(len(kar) - 1): kar[k][1] = kar[k + 1][0]
        kar[-1][1] = d - .05; sc['kar'] = [tuple(k) for k in kar]
        scenes.append(sc); nsc += 1
    # thumbnail
    best = max(range(len(scenes)), key=lambda i: ({'joy': 3, 'shock': 3, 'panic': 2, 'angry': 2}.get(scenes[i]['em'], 0), -i))
    tx = 'GOAL!' if genre == 'sports' and any('goal' in s.lower() for s in sents) else ' '.join(title.split()[:2]).upper() + '!'
    scenes[best]['thumb'] = (tx, scenes[best]['dur'] * .55)
    return scenes, genre, title
ONE_ = set()

# ---------------------------------------------------------------- narration hooks
def tts_edge(voice='en-US-GuyNeural', rate='+0%'):
    import asyncio, edge_tts, tempfile
    def f(s, i):
        mp3 = f'/tmp/_nar{i}.mp3'; wv = f'/tmp/_nar{i}.wav'; txt = re.sub(r'["“”]', '', s)
        asyncio.run(edge_tts.Communicate(txt, voice, rate=rate).save(mp3)); subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', mp3, '-ar', str(E.SR), '-ac', '1', wv], check=True)
        with wave.open(wv) as q: return wv, q.getnframes() / q.getframerate()
    return f
def pack(scenes, genre, title, out):
    t = 0; ch = []; kw = {}
    for sc in scenes:
        if not ch or t - ch[-1][0] >= 20: ch.append((t, sc['text'][:48]))
        for w in re.findall(r'[A-Za-z]{5,}', sc['text'].lower()): kw[w] = kw.get(w, 0) + 1
        t += sc['dur']
    tags = sorted(kw, key=lambda k: -kw[k])[:12]; mm = lambda x: f'{int(x // 60)}:{int(x % 60):02d}'
    txt = f"TITLE: {title}\n\nDESCRIPTION:\n{scenes[0]['text']}\n\nCHAPTERS\n" + '\n'.join(f'{mm(a)} {b}' for a, b in ch) + f"\n\nTAGS: {', '.join(tags + [genre, 'animation', 'lego style', 'storytelling'])}\n\nNOTE: add your own voice/commentary and vary scripts - YouTube's monetization review rewards original, non-repetitive work.\n"
    open(out.rsplit('.', 1)[0] + '_pack.txt', 'w').write(txt)

def pool():
    print(f'backgrounds: {len(E.BGS)} ({", ".join(E.BGS)})\ncities/landmarks: {len(CITIES)} ({", ".join(CITIES)})\ntimes of day: sunrise sunset dusk night day | weather: rain storm snow fog wind dust\nanimals: {len(ANIMALS)} | objects: {len(OBJECTS)} + ball/trophy/flag/mic/balloon/paper/sign/cone/star\nexpressions: {len(E.EXPR)} | actions: {len([1 for _ in "idle move kick header jump celebrate cheer sad shock angry talk point fall getup dive shrug bow wave namaste dance crouch think".split()])} | roles: {len(ROLES)}')
def main():
    ap = argparse.ArgumentParser(); ap.add_argument('script', nargs='?'); ap.add_argument('out', nargs='?'); ap.add_argument('--genre'); ap.add_argument('--title'); ap.add_argument('--fast', action='store_true'); ap.add_argument('--pool', action='store_true')
    ap.add_argument('--tts'); ap.add_argument('--voice-name', default='en-US-GuyNeural'); ap.add_argument('--voice'); ap.add_argument('--by-punct', action='store_true'); a = ap.parse_args()
    global SEMANTIC; SEMANTIC = not a.by_punct
    if a.pool or not a.script: return pool()
    if a.fast: E.K = 1.0
    text = open(a.script).read(); tts = tts_edge(a.voice_name) if a.tts == 'edge' else None
    sc, g, ti = plan(text, a.genre, a.title, tts)
    if a.voice:
        wv = '/tmp/_voice.wav'; subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', a.voice, '-ar', str(E.SR), '-ac', '1', wv], check=True)
        with wave.open(wv) as q: vd = q.getnframes() / q.getframerate()
        tot = sum(s['dur'] for s in sc); f = (vd + 1.0) / tot
        for s in sc: s['dur'] *= f; s['kar'] = tuple((x0 * f, x1 * f, [(w, w0 * f, w1 * f) for w, w0, w1 in ws], em) for x0, x1, ws, em in s['kar'])
        sc[0]['voice'] = wv
    print(f'genre={g} scenes={len(sc)} duration={sum(s["dur"] for s in sc):.1f}s', flush=True); pack(sc, g, ti, a.out); E.make(sc, a.out)

# ================================================================ UNLIMITED OBJECTS (procedural generator)
import json
COLW = dict(red=(215, 40, 45), blue=(50, 100, 225), green=(50, 160, 80), yellow=(250, 210, 50), golden=(240, 190, 50), gold=(240, 190, 50), silver=(190, 195, 205), black=(35, 35, 42), white=(245, 245, 245),
            purple=(150, 70, 190), pink=(240, 120, 170), orange=(245, 135, 40), brown=(130, 85, 50), grey=(130, 130, 140), gray=(130, 130, 140), crimson=(180, 25, 50), golden_=(240, 190, 50))
CAT = lex(dict(
 animal='wolf bear deer monkey ape snake parrot owl duck frog turtle dolphin whale crocodile fox panda penguin donkey goat sheep pig chicken hen cheetah leopard giraffe zebra kangaroo squirrel mouse rat buffalo ox bull peacock crow sparrow dragon dinosaur lizard tortoise hippo rhino gorilla spider ant crab octopus jellyfish seal otter swan goose turkey monster alien',
 flyer='bat bee butterfly dragonfly eagle hawk pigeon crane vulture falcon',
 vehicle='truck train tractor helicopter scooter ambulance taxi jeep van submarine tank cart carriage rickshaw tram motorcycle limousine ferry yacht canoe sled drone jet ufo',
 building='school hospital mosque church tower bridge factory hotel palace fort gate hut cottage barn gym museum station airport lighthouse windmill pagoda cathedral mall bank',
 food='apple banana pizza burger bread rice mango orange grape cherry strawberry watermelon coconut cookie donut sandwich egg candy chocolate pie corn carrot tomato potato lemon pumpkin',
 plant='grass bush palm cactus vine bamboo plant leaf mushroom rose lotus sunflower',
 furniture='sofa bed desk shelf door window mirror cupboard stool fridge stove sink bathtub curtain carpet rug',
 tech='robot screen radio satellite speaker battery bulb server printer watch telescope',
 tool='hammer axe pickaxe spade shovel knife key rope ladder bucket broom saw wrench scissors pen pencil brush bow arrow spear gun cannon bomb',
 wear='hat bag shoes glasses ring necklace scarf helmet mask cape coat jacket boot gloves backpack',
 music='flute piano violin trumpet harp sitar tabla saxophone',
 nature='sun moon star cloud rainbow volcano river waterfall rock stone cave lightning hill island iceberg boulder feather',
 container='box chest bottle jar pot basket barrel cup mug vase bowl plate'))
CAT.update({'balloon': 'flyer'}) if False else None
STOPN = set('day days time way story life world people idea dream hope year years night morning evening moment thing things lot part end start side place man woman men women boy girl child children family friend friends one two three something nothing everything anyone everyone fear joy love anger power voice word words name news fact reason top bottom front back middle air sky ground light dark sound noise silence rest while after before time energy question answer problem plan journey adventure victory defeat game match team city town village country land home house room street road path field fields clouds'.split())
ADJ = set('old new little small big large tiny huge great grand heavy bright shiny ancient broken magic magical wooden golden silver colorful beautiful strange giant mysterious sacred royal tall long short young'.split())
DET = set('a an the his her its their my our your some two three four five many several each every that this these those'.split())
def tup(x):
    if isinstance(x, list) and len(x) == 3 and all(isinstance(v, (int, float)) for v in x): return tuple(x)
    return [tup(v) for v in x] if isinstance(x, list) else x
def load_extra(path='pool_extra.json'):
    if not os.path.exists(path): return
    for n, pl in json.load(open(path)).items():
        POOL_PROPS[n] = (lambda t, c, w, pl=pl: [tuple(tup(v) for v in p) for p in pl]); PROPL[n] = n
load_extra()
def cat_of(w):
    for s in stems(w):
        if s in CAT: return CAT[s], s
    return None, w
def sing(w): return w[:-1] if w.endswith('s') and not w.endswith('ss') and len(w) > 3 else w
def ginfo(pk):
    if not pk.startswith('gen:'): return (FLY.get(pk, 0), pk in MOVE, 1.0)
    w = pk.split(':')[1]; c, _ = cat_of(w)
    if c == 'flyer' or w in ('drone', 'helicopter', 'jet', 'ufo', 'satellite'): return (150 if c == 'flyer' else 110, True, 1.0)
    return (0, c in ('vehicle', 'animal'), {'building': 1.7, 'plant': 1.2, 'nature': 1.3, 'furniture': 1.1, 'vehicle': 1.0}.get(c, .95))
def find_objs(low):
    out = []; seen = set(); myst = 0
    for i, w in enumerate(low):
        col = COLW.get(low[i - 1]) or (COLW.get(low[i - 2]) if i > 1 else None)
        kn = next((PROPL[s] for s in stems(w) if s in PROPL), None)
        if kn:
            if kn not in seen: seen.add(kn); out.append((kn, col))
            continue
        c, base = cat_of(w)
        if c and base not in seen: seen.add(base); out.append(('gen:' + base, col)); continue
        prev = low[i - 1] if i else ''; pp = low[i - 2] if i > 1 else ''
        det = prev in DET or ((prev in ADJ or prev in COLW) and pp in DET)
        if det and myst < 1 and len(w) > 3 and sing(w) not in STOPN and w not in STOPN and not w.endswith(('ly', 'ing', 'ed')) and not any(s in (EML, ACTL, TODL, WXL, BGL, CITYL, ROLES) for s in () ) \
           and not any(s in d_ for d_ in (EML, ACTL, TODL, WXL, BGL, CITYL, ROLES, COLW) for s in stems(w)) and w not in ADJ and w not in DET:
            myst += 1; out.append(('gen:' + sing(w), col))
    return out
def gen_prims(word, t, col, walk):
    h = hsh(word); c, base = cat_of(word); col = col or PAL[h % 10]; dk = shd(col, .7); lt = shd(col, 1.25); b = lambda s, n: (h >> s) % n
    if c == 'animal':
        ex = []
        if b(22, 3) == 0: ex = [('l', [(i, -40 - b(3, 8)), (i + 4, -24)], dk, 3) for i in (-18, -4, 10)]
        elif b(22, 3) == 1: ex = [('e', -8, -34, 7, 6, dk), ('e', 12, -30, 5, 5, dk)]
        if base == 'dragon': ex += [('p', [(-6, -44), (-26, -80), (10, -48)], lt)]
        return quad(t, walk, col, .8 + b(3, 5) * .12, 12 + b(6, 24), 26 + b(9, 20), -8 - b(12, 24), .8 + b(15, 5) * .12, ['pt', 'fl', 'long', 'none'][b(18, 4)], 1 + b(20, 2), ex)
    if c == 'flyer': return animal('bird')(t, col, walk)
    if c == 'vehicle':
        if base in ('helicopter', 'drone', 'ufo'):
            ro = math.sin(t * 40) * 40; return [('e', 0, -26, 26, 14, col), ('l', [(-ro, -44), (ro, -44)], DK, 3), ('l', [(26, -26), (54, -30)], col, 5), ('e', -4, -30, 9, 7, (170, 215, 240))] if base != 'ufo' else [('e', 0, -22, 34, 9, GR), ('e', 0, -32, 16, 14, (170, 220, 240)), ('g', 0, -16, 70, (160, 255, 200), .4)]
        n = 3 if base == 'train' else 1; P = []
        for k in range(n): x0 = k * 70; P += [('r', x0 - 32, -44 if base in ('train', 'van', 'truck', 'ambulance') else -34, x0 + 32, -12, col), ('e', x0 - 18, -10, 8, 8, DK), ('e', x0 + 18, -10, 8, 8, DK)]
        P += [('r', -32 + 20, -58, -32 + 56, -44, shd(col, .85))] if base in ('truck', 'tractor', 'taxi', 'jeep', 'tram') else []
        if base == 'ambulance': P += [('r', -4, -38, 4, -22, WH), ('r', -10, -32, 10, -28, WH)]
        return P
    if c == 'building':
        w2 = 34 + b(3, 5) * 10; hh = 60 + b(6, 6) * 16
        if base in ('tower', 'lighthouse'): w2 = 22; hh = 130
        P = [('r', -w2, -hh, w2, 0, shd(col, 1.15))]
        if base == 'windmill': ro = t * 2; return [('p', [(-26, 0), (-14, -80), (14, -80), (26, 0)], col)] + [('l', [(0, -84), (80 * math.cos(ro + a), -84 + 80 * math.sin(ro + a))], (240, 235, 220), 6) for a in (0, 1.57, 3.14, 4.71)]
        if base == 'bridge': return [('r', -80, -30, 80, -22, GR)] + [('r', x - 5, -22, x + 5, 0, dk) for x in (-70, 0, 70)] + [('l', [(-80, -30), (0, -80), (80, -30)], dk, 4)]
        for r_ in range(max(1, int(hh // 36))):
            for q in (-1, 1): P.append(('r', q * w2 * .45 - 6, -hh + 12 + r_ * 30, q * w2 * .45 + 6, -hh + 26 + r_ * 30, (170, 215, 240)))
        P.append(('r', -8, -26, 8, 0, DK))
        rt = b(9, 3); P.append(('p', [(-w2 - 8, -hh), (0, -hh - 36), (w2 + 8, -hh)], dk) if rt == 0 else ('e', 0, -hh, w2, 24, dk) if rt == 1 else ('r', -w2 - 6, -hh - 8, w2 + 6, -hh, dk)); return P
    if c == 'food':
        if base in ('pizza',): return [('p', [(-26, -10), (26, -10), (0, -46)], (240, 200, 110)), ('e', -6, -22, 5, 5, (200, 50, 40)), ('e', 8, -18, 5, 5, (200, 50, 40))]
        if base in ('burger', 'sandwich'): return [('e', 0, -22, 24, 10, (220, 160, 80)), ('r', -26, -16, 26, -10, (80, 170, 70)), ('r', -24, -10, 24, -4, (130, 70, 50)), ('e', 0, -2, 24, 8, (220, 160, 80))]
        if base in ('bread', 'cookie', 'donut', 'pie', 'egg'): return [('e', 0, -12, 22, 12 if base != 'egg' else 16, (225, 170, 90) if base != 'egg' else WH), ('e', 0, -12, 7 if base == 'donut' else 0.1, 4 if base == 'donut' else 0.1, (60, 60, 60))]
        return [('e', 0, -18, 18, 18, col), ('e', -6, -24, 5, 5, lt), ('l', [(0, -36), (3, -46)], (90, 60, 40), 3), ('p', [(3, -42), (16, -48), (8, -38)], (60, 170, 70))]
    if c == 'plant':
        if base == 'cactus': return [('r', -7, -52, 7, 0, (60, 140, 70)), ('r', -22, -34, -7, -26, (60, 140, 70)), ('r', -22, -42, -15, -26, (60, 140, 70)), ('r', 7, -28, 22, -20, (60, 140, 70))]
        if base == 'mushroom': return [('r', -6, -18, 6, 0, (240, 235, 220)), ('e', 0, -22, 20, 13, (210, 50, 50)), ('e', -7, -25, 3, 3, WH), ('e', 7, -20, 3, 3, WH)]
        if base == 'palm': return [('l', [(0, 0), (8, -50), (2, -80)], (120, 80, 50), 8)] + [('l', [(2, -80), (2 + 34 * math.cos(a + math.sin(t) * .1), -80 + 22 * math.sin(a) + 10)], (60, 160, 80), 6) for a in (-2.6, -1.9, -1.2, -.5)]
        return [('l', [(0, 0), (0, -28 - b(3, 20))], (60, 150, 70), 3)] + [('e', -9 + 9 * i, -20 - 10 * i, 9, 4, (60, 160, 80)) for i in range(3)] + ([('e', 0, -36, 7, 7, col)] if base in ('rose', 'lotus', 'sunflower') else [])
    if c == 'furniture':
        if base in ('sofa',): return [('r', -40, -34, 40, -8, col), ('r', -44, -26, -32, -8, dk), ('r', 32, -26, 44, -8, dk), ('r', -34, -46, 34, -34, lt)]
        if base in ('bed',): return [('r', -44, -16, 44, -6, (240, 240, 245)), ('r', -44, -34, -38, 0, (130, 85, 50)), ('r', -40, -22, -20, -16, WH)]
        if base in ('window', 'mirror', 'door'): return [('r', -14, -64, 14, 0, (150, 100, 60) if base == 'door' else GR), ('r', -10, -60, 10, -4, (170, 215, 240) if base != 'door' else (170, 115, 70))]
        return [('r', -22, -60, 22, 0, col), ('l', [(0, -60), (0, 0)], dk, 2), ('e', -5, -30, 2, 2, DK), ('e', 5, -30, 2, 2, DK)]
    if c == 'tech':
        if base == 'robot': bl = 1 if int(t * 3) % 2 else 0; return [('r', -14, -20, 14, 0, GR), ('r', -18, -52, 18, -20, shd(GR, 1.1)), ('r', -12, -72, 12, -52, GR), ('e', -5, -62, 3, 3, (80, 220, 255)), ('e', 5, -62, 3, 3, (80, 220, 255)), ('l', [(0, -72), (0, -82)], DK, 2), ('e', 0, -84, 3, 3, (240, 60, 60) if bl else DK), ('l', [(-18, -48), (-30, -30)], GR, 5), ('l', [(18, -48), (30, -30)], GR, 5)]
        if base == 'bulb': return [('e', 0, -30, 14, 16, (255, 240, 150)), ('r', -6, -14, 6, -4, GR), ('g', 0, -30, 80, (255, 240, 150), .5)]
        if base == 'satellite': return [('r', -10, -40, 10, -20, GR), ('r', -50, -36, -14, -24, (60, 100, 200)), ('r', 14, -36, 50, -24, (60, 100, 200))]
        return [('r', -24, -40, 24, -6, DK), ('r', -20, -36, 20, -10, mixc((60, 90, 180), (200, 230, 255), .5 + .5 * math.sin(t * 3)))]
    if c == 'tool':
        hd = b(3, 4)
        if base in ('ladder',): return [('l', [(-10, 0), (-10, -70)], (150, 100, 60), 4), ('l', [(10, 0), (10, -70)], (150, 100, 60), 4)] + [('l', [(-10, -14 * i), (10, -14 * i)], (150, 100, 60), 3) for i in range(1, 5)]
        if base in ('bow',): return [('l', [(0, -70 + 70 * math.sin(a) * 1.0 - 0, ) if False else (10 * math.sin(a), -35 - 35 * math.cos(a)) for a in np.linspace(-1.5, 1.5, 9)], (150, 100, 60), 4), ('l', [(0, -70), (0, 0)], WH, 1)]
        if base in ('key',): return [('e', 0, -52, 10, 10, (240, 190, 50)), ('l', [(0, -42), (0, 0)], (240, 190, 50), 5), ('l', [(0, -8), (10, -8)], (240, 190, 50), 4)]
        return [('l', [(0, 0), (0, -60)], (130, 85, 50), 6), ('p', [(-14, -62), (14, -62), (14, -50), (-14, -50)], GR) if hd == 0 else ('p', [(0, -66), (20, -54), (0, -44)], GR) if hd == 1 else ('e', 0, -64, 9, 9, GR) if hd == 2 else ('p', [(-6, -60), (6, -60), (0, -78)], GR)]
    if c == 'wear':
        if base in ('hat', 'helmet'): return [('e', 0, -6, 26, 6, dk), ('e', 0, -16, 16, 14, col)]
        if base == 'glasses': return [('e', -12, -10, 10, 10, (190, 220, 240)), ('e', 12, -10, 10, 10, (190, 220, 240)), ('l', [(-2, -10), (2, -10)], DK, 2)]
        if base in ('shoes', 'boot'): return [('e', -12, -6, 12, 6, col), ('e', 12, -6, 12, 6, col)]
        return [('r', -16, -34, 16, 0, col), ('l', [(-10, -34), (0, -50), (10, -34)], dk, 3)]
    if c == 'music': return [('e', 0, -24, 16, 22, (170, 105, 50)), ('l', [(0, -44), (0, -86)], (80, 55, 35), 5), ('g', 0, -24, 60, (255, 220, 150), .15 + .1 * math.sin(t * 8))] if base != 'piano' else [('r', -40, -36, 40, -6, DK), ('r', -40, -36, 40, -26, WH)]
    if c == 'nature':
        if base == 'sun': return [('g', 0, -40, 120, (255, 230, 120), .6), ('e', 0, -40, 26, 26, (255, 225, 80))]
        if base == 'moon': return [('g', 0, -40, 100, (210, 220, 255), .5), ('e', 0, -40, 24, 24, (240, 240, 225)), ('e', 10, -46, 20, 20, (18, 20, 50))]
        if base == 'cloud': return [('e', -16, -20, 22, 14, WH), ('e', 12, -24, 26, 16, WH), ('e', 0, -32, 18, 14, WH)]
        if base == 'rainbow': return [('l', [(-60 * math.cos(a), -60 * math.sin(a)) for a in np.linspace(0, math.pi, 12)], c_, 5) for c_ in ((230, 50, 50), (250, 180, 40), (80, 190, 90), (70, 120, 230))] if False else [('l', [((60 - 7 * j) * math.cos(a), -(60 - 7 * j) * math.sin(a)) for a in np.linspace(0, math.pi, 12)], c_, 6) for j, c_ in enumerate(((230, 50, 50), (250, 180, 40), (80, 190, 90), (70, 120, 230)))]
        if base == 'volcano': return [('p', [(-70, 0), (-16, -70), (16, -70), (70, 0)], (110, 70, 55)), ('p', [(-16, -70), (0, -90 - 10 * math.sin(t * 9)), (16, -70)], (255, 120, 40)), ('g', 0, -80, 100, (255, 140, 60), .5)]
        if base == 'star': return [('p', [((18 if i % 2 == 0 else 8) * math.sin(i * .6283 + t), -30 - (18 if i % 2 == 0 else 8) * math.cos(i * .6283 + t)) for i in range(10)], (255, 220, 70))]
        if base == 'lightning': return [('p', [(0, -80), (-12, -38), (0, -42), (-8, 0), (16, -50), (4, -46)], (255, 240, 120)), ('g', 0, -40, 90, (255, 250, 180), .5)]
        return [('p', [(-30, 0), (-24, -22), (-6, -30), (18, -24), (30, 0)], (130, 130, 140)), ('p', [(-6, -30), (18, -24), (8, -10)], (160, 160, 170))]
    if c == 'container':
        if base in ('bottle', 'vase', 'jar'): return [('p', [(-12, 0), (12, 0), (10, -26), (-10, -26)], (170, 215, 235) if base != 'vase' else col), ('r', -4, -40, 4, -26, (170, 215, 235)), ('r', -6, -44, 6, -40, (140, 90, 50))]
        if base in ('chest',): return [('r', -30, -26, 30, 0, (150, 100, 60)), ('e', 0, -26, 30, 12, (170, 115, 70)), ('r', -4, -28, 4, -14, (240, 190, 50))]
        return [('p', [(-18, -26), (18, -26), (14, 0), (-14, 0)], col), ('e', 0, -26, 18, 5, lt)]
    # mystery fallback: friendly glowing crystal/blob + label
    n = 5 + b(3, 4); pts = [((16 + b(5 + k, 3) * 6) * math.sin(k * 6.283 / n), -34 - (16 + b(5 + k, 3) * 6) * math.cos(k * 6.283 / n)) for k in range(n)]
    return [('g', 0, -34, 70, lt, .35), ('p', pts, col), ('e', -5, -36, 3, 3, WH), ('e', 5, -36, 3, 3, WH), ('t', 0, -8, 12, word.upper()[:10], (255, 255, 255))]
_dp2 = E.draw_prop
def draw_prop3(r, kind, X, Y, z, size, t, spin=0.0, col=(230, 50, 50), txt=''):
    if not kind.startswith('gen:'): return _dp2(r, kind, X, Y, z, size, t, spin, col, txt)
    w = kind.split(':')[1]; s = (0.55 + clamp((Y - 380) / 340) * .75) * size; k = r.Z() * s; cx, cy = r.X(X), r.Y(Y) - z * k
    if z < 20: r.sshade(X, Y + 2, 32 * s, 7 * s, 70)
    prims(r, cx, cy, k, gen_prims(w, t, col, 'walk' in txt), flip=txt.startswith('L'))
E.draw_prop = draw_prop3

# ================================================================ MOOD SYSTEM (emotion/environment dressing)
MOODL = lex(dict(magic='magic spell mystery secret ghost enchanted wizard', romance='wedding love kiss romantic', action='war battle attack race rush chase explosion thrilling exciting excited fast', calm='peace quiet calm gentle serene peaceful', nostalgia='memory remember childhood nostalgia', fear='haunted shadow horror creepy terrifying nightmare'))
EMOOD = dict(joy='joy', laugh='joy', sad='sad', shock='suspense', panic='fear', angry='anger', awe='wonder', love='romance', think='mystery', proud='epic', tired='sad', neutral='calm')
MOODS = dict(  # mul rgb, saturation, vignette, bloom, tilt deg, particles, music
 joy=((1.06, 1.03, .95), 1.25, .0, .2, 0, 'sparkle', 'up'), sad=((.86, .9, 1.02), .5, .38, 0, 0, 'leaf', 'sad'), fear=((.78, .74, .86), .7, .6, 0, 3, 'dust', 'tense'), suspense=((.9, .9, 1.0), .85, .45, 0, 0, None, 'tense'),
 anger=((1.15, .8, .72), 1.2, .38, 0, 0, 'ember', 'tense'), action=((1.05, 1.0, .96), 1.3, .18, 0, 0, None, 'epic'), wonder=((.95, 1.0, 1.12), 1.1, .1, .32, 0, 'sparkle', None), romance=((1.1, .95, 1.0), 1.1, .15, .38, 0, 'heart', 'sad'),
 magic=((.85, .95, 1.2), 1.2, .25, .32, 0, 'firefly', 'tense'), epic=((1.1, 1.0, .85), 1.2, .15, .2, 0, 'ray', 'epic'), calm=((1.02, 1.0, .98), 1.0, .05, .1, 0, 'drift', None), nostalgia=((1.1, .98, .8), .55, .3, .12, 0, 'drift', 'sad'), mystery=((.88, .92, 1.08), .9, .35, .15, 0, 'firefly', 'tense'))
_VG = None
def mood(im, sc, i):
    mk = sc.get('mood'); m = MOODS.get(mk)
    if not m: return im
    global _VG
    t = i / E.FPS; mul, sat, vg, bl, tilt, part, _ = m; w, h = im.size
    if _VG is None or _VG.shape[1] != w:
        yy, xx = np.mgrid[-1:1:complex(h), -1:1:complex(w)]; _VG = np.clip((np.hypot(xx * .85, yy) - .35) / .9, 0, 1)[:, :, None].astype(np.float32) ** 1.4
    a = np.asarray(im, np.float32); g = a.mean(2, keepdims=True); a = (g + (a - g) * sat) * np.array(mul, np.float32)
    if vg: a = a * (1 - _VG * vg * (1 + (.25 * math.sin(t * 5) if mk in ('fear', 'anger') else 0)))
    if bl: sm_ = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).resize((w // 4, h // 4)).filter(ImageFilter.GaussianBlur(5)).resize((w, h)); a = a + np.asarray(sm_, np.float32) * bl
    if mk == 'nostalgia': a = a + np.random.default_rng(i).normal(0, 7, a.shape[:2])[:, :, None].astype(np.float32)
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    if part:
        ov = Image.new('RGBA', im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov); n = 40 if part != 'ray' else 5
        for j in range(n):
            x = (rnd(j, 1) * w + math.sin(t * 1.2 + j) * 24) % w; ph = (rnd(j, 2) + t * (.08 + rnd(j, 3) * .1)) % 1; q = 2 + rnd(j, 4) * 4
            if part == 'sparkle': y = rnd(j, 5) * h; al = int(230 * abs(math.sin(t * 4 + j))); d.polygon([(x, y - q * 2), (x + q * .5, y - q * .5), (x + q * 2, y), (x + q * .5, y + q * .5), (x, y + q * 2), (x - q * .5, y + q * .5), (x - q * 2, y), (x - q * .5, y - q * .5)], fill=(255, 245, 190, al))
            elif part == 'heart': y = h - ph * h * 1.1; q *= 2; d.ellipse([x - q, y - q, x, y], fill=(255, 100, 140, 200)); d.ellipse([x, y - q, x + q, y], fill=(255, 100, 140, 200)); d.polygon([(x - q, y - q * .4), (x + q, y - q * .4), (x, y + q * 1.1)], fill=(255, 100, 140, 200))
            elif part == 'leaf': y = ph * h; d.ellipse([x - q * 1.5, y - q * .7, x + q * 1.5, y + q * .7], fill=[(150, 100, 60, 190), (190, 130, 60, 190), (120, 90, 60, 190)][j % 3])
            elif part == 'ember': y = h - ph * h; d.ellipse([x - q * .6, y - q * .6, x + q * .6, y + q * .6], fill=(255, 140 + j % 80, 40, int(230 * (1 - ph))))
            elif part == 'firefly': y = 200 + rnd(j, 5) * (h - 300) + math.sin(t * 1.5 + j) * 14; al = int(200 * (.5 + .5 * math.sin(t * 3 + j))); d.ellipse([x - q * 1.4, y - q * 1.4, x + q * 1.4, y + q * 1.4], fill=(255, 250, 140, al))
            elif part == 'drift': y = ph * h; d.ellipse([x - q * .5, y - q * .5, x + q * .5, y + q * .5], fill=(255, 240, 220, 150))
            elif part == 'dust': y = rnd(j, 5) * h; d.ellipse([x - q * .4, y - q * .4, x + q * .4, y + q * .4], fill=(200, 200, 210, 90))
            elif part == 'ray': x0 = 100 + j * 260 + math.sin(t * .5 + j) * 30; d.polygon([(x0, 0), (x0 + 60, 0), (x0 + 380, h), (x0 + 200, h)], fill=(255, 235, 170, 34))
        im = Image.alpha_composite(im.convert('RGBA'), ov).convert('RGB')
    if tilt: z = int(w * .06); im = im.rotate(tilt * math.sin(t * .8), Image.BICUBIC).crop((z, int(z * h / w), w - z, h - int(z * h / w))).resize((w, h))
    return im
def beats(s):
    if re.search(r'["“”]', s): return [s]
    parts = [p.strip(' ,;') for p in re.split(r',\s*(?:and\s+|but\s+|then\s+|while\s+)?|;\s*|\s+(?:but|then|while|until)\s+', s) if p and p.strip(' ,;')]
    out = []
    def sig(p):
        lw = [w.lower() for w in re.findall(r"[A-Za-z']+", p)]; return (next((e for e in PRI if e in looks(EML, lw)), None), bool(look(BGL, lw) or look(CITYL, lw) or look(TODL, lw) or look(WXL, lw)))
    for p in parts:
        if out and (len(p.split()) < 6 or len(out[-1].split()) < 6 or (sig(p)[0] in (None, sig(out[-1])[0]) and not sig(p)[1])): out[-1] += ', ' + p
        else: out.append(p)
    return [o[0].upper() + o[1:] if o else o for o in out] or [s]
_rf3 = E.render_frame
def render3(sc, i, h, pop): return _rf3(sc, i, h, pop)

if __name__ == '__main__': main()
