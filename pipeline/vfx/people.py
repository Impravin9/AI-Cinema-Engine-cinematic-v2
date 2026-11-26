"""Rigged flat-vector presenters: proportioned body, outfits, hair, expressive faces, action poses.

Drawn in unit space (height = 1, feet at origin, facing +x; mirrored for facing left).
Angles are measured from 'straight down', positive toward the facing side.
"""
from __future__ import annotations

import math

import skia

from .gfx import P, R, clamp, lg, mix, rg, shade

SKIN = {"light": (242, 201, 165), "tan": (214, 160, 108), "yellow": (240, 208, 128), "dark": (141, 92, 62), "brown": (176, 120, 80)}
OUTFIT = {"suit": dict(top=(40, 46, 62), pants=(34, 38, 50), shirt=(240, 240, 236), tie=(150, 38, 44), long=True),
          "kit": dict(top=(74, 86, 70), pants=(58, 66, 56), shirt=(74, 86, 70), tie=None, long=True, belt=True),
          "casual": dict(top=(58, 122, 150), pants=(52, 58, 74), shirt=(58, 122, 150), tie=None, long=False)}
# face: (brow_dy, brow_angle(+ = inner down), lid, mouth_curve, mouth_width, mouth_open, eye_scale, smirk)
FACES = {"neutral": (0, 0, .05, 0, .6, 0, 1, 0), "determined": (.004, 12, .12, .12, .55, 0, .95, 0),
         "worried": (-.008, -15, .05, -.4, .5, 0, 1.05, 0), "smug": (-.004, -8, .38, .5, .6, 0, 1, 1),
         "sad": (-.004, -17, .28, -.6, .5, 0, 1, 0), "angry": (.012, 24, .18, -.3, .75, .15, .95, 0),
         "tired": (.006, -6, .55, -.1, .5, 0, 1, 0), "shock": (-.02, 0, 0, 0, .35, .95, 1.3, 0),
         "happy": (-.006, -4, .18, .85, .85, .3, 1, 0), "smile": (-.004, -3, .12, .6, .7, 0, 1, 0),
         "proud": (-.008, -4, .22, .55, .7, 0, 1, 0), "panic": (-.022, -13, 0, -.2, .55, .85, 1.35, 0),
         "think": (.006, 8, .12, 0, .4, 0, 1, 0)}
EMO_FACE = {"shock": "shock", "sad": "sad", "think": "think", "angry": "angry", "awe": "shock", "proud": "proud",
            "neutral": "neutral", "panic": "panic", "joy": "happy", "fear": "worried", "sadness": "sad", "anger": "angry",
            "curiosity": "think", "determined": "determined"}
ACTIONS = {"stand": "idle", "idle": "idle", "walk": "walk", "run": "run", "point": "point", "think": "think", "crouch": "crouch",
           "sign": "sign", "smirk": "smirk", "sad": "sad", "talk": "talk", "angry": "angry", "shock": "shock",
           "celebrate": "celebrate", "speak": "talk", "react": "shock", "fall": "crouch", "observe": "idle"}


def pose(action, t):
    s = math.sin
    p = dict(dx=0, dy=0, lean=0, tilt=0, aB=(.06, .1), aF=(.06, .1), lB=(0, 0), lF=(0, 0), gaze=0, body=0)
    p["aB"] = (.05 + .03 * s(t * 1.3), .1)
    p["aF"] = (.07 + .03 * s(t * 1.3 + 1), .12)
    if action in ("walk", "run"):
        run = action == "run"
        ph = t * 2 * math.pi * (1.45 if run else .95)
        A, K, bob = (.95, 1.15, .02) if run else (.5, .7, .01)
        for key, o in (("lF", 0), ("lB", math.pi)):
            th = A * s(ph + o)
            p[key] = (th, th - K * max(0, math.cos(ph + o)))
        sw = .85 if run else .5
        p["aB"], p["aF"] = (sw * s(ph) , (1.7 if run else .3) + sw * s(ph) * .3), (-sw * s(ph), (1.7 if run else .3) - sw * s(ph) * .3)
        p["dy"] = -bob * abs(s(ph)); p["lean"] = .2 if run else .04; p["gaze"] = .5
    elif action == "point":
        p["aF"] = (1.35 + .05 * s(t * 3), 1.45); p["aB"] = (.35, -.9); p["lean"] = .06; p["gaze"] = .6
    elif action == "think":
        p["aF"] = (.95, 2.55); p["aB"] = (.45, 1.6); p["tilt"] = .09 + .02 * s(t); p["gaze"] = -.2
    elif action == "crouch":
        p["dy"] = .15; p["lean"] = .38; p["lB"] = (1.05, -.1); p["lF"] = (1.25, -.05)
        p["aF"] = (1.5, 1.9); p["aB"] = (1.3, 1.9); p["tilt"] = .12
    elif action == "sign":
        p["lean"] = .26; p["aF"] = (.8 + .08 * s(t * 4), 1.0 + .1 * s(t * 4)); p["aB"] = (.6, .9); p["tilt"] = .2
    elif action == "smirk":
        p["aB"] = (.55, 1.7); p["aF"] = (.55, 1.7); p["tilt"] = -.07; p["lean"] = -.03
    elif action == "sad":
        p["lean"] = .1; p["tilt"] = .27; p["aB"] = (.0, .05); p["aF"] = (.04, .08); p["dy"] = .01
    elif action == "talk":
        p["aF"] = (.65 + .45 * s(t * 2.7), 1.2 + .5 * s(t * 2.7 + .6)); p["aB"] = (.3 + .2 * s(t * 2.1 + 1), .9); p["tilt"] = .03 * s(t * 1.7)
    elif action == "angry":
        p["aF"] = (.8 + .05 * s(t * 14), 1.8); p["aB"] = (.8 + .05 * s(t * 13), 1.8); p["lean"] = .1; p["dx"] = .004 * s(t * 18)
    elif action == "shock":
        p["aF"] = (.75, 1.0); p["aB"] = (.75, 1.0); p["lean"] = -.1; p["tilt"] = -.1; p["dx"] = -.02
    elif action == "celebrate":
        p["aF"] = (2.6 + .15 * s(t * 8), 2.75); p["aB"] = (2.6 - .15 * s(t * 8), 2.75); p["dy"] = -.05 * abs(s(t * 6)); p["tilt"] = -.05
    return p


def _head(c, sp, face, speak, t, G):
    skin = G(SKIN.get(sp.get("skin", "light"), SKIN["light"]))
    hairc = G(tuple(sp.get("haircolor", (48, 36, 30))))
    rx, ry, hs = .085, .1, sp.get("hair", "short")
    bd, ba, lid, mc, mw, mo, es, smirk = FACES.get(face, FACES["neutral"])
    cx = .012  # three-quarter turn toward facing side
    if hs == "long":
        c.drawRoundRect(R(-rx * 1.12, -ry * .8, rx * 2.24, ry * 2.5), .06, .06, P(hairc))
    c.drawOval(R(-rx - .006, -.012, .014, .03), P(skin))
    c.drawOval(R(rx - .012, -.012, .014, .03), P(shade(skin, .9)))
    c.drawOval(R(-rx, -ry, rx * 2, ry * 2), P(shader=lg(-rx, 0, rx, 0, [(0, shade(skin, 1.06)), (1, shade(skin, .9))])))
    c.drawOval(R(cx + .03, .035, .02, .014), P((226, 120, 112), 70, blur=.006))
    for ex in (-.03, .04):
        e = R(ex + cx - .02, -.022 - .016 * es, .04, .032 * es)
        path = skia.Path(); path.addOval(e)
        c.save(); c.clipPath(path, skia.ClipOp.kIntersect, True)
        c.drawRect(e, P((250, 250, 246)))
        gx = cx + ex + .004 * (1 if True else 0) + .003
        c.drawCircle(gx, -.006, .0125, P((70, 52, 40)))
        c.drawCircle(gx, -.006, .0062, P((12, 10, 10)))
        c.drawCircle(gx - .004, -.011, .0035, P((255, 255, 255)))
        L_ = clamp(lid + (1 if (t % 3.6) < .13 else 0))
        c.drawRect(R(e.left() - .004, e.top() - .004, e.width() + .008, (e.height() + .004) * L_), P(shade(skin, .98)))
        c.restore()
        c.drawLine(e.left(), e.top() + e.height() * L_, e.right(), e.top() + e.height() * L_, P((60, 44, 38), 200, stroke=.0035))
        by = -.062 + bd
        ox, ix = (cx + ex - .023, cx + ex + .021) if ex < 0 else (cx + ex + .023, cx + ex - .021)
        c.drawLine(ox, by - ba * .0009, ix, by + ba * .0009, P(hairc if hs != "bald" else shade(skin, .55), 245, stroke=.008))
    c.drawPath(_arc(cx + .004, .02, .012, .018), P(shade(skin, .78), 190, stroke=.0035))
    my = .058
    sm = .012 * smirk
    if mo > .05 or speak:
        o = max(mo, speak) * .036
        c.drawOval(R(cx - mw * .02, my - o * .3, mw * .04, o + .006), P((70, 22, 28)))
        c.drawOval(R(cx - mw * .014, my + o * .35, mw * .028, o * .45), P((200, 84, 90)))
    else:
        p = skia.Path(); p.moveTo(cx - mw * .03, my + sm * .3); p.quadTo(cx, my + mc * .028, cx + mw * .03, my - sm)
        c.drawPath(p, P((120, 52, 52), 255, stroke=.005))
    if "mustache" in sp.get("acc", ()):
        p = skia.Path(); p.moveTo(cx - .026, .042); p.quadTo(cx, .034, cx + .026, .042); p.quadTo(cx, .052, cx - .026, .042)
        c.drawPath(p, P(hairc))
    if "glasses" in sp.get("acc", ()):
        for ex in (-.03, .04):
            c.drawCircle(cx + ex, -.006, .028, P((40, 40, 46), 230, stroke=.0045))
        c.drawLine(cx + .01, -.008, cx + .02, -.008, P((40, 40, 46), 230, stroke=.0045))
    if hs in ("short", "long"):
        p = skia.Path(); p.moveTo(-rx * 1.02, -.01); p.cubicTo(-rx * 1.1, -ry * 1.12, rx * 1.05, -ry * 1.2, rx * 1.02, -.01)
        p.cubicTo(rx * .9, -ry * .55, rx * .5, -ry * .62, -rx * .15, -ry * .7); p.cubicTo(-rx * .6, -ry * .55, -rx * .85, -ry * .4, -rx * 1.02, -.01)
        c.drawPath(p, P(shader=lg(-rx, -ry, rx, 0, [(0, shade(hairc, 1.25)), (1, shade(hairc, .8))])))
    elif hs == "cap":
        capc = G((70, 80, 66)) if sp.get("outfit") == "kit" else G((50, 52, 60))
        p = skia.Path(); p.moveTo(-rx * 1.05, -ry * .42); p.cubicTo(-rx * 1.0, -ry * 1.5, rx * 1.0, -ry * 1.5, rx * 1.05, -ry * .42); p.close()
        c.drawPath(p, P(shader=lg(-rx, 0, rx, 0, [(0, shade(capc, 1.15)), (1, shade(capc, .8))])))
        c.drawRect(R(-rx * 1.07, -ry * .5, rx * 2.14, ry * .2), P(shade(capc, .62)))
        c.drawOval(R(rx * .2, -ry * .5, rx * 1.35, ry * .2), P(shade(capc, .5)))
        c.drawCircle(cx + .02, -ry * .72, .009, P(G((214, 186, 90))))
    elif hs == "bald":
        c.drawOval(R(-rx * .3, -ry * .92, rx * .7, ry * .3), P((255, 255, 255), 70, blur=.01))


def _arc(x, y, w, h):
    p = skia.Path(); p.moveTo(x - w, y); p.quadTo(x - w * .2, y + h, x + w * .6, y + h * .5)
    return p


def draw_person(c, sp, x, gy, S, t, facing, action, face, speak, G, shadow=True):
    o = OUTFIT.get(sp.get("outfit", "casual"), OUTFIT["casual"])
    top = G(tuple(sp["shirt"]) if sp.get("shirt") and sp.get("outfit") != "suit" else o["top"])
    pants, skin = G(o["pants"]), G(SKIN.get(sp.get("skin", "light"), SKIN["light"]))
    pz = pose(ACTIONS.get(action, "idle"), t)
    sleeve = top if o["long"] else skin
    c.save(); c.translate(x + pz["dx"] * S, gy); c.scale(facing * S, S)
    if shadow:
        c.drawOval(R(-.2, -.014, .4, .034), P((0, 0, 0), 85, blur=.014))
    hip = -.44 + pz["dy"]
    # legs
    for key, sx in (("lB", -.045), ("lF", .045)):
        a1, a2 = pz[key]
        kx, ky = sx + .21 * math.sin(a1), hip + .21 * math.cos(a1)
        ax, ay = kx + .2 * math.sin(a2), ky + .2 * math.cos(a2)
        ay = min(ay, -.03 + (pz["dy"] if pz["dy"] > 0 else 0) * 0)
        c.drawLine(sx, hip, kx, ky, P(pants, stroke=.085)); c.drawLine(kx, ky, ax, ay, P(shade(pants, .92), stroke=.07))
        c.drawRoundRect(R(ax - .03, ay - .006, .11, .04), .02, .02, P((28, 26, 28)))
    c.save(); c.translate(0, hip + pz["dx"] * 0); c.rotate(math.degrees(pz["lean"]))
    # back arm
    def arm(key, sx):
        a1, a2 = pz[key]
        a1, a2 = a1 - pz["lean"], a2 - pz["lean"]
        sh_ = (sx, -.3)
        ex_, ey_ = sh_[0] + .17 * math.sin(a1), sh_[1] + .17 * math.cos(a1)
        hx_, hy_ = ex_ + .15 * math.sin(a2), ey_ + .15 * math.cos(a2)
        c.drawLine(sh_[0], sh_[1], ex_, ey_, P(top, stroke=.058)); c.drawLine(ex_, ey_, hx_, hy_, P(sleeve, stroke=.05))
        c.drawCircle(hx_, hy_, .027, P(skin))
    arm("aB", -.1)
    # torso + outfit
    p = skia.Path(); p.moveTo(-.105, -.3); p.quadTo(-.12, -.15, -.088, .045); p.lineTo(.088, .045); p.quadTo(.12, -.15, .105, -.3); p.quadTo(0, -.33, -.105, -.3); p.close()
    c.drawPath(p, P(shader=lg(-.1, 0, .1, 0, [(0, shade(top, 1.14)), (.6, top), (1, shade(top, .78))])))
    if sp.get("outfit", "casual") == "suit":
        c.drawPath(_tri(-.032, -.31, .032, -.31, 0, -.15), P(o["shirt"]))
        if o["tie"]:
            c.drawPath(_tri(-.01, -.3, .01, -.3, 0, -.1), P(G(sp.get("tie", o["tie"]))))
        c.drawPath(_tri(-.032, -.31, -.075, -.29, -.01, -.14), P(shade(top, .8)))
        c.drawPath(_tri(.032, -.31, .075, -.29, .01, -.14), P(shade(top, .7)))
    elif sp.get("outfit") == "kit":
        c.drawRect(R(-.09, -.045, .18, .03), P(G((92, 66, 40)))); c.drawRect(R(-.014, -.047, .028, .034), P(G((214, 186, 90))))
        for sx in (-.06, .03):
            c.drawRect(R(sx, -.24, .03, .035), P(shade(top, .8)))
        c.drawPath(_tri(-.03, -.31, 0, -.27, .03, -.31), P(shade(top, 1.25)))
    else:
        p2 = skia.Path(); p2.moveTo(-.04, -.31); p2.quadTo(0, -.26, .04, -.31)
        c.drawPath(p2, P(shade(top, .7), stroke=.008))
    c.drawRect(R(-.017, -.34, .034, .05), P(shade(skin, .92)))
    # head
    c.save(); c.translate(0, -.355 - .118); c.rotate(math.degrees(pz["tilt"])); c.scale(1.32, 1.32)
    _head(c, sp, face if face in FACES else "neutral", clamp(abs(math.sin(t * 9.3)) * abs(math.sin(t * 2.3 + .7)) * 1.15) if speak else 0, t, G)
    c.restore()
    arm("aF", .1)
    c.restore(); c.restore()
    return -(1 - .0) * S


def _tri(x0, y0, x1, y1, x2, y2):
    p = skia.Path(); p.moveTo(x0, y0); p.lineTo(x1, y1); p.lineTo(x2, y2); p.close()
    return p
