"""Frame compositor: camera + parallax backgrounds + props + presenters + graphics + grade + transitions."""
from __future__ import annotations

import functools
import math
import multiprocessing as mp
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import skia

from . import backgrounds, overlays, people, props
from .gfx import Grade, P, R, clamp, ease, eout, grain_images, surface, vignette

LW, LH = 1280, 720
ZOOM = {"wide": 1.0, "medium_wide": 1.1, "medium": 1.28, "medium_close": 1.55, "close_up": 1.9}
POS_X = {"left": .27, "center": .5, "right": .73}
DEFAULTS = [{"outfit": "suit", "hair": "short", "skin": "light"}, {"outfit": "casual", "hair": "long", "skin": "tan"},
            {"outfit": "kit", "hair": "cap", "skin": "light"}, {"outfit": "suit", "hair": "bald", "skin": "dark", "acc": ["glasses"]}]
SPEED = {"walk": 230.0, "run": 560.0}


class Renderer:
    def __init__(self, plan, out_w=LW, out_h=LH):
        self.plan, self.fps = plan, plan["fps"]
        self.W, self.H = out_w, out_h
        self.scenes, self.shots = plan["scenes"], plan["shots"]
        self.cast = plan.get("cast", {})
        self.bounds = []
        f = 0
        for sh in self.shots:
            self.bounds.append((f, f + sh["frames"], sh))
            f += sh["frames"]
        self.total = f
        self.scene_start = {}
        for a, b, sh in self.bounds:
            self.scene_start.setdefault(sh["scene_index"], a)
        self.scene_end = {}
        for a, b, sh in self.bounds:
            self.scene_end[sh["scene_index"]] = b
        self.grain = grain_images(LW, LH)
        self._bg = {}
        self.surf = surface(out_w, out_h)

    # --- helpers ---------------------------------------------------------------------------
    def _background(self, sc):
        key = (sc.get("bg") or sc.get("location") or "sky", sc.get("time") or sc.get("time_of_day") or "day", sc.get("weather", "none"), sc.get("mood"))
        if key not in self._bg:
            if len(self._bg) >= 2:
                self._bg.pop(next(iter(self._bg)))
            kind, tod, wx, mood = key
            tod = {"sunrise": "sunrise", "sunset": "sunset"}.get(tod, tod)
            grade = Grade(tod if tod in Grade.TOD else "day", mood if mood in Grade.MOOD else "calm", wx)
            self._bg[key] = (backgrounds.build(kind, tod if tod in backgrounds.SKY else "day", wx, LW, LH, grade), grade)
        return self._bg[key]

    def _spec(self, name, i):
        sp = dict(self.cast.get(name) or DEFAULTS[i % len(DEFAULTS)])
        return sp

    def _actors(self, sc):
        acts = sc.get("actors")
        if acts:
            out = [dict(a) for a in acts]
        else:
            out = [{"name": n, "action": sc.get("action", "idle"), "pos": "center"} for n in (sc.get("characters") or ["Protagonist"])]
            if len(out) == 2:
                out[0]["pos"], out[1]["pos"] = "left", "right"
            elif len(out) == 3:
                out[0]["pos"], out[1]["pos"], out[2]["pos"] = "center", "left", "right"
        return out[:3]

    # --- frame ------------------------------------------------------------------------------
    def frame(self, i):
        i = min(i, self.total - 1)
        shot = next(s for a, b, s in self.bounds if a <= i < b)
        a0, a1 = next((a, b) for a, b, s in self.bounds if s is shot)
        sc = self.scenes[shot["scene_index"]]
        fps = self.fps
        t = (i - self.scene_start[shot["scene_index"]]) / fps
        T = (self.scene_end[shot["scene_index"]] - self.scene_start[shot["scene_index"]]) / fps
        u = clamp(t / max(T, .01))
        (bg, grade), G = self._background(sc), None
        G = grade.c
        mood = sc.get("mood", "calm")
        c = self.surf.getCanvas()
        c.resetMatrix(); c.clear(skia.ColorBLACK)
        c.scale(self.W / LW, self.H / LH)
        trans = sc.get("transition", "cut") if t < .5 else "cut"
        if trans == "whip" and t < .3:
            k = 1 - t / .3
            c.saveLayer(None, skia.Paint(ImageFilter=skia.ImageFilters.Blur(60 * k * k, 0.01)))
            c.translate(-LW * .18 * k, 0)
        actors = self._actors(sc)
        lead = next((a for a in actors if a.get("action") in SPEED), None)
        direction = (-1 if (lead or {}).get("pos") == "right" else 1)
        scroll = direction * SPEED[lead["action"]] * t if lead else 0.0
        S = 385.0
        gy = bg["ground"] + 6 + (LH - bg["ground"]) * .22
        base = ZOOM.get(shot["camera"]["shot_type"], 1.2)
        move = sc.get("camera") or {"push_in": "zoom_in", "pull_back": "zoom_out", "tracking": "follow", "slow_pan": "pan_right"}.get(shot["camera"]["move"], "static")
        z = base * (1 + {"zoom_in": .22 * u, "zoom_out": .2 * (1 - u), "follow": .05, "shake": .04}.get(move, .03 * u))
        pan = {"pan_right": 1, "pan_left": -1}.get(move, 0) * .14 * LW * (u - .5)
        subj = actors[0]
        sx = POS_X.get(subj.get("pos", "center"), .5) * LW
        fx, fy = sx, gy - S * (.55 if base < 1.4 else .82)
        shake = 0
        if move == "shake" or "shake" in (sc.get("fx") or []):
            shake = 9 * math.exp(-t * 1.2) + (3 if move == "shake" else 0)
        c.save()
        c.translate(fx + math.sin(t * 47) * shake, fy + math.cos(t * 53) * shake)
        c.scale(z, z); c.translate(-fx, -fy)
        cam_x = scroll + pan
        L, ss = bg["L"], bg["ss"]
        samp = skia.SamplingOptions(skia.FilterMode.kLinear)
        layers = bg["layers"]
        for img, par in layers[:-1] if layers[-1][1] > 1 else layers:
            self._blit(c, img, par, cam_x, L, ss, samp)
        smoke_on = "smoke" in (sc.get("fx") or []) or bg["kind"] == "battlefield"
        if smoke_on:
            overlays.smoke(c, LW, LH, bg["ground"], t)
        for k, pr in enumerate(sc.get("props") or []):
            wx = POS_X["left"] * LW - 100 if pr.get("where") == "left" else LW * .83 if pr.get("where") == "right" else LW * .5
            overlays_ = pr
            props.draw_prop(c, pr, k, wx - cam_x * .6, gy - 10, LW, LH, t, G, (t - .15 * k) / .5)
        order = sorted(range(len(actors)), key=lambda k: -(1 if actors[k].get("pos") == "center" and len(actors) > 1 else 0))
        for k in order:
            ac = actors[k]
            pos = ac.get("pos", "center")
            x = POS_X.get(pos, .5) * LW
            fac = -1 if pos == "right" else 1
            if len(actors) == 1 and pos == "center":
                fac = direction if lead else 1
            faces = ac.get("face") or []
            face = (faces[0] if isinstance(faces, list) and faces else faces if isinstance(faces, str) else None) or people.EMO_FACE.get(sc.get("emotion"), "neutral")
            if sc.get("actors") is None and sc.get("emotion") in people.FACES:
                face = sc["emotion"]
            act = ac.get("action", "idle")
            speak = bool(ac.get("speaks")) or act in ("talk", "point")
            sp = self._spec(ac["name"], k)
            sc_ = S * (.9 if (pos == "center" and len(actors) > 1) else 1)
            drift = -cam_x if (lead is not None and ac is not lead and ac.get("action") not in SPEED) else 0
            people.draw_person(c, sp, x + drift, gy - (14 if sc_ < S else 0), sc_, t + k * .7, fac, act, face, speak, grade.soft)
            if act == "sign":
                c.drawRoundRect(R(x - 130, gy - S * .33, 260, S * .12), 6, 6, P(G((92, 62, 40))))
                c.drawRect(R(x - 150, gy - S * .33, 300, 14), P(G((120, 82, 52))))
        if layers[-1][1] > 1:
            self._blit(c, layers[-1][0], layers[-1][1], cam_x, L, ss, samp, alpha=235)
        c.restore()
        overlays.particles(c, LW, LH, sc.get("weather", "none"), t)
        fxs = sc.get("fx") or []
        if "confetti" in fxs:
            overlays.confetti(c, LW, LH, t)
        if "speed" in fxs or move == "shake" and False:
            overlays.speed_lines(c, LW, LH, t)
        # light grade, grain, vignette
        c.drawRect(R(0, 0, LW, LH), P(tuple(int(120 + 100 * v) for v in grade.tint), 26, blend=skia.BlendMode.kSoftLight))
        vignette(c, LW, LH, grade.vig)
        c.drawImage(self.grain[i % len(self.grain)], 0, 0, samp, P(a=34, blend=skia.BlendMode.kSoftLight))
        if trans == "whip" and t < .3:
            c.restore()
        # graphics
        tag, titles = sc.get("tag"), [f[6:] for f in (sc.get("fx") or []) if f.startswith("title:")]
        win = min(T, 3.6)
        if titles:
            overlays.title_card(c, LW, LH, titles[0], t, win + .4, mood)
        elif tag:
            overlays.tag_chip(c, LW, LH, str(tag), t, min(T, 4.2), mood)
        if titles and tag:
            overlays.tag_chip(c, LW, LH, str(tag), t, min(T, 4.2), mood)
        si = shot["scene_index"]
        prev = {a.get("name") for a in self._actors(self.scenes[si - 1])} if si > 0 else set()
        for ac in actors[:1]:
            if ac["name"] not in prev and ac["name"] not in ("Protagonist", "Narrator"):
                role = (self.plan.get("roles") or {}).get(ac["name"], "")
                overlays.lower_third(c, LW, LH, ac["name"], role, t, min(T, 3.2), mood)
        if not self.plan.get("no_captions"):
            overlays.captions(c, LW, LH, str(sc.get("text", "")), t, T, mood)
        if trans == "flash" and t < .3:
            c.drawRect(R(0, 0, LW, LH), P((255, 255, 255), 255 * (1 - t / .3) ** 2))
        elif trans == "fade" and t < .45:
            c.drawRect(R(0, 0, LW, LH), P((0, 0, 0), 255 * (1 - t / .45)))
        if i < fps * .6 and si == 0:
            c.drawRect(R(0, 0, LW, LH), P((0, 0, 0), 255 * (1 - i / (fps * .6))))
        if self.total - i < fps * .9:
            c.drawRect(R(0, 0, LW, LH), P((0, 0, 0), 255 * (1 - (self.total - i) / (fps * .9))))
        return self.surf.makeImageSnapshot()

    @staticmethod
    def _blit(c, img, par, cam_x, L, ss, samp, alpha=255):
        ox = -((cam_x * par) % L)
        c.save(); c.scale(1 / ss, 1 / ss)
        for x in (ox - L, ox, ox + L):
            if x + L > -200 and x < LW + 200:
                c.drawImage(img, x * ss, 0, samp, P(a=alpha) if alpha != 255 else None)
        c.restore()

    def frame_bytes(self, i):
        return self.frame(i).toarray(colorType=skia.kRGBA_8888_ColorType).tobytes()


_R = None


def _init(plan, w, h):
    global _R
    _R = Renderer(plan, w, h)


def _job(i):
    return _R.frame_bytes(i)


def render_video(plan, out_path, size=(1280, 720), workers=None, log=print):
    """Render the plan to a silent H.264 MP4 via an FFmpeg raw-frame pipe."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found in PATH (winget install Gyan.FFmpeg).")
    w, h = size
    total = sum(s["frames"] for s in plan["shots"])
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}", "-r", str(plan["fps"]), "-i", "-",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    workers = workers if workers is not None else max(1, min((os.cpu_count() or 2) - 1, 6))
    try:
        if workers <= 1 or total < 48:
            r = Renderer(plan, w, h)
            frames = (r.frame_bytes(i) for i in range(total))
            for n, b in enumerate(frames):
                proc.stdin.write(b)
                if n % 120 == 0:
                    log(f"[render] frame {n}/{total}")
        else:
            with mp.get_context("spawn").Pool(workers, _init, (plan, w, h)) as pool:
                for n, b in enumerate(pool.imap(_job, range(total), chunksize=6)):
                    proc.stdin.write(b)
                    if n % 120 == 0:
                        log(f"[render] frame {n}/{total}")
        proc.stdin.close()
    except BrokenPipeError:
        pass
    if proc.wait():
        raise RuntimeError("FFmpeg failed while encoding the rendered frames.")
