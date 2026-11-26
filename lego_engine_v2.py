#!/usr/bin/env python3
"""
LEGO MOTION ENGINE v2  -  script -> LEGO-style mp4 (football, news, politics, folk tales, anything)
  python lego_engine_v2.py script.py out.mp4 [--fast]     script.py defines SCENES (+ optional TITLE)
  python lego_engine_v2.py --demo out.mp4 [--fast]
Features: continuous path motion + walk/run/kick/celebrate/etc cycles, 16 facial expressions that
morph inside ONE shot (blink, eye-tracking of ball, lip-flap), 8 animated backgrounds with parallax
objects, props, FX (confetti/flash/burst/titles/speed-lines), camera follow/zoom/shake, scoreboard HUD,
YouTube-style captions with vector emoji, transitions, and a fully synthesized stereo soundtrack
(crowd/ambience/music bed + ~30 SFX + auto footsteps/kicks/reactions, ducked + smoothed).
"""
import math, random, subprocess, sys, os, io, wave, runpy, argparse
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageChops
from scipy.signal import butter, sosfilt
from scipy.interpolate import PchipInterpolator

W, H, FPS, SR = 1280, 720, 24, 44100
K = 1.5
FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_F = {}; _FD = None
def _find_font():
    here = os.path.dirname(os.path.abspath(__file__))
    c = [os.environ.get('LEGO_FONT', ''), os.path.join(here, 'font.ttf'), FB, '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf', '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
         'C:/Windows/Fonts/arialbd.ttf', 'C:/Windows/Fonts/arial.ttf', '/System/Library/Fonts/Supplemental/Arial Bold.ttf', '/Library/Fonts/Arial Bold.ttf']
    try:
        import matplotlib; c.append(os.path.join(matplotlib.get_data_path(), 'fonts', 'ttf', 'DejaVuSans-Bold.ttf'))
    except Exception: pass
    return next((p for p in c if p and os.path.isfile(p)), None)
def font(sz):
    """cached, even-pixel sizes, font bytes read ONCE (no open file handles), auto path search, safe fallback"""
    global _FD
    sz = int(min(600, max(6, round(sz / 2) * 2)))
    if sz not in _F:
        if _FD is None:
            p = _find_font(); _FD = open(p, 'rb').read() if p else b''
        try: _F[sz] = ImageFont.truetype(io.BytesIO(_FD), sz)
        except Exception:
            try: _F[sz] = ImageFont.load_default(sz)
            except Exception: _F[sz] = ImageFont.load_default()
    return _F[sz]
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def sm(x): x = clamp(x); return x * x * (3 - 2 * x)
def lerp(a, b, t): return a + (b - a) * t
def mixc(c1, c2, t): return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))
def shd(c, f): return tuple(int(clamp(v * f, 0, 255)) for v in c)
def rot2(x, y, a):
    c, s = math.cos(a), math.sin(a); return x * c - y * s, x * s + y * c
def seq(keys, t):
    """smoothstep-interpolated keyframes [(t,val)] (val number or tuple/array)"""
    if t <= keys[0][0]: return np.array(keys[0][1], float)
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t < t1:
            u = sm((t - t0) / (t1 - t0)) if t1 > t0 else 1
            return np.array(v0, float) + (np.array(v1, float) - np.array(v0, float)) * u
    return np.array(keys[-1][1], float)
def val(spec, u, default):
    if spec is None: return default
    if isinstance(spec, (int, float)): return float(spec)
    if isinstance(spec, tuple) and len(spec) == 2: return lerp(spec[0], spec[1], sm(u))
    return float(seq(spec, u))

# ---------------------------------------------------------------- expressions
# [brow_y, tilt, eye_open, curve, mouth_open, mouth_wide, blush, sweat, tear, anger, star, arc_eyes]
EXPR = {
 'neutral':    [0, 0, 1, .2, 0, .5, 0, 0, 0, 0, 0, 0],
 'happy':      [.3, .2, .9, .85, 0, .8, .25, 0, 0, 0, 0, 0],
 'joy':        [.7, .3, .7, 1, .9, 1, .5, 0, 0, 0, 0, 1],
 'laugh':      [.6, .2, .4, 1, 1, 1, .5, 0, .6, 0, 0, 1],
 'shock':      [1.2, .2, 1.35, -.1, .95, .25, 0, .6, 0, 0, 0, 0],
 'angry':      [-.7, -1, .75, -.8, .35, 1, 0, 0, 0, 1, 0, 0],
 'sad':        [.1, 1, .7, -.9, 0, .4, 0, 0, .3, 0, 0, 0],
 'cry':        [.3, 1, .5, -1, .9, .9, .2, 0, 1, 0, 0, 0],
 'worried':    [.6, .8, 1.1, -.4, .15, .6, 0, .8, 0, 0, 0, 0],
 'smug':       [-.1, -.4, .6, .7, 0, .9, 0, 0, 0, 0, 0, 0],
 'determined': [-.3, -.7, .85, .05, 0, .7, 0, 0, 0, 0, 0, 0],
 'tired':      [-.2, .5, .4, -.3, .1, .5, 0, .3, 0, 0, 0, 0],
 'awe':        [1, .5, 1.25, .6, .5, .4, .3, 0, 0, 0, 1, 0],
 'panic':      [1, .9, 1.4, -.5, 1, .7, 0, 1, 0, 0, 0, 0],
 'proud':      [.4, -.2, .65, .8, 0, 1, .3, 0, 0, 0, 0, 0],
 'smirk':      [-.1, -.4, .6, .7, 0, .9, 0, 0, 0, 0, 0, 0],
}
def face_at(keys, t):
    """keys [(t,name)] -> expression vector with 0.22s morph + pop overshoot"""
    if not keys: return np.array(EXPR['neutral'], float)
    i = 0
    for j, (tk, _) in enumerate(keys):
        if tk <= t: i = j
    tk, nm = keys[i]
    cur = np.array(EXPR[nm], float); base = np.array(EXPR['neutral'], float)
    prev = np.array(EXPR[keys[i - 1][1]], float) if i > 0 else base
    dt = t - tk
    v = lerp(prev, cur, sm(dt / .22)) if dt < .22 else cur
    if nm != 'neutral': v = base + (v - base) * (1 + .22 * math.exp(-6 * max(dt, 0)))
    return v
def blinkf(t, seed):
    ph = (t + seed * 1.7) % 3.4
    return abs(ph - .07) / .07 if ph < .14 else 1.0

# ---------------------------------------------------------------- cast
SKIN = {'light': (255, 213, 170), 'tan': (224, 172, 120), 'brown': (165, 110, 72), 'dark': (104, 70, 48), 'yellow': (250, 205, 40)}
CAST = {}
def char(name, shirt=(200, 30, 30), shorts=(250, 250, 250), socks=None, skin='tan', hair='short', hc=(40, 30, 25),
         num=None, outfit='kit', acc=(), size=1.0, hat=(200, 30, 30), trim=None):
    """outfit: kit | suit | dress | robe | casual.  hair: short spiky long curly bald cap bun turban crown
    acc: beard glasses tie headband gloves scarf"""
    CAST[name] = dict(name=name, shirt=shirt, shorts=shorts, socks=socks or shirt, skin=SKIN.get(skin, skin), hair=hair,
                      hc=hc, num=num, outfit=outfit, acc=list(acc), size=size, hat=hat, trim=trim or shd(shirt, .7))
    return CAST[name]
def actor(c, path, act=(), face=(), say=(), look=None, fdir=(), size=None, label=True):
    """c: CAST name. path [(t,x,y[,facing])] (ground pos; y 380..700). act [(t,'run')..]. face [(t,'shock')..]
    say [(t0,t1)] lip-flap windows. look 'ball'|'cam'|None."""
    ch = dict(CAST[c]);
    if size: ch['size'] = size
    return dict(ch=ch, path=list(path), act=list(act), face=list(face) or [(0, 'neutral')], say=list(say), look=look,
                fdir=list(fdir), label=label)

# ---------------------------------------------------------------- poses
ONE = {'kick': .55, 'header': .7, 'jump': .7, 'getup': .6, 'shrug': 1.0, 'bow': 1.0, 'wave': 1.6, 'point': 1.2}
def pose(a, ph, sp, tt, t):
    P = dict(lean=0., bob=0., gL=0., gR=0., aLa=8., aLs=0., aRa=8., aRs=0., hd=0., nod=0., rot=0., dx=0., dy=0., gap=4.)
    if a in ('idle', 'auto'):
        b = math.sin(t * 3.1); P.update(bob=b * 1.2, aLa=9 + b * 1.5, aRa=9 - b * 1.5, hd=math.sin(t * 1.3) * 1.5)
    elif a in ('move', 'walk', 'run'):
        amp = clamp(sp / 260); s = math.sin(ph)
        P.update(gL=s * (20 + 38 * amp), gR=-s * (20 + 38 * amp), aLs=-s * (26 + 42 * amp), aRs=s * (26 + 42 * amp),
                 aLa=10, aRa=10, bob=-abs(math.cos(ph)) * (2 + 9 * amp), lean=3 + 11 * amp, hd=-s * 2, gap=3)
    elif a == 'kick':
        u = clamp(tt / .55)
        P.update(gR=float(seq([(0, 0), (.35, -62), (.55, 98), (1, 0)], u)), gL=8, lean=float(seq([(0, 0), (.35, -6), (.55, 12), (1, 0)], u)),
                 aLa=55, aRa=35, aRs=-20, dx=6 * sm(u))
    elif a == 'header':
        u = clamp(tt / .7); P.update(dy=-30 * math.sin(math.pi * u), lean=float(seq([(0, -6), (.5, 12), (1, 0)], u)), nod=10 * math.sin(math.pi * u),
                                    aLa=45, aRa=45, gL=-10, gR=14)
    elif a == 'jump':
        u = clamp(tt / .7); P.update(dy=-34 * math.sin(math.pi * u), aLa=140, aRa=140, gL=8, gR=-8)
    elif a == 'celebrate':
        w = math.sin(tt * 2 * math.pi * 3)
        P.update(dy=-abs(math.sin(tt * 2 * math.pi * 1.6)) * 16, aLa=155 + 15 * w, aRa=155 - 15 * w, gL=w * 10, gR=-w * 10, lean=-4, hd=w * 6, nod=-4)
    elif a == 'cheer':
        w = math.sin(tt * 2 * math.pi * 2.5)
        P.update(dy=-abs(w) * 8, aLa=105 + 65 * max(w, 0), aRa=105 + 65 * max(-w, 0), lean=-2, hd=w * 4)
    elif a == 'sad':
        P.update(lean=10, nod=9, hd=-4, aLa=5, aRa=5, bob=math.sin(t * 2) * 1.2, gap=2)
    elif a == 'shock':
        e = math.exp(-tt * 6)
        P.update(dx=-9 * (1 - math.exp(-tt * 14)), dy=-14 * e * abs(math.sin(tt * 14)), aLa=78, aRa=78, lean=-9, hd=math.sin(t * 40) * 2.2, gL=-6, gR=8)
    elif a == 'angry':
        P.update(aLa=22, aRa=22, aLs=18, aRs=18, lean=7, bob=-abs(math.sin(tt * 2 * math.pi * 2)) * 4, hd=math.sin(t * 34) * 1.8, nod=4)
    elif a == 'talk':
        P.update(aRa=32 + 26 * math.sin(tt * 10.7), aRs=22 * math.sin(tt * 8.1), aLa=14 + 8 * math.sin(tt * 7.3 + 1), hd=3 * math.sin(tt * 6.9), bob=math.sin(tt * 6.5) * 1.4)
    elif a == 'point':
        P.update(aRa=72, aRs=45, lean=3, aLa=10)
    elif a == 'fall':
        u = clamp(tt / .3); P.update(rot=88 * sm(u), dy=10 * sm(u), aLa=120 * math.sin(tt * 9), aRa=100 * math.sin(tt * 8 + 1))
    elif a == 'getup':
        u = clamp(tt / .6); P.update(rot=88 * (1 - sm(u)), dy=10 * (1 - sm(u)))
    elif a == 'dive':
        u = clamp(tt / .35); P.update(rot=82 * sm(u), dy=-22 * math.sin(math.pi * clamp(u)), aLa=172, aRa=172, gL=14, gR=-14)
    elif a == 'shrug':
        u = clamp(tt); k = math.sin(math.pi * u); P.update(aLa=50 * k + 8, aRa=50 * k + 8, hd=9 * k, dy=-3 * k)
    elif a == 'bow':
        P.update(lean=38 * math.sin(math.pi * clamp(tt)), nod=8 * math.sin(math.pi * clamp(tt)))
    elif a == 'wave':
        P.update(aRa=158 + 20 * math.sin(tt * 18), aLa=8, hd=3 * math.sin(tt * 4))
    elif a == 'namaste':
        P.update(aLa=28, aRa=28, aLs=58, aRs=58, nod=7, lean=3)
    elif a == 'dance':
        w = math.sin(tt * 2 * math.pi * 2)
        P.update(dy=-abs(w) * 7, aLa=95 + 60 * w, aRa=95 - 60 * w, gL=w * 22, gR=-w * 22, hd=w * 9, lean=w * 5)
    elif a == 'crouch':
        P.update(dy=14, aLa=62, aRa=62, gL=-4, gR=4, gap=14, lean=6)
    elif a == 'think':
        P.update(aRa=140, aRs=30, hd=-6, nod=3, aLa=70)
    return P
def blend_pose(p0, p1, w): return {k: lerp(p0[k], p1[k], w) for k in p1}

# ---------------------------------------------------------------- renderer
_GL = {}
def glow_sprite(d):
    d = max(4, int(d))
    if d not in _GL:
        yy, xx = np.mgrid[-1:1:complex(d), -1:1:complex(d)]
        r = np.clip(1 - np.hypot(xx, yy), 0, 1)
        _GL[d] = Image.fromarray((r ** 2 * 255).astype(np.uint8), 'L')
    return _GL[d]

class Cam:
    def __init__(s, x=640, y=360, z=1.0, sx=0, sy=0): s.x, s.y, s.z, s.sx, s.sy = x, y, z, sx, sy

class R:
    def __init__(s, cam, t, sc):
        s.im = Image.new('RGB', (int(W * K), int(H * K))); s.d = ImageDraw.Draw(s.im); s.c = cam; s.t = t; s.sc = sc
    def ze(s, p): return 1 + (s.c.z - 1) * (.35 + .65 * p)
    def X(s, x, p=1.0): return ((x - (640 + (s.c.x - 640) * p)) * s.ze(p) + 640 + s.c.sx * (.4 + .6 * p)) * K
    def Y(s, y, p=1.0): return ((y - (360 + (s.c.y - 360) * p)) * s.ze(p) + 360 + s.c.sy * (.4 + .6 * p)) * K
    def Z(s, p=1.0): return s.ze(p) * K
    def rect(s, x0, y0, x1, y1, col, p=1.0):
        a, b, c, d = s.X(x0, p), s.Y(y0, p), s.X(x1, p), s.Y(y1, p); s.d.rectangle([min(a, c), min(b, d), max(a, c), max(b, d)], fill=col)
    def poly(s, pts, col, p=1.0, out=None, w=1):
        P = [(s.X(x, p), s.Y(y, p)) for x, y in pts]; s.d.polygon(P, fill=col)
        if out: s.d.line(P + [P[0]], fill=out, width=max(1, int(w * s.Z(p))))
    def ell(s, x, y, rx, ry, col, p=1.0):
        z = s.Z(p); cx, cy = s.X(x, p), s.Y(y, p); s.d.ellipse([cx - rx * z, cy - ry * z, cx + rx * z, cy + ry * z], fill=col)
    def line(s, pts, col, w, p=1.0): s.d.line([(s.X(x, p), s.Y(y, p)) for x, y in pts], fill=col, width=max(1, int(w * s.Z(p))))
    def text(s, x, y, txt, sz, col, p=1.0, anchor='mm'): s.d.text((s.X(x, p), s.Y(y, p)), txt, font=font(sz * s.Z(p)), fill=col, anchor=anchor)
    def sshade(s, x, y, rx, ry, a=90, p=1.0):
        z = s.Z(p); cx, cy = s.X(x, p), s.Y(y, p); rx *= z; ry *= z
        if rx < 1 or ry < 1: return
        b = (int(cx - rx), int(cy - ry), int(cx + rx) + 1, int(cy + ry) + 1)
        m = Image.new('L', (b[2] - b[0], b[3] - b[1]), 0); ImageDraw.Draw(m).ellipse([0, 0, b[2] - b[0] - 1, b[3] - b[1] - 1], fill=a)
        s.im.paste((0, 0, 0), b, m)
    def glow(s, x, y, r, col, a=.8, p=1.0, scr=False):
        cx, cy, rr = (x * K, y * K, r * K) if scr else (s.X(x, p), s.Y(y, p), r * s.Z(p))
        d = int(rr * 2)
        if d < 4 or d > 2400: return
        b = (int(cx - rr), int(cy - rr), int(cx - rr) + d, int(cy - rr) + d)
        x0, y0 = max(b[0], 0), max(b[1], 0); x1, y1 = min(b[2], s.im.width), min(b[3], s.im.height)
        if x1 <= x0 or y1 <= y0: return
        m = glow_sprite(d).point(lambda v: int(v * a)).crop((x0 - b[0], y0 - b[1], x1 - b[0], y1 - b[1]))
        reg = s.im.crop((x0, y0, x1, y1)); sol = Image.new('RGB', reg.size, col)
        s.im.paste(ImageChops.add(reg, Image.composite(sol, Image.new('RGB', reg.size), m)), (x0, y0))
    def panel(s, box, rad, col, a):
        x0, y0, x1, y1 = [int(v * K) for v in box]; x0 = max(x0, 0); y0 = max(y0, 0)
        m = Image.new('L', (x1 - x0, y1 - y0), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, x1 - x0 - 1, y1 - y0 - 1], radius=int(rad * K), fill=int(a))
        s.im.paste(col, (x0, y0, x1, y1), m)

# ---------------------------------------------------------------- icons (vector emoji)
def icon(R_, kind, cx, cy, r):
    d = R_.d; Y = (250, 205, 40); ol = (60, 40, 20)
    def face(eyes='dot', mouth='smile', extra=None, col=Y):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col, outline=ol, width=max(1, int(r / 12)))
        for sd in (-1, 1):
            ex, ey = cx + sd * r * .38, cy - r * .18
            if eyes == 'dot': d.ellipse([ex - r * .09, ey - r * .12, ex + r * .09, ey + r * .12], fill=ol)
            elif eyes == 'wide': d.ellipse([ex - r * .17, ey - r * .2, ex + r * .17, ey + r * .2], fill=(255, 255, 255), outline=ol); d.ellipse([ex - r * .07, ey - r * .07, ex + r * .07, ey + r * .07], fill=ol)
            elif eyes == 'arc': d.arc([ex - r * .17, ey - r * .12, ex + r * .17, ey + r * .2], 200, 340, fill=ol, width=max(1, int(r / 8)))
            elif eyes == 'angry': d.line([ex - sd * r * .22, ey - r * .26 - sd * 0, ex + sd * r * .2, ey - r * .05], fill=ol, width=max(1, int(r / 7))); d.ellipse([ex - r * .08, ey - r * .02, ex + r * .08, ey + r * .14], fill=ol)
        my = cy + r * .42
        if mouth == 'smile': d.arc([cx - r * .45, my - r * .45, cx + r * .45, my + r * .15], 20, 160, fill=ol, width=max(1, int(r / 8)))
        elif mouth == 'big': d.pieslice([cx - r * .5, my - r * .45, cx + r * .5, my + r * .35], 0, 180, fill=(120, 30, 30), outline=ol)
        elif mouth == 'o': d.ellipse([cx - r * .15, my - r * .2, cx + r * .15, my + r * .2], fill=(120, 30, 30), outline=ol)
        elif mouth == 'frown': d.arc([cx - r * .4, my - r * .1, cx + r * .4, my + r * .5], 200, 340, fill=ol, width=max(1, int(r / 8)))
        if extra == 'tear':
            for sd in (-1, 1): d.ellipse([cx + sd * r * .45 - r * .07, cy, cx + sd * r * .45 + r * .07, cy + r * .4], fill=(90, 170, 255))
    def star(x, y, rr, col):
        d.polygon([(x + rr * math.sin(i * math.pi / 4 * 1) * (1 if i % 2 == 0 else .4), y - rr * math.cos(i * math.pi / 4) * (1 if i % 2 == 0 else .4)) for i in range(8)], fill=col)
    if kind in ('joy', 'happy', 'smile'): face('dot', 'smile')
    elif kind == 'laugh': face('arc', 'big', 'tear')
    elif kind in ('shock', 'wow'): face('wide', 'o')
    elif kind == 'angry': face('angry', 'frown', col=(235, 90, 50))
    elif kind in ('sad', 'cry'): face('dot', 'frown', 'tear' if kind == 'cry' else None)
    elif kind == 'ball':
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(250, 250, 250), outline=ol, width=max(1, int(r / 10)))
        d.polygon([(cx + r * .45 * math.sin(i * 1.2566), cy - r * .45 * math.cos(i * 1.2566)) for i in range(5)], fill=(30, 30, 30))
    elif kind == 'fire':
        d.polygon([(cx, cy - r), (cx + r * .6, cy - r * .1), (cx + r * .5, cy + r * .7), (cx, cy + r), (cx - r * .5, cy + r * .7), (cx - r * .6, cy - r * .1), (cx - r * .15, cy - r * .35)], fill=(255, 120, 30))
        d.polygon([(cx, cy), (cx + r * .3, cy + r * .5), (cx, cy + r * .85), (cx - r * .3, cy + r * .5)], fill=(255, 215, 70))
    elif kind == 'trophy':
        g = (245, 190, 40); d.polygon([(cx - r * .6, cy - r * .8), (cx + r * .6, cy - r * .8), (cx + r * .45, cy + r * .1), (cx - r * .45, cy + r * .1)], fill=g, outline=ol)
        d.rectangle([cx - r * .12, cy + r * .1, cx + r * .12, cy + r * .5], fill=g); d.rectangle([cx - r * .45, cy + r * .5, cx + r * .45, cy + r * .8], fill=g, outline=ol)
        d.arc([cx - r * .95, cy - r * .7, cx - r * .35, cy - r * .1], 90, 270, fill=g, width=max(1, int(r / 8))); d.arc([cx + r * .35, cy - r * .7, cx + r * .95, cy - r * .1], 270, 90, fill=g, width=max(1, int(r / 8)))
    elif kind in ('party', 'confetti'):
        d.polygon([(cx - r * .7, cy + r * .8), (cx + r * .1, cy - r * .1), (cx + r * .4, cy + r * .5)], fill=(255, 90, 140))
        for (a, b, c) in [(.5, -.6, (80, 200, 255)), (.8, -.2, (255, 220, 60)), (.2, -.9, (120, 230, 120)), (.9, .3, (255, 120, 80))]: d.ellipse([cx + r * a - r * .09, cy + r * b - r * .09, cx + r * a + r * .09, cy + r * b + r * .09], fill=c)
    elif kind in ('star', 'sparkle'): star(cx, cy, r, (255, 215, 60))
    elif kind in ('clap', 'hands'):
        for sd in (-1, 1): d.ellipse([cx - r * .3 + sd * r * .25, cy - r * .7, cx + r * .3 + sd * r * .25, cy + r * .7], fill=Y, outline=ol)
        star(cx, cy - r * .85, r * .25, (255, 255, 255))
    elif kind in ('whistle',): d.ellipse([cx - r * .6, cy - r * .3, cx + r * .4, cy + r * .7], fill=(190, 190, 200), outline=ol); d.rectangle([cx, cy - r * .5, cx + r * .9, cy - r * .1], fill=(190, 190, 200), outline=ol)
    elif kind in ('flag',): d.line([cx - r * .6, cy - r, cx - r * .6, cy + r], fill=ol, width=max(2, int(r / 6))); d.polygon([(cx - r * .55, cy - r), (cx + r * .8, cy - r * .5), (cx - r * .55, cy)], fill=(230, 50, 50))
    elif kind in ('mic', 'news'): d.ellipse([cx - r * .35, cy - r * .9, cx + r * .35, cy - r * .1], fill=(70, 70, 80), outline=ol); d.line([cx, cy - r * .1, cx, cy + r * .8], fill=(70, 70, 80), width=max(2, int(r / 5)))
    elif kind in ('heart', 'love'): d.polygon([(cx, cy + r * .8), (cx - r * .9, cy - r * .1), (cx - r * .5, cy - r * .7), (cx, cy - r * .3), (cx + r * .5, cy - r * .7), (cx + r * .9, cy - r * .1)], fill=(235, 50, 80))
    elif kind in ('think', 'question'): face('dot', 'frown'); d.text((cx + r, cy - r), '?', font=font(r * 1.2), fill=(255, 255, 255), anchor='mm')
    elif kind == 'alert': d.polygon([(cx, cy - r), (cx + r, cy + r * .8), (cx - r, cy + r * .8)], fill=(255, 200, 30), outline=ol); d.text((cx, cy + r * .25), '!', font=font(r * 1.1), fill=ol, anchor='mm')
    else: face('dot', 'smile')

# ---------------------------------------------------------------- actor drawing
OL = (28, 24, 30)
class Rig:
    def __init__(s, r, X, Y, sc, f, P, hd):
        s.r, s.X, s.Y, s.s, s.f, s.P = r, X, Y, sc, f, P
        s.ph = math.radians(P['lean'] * f); s.rho = math.radians(P['rot']); s.hd = math.radians((P['hd'] + P['nod'] * .8) * f)
        s.k = r.Z() * sc
    def pt(s, x, y, up=True, head=False):
        if head:
            x, y = rot2(x, y + 56, s.hd); y -= 56 - s.P['nod'] * .3
        if up: x, y = rot2(x, y, s.ph)
        x, y = rot2(x, y - 56, s.rho); y += 56
        wx = s.X + (x * s.f * 0 + x + s.P['dx'] * s.f) * s.s
        wy = s.Y - 56 * s.s + (y + s.P['dy'] + s.P['bob']) * s.s
        return (s.r.X(wx), s.r.Y(wy))
    def poly(s, pts, col, up=True, head=False, out=True):
        P = [s.pt(x, y, up, head) for x, y in pts]; s.r.d.polygon(P, fill=col)
        if out: s.r.d.line(P + [P[0]], fill=OL, width=max(1, int(1.3 * s.k)))
    def circ(s, x, y, rad, col, up=True, head=False, out=True):
        cx, cy = s.pt(x, y, up, head); q = rad * s.k
        s.r.d.ellipse([cx - q, cy - q, cx + q, cy + q], fill=col, outline=OL if out else None, width=max(1, int(1.2 * s.k)))
    def line(s, pts, col, w, up=True, head=False):
        s.r.d.line([s.pt(x, y, up, head) for x, y in pts], fill=col, width=max(1, int(w * s.k)), joint='curve')
    def limb(s, p0, ab, sw, side, L, w, col, up, col2=None, split=1.0, boot=None):
        a, b = math.radians(ab), math.radians(sw)
        dx, dy = side * math.sin(a) * math.cos(b) + s.f * math.sin(b) * .55, math.cos(a) * math.cos(b)
        n = math.hypot(dx, dy) or 1; dx, dy = dx / n, dy / n
        px, py = -dy, dx
        def seg(t0, t1, c):
            q0 = (p0[0] + dx * L * t0, p0[1] + dy * L * t0); q1 = (p0[0] + dx * L * t1, p0[1] + dy * L * t1)
            s.poly([(q0[0] - px * w / 2, q0[1] - py * w / 2), (q1[0] - px * w / 2, q1[1] - py * w / 2), (q1[0] + px * w / 2, q1[1] + py * w / 2), (q0[0] + px * w / 2, q0[1] + py * w / 2)], c, up)
        seg(0, split, col)
        if col2 is not None and split < 1: seg(split, 1.0, col2)
        if boot: seg(.86, 1.0, boot)
        return (p0[0] + dx * L, p0[1] + dy * L)

def draw_hair(g, ch, head_back=False):
    st, hc = ch['hair'], ch['hc']; f = g.f
    if head_back:
        if st == 'long': g.poly([(-24, -102), (24, -102), (25, -52), (-25, -52)], hc, up=True, head=True)
        return
    if st in ('short', 'spiky', 'long', 'bun', 'curly'):
        g.poly([(-22, -78), (-23, -98), (-16, -105), (16, -105), (23, -98), (22, -78), (15, -91), (-15, -91)], hc, head=True)
    if st == 'spiky':
        for x in (-16, -6, 5, 15): g.poly([(x - 6, -103), (x + 1, -121), (x + 7, -103)], hc, head=True)
    if st == 'bun': g.circ(0, -113, 9, hc, head=True)
    if st == 'curly':
        for x in (-18, -9, 0, 9, 18): g.circ(x, -104, 8, hc, head=True)
    if st == 'cap':
        g.poly([(-23, -84), (-22, -100), (-12, -109), (12, -109), (22, -100), (23, -84)], ch['hat'], head=True)
        g.poly([(5 * f, -85), (36 * f, -85), (36 * f, -80), (5 * f, -80)], shd(ch['hat'], .8), head=True)
    if st == 'turban':
        g.poly([(-25, -80), (-26, -100), (-14, -117), (14, -117), (26, -100), (25, -80), (14, -86), (-14, -86)], ch['hat'], head=True)
        g.line([(-22, -92), (0, -100), (22, -90)], shd(ch['hat'], .7), 1.6, head=True); g.line([(-20, -100), (2, -108), (20, -100)], shd(ch['hat'], 1.2), 1.4, head=True)
        g.circ(0, -96, 3.2, (240, 200, 60), head=True)
    if st == 'crown':
        g.poly([(-17, -104), (-17, -120), (-8, -111), (0, -123), (8, -111), (17, -120), (17, -104)], (245, 195, 40), head=True)
    if st == 'bald': g.poly([(-8, -106), (8, -106), (8, -100), (-8, -100)], ch['skin'], head=True)

def draw_face(g, ch, fv, look, mt, spk, seed, t):
    brow, tilt, eo, curve, mo, mw, blush, sweat, tear, ang, star, arc = fv
    eo = eo * blinkf(t, seed); skin = ch['skin']; lx, ly = look
    mo = max(mo, spk * (.25 + .7 * abs(math.sin(mt * 31 + seed))))
    for sd in (-1, 1):
        ex, ey = sd * 10, -81
        if blush > .05: g.circ(sd * 15.5, -68, 4.6, mixc(skin, (255, 110, 130), min(blush, 1) * .75), head=True, out=False)
        if arc > .5 or eo < .22: g.line([(ex - 5.5, ey + 2.5), (ex, ey - 3), (ex + 5.5, ey + 2.5)], OL, 2.3, head=True)
        else:
            g.circ(ex, ey, 6.2, (255, 255, 255), head=True)
            ry = max(.8, eo)
            if star > .5:
                pts = [(ex + (6 if i % 2 == 0 else 2.5) * math.sin(i * math.pi / 4 + t * 3), ey - (6 if i % 2 == 0 else 2.5) * math.cos(i * math.pi / 4 + t * 3)) for i in range(8)]
                g.poly(pts, (255, 200, 40), head=True, out=False)
            else:
                g.circ(ex + lx * 2.1, ey + ly * 1.6, 3.4 * min(1, .55 + eo * .45), (25, 25, 35), head=True, out=False)
                g.circ(ex + lx * 2.1 - 1, ey + ly * 1.6 - 1.2, 1.1, (255, 255, 255), head=True, out=False)
            if eo < .95:  # eyelid
                g.poly([(ex - 7, ey - 8), (ex + 7, ey - 8), (ex + 7, ey - 6 + 12 * (1 - min(eo, 1)) * .5 - 0), (ex - 7, ey - 6 + 12 * (1 - min(eo, 1)) * .5)], skin, head=True, out=False)
        by = -93 - brow * 3.2; inn = by - tilt * 5; out_ = by + tilt * 2
        g.line([(ex + sd * 7.5, out_), (ex - sd * 6, inn)], ch['hc'] if ch['hair'] != 'bald' else (60, 45, 35), 2.8, head=True)
    my = -66; w = 7 + mw * 3.5
    if mo < .1:
        pts = [(x, my + curve * 4 * (1 - (x / w) ** 2) - curve * 1.2 - (abs(x) / w) ** 3 * curve * 2) for x in np.linspace(-w, w, 9)]
        g.line(pts, OL, 2.2, head=True)
    else:
        mh = 2 + mo * 9
        if curve > .3:
            pts = [(-w, my - 1.5)] + [(x, my - 1.5 + mh * 1.2 * (1 - (x / w) ** 2)) for x in np.linspace(-w, w, 9)] + [(w, my - 1.5)]
            g.poly(pts, (120, 30, 40), head=True); g.poly([(-w * .85, my - 1.2), (w * .85, my - 1.2), (w * .85, my + 2.4), (-w * .85, my + 2.4)], (255, 255, 255), head=True, out=False)
            if mo > .5: g.circ(0, my + mh * .8, 3.6, (235, 110, 120), head=True, out=False)
        elif curve < -.2:
            pts = [(x, my + mh * .6 - mh * 1.0 * (1 - (x / w) ** 2)) for x in np.linspace(-w * .8, w * .8, 9)] + [(w * .8, my + mh * .6), (-w * .8, my + mh * .6)]
            g.poly(pts, (120, 30, 40), head=True)
        else: g.circ(0, my + mh * .3, max(2.5, w * .42 * (.6 + mo * .5)), (120, 30, 40), head=True)
    if sweat > .2:
        o = (mt * 14) % 12; g.poly([(19, -92 + o), (21.5, -87 + o), (19, -83.5 + o), (16.5, -87 + o)], (120, 190, 255), head=True, out=False)
    if tear > .2:
        for sd in (-1, 1):
            o = (mt * 22 + sd * 3) % 14; g.line([(sd * 11, -77), (sd * 12.5, -70 + o * .4)], (110, 180, 255), 2.4, head=True); g.circ(sd * 12.5, -68 + o, 2.2, (110, 180, 255), head=True, out=False)
    if ang > .5:
        p = 1 + .25 * math.sin(t * 22)
        for (vx, vy) in ((15, -98), (-15, -98)):
            g.line([(vx - 2 * p, vy), (vx, vy + 2 * p)], (225, 40, 40), 1.8, head=True); g.line([(vx, vy - 3 * p), (vx + 3 * p, vy)], (225, 40, 40), 1.8, head=True)

def draw_actor(r, ch, X, Y, f, P, fv, look, mt, spk, seed, t, label_a=0):
    s = (0.55 + clamp((Y - 380) / 340) * .75) * ch['size']
    g = Rig(r, X, Y, s, f, P, 0); skin, shirt, o = ch['skin'], ch['shirt'], ch['outfit']
    legc = {'kit': ch['shorts'], 'suit': (45, 45, 60), 'casual': (60, 80, 140), 'dress': ch['shirt'], 'robe': ch['shirt']}[o]
    sockc = ch['socks'] if o == 'kit' else (legc if o != 'robe' else skin)
    boot = (25, 25, 30)
    draw_hair(g, ch, True)
    # legs
    for side, sw in ((-1, P['gL']), (1, P['gR'])):
        g.limb((side * 9, 8), P['gap'], sw, side, 50, 17, legc, False, sockc if o == 'kit' else (legc if o != 'robe' else skin), .42 if o == 'kit' else 1.0, boot)
    if o in ('dress', 'robe'): g.poly([(-20, 6), (20, 6), (27, 40), (-27, 40)], ch['shirt'], False)
    g.poly([(-19, 0), (19, 0), (20, 14), (-20, 14)], legc if o != 'dress' else shd(ch['shirt'], .9), False)
    # torso
    tc = shirt if o != 'suit' else (45, 45, 60)
    g.poly([(-20, -50), (20, -50), (24, 0), (-24, 0)], tc)
    if o == 'kit':
        g.poly([(-6, -50), (6, -50), (0, -43)], skin); g.line([(-24, -4), (24, -4)], ch['trim'], 3)
        if ch['num'] is not None:
            cx, cy = g.pt(0, -26); r.d.text((cx, cy), str(ch['num']), font=font(22 * g.k), fill=shd(ch['shorts'], 1.0), anchor='mm')
    if o == 'suit':
        g.poly([(-7, -50), (7, -50), (0, -20)], (245, 245, 245), out=False); g.line([(-7, -50), (0, -20), (7, -50)], OL, 1.2)
        if 'tie' in ch['acc'] or True: g.poly([(-3, -48), (3, -48), (4, -24), (0, -18), (-4, -24)], ch['trim'] if ch['trim'] != shd(shirt, .7) else (200, 40, 50))
    if o in ('casual', 'robe', 'dress'): g.poly([(-7, -50), (7, -50), (0, -42)], skin)
    if o == 'robe': g.line([(-22, -4), (22, -22)], (240, 200, 60), 5)
    if 'scarf' in ch['acc']: g.poly([(-17, -52), (17, -52), (17, -44), (-17, -44)], (230, 230, 240)); g.line([(-17, -48), (17, -48)], ch['shirt'], 2)
    # arms
    for side, ab, sw in ((-1, P['aLa'], P['aLs']), (1, P['aRa'], P['aRs'])):
        sl = ch['outfit'] in ('suit', 'robe', 'casual')
        e = g.limb((side * 24, -44), ab, sw, side, 38, 13, tc if o != 'casual' else shirt, True, skin if not sl else tc, .45 if not sl else 1.0)
        g.circ(e[0], e[1], 7.2 if 'gloves' not in ch['acc'] else 8.5, skin if 'gloves' not in ch['acc'] else (60, 200, 90), True)
    # head
    g.poly([(-6, -60), (6, -60), (6, -52), (-6, -52)], skin, out=False)
    g.poly([(-21, -98), (-19, -100), (19, -100), (21, -98), (21, -58), (19, -56), (-19, -56), (-21, -58)], skin, head=True)
    g.line([(20, -97), (20, -59)], shd(skin, .85), 3, head=True)
    if ch['hair'] in ('bald', 'cap') or True:
        if ch['hair'] == 'bald': pass
    draw_face(g, ch, fv, look, mt, spk, seed, t)
    draw_hair(g, ch)
    if 'beard' in ch['acc']: g.poly([(-20, -76), (-21, -60), (-14, -54), (14, -54), (21, -60), (20, -76), (13, -66), (0, -70), (-13, -66)], ch['hc'], head=True)
    if 'glasses' in ch['acc']:
        for sd in (-1, 1): g.circ(sd * 10, -81, 7.5, (255, 255, 255), head=True, out=True) if False else g.line([(sd * 10 - 7.5, -81), (sd * 10 - 3, -87), (sd * 10 + 3, -87), (sd * 10 + 7.5, -81), (sd * 10 + 3, -75), (sd * 10 - 3, -75), (sd * 10 - 7.5, -81)], (30, 30, 40), 1.6, head=True)
        g.line([(-3, -82), (3, -82)], (30, 30, 40), 1.6, head=True)
    if 'headband' in ch['acc']: g.poly([(-22, -92), (22, -92), (22, -87), (-22, -87)], ch['trim'], head=True)
    if ch['hair'] not in ('bald',) and False: pass
    if ch['hair'] == 'bald' or True: pass
    return s

# ---------------------------------------------------------------- props
def draw_prop(r, kind, X, Y, z, size, t, spin=0.0, col=(230, 50, 50), txt=''):
    k = r.Z() * size * (0.55 + clamp((Y - 380) / 340) * .75)
    cx, cy = r.X(X), r.Y(Y) - z * k; d = r.d
    if z > 1 or kind == 'ball': r.sshade(X, Y + 2, 11 * size * (0.55 + clamp((Y - 380) / 340) * .75) * max(.35, 1 - z / 260), 4 * size * (0.55 + clamp((Y - 380) / 340) * .75), 80)
    if kind == 'ball':
        q = 11 * k; cy -= q; d.ellipse([cx - q, cy - q, cx + q, cy + q], fill=(250, 250, 250), outline=OL, width=max(1, int(k * 1.2)))
        for i in range(3):
            a = spin + i * 2.094; px, py = cx + q * .55 * math.cos(a), cy + q * .55 * math.sin(a) * .8; rr = q * .3
            d.polygon([(px + rr * math.cos(j * 1.2566 + a), py + rr * math.sin(j * 1.2566 + a)) for j in range(5)], fill=(30, 30, 35))
    elif kind == 'trophy':
        g = (245, 195, 40); q = k * 14
        d.polygon([(cx - q, cy - 5 * q), (cx + q, cy - 5 * q), (cx + .7 * q, cy - 2 * q), (cx - .7 * q, cy - 2 * q)], fill=g, outline=OL)
        d.rectangle([cx - .25 * q, cy - 2 * q, cx + .25 * q, cy - q], fill=g); d.rectangle([cx - .7 * q, cy - q, cx + .7 * q, cy], fill=(60, 60, 70), outline=OL)
        r.glow(cx / K, (cy - 3 * q) / K, 40 * size, (255, 220, 120), .35 + .15 * math.sin(t * 6), scr=True)
    elif kind == 'flag':
        d.line([cx, cy, cx, cy - 70 * k], fill=(90, 70, 50), width=max(2, int(2.5 * k)))
        for i in range(10):
            x0 = cx + i * 4.2 * k; w0 = math.sin(t * 7 - i * .6) * 3 * k
            d.rectangle([x0, cy - 70 * k + w0, x0 + 4.4 * k, cy - 70 * k + 34 * k + w0], fill=col if i % 4 < 2 else (245, 245, 245))
    elif kind == 'mic':
        d.line([cx, cy, cx, cy - 22 * k], fill=(50, 50, 55), width=max(2, int(4 * k))); d.ellipse([cx - 7 * k, cy - 36 * k, cx + 7 * k, cy - 20 * k], fill=(70, 70, 80), outline=OL)
    elif kind == 'balloon':
        d.line([cx, cy, cx + math.sin(t * 2) * 6 * k, cy + 40 * k], fill=(120, 120, 120), width=max(1, int(k))); d.ellipse([cx - 14 * k, cy - 36 * k, cx + 14 * k, cy], fill=col, outline=OL)
    elif kind == 'sign':
        d.rectangle([cx - 2 * k, cy - 60 * k, cx + 2 * k, cy], fill=(110, 80, 50)); d.rectangle([cx - 40 * k, cy - 90 * k, cx + 40 * k, cy - 55 * k], fill=(250, 250, 245), outline=OL)
        d.text((cx, cy - 72 * k), txt, font=font(15 * k), fill=(30, 30, 40), anchor='mm')
    elif kind == 'cone':
        d.polygon([(cx - 10 * k, cy), (cx + 10 * k, cy), (cx, cy - 26 * k)], fill=(255, 140, 30), outline=OL); d.rectangle([cx - 12 * k, cy - 2 * k, cx + 12 * k, cy + 2 * k], fill=(255, 140, 30))
    elif kind == 'paper':
        d.polygon([(cx - 14 * k, cy - 18 * k), (cx + 14 * k, cy - 22 * k), (cx + 16 * k, cy + 4 * k), (cx - 12 * k, cy + 8 * k)], fill=(248, 248, 240), outline=OL)
        for i in range(4): d.line([cx - 9 * k, cy - 12 * k + i * 5 * k, cx + 10 * k, cy - 15 * k + i * 5 * k], fill=(110, 110, 120), width=max(1, int(k)))
    elif kind == 'star':
        q = 14 * k; d.polygon([(cx + q * (1 if i % 2 == 0 else .45) * math.sin(i * .6283 + t * 2), cy - q * (1 if i % 2 == 0 else .45) * math.cos(i * .6283 + t * 2)) for i in range(10)], fill=(255, 215, 60), outline=OL)

# ---------------------------------------------------------------- backgrounds
_SKY = {}
def sky(r, top, bot, y1):
    key = (top, bot, int(y1 * K))
    if key not in _SKY:
        h = max(2, int(y1 * K)); a = np.linspace(0, 1, h)[:, None, None]
        arr = (np.array(top) * (1 - a) + np.array(bot) * a).astype(np.uint8)
        _SKY[key] = Image.fromarray(np.repeat(arr, int(W * K), axis=1))
    r.im.paste(_SKY[key], (0, 0))
def rnd(i, n=0): return random.Random(i * 7919 + n).random()
def clouds(r, t, p, y0, n=6, col=(255, 255, 255), spd=6):
    for i in range(n):
        x = (rnd(i, 1) * 2600 - 500 + t * spd * (.6 + rnd(i, 2))) % 2600 - 600; y = y0 + rnd(i, 3) * 90; s = .7 + rnd(i, 4) * .8
        for dx, dy, rx in ((0, 0, 46), (38, 8, 34), (-38, 10, 32), (14, -14, 34)): r.ell(x + dx * s, y + dy * s, rx * s, rx * .55 * s, col, p)
def birds(r, t, p, n=4, y0=120):
    for i in range(n):
        x = (rnd(i, 5) * 1800 + t * (40 + 20 * rnd(i, 6))) % 1900 - 300; y = y0 + rnd(i, 7) * 90 + math.sin(t * 1.5 + i) * 10; fl = math.sin(t * 11 + i * 2) * 6
        r.line([(x - 12, y - fl), (x, y), (x + 12, y - fl)], (40, 40, 50), 2.2, p)
def flag_wave(r, x, y, w, h, cols, t, p=1.0, vert=False, pole=True):
    if pole: r.line([(x, y - 6), (x, y + h * 3.2)], (90, 80, 70), 3, p)
    n = 12
    for i in range(n):
        x0 = x + i * w / n; wv = math.sin(t * 6 - i * .55) * (2 + i * .35)
        c = cols[int(i / n * len(cols))] if vert else cols[min(int((1.0) * len(cols) * 0, len(cols) - 1)) if False else 0]
        if vert: r.rect(x0, y + wv, x0 + w / n + 1, y + h + wv, c, p)
        else:
            m = len(cols)
            for j, cc in enumerate(cols): r.rect(x0, y + wv + j * h / m, x0 + w / n + 1, y + wv + (j + 1) * h / m, cc, p)
def crowd(r, t, exc, night, y_top, rows, x_lo, x_hi, step=24, p=.55):
    pal = [(220, 40, 40), (240, 240, 240), (60, 100, 220), (250, 200, 40), (50, 170, 90), (230, 120, 40), (150, 60, 170), (30, 30, 40)]
    for rw in range(rows):
        y = y_top + rw * 23
        for i in range(int(x_lo // step), int(x_hi // step)):
            x = i * step + (rw % 2) * step / 2
            sx = r.X(x, p)
            if sx < -30 or sx > W * K + 30: continue
            q = rnd(i + rw * 977); c = pal[int(q * len(pal))]
            bob = abs(math.sin(t * (3 + q * 4) + q * 20)) * (2 + exc * 9)
            up = exc > .45 and q > .45
            r.rect(x - 7, y - bob + 3, x + 7, y + 13, shd(c, .6 if night else 1), p)
            r.ell(x, y - bob - 1, 5.5, 5.5, (235, 190, 150) if q > .5 else (160, 110, 80), p)
            if up: r.line([(x - 6, y - bob + 4), (x - 11, y - bob - 12 - 4 * math.sin(t * 8 + q * 9))], shd(c, .8), 3, p); r.line([(x + 6, y - bob + 4), (x + 11, y - bob - 12 + 4 * math.sin(t * 8 + q * 9))], shd(c, .8), 3, p)
            if night and q > .93 and math.sin(t * 9 + q * 50) > .92: r.glow(x, y - 10, 22, (255, 255, 255), .9, p)

def bg_stadium(r, t, o):
    night = o.get('night', False); exc = o.get('exc', .4)
    sky(r, (8, 14, 40) if night else (80, 150, 235), (42, 52, 100) if night else (190, 225, 250), 330)
    if not night: clouds(r, t, .12, 40, 5); birds(r, t, .18, 3, 90)
    else:
        for i in range(60): r.ell(rnd(i, 1) * 2400 - 300, rnd(i, 2) * 150, 1.3, 1.3, (255, 255, 255), .05)
    # skyline silhouette
    for i in range(24):
        x = i * 110 - 400; h = 50 + rnd(i, 9) * 90; r.rect(x, 230 - h, x + 100, 300, (28, 36, 64) if night else (120, 150, 190), .25)
        if night:
            for wy in range(int(230 - h) + 8, 296, 14):
                for wx in range(int(x) + 8, int(x) + 96, 18):
                    if rnd(wx, wy) > .55: r.rect(wx, wy, wx + 7, wy + 7, (255, 220, 120), .25)
    # stands
    r.rect(-900, 118, 2300, 352, (58, 58, 78) if night else (150, 150, 165), .55)
    for i in range(7): r.line([(-900, 140 + i * 23), (2300, 140 + i * 23)], (40, 40, 58) if night else (120, 120, 140), 2, .55)
    crowd(r, t, exc, night, 140, 8, -300, 1900, 24, .55)
    r.rect(-900, 100, 2300, 118, (35, 40, 60) if night else (95, 100, 120), .55)
    for x in (-250, 420, 1100, 1800):  # floodlight towers
        r.rect(x - 5, 20, x + 5, 330, (70, 70, 80), .45); r.rect(x - 52, 4, x + 52, 52, (50, 52, 62), .45)
        for a in range(5):
            for b in range(2): r.rect(x - 46 + a * 20, 8 + b * 20, x - 32 + a * 20, 22 + b * 20, (255, 255, 235), .45)
        if night: r.glow(x, 30, 190, (255, 250, 220), .55 + .08 * math.sin(t * 3 + x), .45)
    # ad boards
    words = ['GOAL', 'LIVE', 'PLAY', 'FANS', 'MATCH', 'LEGO FC', 'FOOTBALL']
    r.rect(-900, 346, 2300, 380, (20, 22, 30), .85)
    for i in range(-6, 22):
        x = i * 150 - (t * 70) % 150
        cs = [(220, 40, 40), (40, 110, 230), (250, 200, 30), (40, 170, 100)]
        r.rect(x + 2, 349, x + 146, 377, cs[i % 4], .85); r.text(x + 74, 363, words[i % len(words)], 19, (255, 255, 255), .85)
    # pitch
    gy = 380; r.rect(-900, gy, 2300, 900, (44, 140, 62), 1)
    for k in range(14):
        y0 = gy + (k ** 1.35) * 9; y1 = gy + ((k + 1) ** 1.35) * 9
        if k % 2 == 0: r.rect(-900, y0, 2300, y1, (52, 156, 70), 1)
    wl = (235, 245, 235)
    r.line([(640, gy), (640, 800)], wl, 4); r.d.arc([r.X(480), r.Y(520), r.X(800), r.Y(700)], 0, 360, fill=wl, width=int(4 * r.Z()))
    for gx, sd in ((100, 1), (1180, -1)):
        r.line([(gx - 60 * sd, 410), (gx + 300 * sd, 410), (gx + 380 * sd, 700), (gx - 20 * sd, 700)], wl, 4)
        r.line([(gx, 410), (gx + 150 * sd, 410), (gx + 190 * sd, 560), (gx + 20 * sd, 560)], wl, 3)
    if o.get('goals', True):
        for gx, sd in ((90, 1), (1190, -1)):
            for i in range(0, 13): r.line([(gx - 8 * sd + i * 1, 395), (gx + 22 * sd + i * 1, 520)], (230, 230, 230), 1, 1) if False else None
            r.rect(gx - 6, 330, gx + 6, 470, (250, 250, 250)); r.rect(gx - 6, 330, gx + 150 * sd if sd > 0 else gx - 150, 344, (250, 250, 250))
            for i in range(1, 9): r.line([(gx + sd * i * 18, 344), (gx + sd * i * 18 + sd * 20, 470)], (215, 215, 220), 1)
            for j in range(1, 5): r.line([(gx, 344 + j * 28), (gx + sd * 150, 344 + j * 28 + 20)], (215, 215, 220), 1)
def bg_tunnel(r, t, o):
    r.rect(-100, -100, 1400, 800, (22, 24, 32), 0)
    vp = (640, 330)
    r.poly([(-300, -200), (1580, -200), (760, 290), (520, 290)], (38, 40, 52), .3)
    r.poly([(-300, 900), (1580, 900), (760, 400), (520, 400)], (58, 58, 70), .3)
    r.poly([(-300, -200), (520, 290), (520, 400), (-300, 900)], (46, 48, 60), .3); r.poly([(1580, -200), (760, 290), (760, 400), (1580, 900)], (46, 48, 60), .3)
    for i in range(10):
        u = i / 10; w = lerp(500, 40, u ** .6); y = lerp(-40, 280, u ** .6); fl = .7 + .3 * math.sin(t * 9 + i * 1.7)
        r.rect(640 - w / 2, y, 640 + w / 2, y + lerp(18, 4, u), mixc((20, 20, 20), (255, 245, 220), fl), .3)
    r.rect(520, 290, 760, 400, (255, 255, 240), .3); r.glow(640, 345, 260, (255, 250, 220), .7 + .1 * math.sin(t * 5), .3)
    for i in range(30): r.ell((i * 97 + t * 14) % 1400 - 60, (i * 53) % 700, 1.6, 1.6, (200, 200, 210), .6)
    r.rect(-900, 520, 2300, 900, (50, 52, 64), .9)
    for i in range(-5, 12): r.line([(i * 140 - (t * 20) % 140, 520), (i * 140 - 300 - (t * 20) % 140, 800)], (70, 72, 86), 3, .9)
def bg_city(r, t, o):
    mode = o.get('time', 'day')
    top, bot = {'day': ((95, 170, 240), (200, 230, 250)), 'dusk': ((70, 60, 120), (255, 150, 90)), 'night': ((8, 12, 34), (40, 46, 90))}[mode]
    sky(r, top, bot, 420)
    if mode == 'day': r.ell(1020, 110, 46, 46, (255, 240, 150), .05); r.glow(1020, 110, 130, (255, 235, 150), .5, .05); clouds(r, t, .1, 50, 6); birds(r, t, .15, 4, 120)
    elif mode == 'dusk': r.ell(900, 330, 60, 60, (255, 200, 120), .05); r.glow(900, 330, 190, (255, 170, 100), .6, .05); clouds(r, t, .1, 100, 4, (255, 190, 170))
    else:
        r.ell(1000, 100, 34, 34, (240, 240, 225), .05); r.glow(1000, 100, 120, (200, 210, 255), .5, .05)
        for i in range(70): r.ell(rnd(i, 1) * 2600 - 400, rnd(i, 2) * 260, 1.2, 1.2, (255, 255, 255), .05)
    for layer, (p, base, hmin, hmax, col) in enumerate([(.25, 400, 90, 230, (70, 80, 120)), (.5, 420, 120, 300, (50, 58, 90))]):
        if mode == 'day': col = shd(col, 1.7)
        for i in range(-3, 28):
            x = i * 130 + rnd(i, layer) * 20; h = hmin + rnd(i, layer + 4) * (hmax - hmin); w = 110
            r.rect(x, base - h, x + w, base + 40, shd(col, .9 + .2 * rnd(i, 3)), p)
            for wy in range(int(base - h) + 10, base + 20, 20):
                for wx in range(int(x) + 10, int(x) + w - 10, 22):
                    on = rnd(wx * 13 + wy, layer) > .5
                    c = (255, 225, 130) if (mode != 'day' and on) else shd(col, 1.25 if mode == 'day' else .8)
                    r.rect(wx, wy, wx + 10, wy + 12, c, p)
    r.rect(-900, 440, 2300, 900, (70, 72, 80), .9); r.rect(-900, 430, 2300, 462, (150, 150, 155), .9)
    for i in range(-4, 16): r.rect(i * 170 - (t * 120) % 170, 585, i * 170 - (t * 120) % 170 + 90, 595, (235, 235, 220), 1)
    for k in range(3):  # cars
        x = ((t * (90 + k * 55) + k * 640) % 2200) - 500; y = 520 + k * 52; c = [(210, 50, 50), (50, 110, 210), (240, 200, 50)][k]
        r.rect(x, y - 24, x + 108, y + 6, c, 1); r.rect(x + 22, y - 40, x + 82, y - 24, shd(c, .85), 1); r.rect(x + 28, y - 37, x + 76, y - 26, (170, 215, 240), 1)
        r.ell(x + 22, y + 8, 11, 11, (25, 25, 30), 1); r.ell(x + 86, y + 8, 11, 11, (25, 25, 30), 1)
        if mode != 'day': r.glow(x + 112, y - 8, 70, (255, 240, 180), .6, 1)
    for i in range(-2, 8):
        x = i * 420; r.rect(x - 3, 330, x + 3, 460, (60, 60, 70), .9); r.ell(x, 330, 11, 7, (255, 240, 170) if mode != 'day' else (200, 200, 190), .9)
        if mode != 'day': r.glow(x, 332, 120, (255, 225, 150), .45, .9)
def bg_hall(r, t, o):
    banner = o.get('banner', 'ASSEMBLY'); fl = o.get('flags', [[(30, 60, 160), (245, 245, 245), (200, 40, 40)]])
    sky(r, (226, 216, 196), (190, 176, 150), 420)
    for i in range(-2, 8):
        x = i * 260 + 60; r.poly([(x - 60, 130), (x - 60, 330), (x + 60, 330), (x + 60, 130)], (170, 200, 230), .35) if False else None
        r.rect(x - 38, 150, x + 38, 360, shd((235, 228, 210), .94), .5); r.ell(x, 150, 38, 30, (170, 205, 235), .5); r.rect(x - 38, 150, x + 38, 360, (175, 208, 238), .5)
        r.rect(x - 34, 150, x + 34, 356, (205, 225, 245), .5); r.line([(x, 120), (x, 360)], (150, 140, 120), 3, .5); r.line([(x - 34, 250), (x + 34, 250)], (150, 140, 120), 3, .5)
    for i in range(-2, 9):
        x = i * 200 + 20; r.rect(x - 24, 70, x + 24, 430, (240, 235, 222), .75)
        for j in (-14, -4, 6, 16): r.rect(x + j - 1, 70, x + j + 1, 430, (205, 198, 182), .75)
        r.rect(x - 32, 60, x + 32, 80, (222, 214, 196), .75); r.rect(x - 32, 420, x + 32, 440, (222, 214, 196), .75)
    r.rect(300, 100, 980, 200, (28, 40, 90), .85); r.rect(308, 108, 972, 192, (210, 170, 60), .85); r.rect(312, 112, 968, 188, (28, 40, 90), .85)
    r.text(640, 150, banner, 46, (240, 205, 90), .85)
    for k, cols in enumerate(fl): flag_wave(r, 150 + k * 900, 200, 110, 70, cols, t + k, .85)
    r.rect(-900, 440, 2300, 900, (120, 88, 62), 1)
    for k in range(12): r.rect(-900, 440 + k ** 1.6 * 4.5, 2300, 440 + (k + .08) ** 1.6 * 4.5 + 3, (96, 70, 50), 1)
    r.rect(500, 420, 780, 470, (60, 44, 34), 1); r.rect(490, 408, 790, 424, (90, 64, 48), 1)
    for i in range(10):  # camera flashes
        if math.sin(t * 7 + i * 3.1) > .96: r.glow(rnd(i, 3) * 1280, 470 + rnd(i, 4) * 150, 60, (255, 255, 255), .9, 1)
def bg_studio(r, t, o):
    sky(r, (14, 22, 58), (28, 60, 120), 480); sc = o.get('screen', 'BREAKING NEWS'); tick = o.get('ticker', 'LIVE • WORLD • SPORTS • POLITICS • ')
    for i in range(-2, 12):
        for j in range(4):
            x = i * 130 + (j % 2) * 65; y = 40 + j * 90; pulse = .5 + .5 * math.sin(t * 2 + i * .7 + j)
            r.poly([(x, y), (x + 40, y - 22), (x + 80, y), (x + 80, y + 46), (x + 40, y + 68), (x, y + 46)], mixc((20, 40, 90), (40, 90, 170), pulse), .3)
    r.rect(250, 60, 1030, 350, (10, 14, 30), .6); r.rect(258, 68, 1022, 342, (24, 80, 170), .6); r.rect(258, 68, 1022, 120, (220, 40, 50), .6)
    r.text(640, 94, sc, 40, (255, 255, 255), .6)
    gx, gy = 640, 235
    r.ell(gx, gy, 70, 70, (30, 100, 190), .6)
    for k in range(-3, 4): r.d.arc([min(r.X(gx - 70 * math.cos(k * .4 + t * .8), .6), r.X(gx + 70 * math.cos(k * .4 + t * .8), .6)), r.Y(gy - 70, .6), max(r.X(gx - 70 * math.cos(k * .4 + t * .8), .6), r.X(gx + 70 * math.cos(k * .4 + t * .8), .6)) + 1, r.Y(gy + 70, .6)], 0, 360, fill=(150, 210, 255), width=max(1, int(1.5 * r.Z(.6))))
    r.rect(-900, 395, 2300, 430, (200, 40, 50), .8); r.rect(-900, 400, 2300, 425, (20, 20, 30), .8)
    r.text(((-t * 140) % 1500) + 100, 413, tick * 3, 20, (255, 255, 255), .8, anchor='lm')
    r.rect(-900, 430, 2300, 900, (22, 26, 44), 1)
    for k in range(10): r.line([(-900, 440 + k ** 1.7 * 8), (2300, 440 + k ** 1.7 * 8)], (36, 42, 70), 2)
    for x, c in ((100, (38, 70, 120)), (1180, (110, 80, 48))): r.poly([(x, 0), (x - 170, 520), (x + 170, 520)], c, .3); r.glow(x, 20, 100, c, .5, .3)
    r.rect(380, 470, 900, 520, (230, 232, 240), 1); r.rect(380, 520, 900, 560, (60, 90, 160), 1)
def bg_village(r, t, o):
    mode = o.get('time', 'day')
    top, bot = {'day': ((100, 175, 240), (215, 238, 250)), 'dusk': ((90, 70, 140), (255, 175, 100)), 'night': ((10, 16, 44), (44, 56, 100))}[mode]
    sky(r, top, bot, 400)
    sun = (880, 150) if mode != 'dusk' else (880, 330)
    if mode == 'night': r.ell(900, 110, 36, 36, (240, 240, 225), .05); r.glow(900, 110, 130, (200, 210, 255), .5, .05)
    else:
        r.glow(sun[0], sun[1], 200, (255, 235, 150), .55, .05); r.ell(sun[0], sun[1], 50, 50, (255, 240, 150), .05)
        for i in range(12): a = i * .5236 + t * .3; r.line([(sun[0] + 62 * math.cos(a), sun[1] + 62 * math.sin(a)), (sun[0] + 84 * math.cos(a), sun[1] + 84 * math.sin(a))], (255, 230, 120), 4, .05)
    clouds(r, t, .1, 40, 5, (255, 255, 255) if mode == 'day' else (250, 200, 180)); birds(r, t, .2, 5, 110)
    for p, base, col in ((.2, 390, (100, 150, 140)), (.4, 420, (70, 135, 90))):
        if mode == 'night': col = shd(col, .35)
        pts = [(x, base - 70 * math.sin(x / 190 + p * 9) - 30 * math.sin(x / 71)) for x in range(-600, 2300, 40)]; r.poly(pts + [(2300, 700), (-600, 700)], col, p)
    r.rect(-900, 440, 2300, 900, (86, 160, 70) if mode != 'night' else (34, 70, 44), 1)
    r.poly([(560, 440), (720, 440), (1100, 760), (260, 760)], (196, 160, 110) if mode != 'night' else (90, 80, 70), 1)
    r.rect(-900, 440, 2300, 470, (80, 150, 220) if mode != 'night' else (30, 50, 100), .5) if o.get('river') else None
    for i in range(-3, 9):  # trees
        x = i * 280 + 40 + rnd(i, 1) * 60; sway = math.sin(t * 1.6 + i) * 4; y = 450 + rnd(i, 2) * 30
        r.rect(x - 9, y - 90, x + 9, y, (100, 70, 45), .85)
        for dx, dy, rr in ((0, -110, 52), (-34, -90, 38), (34, -92, 38), (4, -140, 36)): r.ell(x + dx + sway, y + dy, rr, rr * .85, (50, 140, 60) if mode != 'night' else (22, 70, 40), .85)
    if o.get('temple', False):
        x = 340; r.rect(x - 90, 330, x + 90, 450, (226, 190, 140), .7); r.poly([(x - 100, 330), (x, 220), (x + 100, 330)], (214, 160, 100), .7)
        r.poly([(x - 40, 220), (x, 150), (x + 40, 220)], (230, 170, 100), .7); r.rect(x - 22, 380, x + 22, 450, (80, 50, 40), .7); r.line([(x, 150), (x, 120)], (240, 200, 60), 3, .7)
        flag_wave(r, x, 120, 40, 22, [(240, 120, 30)], t, .7, pole=False)
        r.glow(x, 410, 80, (255, 190, 90), .5 + .15 * math.sin(t * 9), .7)
    for i in range(30):
        x = i * 90 + math.sin(t * 2 + i) * 3; r.line([(x, 640 + (i % 5) * 12), (x - 3, 626 + (i % 5) * 12)], (60, 130, 50) if mode != 'night' else (28, 60, 36), 2, 1)
    for i in range(3):
        bx = (rnd(i, 3) * 1300 + t * 30) % 1400 - 60; by = 520 + rnd(i, 4) * 100 + math.sin(t * 4 + i) * 12; fl = abs(math.sin(t * 14 + i)) * 6
        r.poly([(bx, by), (bx - 7, by - fl), (bx - 3, by + 3)], (250, 150, 40), 1); r.poly([(bx, by), (bx + 7, by - fl), (bx + 3, by + 3)], (250, 190, 60), 1)
def bg_locker(r, t, o):
    sky(r, (30, 90, 110), (24, 70, 88), 450)
    for i in range(-3, 11):
        x = i * 150; r.rect(x, 130, x + 140, 450, (50, 120, 150) if i % 2 else (44, 108, 136), .8); r.rect(x + 8, 140, x + 132, 300, shd((50, 120, 150), 1.12), .8)
        for k in range(3): r.rect(x + 30, 160 + k * 8, x + 110, 163 + k * 8, (20, 50, 66), .8)
        r.rect(x + 8, 310, x + 132, 440, shd((50, 120, 150), 1.05), .8); r.ell(x + 120, 360, 4, 4, (210, 210, 220), .8)
    r.rect(-900, 450, 2300, 900, (150, 120, 90), 1)
    for k in range(10): r.line([(-900, 460 + k ** 1.7 * 7), (2300, 460 + k ** 1.7 * 7)], (128, 100, 74), 2)
    r.rect(-900, 480, 2300, 506, (110, 80, 55), .9); r.glow(640, 40, 700, (255, 245, 210), .35 + .04 * math.sin(t * 20), 0)
BGS = dict(stadium=bg_stadium, tunnel=bg_tunnel, city=bg_city, hall=bg_hall, studio=bg_studio, village=bg_village, locker=bg_locker)

# ---------------------------------------------------------------- scene spec + build
def fx(t, k, **kw): d = dict(t=t, k=k); d.update(kw); return d
def prop(type, path=None, follow=None, size=1.0, col=(230, 50, 50), txt='', dribble=False):
    return dict(type=type, path=path or [(0, 640, 560, 0)], follow=follow, size=size, col=col, txt=txt, dribble=dribble)
def scene(dur, bg='stadium', bgopt=None, actors=(), props=(), cam=None, fx=(), sfx=(), cap=None, emoji='star', crowd=(.5, .5),
          music='up', tr='cut', hud=None, thumb=None, auto=True):
    """bg: stadium tunnel city hall studio village locker.  cap: str or [(t0,t1,text,emoji)].
    sfx: [(t,'name'[,vol[,pan]])].  tr: cut|whip|fade|flash.  music: up|tense|sad|epic|off.  hud: dict or None (keeps previous)."""
    return dict(dur=dur, bg=bg, bgopt=bgopt or {}, actors=list(actors), props=list(props), cam=cam or {}, fx=list(fx), sfx=list(sfx),
                cap=cap, emoji=emoji, crowd=crowd, music=music, tr=tr, hud=hud, thumb=thumb, auto=auto)
def hud(a, b, sa, sb, clock, ca=(220, 30, 40), cb=(40, 90, 220)): return dict(a=a, b=b, sa=sa, sb=sb, clock=clock, ca=ca, cb=cb)

def pchip(keys, n, idx, clampend=True):
    ts = [k[0] for k in keys]
    if len(keys) == 1: return lambda t: keys[0][idx]
    f = PchipInterpolator(ts, [k[idx] for k in keys], extrapolate=False)
    return lambda t: float(f(clamp(t, ts[0], ts[-1])))

SEEN = set()
def build(sc, t0):
    n = int(round(sc['dur'] * FPS)); sc['n'] = n; sc['t0'] = t0; ev = []
    for a in sc['actors']:
        pa = a['path']; fx_, fy_ = pchip(pa, n, 1), pchip(pa, n, 2)
        f = pa[0][3] if len(pa[0]) > 3 else 1; ph = 0.; st = []
        segs = [(0., 'auto')]
        for tk, nm in sorted(a['act']):
            if segs and tk == segs[-1][0]: segs.pop()
            segs.append((tk, nm))
            if nm in ONE: segs.append((tk + ONE[nm], 'auto'))
        segs = sorted(segs, key=lambda x: x[0]); cl = []
        for q in segs:
            if cl and cl[-1][0] == q[0]: cl[-1] = q
            else: cl.append(q)
        # keep later explicit keys overriding auto-returns that fall after them
        fin = []
        for i, (ts, nm) in enumerate(cl):
            if nm == 'auto' and i > 0 and cl[i - 1][1] in ONE and any(abs(k[0] - ts) < 1e-6 and k[1] != 'auto' for k in a['act']): continue
            fin.append((ts, nm))
        segs = fin
        prevx, prevy = fx_(0), fy_(0)
        for i in range(n):
            t = i / FPS; x, y = fx_(t), fy_(t); vx, vy = (x - prevx) * FPS, (y - prevy) * FPS if i else 0; sp = math.hypot(vx, vy) if i else 0
            if i == 0: vx = vy = 0
            if abs(vx) > 25: f = 1 if vx > 0 else -1
            for tk, d in a['fdir']:
                if tk <= t: f = d
            if len(pa[0]) > 3 and not a['fdir'] and abs(vx) <= 25:
                f = [p for p in pa if p[0] <= t][-1][3] if len(pa[0]) > 3 else f
            ph += math.pi * (min(sp, 420) / 70) / FPS
            j = max(k for k, q in enumerate(segs) if q[0] <= t + 1e-9)
            ts, nm = segs[j]; pnm, pts = (segs[j - 1][1], segs[j - 1][0]) if j > 0 else (nm, ts)
            st.append(dict(x=x, y=y, f=f, ph=ph, sp=sp, a=nm, tt=t - ts, pa=pnm, ptt=t - pts, w=sm((t - ts) / .2) if j > 0 else 1.0,
                           fv=face_at(sorted(a['face']), t), spk=1.0 if any(s0 <= t <= s1 for s0, s1 in a['say']) else 0.0))
            prevx, prevy = x, y
        a['st'] = st; a['seed'] = (hash(a['ch']['name']) % 97) / 97.0 * 5
        if sc['auto']:
            last = 0
            for i, q in enumerate(st):  # footsteps
                if q['a'] in ('auto',) and q['sp'] > 40 and i > 0 and math.sin(st[i - 1]['ph']) * math.sin(q['ph']) <= 0 and i - last > 3:
                    ev.append((t0 + i / FPS, 'step', clamp(q['sp'] / 330) * .5 + .12, (q['x'] - 640) / 640 * .6)); last = i
            for tk, nm in a['act']:
                if nm == 'kick': ev.append((t0 + tk + .3, 'kick', .85, 0.0))
                if nm == 'celebrate': ev.append((t0 + tk, 'cheer_s', .5, 0.0))
                if nm == 'fall': ev.append((t0 + tk + .22, 'thud', .6, 0.0))
                if nm in ('jump', 'header'): ev.append((t0 + tk + .5, 'thud', .35, 0.0))
            fk = sorted(a['face'])
            for tk, nm in fk:
                if tk > .01 or nm != 'neutral':
                    m = {'laugh': 'laugh_s', 'shock': 'gasp_s', 'panic': 'gasp_s', 'sad': 'sigh', 'cry': 'sigh', 'angry': 'growl'}.get(nm)
                    if m: ev.append((t0 + tk + .1, m, .4, (st[min(n - 1, int(tk * FPS))]['x'] - 640) / 640 * .6))
    for p in sc['props']:
        if p['follow']:
            nm, dx, dy, dz = p['follow']; A = [a for a in sc['actors'] if a['ch']['name'] == nm][0]
            p['st'] = [(q['x'] + q['f'] * dx, q['y'] + dy, dz + (abs(math.sin(q['ph'] * 1.0)) * 14 if p['dribble'] and q['sp'] > 30 else 0)) for q in A['st']]
        else:
            fx_, fy_, fz_ = pchip(p['path'], n, 1), pchip(p['path'], n, 2), pchip(p['path'], n, 3)
            p['st'] = [(fx_(i / FPS), fy_(i / FPS), fz_(i / FPS)) for i in range(n)]
        sp, ang, out = 0, 0., []
        for i, (x, y, z) in enumerate(p['st']):
            if i: ang += math.hypot(x - p['st'][i - 1][0], y - p['st'][i - 1][1]) / 11 + abs(z - p['st'][i - 1][2]) / 14
            out.append(ang)
        p['spin'] = out
    # camera
    c = sc['cam']; fol = c.get('follow'); cxs = None; cams = []
    FA = [a for a in sc['actors'] if a['ch']['name'] == fol] if fol else []
    for i in range(n):
        u = i / max(1, n - 1); t = i / FPS
        z = val(c.get('z'), u, 1.0); x = val(c.get('x'), u, 640.); y = val(c.get('y'), u, 360.)
        if FA:
            q = FA[0]['st'][i]; tx = q['x'] + q['f'] * c.get('lead', 30); ty = 360 + (q['y'] - 85 - 360) * clamp((z - 1) / .5) * .9
            cxs = tx if cxs is None else cxs + (tx - cxs) * .13; x = cxs
            cys = ty; y = ty if i == 0 else lerp(cams[-1].y, ty, .15)
        sh = val(c.get('shake'), u, 0.0); sx = sy = 0.
        for e in sc['fx']:
            if e['k'] == 'shake' and t >= e['t']: sh += e.get('amp', 14) * math.exp(-(t - e['t']) * e.get('decay', 7))
        sx = sh * (math.sin(t * 43) * .6 + math.sin(t * 29 + 1.3) * .4); sy = sh * (math.sin(t * 37 + .4) * .6 + math.sin(t * 23) * .4)
        cams.append(Cam(x, y, z, sx, sy))
    sc['cams'] = cams
    # events
    for e in sc['sfx']: ev.append((t0 + e[0], e[1], e[2] if len(e) > 2 else 1.0, e[3] if len(e) > 3 else 0.0))
    sc['capl'] = sc['cap'] if isinstance(sc['cap'], list) else ([(.15, sc['dur'] - .1, sc['cap'], sc['emoji'])] if sc['cap'] else [])
    for c0 in sc['capl']: ev.append((t0 + c0[0], 'pop', .25, 0.0))
    if sc['tr'] == 'whip': ev.append((t0, 'whoosh', .6, 0.0))
    if sc['tr'] == 'flash': ev.append((t0, 'cymbal', .4, 0.0))
    for e in sc['fx']:
        if e['k'] == 'confetti': ev.append((t0 + e['t'], 'pop', .6, 0.0))
        if e['k'] == 'burst': ev.append((t0 + e['t'], 'thud', .5, 0.0))
    sc['ev'] = ev
    for a in sc['actors']:
        a['intro'] = a['ch']['name'] not in SEEN and a['label']; SEEN.add(a['ch']['name'])

# ---------------------------------------------------------------- overlays
_VIG = None
def vignette():
    global _VIG
    if _VIG is None:
        yy, xx = np.mgrid[-1:1:complex(int(H * K)), -1:1:complex(int(W * K))]
        v = 1 - np.clip((np.hypot(xx * .9, yy) - .55) / 1.0, 0, 1) ** 1.6 * .38
        _VIG = Image.fromarray((np.stack([v] * 3, -1) * 255).astype(np.uint8))
    return _VIG
def draw_fx(r, sc, t):
    d = r.d
    for e in sc['fx']:
        dt = t - e['t']
        if dt < 0: continue
        k = e['k']
        if k == 'confetti' and dt < e.get('d', 3.2):
            cols = [(255, 70, 90), (255, 210, 50), (70, 190, 255), (120, 230, 120), (255, 255, 255), (200, 100, 255)]
            for i in range(150):
                x = (rnd(i, 1) * W + math.sin(dt * 2 + i) * 30) * K; y = ((-30 + dt * (160 + rnd(i, 2) * 260) + 40 * dt * dt - rnd(i, 3) * 200)) * K
                if y < -20 or y > H * K + 20: continue
                a = dt * (3 + rnd(i, 4) * 8) + i; w, h = (5 + rnd(i, 5) * 6) * K, (3 + rnd(i, 6) * 4) * K * abs(math.cos(a * 1.3)) + 1
                d.polygon([(x + w * math.cos(a) - h * math.sin(a), y + w * math.sin(a) + h * math.cos(a)), (x - w * math.cos(a) - h * math.sin(a), y - w * math.sin(a) + h * math.cos(a)),
                           (x - w * math.cos(a) + h * math.sin(a), y - w * math.sin(a) - h * math.cos(a)), (x + w * math.cos(a) + h * math.sin(a), y + w * math.sin(a) - h * math.cos(a))], fill=cols[i % 6])
        elif k == 'flash' and dt < .35:
            r.im.paste(Image.blend(r.im, Image.new('RGB', r.im.size, (255, 255, 255)), (1 - dt / .35) ** 2 * e.get('a', .85)))
        elif k == 'speed' and dt < e.get('d', 1.0):
            rng = random.Random(int(t * FPS)); cx, cy = W * K / 2, H * K / 2
            for i in range(38):
                a = rng.random() * 6.283; r0 = (.55 + rng.random() * .25) * W * K / 2; r1 = r0 + (.25 + rng.random() * .3) * W * K / 2
                d.line([(cx + r0 * math.cos(a), cy + r0 * math.sin(a) * .8), (cx + r1 * math.cos(a), cy + r1 * math.sin(a) * .8)], fill=(255, 255, 255), width=max(1, int(2.4 * K)))
        elif k == 'burst' and dt < e.get('d', .9):
            sc_ = 1 + .35 * math.sin(clamp(dt / .25) * 3.14159) if dt < .25 else 1.0; sc_ *= clamp(dt / .1 + .2, 0, 1)
            bx, by = e.get('x', 640) * K, e.get('y', 250) * K; rr = 130 * K * sc_
            pts = [(bx + (rr if i % 2 == 0 else rr * .68) * math.cos(i * .2618 + dt * .6), by + (rr if i % 2 == 0 else rr * .68) * .75 * math.sin(i * .2618 + dt * .6)) for i in range(24)]
            d.polygon(pts, fill=(255, 225, 50), outline=(220, 40, 40)); d.text((bx, by), e['text'], font=font(52 * K * sc_), fill=(220, 40, 40), anchor='mm', stroke_width=int(3 * K), stroke_fill=(255, 255, 255))
        elif k == 'title' and dt < e.get('d', 1.6) + .3:
            u = clamp(dt / .3); s_ = (1 + .25 * math.sin(u * 3.14159)) * sm(u + .05) if dt < .3 else 1.0; al = 1 - clamp((dt - e.get('d', 1.6)) / .3)
            if al > .02:
                col = e.get('col', (255, 225, 50)); fs = e.get('size', 120) * K * s_
                d.text((W * K / 2, e.get('y', 300) * K), e['text'], font=font(fs), fill=mixc((0, 0, 0), col, al), anchor='mm', stroke_width=int(9 * K * s_), stroke_fill=mixc((0, 0, 0), (30, 20, 20), al))
        elif k == 'sparkle' and dt < .8:
            x, y = r.X(e['x']), r.Y(e['y']); q = (14 + 12 * math.sin(dt * 8)) * K * (1 - dt / .8)
            d.polygon([(x, y - q), (x + q * .25, y - q * .25), (x + q, y), (x + q * .25, y + q * .25), (x, y + q), (x - q * .25, y + q * .25), (x - q, y), (x - q * .25, y - q * .25)], fill=(255, 250, 200))
def draw_hud(r, h, t, pop):
    if not h: return
    x0, y0 = 28, 24
    r.panel((x0, y0, x0 + 300, y0 + 52), 12, (15, 18, 28), 205)
    r.panel((x0 + 6, y0 + 6, x0 + 76, y0 + 46), 8, h['ca'], 255); r.panel((x0 + 224, y0 + 6, x0 + 294, y0 + 46), 8, h['cb'], 255)
    d = r.d
    d.text(((x0 + 41) * K, (y0 + 26) * K), h['a'], font=font(22 * K), fill=(255, 255, 255), anchor='mm', stroke_width=int(1.2 * K), stroke_fill=(0, 0, 0))
    d.text(((x0 + 259) * K, (y0 + 26) * K), h['b'], font=font(22 * K), fill=(255, 255, 255), anchor='mm', stroke_width=int(1.2 * K), stroke_fill=(0, 0, 0))
    s = 1 + .35 * pop
    d.text(((x0 + 150) * K, (y0 + 25) * K), f"{h['sa']} - {h['sb']}", font=font(28 * K * s), fill=(255, 235, 120), anchor='mm')
    r.panel((x0 + 100, y0 + 56, x0 + 200, y0 + 80), 8, (15, 18, 28), 205)
    d.text(((x0 + 150) * K, (y0 + 68) * K), h['clock'], font=font(17 * K), fill=(255, 255, 255), anchor='mm')
def draw_caption(r, text, em, t, t0, t1):
    if not (t0 <= t <= t1): return
    u = sm((t - t0) / .15); o = 1 - sm((t - (t1 - .12)) / .12) if t > t1 - .12 else 1
    words = text.split(); lines = [text]
    if len(text) > 46:
        half = len(text) // 2; k = min(range(len(words)), key=lambda i: abs(len(' '.join(words[:i + 1])) - half)); lines = [' '.join(words[:k + 1]), ' '.join(words[k + 1:])]
    fs = 30 * K * (.9 + .1 * u); f_ = font(fs); wmax = max(r.d.textlength(l, font=f_) for l in lines)
    pad = 20 * K; ih = 40 * K; bw = wmax + pad * 2 + ih + 10 * K; bh = (len(lines) * 40 + 22) * K
    cx = W * K / 2; yb = (H - 24) * K + (1 - u) * 20 * K; x0, y0 = cx - bw / 2, yb - bh
    m = Image.new('L', (int(bw), int(bh)), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, bw - 1, bh - 1], radius=int(16 * K), fill=int(175 * o))
    r.im.paste((8, 10, 18), (int(x0), int(y0), int(x0) + int(bw), int(y0) + int(bh)), m)
    icon(r, em, x0 + pad + ih / 2, y0 + bh / 2, ih / 2 * .92)
    for i, l in enumerate(lines):
        r.d.text((x0 + pad + ih + 10 * K, y0 + (11 + 20 + i * 40) * K), l, font=f_, fill=tuple(int(255 * o) for _ in range(3)), anchor='lm')

# ---------------------------------------------------------------- frame composer
def render_frame(sc, i, H_, pop):
    t = i / FPS; cam = sc['cams'][i]; r = R(cam, t, sc)
    opt = dict(sc['bgopt']); cr = sc['crowd']; opt['exc'] = lerp(cr[0], cr[1], i / max(1, sc['n'] - 1)) if isinstance(cr, tuple) else cr
    BGS[sc['bg']](r, t, opt)
    items = []
    for a in sc['actors']: items.append((a['st'][i]['y'], 'a', a))
    for p in sc['props']: items.append((p['st'][i][1] + (.5 if p['type'] == 'ball' else 0), 'p', p))
    items.sort(key=lambda q: q[0])
    ball = next((p['st'][i] for p in sc['props'] if p['type'] == 'ball'), None)
    for _, kind, o in items:
        if kind == 'p':
            x, y, z = o['st'][i]; draw_prop(r, o['type'], x, y, z, o['size'], t, o['spin'][i] * .5, o['col'], o['txt'])
        else:
            q = o['st'][i]; s_ = (0.55 + clamp((q['y'] - 380) / 340) * .75) * o['ch']['size']
            r.sshade(q['x'], q['y'] + 2, 30 * s_, 8 * s_, 85)
            an = lambda a_: ('move' if q['sp'] > 18 else 'idle') if a_ == 'auto' else a_
            P = pose(an(q['a']), q['ph'], q['sp'], q['tt'], t)
            if q['w'] < 1: P = blend_pose(pose(an(q['pa']), q['ph'], q['sp'], q['ptt'], t), P, q['w'])
            look = (q['f'] * .6, 0.0)
            if o['look'] == 'cam': look = (0.0, .2)
            elif ball and o['look'] != 'none':
                look = (clamp((ball[0] - q['x']) / 220, -1, 1), clamp((ball[1] - ball[2] - (q['y'] - 80)) / 200, -1, 1))
            draw_actor(r, o['ch'], q['x'], q['y'], q['f'], P, q['fv'], look, q['tt'], q['spk'], o['seed'], t)
            if o['intro'] and t < 1.5:
                al = int(215 * (1 - sm((t - 1.1) / .4))); nm = o['ch']['name'].upper(); wpx = r.d.textlength(nm, font=font(15 * r.Z()))
                px, py = r.X(q['x']), r.Y(q['y']) - 185 * s_ * r.Z(); r.panel(((px - wpx / 2 - 10 * K) / K, (py - 14 * K) / K, (px + wpx / 2 + 10 * K) / K, (py + 14 * K) / K), 8, o['ch']['shirt'] if sum(o['ch']['shirt']) < 600 else (60, 60, 80), al)
                r.d.text((px, py), nm, font=font(15 * r.Z()), fill=(255, 255, 255), anchor='mm')
    draw_fx(r, sc, t)
    im = ImageChops.multiply(r.im, vignette()); r.im = im; r.d = ImageDraw.Draw(im)
    draw_hud(r, H_, t, pop)
    for (c0, c1, tx, em) in sc['capl']: draw_caption(r, tx, em, t, c0, c1)
    return r.im.resize((W, H), Image.LANCZOS)

# ---------------------------------------------------------------- audio
_RNG = np.random.default_rng(7)
def nz(n): return _RNG.standard_normal(n).astype(np.float32)
def Tt(d): return np.arange(int(d * SR), dtype=np.float32) / SR
def bp(x, lo, hi, o=2): return sosfilt(butter(o, [lo, min(hi, SR / 2 - 100)], 'band', fs=SR, output='sos'), x).astype(np.float32)
def lp(x, f, o=2): return sosfilt(butter(o, f, 'low', fs=SR, output='sos'), x).astype(np.float32)
def hp(x, f, o=2): return sosfilt(butter(o, f, 'high', fs=SR, output='sos'), x).astype(np.float32)
def saw(f): return (2 * ((np.cumsum(f) / SR) % 1) - 1).astype(np.float32)
def sine(f): return np.sin(2 * np.pi * np.cumsum(f) / SR).astype(np.float32)
def ad(t, a, dcy): return (np.minimum(t / max(a, 1e-4), 1) * np.exp(-np.maximum(t - a, 0) / dcy)).astype(np.float32)
def swell(t, a, hold, rel):
    d = t[-1] if len(t) else 0; return (np.clip(t / a, 0, 1) * np.clip((a + hold + rel - t) / rel, 0, 1) ** 1.5).astype(np.float32)
def fin(x, a=.004, b=.03):
    ia, ib = int(a * SR), min(int(b * SR), len(x)); x = x.copy(); x[:ia] *= np.linspace(0, 1, ia); x[-ib:] *= np.linspace(1, 0, ib); return x

def s_whistle(d=.55):
    t = Tt(d); f = 2850 + 70 * np.sin(2 * np.pi * 5 * t); x = sine(f) * (.62 + .38 * (np.sin(2 * np.pi * 36 * t) > 0)) * swell(t, .03, d - .1, .08)
    return fin(x * .5 + hp(nz(len(t)), 3500) * .05 * swell(t, .03, d - .1, .08))
def s_whistle_long(d=1.5): return np.concatenate([s_whistle(.35), np.zeros(int(.08 * SR), np.float32), s_whistle(.35), np.zeros(int(.08 * SR), np.float32), s_whistle(.7)])
def s_kick():
    t = Tt(.25); f = 45 + 150 * np.exp(-t * 20); return fin(sine(f) * ad(t, .002, .05) * .9 + bp(nz(len(t)), 1200, 5500) * ad(t, .001, .012) * .5 + lp(nz(len(t)), 400) * ad(t, .001, .03) * .3)
def s_step():
    t = Tt(.1); return fin(lp(nz(len(t)), 1100) * ad(t, .002, .018) * .6 + sine(85 + 0 * t) * ad(t, .002, .02) * .35, .002, .02)
def s_thud():
    t = Tt(.4); return fin(sine(38 + 40 * np.exp(-t * 14)) * ad(t, .003, .09) * .9 + lp(nz(len(t)), 300) * ad(t, .002, .05) * .35)
def s_net():
    t = Tt(.6); return fin(bp(nz(len(t)), 900, 6000) * (ad(t, .02, .12) * .7 + ad(t, .06, .25) * (.5 + .5 * np.sin(2 * np.pi * 38 * t)) * .3) * .6)
def s_post():
    t = Tt(1.0); x = sum(sine(f + 0 * t) * ad(t, .001, d_) * a for f, d_, a in ((1240, .22, 1), (1830, .15, .6), (2710, .1, .4), (410, .3, .5)))
    th = np.pad(s_thud(), (0, max(0, len(t) - len(s_thud()))))[:len(t)]; return fin(x * .5 + th * .4)
def s_whoosh(d=.6):
    t = Tt(d); n = nz(len(t)); lo = lp(n, 500); mid = bp(n, 600, 2500); hi = hp(n, 3000)
    a = np.exp(-((t / d - .25) / .22) ** 2); b = np.exp(-((t / d - .5) / .2) ** 2); c = np.exp(-((t / d - .75) / .2) ** 2)
    return fin((lo * a * 1.4 + mid * b + hi * c * .5) * .55, .02, .1)
def s_pop(): t = Tt(.08); return fin(sine(350 + 600 * np.exp(-t * 60)) * ad(t, .001, .02) * .8, .001, .01)
def s_ding(): t = Tt(1.0); return fin((sine(1568 + 0 * t) + .5 * sine(3136 + 0 * t) + .25 * sine(4700 + 0 * t)) * ad(t, .002, .28) * .35)
def s_horn(): t = Tt(1.2); f = 440 + 0 * t; x = (saw(f) + saw(f * 1.26) + saw(f * 1.5)) / 3; return fin(lp(x, 2400) * swell(t, .06, .8, .3) * .5)
def s_cymbal(): t = Tt(1.8); return fin(hp(nz(len(t)), 5500) * ad(t, .004, .5) * .45 + bp(nz(len(t)), 3000, 9000) * ad(t, .004, .25) * .2, .002, .3)
def s_roar(d=3.2):
    t = Tt(d); n = nz(len(t)); lo = bp(n, 250, 1400) * swell(t, .35, d * .35, d * .5); hi = bp(n, 1400, 5000) * swell(t, .2, d * .25, d * .5) * .7
    voc = sum(saw(f * (1 + .01 * np.sin(2 * np.pi * (3 + k) * t))) for k, f in enumerate((180, 230, 290, 340, 410))) / 5
    return fin((lo + hi) * .8 + lp(voc, 1800) * swell(t, .4, d * .3, d * .5) * .25, .01, .3)
def s_cheer_s(d=1.6): return s_roar(d) * .55
def s_aww(d=2.2):
    t = Tt(d); f = 330 * np.exp(-t * .28) * (1 + .012 * np.sin(2 * np.pi * 5 * t)); x = sum(saw(f * (1 + dt)) for dt in (-.012, 0, .01, .02, -.02)) / 5
    return fin((lp(x, 1400) * .6 + bp(nz(len(t)), 300, 2000) * .5) * swell(t, .2, d * .3, d * .55) * .6, .01, .3)
def s_ooh(d=1.1):
    t = Tt(d); f = 230 + 110 * t / d; x = sum(saw(f * (1 + dt)) for dt in (-.015, 0, .012, .022)) / 4
    return fin((lp(x, 1200) * .6 + bp(nz(len(t)), 400, 2500) * .45) * swell(t, .25, d * .3, d * .4) * .6, .01, .2)
def s_boo(d=2.2):
    t = Tt(d); f = 150 + 6 * np.sin(2 * np.pi * 4 * t); x = sum(saw(f * (1 + dt)) for dt in (-.02, 0, .015, .03)) / 4
    return fin((lp(x, 700) * .8 + bp(nz(len(t)), 200, 900) * .4) * swell(t, .3, d * .5, d * .3) * .6, .01, .3)
def s_applause(d=3.0):
    t = Tt(d); imp = (_RNG.random(len(t)) > .9985).astype(np.float32) * nz(len(t)) * 6; x = bp(imp, 1200, 7000) + bp(nz(len(t)), 800, 5000) * .15
    return fin(x * swell(t, .4, d * .5, d * .4) * .9, .01, .3)
def s_gasp_s(): t = Tt(.45); return fin(bp(nz(len(t)), 600, 4200) * (t / .45) ** 1.5 * np.exp(-np.maximum(t - .3, 0) * 18) * .8 + lp(saw(300 + 120 * t / .45 + 0 * t), 900) * .15 * (t / .45), .01, .06)
def s_laugh_s():
    out = np.zeros(int(1.3 * SR), np.float32)
    for k in range(5):
        t = Tt(.13); f = (280 - k * 14) * (1 + .1 * np.exp(-t * 30)) + 0 * t; x = bp(saw(f), 500, 1400) * ad(t, .01, .045) * (1 - k * .13)
        o = int(k * .19 * SR); out[o:o + len(x)] += x * 1.6
    return fin(out * .5)
def s_sigh(): t = Tt(1.0); f = 200 * np.exp(-t * .5) + 0 * t; return fin((bp(nz(len(t)), 500, 2600) * .4 + lp(saw(f), 800) * .5) * swell(t, .2, .3, .45) * .6, .01, .2)
def s_growl(): t = Tt(.7); x = saw(95 + 8 * np.sin(2 * np.pi * 7 * t)) * (.6 + .4 * np.sign(np.sin(2 * np.pi * 30 * t))); return fin(lp(x, 600) * swell(t, .06, .35, .25) * .7)
def s_drumroll(d=1.6):
    out = np.zeros(int(d * SR) + 4000, np.float32); tt = 0.
    while tt < d:
        x = bp(nz(int(.05 * SR)), 800, 4000) * ad(Tt(.05), .002, .02); o = int(tt * SR); out[o:o + len(x)] += x * (.3 + .7 * tt / d); tt += .12 - .09 * tt / d
    return fin(out[:int(d * SR)])
def s_sting(): n = max(len(s_thud()), len(s_cymbal())); x = np.zeros(n, np.float32); x[:len(s_thud())] += s_thud() * 1.2; x += np.pad(s_cymbal(), (0, n - len(s_cymbal()))) * .8; return x
def s_chirp():
    t = Tt(.14); f = 3600 + 900 * np.sin(2 * np.pi * 22 * t) * np.exp(-t * 6); return fin(sine(f) * ad(t, .005, .05) * .25, .003, .03)
def s_clap_s(): t = Tt(.15); return fin(bp(nz(len(t)), 900, 4500) * ad(t, .002, .03), .002, .02)
SFX = dict(whistle=s_whistle, whistle_long=s_whistle_long, kick=s_kick, step=s_step, thud=s_thud, net=s_net, post=s_post, whoosh=s_whoosh, pop=s_pop,
           ding=s_ding, horn=s_horn, cymbal=s_cymbal, roar=s_roar, cheer_s=s_cheer_s, aww=s_aww, ooh=s_ooh, boo=s_boo, applause=s_applause,
           gasp_s=s_gasp_s, gasp=s_gasp_s, laugh_s=s_laugh_s, laugh=s_laugh_s, sigh=s_sigh, growl=s_growl, drumroll=s_drumroll, sting=s_sting, chirp=s_chirp, clap=s_clap_s)

def place(buf, x, t, vol=1.0, pan=0.0):
    o = int(t * SR)
    if o >= len(buf) or o < 0: return
    x = x[:len(buf) - o]; a = (pan + 1) * math.pi / 4; buf[o:o + len(x), 0] += x * vol * math.cos(a); buf[o:o + len(x), 1] += x * vol * math.sin(a)
def smooth_env(pts, total, win=.5):
    """pts [(t,v)] -> per-sample smoothed envelope"""
    n = int(total * SR); ts = np.array([p[0] for p in pts]); vs = np.array([p[1] for p in pts]); e = np.interp(np.arange(0, n, 441) / SR, ts, vs)
    k = max(1, int(win * 100)); e = np.convolve(np.pad(e, (k, k), mode='edge'), np.ones(k) / k, 'same')[k:-k]
    return np.interp(np.arange(n) / SR, np.arange(len(e)) * 441 / SR, e).astype(np.float32)

def audio(scenes, total, path):
    np.random.seed(3); n = int((total + 2.0) * SR); fg = np.zeros((n, 2), np.float32); bed = np.zeros((n, 2), np.float32)
    # foreground events
    for sc in scenes:
        for (t, nm, vol, pan) in sc['ev']:
            if nm in SFX: place(fg, SFX[nm](), t, vol, pan)
    # birds / city chirps
    for sc in scenes:
        if sc['bg'] == 'village' or (sc['bg'] == 'city' and sc['bgopt'].get('time', 'day') == 'day'):
            tt = sc['t0'] + .3
            while tt < sc['t0'] + sc['dur'] - .2: place(fg, s_chirp(), tt, .22, random.uniform(-.7, .7)); tt += random.uniform(.5, 1.6)
    # ambience buses
    amb = {k: [] for k in ('crowd', 'tunnel', 'city', 'hall', 'wind', 'room')}
    kind = dict(stadium='crowd', tunnel='tunnel', city='city', hall='hall', studio='room', village='wind', locker='room')
    for sc in scenes:
        k = kind[sc['bg']]; cr = sc['crowd']; a, b = (cr if isinstance(cr, tuple) else (cr, cr)); lv = {'crowd': (.06, .32), 'tunnel': (.1, .2), 'city': (.14, .14), 'hall': (.1, .2), 'wind': (.1, .1), 'room': (.06, .06)}[k]
        for kk in amb: amb[kk] += [(sc['t0'] + .01, 0.), (sc['t0'] + .02, 0.)] if kk != k else [(sc['t0'] + .01, lerp(lv[0], lv[1], a)), (sc['t0'] + sc['dur'], lerp(lv[0], lv[1], b))]
        if k == 'tunnel': amb['crowd'][-2:] = [(sc['t0'] + .01, .08), (sc['t0'] + sc['dur'], .12)]
    base = nz(n)
    src = dict(crowd=bp(base, 250, 3200) * 2.2, tunnel=lp(base, 220) * 2.6, city=bp(base, 60, 700) * 2.2, hall=bp(base, 200, 1600) * 2.0, wind=lp(base, 700) * 1.6, room=lp(base, 200) * .8 + sine(120 + 0 * Tt(total + 2)) * .02)
    for k, pts in amb.items():
        pts = sorted(pts); e = smooth_env(pts + [(total + 2, pts[-1][1])], total + 2, .45)[:n]
        m = 1 + .25 * smooth_env([(i * .7, random.random()) for i in range(int((total + 3) / .7))], total + 2, .6)[:n]
        x = src[k][:n] * e * m; bed[:, 0] += x; bed[:, 1] += np.roll(x, 37)
    # music bed (120 BPM)
    prog = [(110, 165, 220), (87.3, 130.8, 174.6), (130.8, 196, 261.6), (98, 146.8, 196)]
    ctl = dict(up=(.9, .7, .25), tense=(.35, .8, .5), sad=(0, 0, .8), epic=(1, .9, .6), off=(0, 0, 0)); pts = [[], [], []]
    for sc in scenes:
        v = ctl[sc['music']]
        for i in range(3): pts[i] += [(sc['t0'] + .01, v[i]), (sc['t0'] + sc['dur'], v[i])]
    en = [smooth_env(p, total + 2, .6)[:n] for p in pts]; mus = np.zeros((n, 2), np.float32); beat = .5; nb = int((total + 1) / beat)
    kk, hh, sn = s_kick(), hp(nz(int(.05 * SR)), 6500) * ad(Tt(.05), .001, .012), bp(nz(int(.15 * SR)), 1200, 6000) * ad(Tt(.15), .002, .04)
    for b in range(nb):
        t = b * beat; o = int(t * SR); e0 = en[0][min(o, n - 1)]
        if e0 > .05:
            if b % 4 in (0, 2) or e0 > .8: place(mus, kk, t, .6 * e0)
            if b % 2 == 1: place(mus, sn, t, .3 * e0)
            place(mus, hh, t + beat / 2, .25 * e0)
        bar = (b // 4) % 4; ch = prog[bar]; e1 = en[1][min(o, n - 1)]
        if e1 > .05:
            tb = Tt(.4); note = lp(saw(ch[0] / 2 + 0 * tb), 380) * ad(tb, .005, .16) * .55
            place(mus, note, t, e1 * .8); place(mus, note, t + beat / 2, e1 * .5)
        if b % 4 == 0:
            e2 = en[2][min(o, n - 1)]
            if e2 > .05:
                tp = Tt(2.2); pad = sum(lp(saw(f + 0 * tp) * 1.0 + saw(f * 1.004 + 0 * tp), 1300) for f in prog[bar]) / 3
                place(mus, pad * np.clip(tp / .3, 0, 1) * np.clip((2.2 - tp) / .5, 0, 1) * .22, t, e2)
    bed += mus * .55
    # sidechain duck + mix
    mid = np.abs(fg[:, 0] + fg[:, 1]); blk = np.pad(mid, (0, 441 - len(mid) % 441)).reshape(-1, 441).max(1); kw = 15; env = np.convolve(np.pad(blk, (kw, kw), mode='edge'), np.ones(kw) / kw, 'same')[kw:-kw]
    duck = np.interp(np.arange(n) / SR, np.arange(len(env)) * .01, 1 - .5 * np.clip(env * 2.2, 0, 1)).astype(np.float32)
    mix = fg + bed * duck[:, None]
    mix = np.tanh(mix * 1.15) / np.tanh(1.15); mix *= .92 / max(np.abs(mix).max(), 1e-6)
    f1, f2 = int(.05 * SR), int(.8 * SR); mix[:f1] *= np.linspace(0, 1, f1)[:, None]; mix[-f2:] *= np.linspace(1, 0, f2)[:, None]
    with wave.open(path, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((mix * 32767).astype(np.int16).tobytes())

# ---------------------------------------------------------------- pipeline
def transition(prev, new, kind, p):
    p = sm(p)
    if kind == 'fade': return Image.blend(prev, new, p)
    if kind == 'flash':
        wh = Image.new('RGB', prev.size, (255, 255, 255)); return Image.blend(prev, wh, p * 2) if p < .5 else Image.blend(wh, new, (p - .5) * 2)
    if kind == 'whip':
        cv = Image.new('RGB', prev.size); cv.paste(prev, (-int(p * W), 0)); cv.paste(new, (int((1 - p) * W), 0))
        bl = int(60 * math.sin(p * math.pi)); a = ImageChops.offset(cv, bl, 0); b = ImageChops.offset(cv, -bl, 0)
        return Image.blend(Image.blend(a, b, .5), cv, .35)
    return new
def thumb_img(im, text):
    d = ImageDraw.Draw(im); f_ = font(150); d.text((60, H - 70), text, font=f_, fill=(255, 225, 50), anchor='ls', stroke_width=12, stroke_fill=(20, 10, 10)); return im

def make(scenes, out, quiet=False):
    global SEEN
    SEEN = set(); t = 0.
    for sc in scenes: build(sc, t); t += sc['dur']
    wav = out.rsplit('.', 1)[0] + '_audio.wav'; audio(scenes, t, wav)
    pr = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-i', wav,
                           '-c:v', 'libx264', '-preset', 'medium', '-crf', '19', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', out], stdin=subprocess.PIPE)
    h = None; prev = None; changed = False
    for si, sc in enumerate(scenes):
        if sc['hud'] is not None:
            changed = h is None or (h['sa'], h['sb']) != (sc['hud']['sa'], sc['hud']['sb']); h = sc['hud']
        else: changed = False
        trf = int(.25 * FPS) if sc['tr'] != 'cut' and prev is not None else 0
        for i in range(sc['n']):
            im = render_frame(sc, i, h, max(0, 1 - i / FPS / .6) if changed else 0)
            if sc['thumb'] and i == int(sc['thumb'][1] * FPS): thumb_img(im.copy(), sc['thumb'][0]).save(out.rsplit('.', 1)[0] + '_thumb.jpg', quality=92)
            pr.stdin.write((transition(prev, im, sc['tr'], (i + 1) / trf) if i < trf else im).tobytes())
        prev = im
        if not quiet: print(f'scene {si + 1}/{len(scenes)} done', flush=True)
    pr.stdin.close(); pr.wait(); os.remove(wav) if False else None
    return out

def main():
    global K, FPS
    ap = argparse.ArgumentParser(); ap.add_argument('script', nargs='?'); ap.add_argument('out'); ap.add_argument('--fast', action='store_true'); ap.add_argument('--demo', action='store_true')
    a = ap.parse_args()
    if a.fast: K = 1.0
    if a.demo or not a.script: sc = demo()
    else: sc = runpy.run_path(a.script)['SCENES']
    make(sc, a.out)

# ---------------------------------------------------------------- demo
def demo():
    char('Rafa', shirt=(205, 30, 40), shorts=(250, 250, 250), socks=(205, 30, 40), skin='tan', hair='spiky', hc=(25, 20, 20), num=9)
    char('Leo', shirt=(40, 90, 220), shorts=(20, 40, 120), socks=(40, 90, 220), skin='light', hair='short', hc=(110, 70, 40), num=10)
    char('Max', shirt=(40, 170, 90), shorts=(30, 30, 40), socks=(40, 170, 90), skin='brown', hair='curly', hc=(25, 18, 15), num=1, acc=['gloves'], size=1.05)
    char('Coach', shirt=(40, 44, 70), skin='light', hair='short', hc=(150, 150, 150), outfit='suit', acc=['glasses', 'beard'], trim=(200, 40, 50))
    char('Anna', shirt=(200, 60, 120), skin='tan', hair='long', hc=(60, 35, 25), outfit='dress')
    char('Dev', shirt=(240, 130, 30), skin='brown', hair='turban', hc=(30, 20, 20), outfit='robe', hat=(240, 130, 30))
    GOAL = dict(night=True)
    S = []
    S.append(scene(2.6, 'tunnel', actors=[
        actor('Rafa', [(0, 500, 470), (2.6, 540, 650)], face=[(0, 'neutral'), (1.2, 'determined')]),
        actor('Leo', [(0, 700, 470), (2.6, 740, 650)], face=[(0, 'neutral'), (1.0, 'smug'), (1.9, 'determined')])],
        cam=dict(z=(1.0, 1.2)), cap='Derby night. Two rivals. One trophy.', emoji='trophy', crowd=(.2, .5), music='tense', sfx=[(0.1, 'drumroll', .5)]))
    S.append(scene(3.0, 'stadium', GOAL, actors=[
        actor('Rafa', [(0, 300, 520), (3.0, 760, 560)], face=[(0, 'happy'), (1.6, 'determined')], look='ball'),
        actor('Leo', [(0, 620, 540), (1.5, 560, 560), (3.0, 640, 600)], face=[(0, 'neutral'), (1.2, 'angry')], look='ball'),
        actor('Max', [(0, 1110, 470)], act=[(0, 'crouch')], face=[(0, 'neutral'), (2.0, 'worried')], fdir=[(0, -1)], look='ball')],
        props=[prop('ball', follow=('Rafa', 34, 4, 0), dribble=True)], cam=dict(follow='Rafa', z=(1.15, 1.3), lead=90), tr='whip',
        hud=hud('RED', 'BLU', 0, 0, "1'"), crowd=(.5, .75), sfx=[(0.2, 'whistle', 1.0), (0.3, 'cheer_s', .6)], cap='Kick-off! Rafa bursts forward!', emoji='fire'))
    S.append(scene(3.2, 'stadium', GOAL, actors=[
        actor('Rafa', [(0, 780, 560), (1.0, 820, 560), (3.2, 850, 560)], act=[(0, 'auto'), (1.0, 'kick'), (1.9, 'cheer')], face=[(0, 'determined'), (1.9, 'happy'), (2.5, 'joy')], look='ball'),
        actor('Leo', [(0, 640, 600), (1.2, 760, 590), (3.2, 790, 590)], act=[(1.9, 'angry')], face=[(0, 'angry'), (1.8, 'shock'), (2.4, 'cry')], look='ball'),
        actor('Max', [(0, 1110, 470), (1.15, 1110, 470), (1.75, 1075, 520)], act=[(0, 'crouch'), (1.2, 'dive'), (2.0, 'fall')], face=[(0, 'worried'), (1.2, 'panic'), (2.0, 'cry')], fdir=[(0, -1)], look='ball')],
        props=[prop('ball', path=[(0, 814, 562, 0), (1.12, 814, 562, 4), (1.4, 940, 520, 55), (1.8, 1100, 485, 62), (2.0, 1130, 480, 38), (2.3, 1130, 490, 0), (3.2, 1135, 494, 0)])],
        cam=dict(x=(700, 960), z=(1.05, 1.35)), fx=[fx(1.15, 'speed', d=.7), fx(1.9, 'flash', a=.6), fx(1.9, 'shake', amp=16)],
        crowd=(.6, 1.0), sfx=[(1.1, 'kick', 1.0), (1.35, 'whoosh', .5), (1.95, 'net', 1.0), (2.0, 'roar', 1.0), (2.05, 'horn', .5), (2.6, 'aww', .35)], cap=[(.2, 1.6, 'Rafa lines up the shot...', 'fire'), (1.9, 3.1, 'GOAL! The keeper had no chance!', 'ball')]))
    S.append(scene(3.2, 'stadium', GOAL, actors=[
        actor('Rafa', [(0, 600, 590), (3.2, 660, 600)], act=[(0, 'celebrate')], face=[(0, 'joy'), (1.6, 'laugh'), (2.6, 'proud')], look='cam'),
        actor('Leo', [(0, 780, 560)], act=[(0, 'sad')], face=[(0, 'cry'), (2.0, 'sad')], look='none'),
        actor('Max', [(0, 940, 520)], act=[(0, 'fall')], face=[(0, 'cry')], look='none')],
        cam=dict(follow='Rafa', z=(1.0, 1.45)), fx=[fx(0.0, 'confetti', d=3.2), fx(0.1, 'burst', text='GOAL!', x=640, y=210), fx(0.1, 'flash', a=.5), fx(1.4, 'sparkle', x=600, y=500)],
        hud=hud('RED', 'BLU', 1, 0, "12'"), crowd=1.0, music='epic', sfx=[(0, 'roar', 1.0), (0.2, 'applause', .8), (1.0, 'laugh', .4)], cap='1-0! Rafa celebrates while the stands go wild!', emoji='party', thumb=('GOAL!', 1.0)))
    S.append(scene(2.8, 'locker', actors=[
        actor('Coach', [(0, 620, 520)], act=[(0, 'talk'), (1.6, 'angry')], face=[(0, 'angry'), (1.5, 'determined')], say=[(0.2, 2.6)], fdir=[(0, -1)]),
        actor('Leo', [(0, 400, 570)], act=[(0, 'sad')], face=[(0, 'worried'), (1.4, 'shock')], look='cam'),
        actor('Max', [(0, 860, 570)], act=[(0, 'shrug')], face=[(0, 'worried'), (1.6, 'tired')], fdir=[(0, -1)], look='cam')],
        cam=dict(x=(560, 700), z=(1.05, 1.25)), tr='fade', hud=hud('RED', 'BLU', 1, 0, "45'"), crowd=.2, music='tense', sfx=[(0.3, 'growl', .5)], cap='Half-time: the coach is NOT happy...', emoji='angry'))
    S.append(scene(3.0, 'studio', dict(screen='FULL TIME  •  RED 2-1 BLU'), actors=[
        actor('Anna', [(0, 520, 560)], act=[(0, 'talk'), (1.8, 'point')], face=[(0, 'happy'), (1.2, 'awe'), (2.2, 'smug')], say=[(0.1, 2.7)]),
        actor('Rafa', [(0, 780, 560)], act=[(0, 'wave'), (1.8, 'cheer')], face=[(0, 'smug'), (1.5, 'laugh')], fdir=[(0, -1)], look='cam')],
        props=[prop('mic', follow=('Anna', 26, 0, 58), size=1.0), prop('trophy', follow=('Rafa', -30, 0, 36), size=1.2)],
        cam=dict(z=(1.0, 1.25), x=(640, 650)), tr='whip', crowd=.3, music='up', cap='Full time: Rafa lifts the derby trophy!', emoji='mic', sfx=[(0.1, 'ding', .5), (1.9, 'applause', .5)]))
    S.append(scene(2.8, 'city', dict(time='dusk'), actors=[
        actor('Leo', [(0, 380, 600), (2.8, 560, 620)], act=[(0, 'dance')], face=[(0, 'happy'), (1.4, 'laugh')]),
        actor('Anna', [(0, 760, 610), (2.8, 700, 620)], act=[(0, 'dance')], face=[(0, 'joy')], fdir=[(0, -1)])],
        props=[prop('balloon', path=[(0, 300, 560, 120), (2.8, 330, 560, 190)], col=(230, 60, 80)), prop('balloon', path=[(0, 900, 560, 100), (2.8, 880, 560, 170)], col=(60, 150, 230)), prop('flag', path=[(0, 1000, 600, 0)], col=(210, 40, 50))],
        cam=dict(z=(1.0, 1.15)), tr='fade', crowd=.5, music='up', cap='Fans dance through the city till sunset.', emoji='happy'))
    S.append(scene(2.6, 'village', dict(time='dusk', temple=True), actors=[
        actor('Dev', [(0, 700, 560)], act=[(0, 'namaste'), (1.5, 'bow')], face=[(0, 'proud'), (1.5, 'happy')], look='cam')],
        cam=dict(z=(1.0, 1.35), x=(660, 700)), tr='fade', crowd=.3, music='sad', cap='Same engine, any story: a village tale begins.', emoji='star'))
    return S

if __name__ == '__main__': main()
