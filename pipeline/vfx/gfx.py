"""Skia helpers: colour maths, grading, gradients, fonts, easing, grain/vignette."""
from __future__ import annotations

import functools
import math

import numpy as np
import skia

Color = tuple


def hx(h: str) -> Color:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def shade(c, k):
    return tuple(min(255, max(0, v * k)) for v in c[:3])


def col(c, a=255):
    return skia.Color(int(min(255, max(0, c[0]))), int(min(255, max(0, c[1]))), int(min(255, max(0, c[2]))),
                      int(min(255, max(0, a))))


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def ease(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def eout(t):
    return 1 - (1 - clamp(t)) ** 3


def back(t):
    t = clamp(t)
    return 1 + 2.70158 * (t - 1) ** 3 + 1.70158 * (t - 1) ** 2


class Grade:
    """Scene colour grade: every drawn colour passes through .c() so bg, people and props match."""
    TOD = {"day": ((1, 1, 1), 1.0, 1.0), "sunrise": ((1.10, .97, .86), 1.05, .98), "sunset": ((1.12, .90, .76), 1.1, .95),
           "dusk": ((.88, .86, 1.0), .95, .88), "night": ((.68, .74, .95), .9, .8)}
    MOOD = {"suspense": (.78, (.92, .98, 1.06), .95), "fear": (.7, (.9, 1.0, 1.08), .92), "mystery": (.8, (.9, .96, 1.1), .93),
            "sad": (.6, (.93, .98, 1.06), .95), "epic": (1.12, (1.06, .98, .92), 1.0), "action": (1.15, (1.05, .96, .92), 1.02),
            "anger": (1.1, (1.1, .93, .9), .97), "calm": (1.0, (1, 1, 1), 1.05), "wonder": (1.1, (1, 1.02, 1.06), 1.06)}

    def __init__(self, tod="day", mood="calm", weather="none"):
        t, s, b = self.TOD.get(tod, self.TOD["day"])
        ms, mt, mb = self.MOOD.get(mood, (1.0, (1, 1, 1), 1.0))
        self.tint = tuple(t[i] * mt[i] for i in range(3))
        self.sat = s * ms * (0.82 if weather in ("fog", "rain", "snow") else 1)
        self.bright = b * mb
        self.vig = 0.55 if mood in ("suspense", "fear", "sad", "mystery") else 0.4

    def soft(self, c):
        return mix(c[:3], self.c(c), .5)

    def c(self, c):
        g = 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2]
        return tuple(min(255, max(0, (g + (c[i] - g) * self.sat) * self.tint[i] * self.bright)) for i in range(3))


def P(c=(0, 0, 0), a=255, stroke=0, shader=None, blur=0, blend=None):
    p = skia.Paint(AntiAlias=True, Color=col(c, a))
    if shader is not None:
        p.setShader(shader)
    if stroke:
        p.setStyle(skia.Paint.kStroke_Style)
        p.setStrokeWidth(stroke)
        p.setStrokeCap(skia.Paint.kRound_Cap)
        p.setStrokeJoin(skia.Paint.kRound_Join)
    if blur:
        p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, blur))
    if blend is not None:
        p.setBlendMode(blend)
    return p


def lg(x0, y0, x1, y1, stops):
    return skia.GradientShader.MakeLinear([(x0, y0), (x1, y1)], [col(s[1], s[2] if len(s) > 2 else 255) for s in stops],
                                          [s[0] for s in stops])


def rg(cx, cy, r, stops):
    return skia.GradientShader.MakeRadial((cx, cy), max(1.0, r), [col(s[1], s[2] if len(s) > 2 else 255) for s in stops],
                                          [s[0] for s in stops])


def R(x, y, w, h):
    return skia.Rect.MakeXYWH(x, y, w, h)


@functools.lru_cache(maxsize=None)
def _face(bold):
    mgr = skia.FontMgr()
    style = skia.FontStyle.Bold() if bold else skia.FontStyle.Normal()
    for fam in ("Segoe UI", "Bahnschrift", "Arial", "Helvetica Neue", "Roboto", "Noto Sans", "DejaVu Sans", "Liberation Sans"):
        t = mgr.matchFamilyStyle(fam, style)
        if t and t.getFamilyName().lower().startswith(fam.lower()[:5]):
            return t
    return skia.Typeface.MakeDefault()


@functools.lru_cache(maxsize=256)
def font(size, bold=True):
    f = skia.Font(_face(bold), float(size))
    f.setSubpixel(True)
    return f


def tw(s, size, bold=True, sp=0):
    return font(round(size, 1), bold).measureText(s) + sp * max(0, len(s) - 1)


def text(c, s, x, y, size, color=(255, 255, 255), a=255, bold=True, align="l", sp=0, shadow=0):
    f = font(round(size, 1), bold)
    w = tw(s, size, bold, sp)
    x0 = x - (w / 2 if align == "c" else w if align == "r" else 0)

    def draw(dx, dy, paint):
        if sp:
            cx = x0
            for ch in s:
                c.drawString(ch, cx + dx, y + dy, f, paint)
                cx += f.measureText(ch) + sp
        else:
            c.drawString(s, x0 + dx, y + dy, f, paint)
    if shadow:
        draw(shadow * .5, shadow, P((0, 0, 0), a * .6, blur=shadow * .7))
    draw(0, 0, P(color, a))
    return w


def wrap(s, size, maxw, bold=True):
    lines, cur = [], ""
    for w in s.split():
        t = (cur + " " + w).strip()
        if tw(t, size, bold) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    return lines + ([cur] if cur else [])


def surface(w, h):
    return skia.Surface.MakeRaster(skia.ImageInfo.Make(int(w), int(h), skia.kRGBA_8888_ColorType, skia.kPremul_AlphaType))


def grain_images(w, h, n=3, seed=5):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        a = np.clip(rng.normal(128, 38, (h, w)), 0, 255).astype(np.uint8)
        arr = np.dstack([a, a, a, np.full_like(a, 255)])
        out.append(skia.Image.fromarray(arr, colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kPremul_AlphaType))
    return out


def vignette(c, w, h, strength=.45):
    sh_ = rg(w / 2, h / 2, math.hypot(w, h) * .55, [(0, (0, 0, 0), 0), (.55, (0, 0, 0), 0), (1, (0, 0, 0), 255 * strength)])
    c.drawRect(R(0, 0, w, h), P(shader=sh_))
