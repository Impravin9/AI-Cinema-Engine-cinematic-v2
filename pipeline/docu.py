"""Stage 4 - Documentary compositor.

Parallax procedural landscapes with atmospheric perspective, rim-lit silhouette actors,
Ken-Burns photo plates, animated infographics (stats / timeline / quote / map), lower-thirds,
karaoke captions, particles, cross-dissolves and a filmic grade (split-tone, bloom, vignette, grain).
Pure Pillow + NumPy: no GPU, no network, no external assets required.
"""
from __future__ import annotations

import math
import os
import re
import subprocess
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

SKY = {"dawn": ((28, 36, 76), (244, 150, 96)), "morning": ((52, 104, 168), (250, 214, 168)),
       "noon": ((34, 116, 196), (196, 228, 252)), "dusk": ((38, 28, 88), (252, 122, 72)),
       "night": ((5, 9, 26), (32, 52, 104))}
ACCENT = {"fear": (214, 64, 52), "joy": (255, 196, 72), "sadness": (104, 150, 214), "anger": (226, 48, 60),
          "curiosity": (64, 200, 196), "determined": (255, 164, 56)}
PALETTES = [((10, 12, 18), (236, 168, 92)), ((12, 14, 22), (120, 190, 230)), ((14, 10, 16), (230, 110, 120))]
_FONT_CANDIDATES = ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
                    "/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
_FONTS: dict = {}


def clamp(v, a=0.0, b=1.0):
    return a if v < a else b if v > b else v


def ease_out(t):
    return 1 - (1 - clamp(t)) ** 3


def ease_io(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def mix(a, b, w):
    return tuple(x + (y - x) * w for x, y in zip(a, b))


def lerp(a, b, t):
    return a + (b - a) * t


_ROLE_PATHS: dict[str, list] = {}


def set_theme_fonts(head, body):
    _FONTS.clear()
    _ROLE_PATHS.update(head=list(head) + _FONT_CANDIDATES, body=list(body) + _FONT_CANDIDATES)


def font(size, role="head"):
    size = int(max(8, size))
    key = (size, role)
    if key not in _FONTS:
        for p in _ROLE_PATHS.get(role, _FONT_CANDIDATES):
            if os.path.isfile(p):
                try:
                    _FONTS[key] = ImageFont.truetype(p, size)
                    break
                except OSError:
                    pass
        else:
            try:
                _FONTS[key] = ImageFont.load_default(size=size)
            except TypeError:
                _FONTS[key] = ImageFont.load_default()
    return _FONTS[key]


def fbm(w, h, rng, octaves=5, base=3):
    acc, amp, tot = np.zeros((h, w), np.float32), 1.0, 0.0
    for o in range(octaves):
        g = (rng.random((base * 2 ** o + 1, int(base * 2 ** o * w / max(h, 1)) + 2)) * 255).astype(np.uint8)
        acc += np.asarray(Image.fromarray(g).resize((w, h), Image.BICUBIC), np.float32) / 255 * amp
        tot += amp
        amp *= 0.5
    return acc / tot


def _arr_img(a):
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGBA")


# --------------------------------------------------------------------------- layers
def _sky(CW, CH, pal, rng, night, hz):
    top, bot = pal
    t = np.linspace(0, 1, CH, dtype=np.float32)[:, None, None] ** 0.85
    a = np.repeat(np.array(top, np.float32) * (1 - t) + np.array(bot, np.float32) * t, CW, axis=1)
    yy, xx = np.mgrid[0:CH, 0:CW].astype(np.float32)
    sx, sy = CW * rng.uniform(0.3, 0.7), hz - CH * 0.08
    g = np.exp(-(((xx - sx) ** 2) / (2 * (CW * .16) ** 2) + ((yy - sy) ** 2) / (2 * (CH * .22) ** 2)))[..., None]
    a += g * np.array((150, 170, 230) if night else mix(bot, (255, 236, 200), .5), np.float32) * (.3 if night else .55)
    n = fbm(CW // 4, CH // 4, rng)
    n = np.asarray(Image.fromarray((n * 255).astype(np.uint8)).resize((CW, CH), Image.BICUBIC), np.float32) / 255
    c = (np.clip((n - .52) * 3.2, 0, 1) * np.clip(1 - yy / hz, 0, 1))[..., None] * .4
    a = a * (1 - c) + np.array(mix(bot, (255, 255, 255), .35), np.float32) * c
    img = _arr_img(a)
    if night:
        d = ImageDraw.Draw(img)
        for _ in range(160):
            x, y, r = rng.uniform(0, CW), rng.uniform(0, hz * .9), rng.uniform(.6, 1.6)
            d.ellipse((x - r, y - r, x + r, y + r), fill=(235, 240, 255, int(rng.uniform(90, 230))))
    return img


def _ridge(CW, CH, rng, base, amp, col_top, col_bot, snow=False):
    x = np.linspace(0, 1, CW)
    h = sum((.5 ** i) * np.sin(2 * math.pi * 1.3 * 2 ** i * x + rng.uniform(0, 6.28)) for i in range(6))
    prof = base - amp * (h - h.min()) / (h.max() - h.min() + 1e-6)
    mask = Image.new("L", (CW, CH), 0)
    ImageDraw.Draw(mask).polygon([(0, CH)] + [(i, float(prof[i])) for i in range(0, CW, 2)] + [(CW, float(prof[-1])), (CW, CH)], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(.7))
    top_y = base - amp
    t = np.clip((np.arange(CH) - top_y) / max(1, CH - top_y), 0, 1)[:, None, None].astype(np.float32)
    arr = np.array(col_top, np.float32) * (1 - t) + np.array(col_bot, np.float32) * t
    if snow:
        s = np.clip(1 - (np.arange(CH) - top_y) / (amp * .35), 0, 1)[:, None, None] * .55
        arr = arr * (1 - s) + np.array((235, 240, 250), np.float32) * s
    arr = np.repeat(arr, CW, axis=1)
    layer = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    layer.paste(_arr_img(arr), mask=mask)
    return layer, prof


def _decor(layer, loc, prof, rng, col, night, S):
    d = ImageDraw.Draw(layer)
    CW = layer.width
    col = tuple(int(c) for c in col) + (255,)
    if loc == "forest":
        x = 0
        while x < CW:
            y, hh = float(prof[min(x, CW - 1)]), rng.uniform(55, 135) * S
            for i in range(3):
                ty = y - hh + i * hh * .28
                hw = hh * (.16 + .07 * i)
                d.polygon([(x, ty), (x - hw, ty + hh * .42), (x + hw, ty + hh * .42)], fill=col)
            d.rectangle((x - 2, y - hh * .1, x + 2, y + 8), fill=col)
            x += int(rng.uniform(14, 34) * S)
    elif loc == "village":
        x = int(40 * S)
        while x < CW - 100:
            y, bw, bh = float(prof[x]), rng.uniform(46, 92) * S, rng.uniform(34, 66) * S
            d.rectangle((x, y - bh, x + bw, y + 8), fill=col)
            d.polygon([(x - 7, y - bh), (x + bw / 2, y - bh - bw * .36), (x + bw + 7, y - bh)], fill=col)
            lit = (255, 196, 110, 255) if night or rng.random() < .25 else (60, 54, 52, 255)
            for k in range(int(rng.integers(1, 4))):
                wx = x + bw * (.15 + .3 * k)
                d.rectangle((wx, y - bh * .6, wx + bw * .12, y - bh * .3), fill=lit)
            x += int(bw + rng.uniform(30, 110) * S)
    elif loc == "battlefield":
        x = int(30 * S)
        while x < CW - 80:
            y, w = float(prof[x]), rng.uniform(40, 110) * S
            pts, cx = [(x, y + 8)], x
            while cx < x + w:
                pts.append((cx, y - rng.uniform(10, 70) * S)); cx += rng.uniform(8, 22) * S
            pts += [(x + w, y - 6 * S), (x + w, y + 8)]
            d.polygon(pts, fill=col)
            x += int(w + rng.uniform(80, 220) * S)


def _glow(CW, CH, cx, cy, rx, ry, color, strength):
    yy, xx = np.mgrid[0:CH, 0:CW].astype(np.float32)
    g = np.exp(-(((xx - cx) ** 2) / (2 * rx * rx) + ((yy - cy) ** 2) / (2 * ry * ry)))
    a = np.zeros((CH, CW, 4), np.float32)
    a[..., :3] = color
    a[..., 3] = g * 255 * strength
    return _arr_img(a)


def _smoke(CW, CH, rng, hz):
    n = fbm(CW // 3, CH // 3, rng, 5, 3)
    n = np.asarray(Image.fromarray((n * 255).astype(np.uint8)).resize((CW, CH), Image.BICUBIC), np.float32) / 255
    yy, xx = np.mgrid[0:CH, 0:CW].astype(np.float32)
    cols = sum(np.exp(-((xx - CW * rng.uniform(.15, .85)) ** 2) / (2 * (CW * .07) ** 2)) for _ in range(3))
    vert = np.clip(1 - np.abs(yy - hz * .75) / (CH * .55), 0, 1)
    a = np.zeros((CH, CW, 4), np.float32)
    a[..., :3] = (62, 62, 70)
    a[..., 3] = np.clip((n - .38) * 2.4, 0, 1) * np.clip(cols, 0, 1) * vert * 190
    return _arr_img(a)


def _water(CW, CH, sky, hz, rng):
    rows = CH - hz
    src = np.asarray(sky, np.float32)[:, :, :3]
    refl = src[max(0, hz - rows):hz][::-1]
    if refl.shape[0] < rows:
        refl = np.pad(refl, ((0, rows - refl.shape[0]), (0, 0), (0, 0)), mode="edge")
    yy = np.arange(rows)[:, None]
    shift = (np.sin(yy * .35 + rng.uniform(0, 6)) * (2 + yy * .04)).astype(int)
    idx = (np.arange(CW)[None, :] + shift) % CW
    refl = np.take_along_axis(refl, idx[..., None].repeat(3, 2), axis=1)
    refl = refl * .62 + np.array((8, 26, 40), np.float32) * .38
    out = np.zeros((CH, CW, 4), np.float32)
    out[hz:, :, :3], out[hz:, :, 3] = refl, 255
    return _arr_img(out)


def _interior(CW, CH, pal, rng, accent):
    a = np.repeat((np.linspace(0, 1, CH, dtype=np.float32)[:, None, None] * np.array((30, 20, 14), np.float32)
                   + np.array((16, 12, 12), np.float32)), CW, axis=1)
    bg = _arr_img(a)
    d = ImageDraw.Draw(bg)
    wx, wy, ww, wh = CW * .58, CH * .12, CW * .16, CH * .46
    d.rectangle((wx, wy, wx + ww, wy + wh), fill=tuple(int(c) for c in pal[1]) + (255,))
    for k in (1, 2):
        d.line((wx + ww * k / 3, wy, wx + ww * k / 3, wy + wh), fill=(14, 12, 14, 255), width=5)
    d.line((wx, wy + wh / 2, wx + ww, wy + wh / 2), fill=(14, 12, 14, 255), width=5)
    for x in (CW * .12, CW * .86):
        d.rectangle((x, 0, x + CW * .05, CH), fill=(10, 8, 9, 255))
    d.rectangle((0, CH * .8, CW, CH), fill=(12, 9, 8, 255))
    shaft = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    ImageDraw.Draw(shaft).polygon([(wx, wy + wh), (wx + ww, wy + wh), (CW * .5, CH * .95), (CW * .22, CH * .95)],
                                  fill=tuple(int(c) for c in mix(pal[1], (255, 255, 255), .3)) + (70,))
    return bg, shaft.filter(ImageFilter.GaussianBlur(18))


def _cover(img, w, h):
    s = max(w / img.width, h / img.height)
    img = img.resize((int(img.width * s) + 1, int(img.height * s) + 1), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def build_layers(shot, W, H, rng):
    CW, CH = int(W * 1.4), int(H * 1.25)
    S = H / 540
    plate = shot.get("plate")
    if plate and os.path.isfile(plate):
        return [(_cover(Image.open(plate).convert("RGB"), CW, CH).convert("RGBA"), .5)], True
    tod, loc, emo = shot.get("time_of_day", "morning"), shot.get("location", "landscape"), shot.get("emotion", "determined")
    pal, night = SKY.get(tod, SKY["morning"]), tod == "night"
    accent = ACCENT.get(emo, ACCENT["determined"])
    off = int(H * .125)
    hz = int(H * .70 + off)
    if loc == "interior":
        bg, shaft = _interior(CW, CH, pal, rng, accent)
        return [(bg, .1), (shaft, .3)], False
    sky = _sky(CW, CH, pal, rng, night, hz)
    layers = [(sky, .05)]
    if loc == "battlefield":
        layers.append((_glow(CW, CH, CW * .5, hz, CW * .35, CH * .12, accent, .55), .2))
    deep = (8, 12, 24)
    specs = [(.30, hz - 18 * S, 85 * S, .18), (.55, hz + 10 * S, 70 * S, .5), (.82, H * .93 + off, 16 * S, .75)]
    if loc == "mountain":
        specs = [(.30, hz, 190 * S, .18), (.55, hz + 40 * S, 150 * S, .5), (.82, H * .95 + off, 24 * S, .75)]
    if loc == "water":
        specs = specs[:1] + [(.55, hz + 6 * S, 28 * S, .5)]
    for k, (dm, base, amp, depth) in enumerate(specs):
        c = mix(pal[1], deep, dm)
        top_c = mix(c, accent if k == 0 else pal[1], .14)
        layer, prof = _ridge(CW, CH, rng, base, amp, top_c, c, snow=(loc == "mountain" and k < 2))
        if loc in ("forest", "village", "battlefield") and k >= 1:
            _decor(layer, loc, prof, rng, c, night, S * (.8 if k == 1 else 1.25))
        layers.append((layer, depth))
        if loc == "water" and k == 0:
            layers.append((_water(CW, CH, sky, int(base), rng), .35))
    if loc in ("forest", "water", "mountain") or tod in ("dawn", "morning"):
        fog = np.zeros((CH, CW, 4), np.float32)
        fog[..., :3] = pal[1]
        fog[..., 3] = np.clip(1 - np.abs(np.arange(CH)[:, None] - hz) / (CH * .14), 0, 1) * 75
        layers.append((_arr_img(fog), .55))
    if loc == "battlefield" or "smoke" in shot.get("fx", []):
        layers.append((_smoke(CW, CH, rng, hz), .5))
    return layers, False


# --------------------------------------------------------------------------- figures
def draw_figure(img, fx, fy, hpx, phase, action, fall, col, rim, flip, gesture):
    ss = 2
    Wc, Hc = int(hpx * 1.2) * ss, int(hpx * 1.3) * ss
    h, cx, by = hpx * ss, Wc / 2, Hc - hpx * .08 * ss
    sgn = -1 if flip else 1
    A = {"walk": .42, "run": .78}.get(action, .035)
    sw = math.sin(phase) * A
    lean = .07 if action == "run" else 0
    fa = fall * 1.45 * sgn

    def T(x, y):
        x += lean * (-y - .5 if y < -.5 else 0) * 0
        xr, yr = x * math.cos(fa) - y * math.sin(fa), x * math.sin(fa) + y * math.cos(fa)
        return cx + sgn * xr * h, by + yr * h

    def seg(d, p, q, w, fill, dx, dy):
        a, b = T(*p), T(*q)
        a, b = (a[0] + dx, a[1] + dy), (b[0] + dx, b[1] + dy)
        d.line([a, b], fill=fill, width=max(2, int(w * h)))
        for e in (a, b):
            r = w * h / 2
            d.ellipse((e[0] - r, e[1] - r, e[0] + r, e[1] + r), fill=fill)

    def paint(d, fill, dx, dy):
        shoulder_x = lean
        seg(d, (0, -.5), (shoulder_x, -.82), .15, fill, dx, dy)
        hx, hy = T(shoulder_x, -.93)
        r = .068 * h
        d.ellipse((hx + dx - r, hy + dy - r, hx + dx + r, hy + dy + r), fill=fill)
        for s in (1, -1):
            ang = sw * s
            hip = (.02 * s, -.5)
            knee = (hip[0] + .25 * math.sin(ang), hip[1] + .25 * math.cos(ang))
            sa = ang * .4 - (.35 * A if s * math.cos(phase) > 0 else 0)
            foot = (knee[0] + .25 * math.sin(sa), knee[1] + .25 * math.cos(sa))
            seg(d, hip, knee, .075, fill, dx, dy)
            seg(d, knee, foot, .06, fill, dx, dy)
            seg(d, foot, (foot[0] + .05, foot[1]), .05, fill, dx, dy)
            aa = -sw * s * 1.1
            if gesture and s == 1:
                aa = -1.35 + .35 * math.sin(phase * .6)
            sh = (shoulder_x + .07 * s, -.8)
            el = (sh[0] + .17 * math.sin(aa), sh[1] + .17 * math.cos(aa))
            ha = aa - (.5 if not gesture else -.3)
            hand = (el[0] + .16 * math.sin(ha), el[1] + .16 * math.cos(ha))
            seg(d, sh, el, .05, fill, dx, dy)
            seg(d, el, hand, .042, fill, dx, dy)

    cv = Image.new("RGBA", (Wc, Hc), (0, 0, 0, 0))
    d = ImageDraw.Draw(cv, "RGBA")
    d.ellipse((cx - .22 * h, by - .02 * h, cx + .22 * h, by + .025 * h), fill=(0, 0, 0, 70))
    paint(d, tuple(rim) + (255,), -2 * ss, -1 * ss)
    paint(d, tuple(col) + (255,), 0, 0)
    small = cv.resize((Wc // ss, Hc // ss), Image.LANCZOS)
    img.alpha_composite(small, (int(fx - Wc / ss / 2), int(fy - by / ss)))


def make_texture(kind, W, H, rng, acc):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im, "RGBA")
    if kind == "paper":
        n = (fbm(W // 2, H // 2, rng, 4, 20) * 255).astype(np.uint8)
        a = np.zeros((H, W, 4), np.uint8)
        a[..., :3] = (255, 240, 210)
        a[..., 3] = np.asarray(Image.fromarray(n).resize((W, H)), np.uint8) // 9
        return Image.fromarray(a)
    if kind in ("grid", "blueprint"):
        st = max(16, W // 32)
        for x in range(0, W, st):
            d.line((x, 0, x, H), fill=(255, 255, 255, 14))
        for y in range(0, H, st):
            d.line((0, y, W, y), fill=(255, 255, 255, 14))
        if kind == "blueprint":
            for x in range(-H, W, st * 4):
                d.line((x, H, x + H, 0), fill=tuple(acc) + (22,))
    elif kind == "halftone":
        st = max(6, W // 90)
        for y in range(0, H, st):
            for x in range(0, W, st):
                r = st * .28 * (.5 + .5 * math.sin(x * .02 + y * .03))
                d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, 20))
    elif kind == "scanlines":
        for y in range(0, H, 3):
            d.line((0, y, W, y), fill=(0, 0, 0, 40))
    else:  # dust
        for _ in range(W * H // 2500):
            x, y, r = rng.uniform(0, W), rng.uniform(0, H), rng.uniform(.5, 1.8)
            d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, int(rng.uniform(40, 120))))
        for _ in range(6):
            x = rng.uniform(0, W)
            d.line((x, 0, x + rng.uniform(-6, 6), H), fill=(255, 255, 255, 26))
    return im


# --------------------------------------------------------------------------- renderer
def _fmt(v):
    return f"{v:,.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{v:,.1f}"


class DocuRenderer:
    def __init__(self, plan: dict, width: int, height: int, fps: int):
        self.plan, self.W, self.H, self.fps = plan, width, height, fps
        self.shots = plan["shots"]
        self.cache: dict[str, tuple] = {}
        self.grain = np.random.default_rng(3)
        yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
        r2 = ((xx / width - .5) ** 2 + (yy / height - .5) ** 2) * 2.2
        self.vig = np.clip(1 - .55 * r2, .35, 1)[..., None]
        self.total = sum(s["frames"] for s in self.shots)
        th = self.theme = plan.get("theme") or {}
        self.acc = tuple(th["accent"]) if th else None
        self.acc2 = tuple(th["accent2"]) if th else (255, 255, 255)
        self.shadow = np.array(th.get("shadow", (-.02, .02, .05)), np.float32)
        self.high = np.array(th.get("highlight", (.05, .02, -.04)), np.float32)
        self.style = th.get("transition", "dissolve")
        if th:
            set_theme_fonts(th["font_head"], th["font_body"])
        self.tex = make_texture(th.get("texture", "dust"), width, height, np.random.default_rng(th.get("seed", 1)),
                                self.acc or (255, 255, 255))

    # ---- helpers
    def _prep(self, shot):
        if shot["id"] not in self.cache:
            if len(self.cache) > 3:
                self.cache.pop(next(iter(self.cache)))
            rng = np.random.default_rng(abs(hash(shot["id"])) % (2 ** 32) if False else sum(map(ord, shot["id"])) * 7919)
            layers, is_plate = build_layers(shot, self.W, self.H, rng)
            n = 46
            parts = np.stack([rng.random(n), rng.random(n), rng.uniform(.4, 1.0, n), rng.random(n)], 1)
            self.cache[shot["id"]] = (layers, is_plate, parts)
        return self.cache[shot["id"]]

    def _xf(self, shot, depth, u):
        cam, W, H = shot["camera"], self.W, self.H
        e = ease_io(u)
        z = lerp(cam["zoom"][0], cam["zoom"][1], e)
        zl = 1 + (z - 1) * (.5 + .5 * depth)
        pan = lerp(cam["pan"][0], cam["pan"][1], e) * W * (.25 + .75 * depth)
        cx, cy = W * .7 + pan, H * .625 + cam.get("drift", 0) * H * e
        w, h = W / zl, H / zl
        return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)

    def _base(self, shot, u, t):
        W, H = self.W, self.H
        layers, is_plate, parts = self._prep(shot)
        base = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        for img, depth in layers:
            base.alpha_composite(img.resize((W, H), Image.BILINEAR, box=self._xf(shot, depth, u)))
        lay = shot["layout"]
        dim = {"title": .38, "timeline": .5, "quote": .5, "stat": .5, "map": .45, "chart": .55, "split": .55, "doc": .5, "flow": .5}.get(lay, 0)
        if dim:
            base.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(255 * dim))))
        if lay == "timeline":  # archival: desaturate + sepia
            g = base.convert("L").convert("RGBA")
            base = Image.blend(g, base, .35)
            base.alpha_composite(Image.new("RGBA", (W, H), (112, 70, 24, 80)))
        # silhouette actors (not on photo plates / infographic layouts)
        if not is_plate and lay == "hero" and shot.get("location") != "interior":
            box = self._xf(shot, .75, u)
            k = W / (box[2] - box[0])
            names = shot.get("characters") or ["Protagonist"]
            subj = shot.get("subject") or names[0]
            order = [subj] + [n for n in names if n != subj]
            pal = (SKY.get(shot.get("time_of_day"), SKY["morning"])[1])
            rim = ACCENT.get(shot.get("emotion"), ACCENT["determined"])
            ground = (self.H * .93 + self.H * .125 - box[1]) * k
            for j, n in enumerate(order[:3]):
                sub = j == 0
                act = shot.get("action", "observe") if sub else "observe"
                spd = 7.5 if act == "walk" else 11 if act == "run" else 1.6
                direction = shot.get("direction", 1)
                if sub and act in ("walk", "run"):
                    span = .30 if act == "walk" else .44
                    fx = W * (.5 - direction * span / 2 + direction * span * ease_io(u))
                else:
                    fx = W * (.5 + (0 if sub else (-1 if j == 1 else 1) * .17 + .02 * j))
                hp = H * (.40 if sub else .33) * (1.15 if shot.get("shot_type") in ("close_up", "medium_close") else 1)
                body = tuple(int(c * .22 + 6) for c in mix(pal, (0, 0, 0), .8 - .1 * j))
                draw_figure(base, fx, ground, hp, t * spd + j, act, ease_io((u - .35) / .65) if act == "fall" and sub else 0,
                            body, rim, direction < 0 and sub, act == "speak" and sub)
        # particles
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov, "RGBA")
        loc, emo = shot.get("location"), shot.get("emotion")
        ember = loc == "battlefield" or emo == "anger" or "smoke" in shot.get("fx", [])
        glow = ACCENT["anger"] if ember else (210, 240, 150) if shot.get("time_of_day") == "night" else (255, 238, 206)
        for px, py, sz, ph in parts:
            x = (px * W + (math.sin(t * .6 + ph * 6.28) * 18 + t * (14 if ember else 5) * sz)) % W
            y = (py * H - t * (46 if ember else 9) * sz) % H
            a = int(clamp(math.sin(t * 2 + ph * 9) * .5 + .6) * (190 if ember else 110) * sz)
            r = (1 + 2.2 * sz) * H / 540
            d.ellipse((x - r * 2.4, y - r * 2.4, x + r * 2.4, y + r * 2.4), fill=glow + (a // 5,))
            d.ellipse((x - r, y - r, x + r, y + r), fill=glow + (a,))
        base.alpha_composite(ov)
        return base.convert("RGB")

    def _grade(self, im):
        x = np.asarray(im, np.float32) / 255
        s = lambda v: 1 / (1 + np.exp(-(v - .5) * 5))
        x = (s(x) - s(0.0)) / (s(1.0) - s(0.0))
        lum = x.mean(2, keepdims=True)
        x = x + (1 - lum) ** 2 * self.shadow + lum ** 2 * self.high
        b = Image.fromarray((np.clip(x - .6, 0, 1) * 255).astype(np.uint8)).resize((self.W // 4, self.H // 4), Image.BILINEAR)
        b = np.asarray(b.filter(ImageFilter.GaussianBlur(6)).resize((self.W, self.H), Image.BILINEAR), np.float32) / 255
        x = 1 - (1 - x) * (1 - b * .6)
        x = x * self.vig + self.grain.normal(0, .011, (self.H, self.W, 1)).astype(np.float32)
        return Image.fromarray((np.clip(x, 0, 1) * 255).astype(np.uint8))

    # ---- UI
    def _text(self, d, xy, s, size, fill, anchor="la", shadow=True, role="head"):
        f = font(size, role)
        if shadow:
            d.text((xy[0] + 2, xy[1] + 2), s, font=f, fill=(0, 0, 0, int(fill[3] * .6) if len(fill) > 3 else 150), anchor=anchor)
        d.text(xy, s, font=f, fill=fill, anchor=anchor)

    def _wrap(self, s, size, maxw, role="head"):
        f, lines, cur = font(size, role), [], ""
        for w in s.split():
            if f.getlength((cur + " " + w).strip()) <= maxw:
                cur = (cur + " " + w).strip()
            else:
                lines.append(cur)
                cur = w
        return lines + ([cur] if cur else [])

    def _ui(self, shot, u, t):
        W, H = self.W, self.H
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov, "RGBA")
        acc = self.acc or ACCENT.get(shot.get("emotion"), ACCENT["determined"])
        lay = shot["layout"]
        if lay == "title":
            lines = self._wrap(shot["text"].upper(), int(H * .085), W * .8)
            y = H * .42 - len(lines) * H * .05
            for i, ln in enumerate(lines):
                a = int(255 * ease_out((t - .25 - i * .25) / .8))
                self._text(d, (W / 2, y + i * H * .11 + (1 - ease_out((t - .25 - i * .25) / .8)) * 18), ln, int(H * .085), (255, 255, 255, a), "mm")
            w = W * .22 * ease_out((t - .9) / 1.0)
            d.rectangle((W / 2 - w, H * .62, W / 2 + w, H * .62 + 4), fill=acc + (255,))
        elif lay == "stat":
            st = shot["stat"]
            pw = ease_out(t / .5)
            d.rounded_rectangle((W * .07, H * .2, W * (.07 + .86 * pw), H * .68), 18, fill=(8, 10, 18, 150), outline=acc + (140,), width=2)
            p = ease_out(t / 1.5)
            v = st["value"] * p
            txt = (f"{v:,.0f}" if st["value"] >= 100 or float(st["value"]).is_integer() else f"{v:,.1f}")
            if pw > .9:
                self._text(d, (W * .11, H * .3), txt, int(H * .2), (255, 255, 255, 255))
                self._text(d, (W * .11, H * .56), st["unit"].upper(), int(H * .05), acc + (255,))
                for i, ln in enumerate(self._wrap(st["label"], int(H * .04), W * .38)[:2]):
                    self._text(d, (W * .11, H * .61 + i * H * .05), ln, int(H * .04), (220, 224, 232, 230), shadow=False)
                heights = st["bars"]
                bx, bw = W * .56, W * .05
                for i, hv in enumerate(heights):
                    g = ease_out((t - .3 - i * .12) / .8)
                    top = H * .62 - H * .34 * hv * g
                    d.rounded_rectangle((bx + i * bw * 1.4, top, bx + i * bw * 1.4 + bw, H * .62), 5,
                                        fill=(acc + (255,)) if i == len(heights) - 1 else (255, 255, 255, 120))
                d.line((bx - 10, H * .62, bx + len(heights) * bw * 1.4, H * .62), fill=(255, 255, 255, 160), width=2)
        elif lay == "timeline":
            ys = shot["years"]
            prog = ease_io(t / 1.4)
            y0, x0, x1 = H * .5, W * .1, W * .9
            d.line((x0, y0, x0 + (x1 - x0) * prog, y0), fill=(255, 255, 255, 200), width=3)
            for i, yr in enumerate(ys):
                xi = x0 + (x1 - x0) * (i / max(1, len(ys) - 1))
                a = ease_out((t - .3 - i * .45) / .6)
                if a > 0:
                    r = 11 * a
                    d.ellipse((xi - r, y0 - r, xi + r, y0 + r), fill=acc + (255,), outline=(255, 255, 255, 255), width=3)
                    self._text(d, (xi, y0 - H * .09 * a), str(yr), int(H * .09), (255, 255, 255, int(255 * a)), "mm")
        elif lay == "quote":  # kinetic: word-by-word highlight tied to speech progress
            words = shot["quote"].split()
            p = clamp((shot["scene_t0"] + t) / max(.5, shot["scene_dur"] - .4))
            cur = min(len(words) - 1, int(p * len(words)))
            if shot.get("is_quote"):
                self._text(d, (W * .08, H * .14), "\u201c", int(H * .3), acc + (230,), shadow=False)
            f = font(H * .068)
            x0, x, y = W * .14, W * .14, H * .38
            for i, w in enumerate(words):
                wl = f.getlength(w + " ")
                if x + wl > W * .86:
                    x, y = x0, y + H * .1
                col = acc + (255,) if i == cur else (255, 255, 255, 255) if i < cur else (255, 255, 255, 70)
                lift = (1 - ease_out((p * len(words) - i) * 2)) * 10 if i <= cur else 10
                self._text(d, (x, y - 0 + lift), w, int(H * .068 * (1.1 if i == cur else 1)), col, "lm")
                x += wl
        elif lay == "map":
            a = ease_out(t / .6)
            for gx in range(0, W, int(W / 24)):
                d.line((gx, 0, gx, H), fill=(255, 255, 255, int(22 * a)))
            for gy in range(0, H, int(W / 24)):
                d.line((0, gy, W, gy), fill=(255, 255, 255, int(22 * a)))
            cx, cy = W * .5, H * .44
            for k in range(3):
                ph = ((t * .7 + k / 3) % 1)
                r = ph * H * .3
                d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=acc + (int(200 * (1 - ph) * a),), width=3)
            r = 9 * a
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=acc + (255,), outline=(255, 255, 255, 255), width=3)
            self._text(d, (cx, cy + H * .1), (shot.get("tag") or "").upper(), int(H * .07), (255, 255, 255, int(255 * a)), "mm")
        elif lay == "chart":
            c = shot["chart"]
            self._text(d, (W * .08, H * .1), c["title"].upper(), int(H * .045), acc + (255,))
            d.line((W * .08, H * .16, W * .08 + W * .25 * ease_out(t / .6), H * .16), fill=acc + (255,), width=3)
            ov.alpha_composite(self._chart(shot, t), (int(W * .08), int(H * .2)))
        elif lay == "split":
            pw = ease_out(t / .6)
            for X, side in enumerate((shot["left"], shot["right"])):
                x0 = W * (.06 + X * .47) + (-1 if X == 0 else 1) * (1 - pw) * W * .3
                col = self.acc2 if X == 0 else acc
                d.rounded_rectangle((x0, H * .2, x0 + W * .41, H * .66), 18, fill=(8, 10, 18, 160), outline=col + (190,), width=2)
                if side["value"] is not None:
                    self._text(d, (x0 + W * .205, H * .34), _fmt(side["value"] * ease_out((t - .3) / 1.3)), int(H * .13), (255, 255, 255, 255), "mm")
                for i, ln in enumerate(self._wrap(side["label"], int(H * .04), W * .36, "body")[:3]):
                    self._text(d, (x0 + W * .205, H * (.5 + i * .05)), ln, int(H * .04), col + (255,), "mm", role="body")
            r = H * .06 * ease_out((t - .2) / .5)
            d.ellipse((W / 2 - r, H * .43 - r, W / 2 + r, H * .43 + r), fill=acc + (255,))
            self._text(d, (W / 2, H * .43), "VS", int(H * .045), (10, 10, 14, 255), "mm", False)
        elif lay == "doc":
            doc = self._doc_img(shot)
            sc = lerp(.82, 1.18, ease_io(u))
            im = doc.resize((int(doc.width * sc), int(doc.height * sc)), Image.BILINEAR)
            x, y = int(W * (.5 + lerp(-.04, .04, u)) - im.width / 2), int(H * (.5 + lerp(.03, -.03, u)) - im.height / 2)
            sh = Image.new("RGBA", im.size, (0, 0, 0, 150))
            ov.paste(sh, (x + 12, y + 16), sh)
            ov.paste(im, (x, y), im)
        elif lay == "flow":
            nodes = shot["nodes"]
            n, nw, nh = len(nodes), W * .19, H * .15
            gap = (W * .84 - n * nw) / max(1, n - 1)
            for i, tx in enumerate(nodes):
                a = ease_out((t - .2 - i * .5) / .5)
                if a <= 0:
                    continue
                x0, y0 = W * .08 + i * (nw + gap), H * .4 - (1 - a) * 20
                pulse = .5 + .5 * math.sin(t * 3 + i)
                d.rounded_rectangle((x0, y0, x0 + nw, y0 + nh), 16, fill=(10, 12, 20, int(190 * a)), outline=acc + (int((120 + 100 * pulse) * a),), width=3)
                ls = self._wrap(tx, int(H * .036), nw * .88, "body")[:3]
                for k, ln in enumerate(ls):
                    self._text(d, (x0 + nw / 2, y0 + nh / 2 + (k - (len(ls) - 1) / 2) * H * .042), ln, int(H * .036), (255, 255, 255, int(255 * a)), "mm", role="body")
                if i < n - 1:
                    la = ease_out((t - .45 - i * .5) / .5)
                    xa, xb, ym = x0 + nw + 6, x0 + nw + gap - 6, y0 + nh / 2
                    d.line((xa, ym, xa + (xb - xa) * la, ym), fill=acc + (255,), width=4)
                    if la > .95:
                        d.polygon([(xb, ym), (xb - 14, ym - 9), (xb - 14, ym + 9)], fill=acc + (255,))
        if lay == "timeline":
            d.rectangle((W * .03, H * .05, W * .97, H * .95), outline=(230, 210, 170, 140), width=3)
            self._text(d, (W * .05, H * .08), "ARCHIVE FOOTAGE", int(H * .03), (230, 210, 170, 220), role="body")
        for ci, chip in enumerate(shot.get("chips") or []):
            a = ease_out((t - .3 - ci * .25) / .5)
            f = font(H * .04)
            cw = f.getlength(chip) + H * .06
            x0 = W * .95 - cw + (1 - a) * 80
            d.rounded_rectangle((x0, H * (.07 + ci * .08), x0 + cw, H * (.07 + ci * .08) + H * .065), 8, fill=(8, 10, 18, int(180 * a)), outline=acc + (int(230 * a),), width=2)
            self._text(d, (x0 + cw / 2, H * (.102 + ci * .08)), chip, int(H * .04), (255, 255, 255, int(255 * a)), "mm", False)
        # tag chip (place / year) and lower third
        if shot.get("tag") and lay in ("hero",):
            a = ease_out(t / .6) * (1 - ease_io((t - (shot["duration"] - .5)) / .5))
            f = font(H * .036)
            tw = f.getlength(shot["tag"].upper()) + H * .06
            d.rounded_rectangle((W * .05, H * .07, W * .05 + tw, H * .07 + H * .06), 8, fill=(8, 10, 18, int(170 * a)), outline=acc + (int(220 * a),), width=2)
            self._text(d, (W * .05 + H * .03, H * .1), shot["tag"].upper(), int(H * .036), (255, 255, 255, int(255 * a)), "lm", False)
        lt = shot.get("lower_third")
        if lt and lay == "hero":
            a = ease_out((t - .4) / .5) * (1 - ease_io((t - min(3.4, shot["duration"] - .3)) / .5))
            if a > 0:
                x, y = W * .05 - (1 - a) * 60, H * .72
                d.rectangle((x, y, x + 6, y + H * .1), fill=acc + (int(255 * a),))
                self._text(d, (x + 20, y + H * .01), lt["name"].upper(), int(H * .05), (255, 255, 255, int(255 * a)))
                if lt.get("role"):
                    self._text(d, (x + 20, y + H * .07), lt["role"].upper(), int(H * .028), acc + (int(255 * a),), shadow=False)
        # karaoke captions
        words = shot["text"].split() if lay != "title" else []
        if words:
            p = clamp((shot["scene_t0"] + t - .1) / max(.5, shot["scene_dur"] - .5))
            cur = min(len(words) - 1, int(p * len(words)))
            f, lines, row, rw = font(H * .043, "body"), [], [], 0
            for i, w in enumerate(words):
                wl = f.getlength(w + " ")
                if rw + wl > W * .8 and row:
                    lines.append(row); row, rw = [], 0
                row.append(i); rw += wl
            lines.append(row)
            li = next(k for k, r in enumerate(lines) if cur in r)
            vis = lines[li - li % 2: li - li % 2 + 2]
            y = H * .87 - (len(vis) - 1) * H * .026
            for r in vis:
                tw = sum(f.getlength(words[i] + " ") for i in r)
                x = W / 2 - tw / 2
                for i in r:
                    col = acc + (255,) if i == cur else (255, 255, 255, 255) if i < cur else (205, 208, 218, 170)
                    self._text(d, (x, y), words[i], int(H * .043), col, "lm", role="body")
                    x += f.getlength(words[i] + " ")
                y += H * .055
        return ov

    def _chart(self, shot, t):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        W, H, c = self.W, self.H, shot["chart"]
        if getattr(self, "_fig_key", None) != shot["id"]:
            if getattr(self, "_fig", None) is not None:
                plt.close(self._fig)
            self._fig = plt.figure(figsize=(W * .84 / 100, H * .56 / 100), dpi=100)
            self._ax, self._fig_key = self._fig.add_axes([.06, .12, .92, .8]), shot["id"]
        fig, ax = self._fig, self._ax
        ax.clear()
        fig.patch.set_alpha(0)
        ax.set_facecolor((0, 0, 0, .3))
        vals, n, p = c["values"], len(c["values"]), ease_out(t / 1.8)
        col, x = tuple(v / 255 for v in (self.acc or (255, 180, 60))), np.arange(len(c["values"]))
        if c["kind"] == "bar":
            ax.bar(x, [v * clamp(p * n - i) for i, v in enumerate(vals)], color=col, width=.6)
        else:
            xs = np.linspace(0, max(.01, p * (n - 1)), 60)
            ys = np.interp(xs, x, vals)
            ax.plot(xs, ys, color=col, lw=4, solid_capstyle="round")
            if c["kind"] == "area":
                ax.fill_between(xs, ys, color=col, alpha=.35)
            ax.scatter([xs[-1]], [ys[-1]], s=120, color="white", zorder=5)
        ax.set_xlim(-.4, n - .6)
        ax.set_ylim(min(0, min(vals)), max(vals) * 1.18 or 1)
        ax.set_xticks(x)
        ax.set_xticklabels(c["labels"])
        ax.tick_params(colors="white", labelsize=H * .03 * .72)
        ax.grid(color="white", alpha=.15)
        for sp in ax.spines.values():
            sp.set_visible(False)
        fig.canvas.draw()
        return Image.fromarray(np.asarray(fig.canvas.buffer_rgba()).copy()).convert("RGBA")

    def _doc_img(self, shot):
        if "doc:" + shot["id"] in self.cache:
            return self.cache["doc:" + shot["id"]]
        W, H, dc = self.W, self.H, shot["doc"]
        im = Image.new("RGBA", (int(W * .62), int(H * .82)), (236, 228, 208, 255))
        d = ImageDraw.Draw(im, "RGBA")
        w, h = im.size
        d.rectangle((0, 0, w, h * .1), fill=(40, 36, 30, 255))
        self._text(d, (w * .04, h * .05), dc["title"].upper(), int(H * .032), (236, 228, 208, 255), "lm", False)
        f, y = font(H * .045, "body"), h * .17
        rng = np.random.default_rng(len(dc["text"]))
        for ln in self._wrap(dc["text"], int(H * .045), w * .9, "body"):
            x = w * .05
            for wd in ln.split():
                wl = f.getlength(wd + " ")
                if dc["hl"].lower() in wd.lower():
                    d.rectangle((x - 3, y - 2, x + wl - 6, y + H * .05), fill=(255, 218, 80, 190))
                d.text((x, y), wd, font=f, fill=(30, 28, 24, 255))
                x += wl
            y += H * .062
        while y < h * .93:
            d.rectangle((w * .05, y, w * (.05 + .9 * rng.uniform(.5, 1)), y + H * .008), fill=(196, 186, 164, 255))
            y += H * .04
        self.cache["doc:" + shot["id"]] = im
        return im

    def _transit(self, a, b, p, style):
        W, H = a.size
        p = ease_io(p)
        if style == "wipe":
            m = np.clip((p * (W + 80) - np.arange(W, dtype=np.float32)[None, :]) / 80, 0, 1)
            return Image.composite(b, a, Image.fromarray((np.repeat(m, H, 0) * 255).astype(np.uint8)))
        if style == "slide":
            c = a.copy()
            c.paste(b, (int((1 - p) * W), 0))
            return c
        if style == "zoom":
            s = 1 + p * .35
            w2, h2 = int(W * s), int(H * s)
            x, y = (w2 - W) // 2, (h2 - H) // 2
            return Image.blend(a.resize((w2, h2), Image.BILINEAR).crop((x, y, x + W, y + H)), b, p)
        if style == "flash":
            w = Image.new("RGB", a.size, (255, 255, 255))
            return Image.blend(a, w, p * 2) if p < .5 else Image.blend(w, b, (p - .5) * 2)
        return Image.blend(a, b, p)

    # ---- public
    def frame_at(self, gi: int) -> Image.Image:
        acc, k = 0, 0
        for k, s in enumerate(self.shots):
            if gi < acc + s["frames"]:
                break
            acc += s["frames"]
        s = self.shots[k]
        j = gi - acc
        t, u = j / self.fps, j / max(1, s["frames"] - 1)
        img = self._grade(self._base(s, u, t))
        tf = 10 if k and self.shots[k - 1]["scene_index"] != s["scene_index"] else 5
        if k and j < tf:
            ps = self.shots[k - 1]
            pimg = self._grade(self._base(ps, 1.0, ps["duration"] + j / self.fps))
            img = self._transit(pimg, img, (j + 1) / (tf + 1), self.style)
        img = img.convert("RGBA")
        tx = ImageChops.offset(self.tex, int(gi * .6) % self.W, int(gi * .4) % self.H)
        img.alpha_composite(tx)
        img.alpha_composite(self._ui(s, u, t))
        img = img.convert("RGB")
        if gi < 12:
            img = Image.blend(Image.new("RGB", img.size), img, gi / 12)
        if gi > self.total - 19:
            img = Image.blend(Image.new("RGB", img.size), img, max(0, (self.total - 1 - gi) / 18))
        return img

    def render(self, out: str, ffmpeg: str = "ffmpeg", log=print) -> None:
        """Stream frames to FFmpeg with fast encoding and live progress/ETA.

        The previous renderer only logged after a frame had finished, making a
        costly first 1080p frame look like a frozen process. It also used x264's
        medium preset, spending excessive time encoding procedurally generated
        animation. Keep full output resolution and use a visually high-quality,
        substantially faster x264 preset.
        """
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "warning",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{self.W}x{self.H}",
               "-r", str(self.fps), "-i", "-", "-an",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
        log(f"[cinematic] renderer initialized: {self.W}x{self.H} @ {self.fps} fps; {self.total} frames")
        log("[cinematic] preparing first frame (1080p procedural composition can take a little longer)...")
        started = time.monotonic()
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        last_log = started
        completed = 0
        try:
            for i in range(self.total):
                frame = self.frame_at(i)
                if p.poll() is not None:
                    raise RuntimeError(f"FFmpeg exited early with code {p.returncode}; check the FFmpeg warning above.")
                p.stdin.write(frame.tobytes())
                completed = i + 1
                now = time.monotonic()
                # Report once per second so slow frame generation never appears frozen.
                if completed == 1 or completed % max(1, self.fps) == 0 or now - last_log >= 5:
                    elapsed = max(.001, now - started)
                    rate = completed / elapsed
                    remaining = (self.total - completed) / max(rate, .001)
                    log(f"[cinematic] rendered {completed}/{self.total} frames "
                        f"({completed / self.total * 100:.1f}%) | {rate:.2f} fps | "
                        f"elapsed {elapsed / 60:.1f} min | ETA {remaining / 60:.1f} min")
                    last_log = now
            p.stdin.close()
        except BrokenPipeError as exc:
            if p.stdin and not p.stdin.closed:
                p.stdin.close()
            code = p.wait()
            raise RuntimeError(f"FFmpeg stopped accepting frames (exit code {code}).") from exc
        except Exception:
            if p.stdin and not p.stdin.closed:
                p.stdin.close()
            p.terminate()
            p.wait()
            raise
        code = p.wait()
        if code:
            raise RuntimeError(f"FFmpeg failed while encoding the documentary video (exit code {code}).")
        log(f"[cinematic] video render complete: {completed} frames in {(time.monotonic() - started) / 60:.1f} min")
