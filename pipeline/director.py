"""Stage 2 - Cinematic director: phrase segmentation, archetype layouts, camera, frame-exact timing."""
from __future__ import annotations

import random
import re
from pathlib import Path

from cinematic_director import direct_scene
from .variety import LAYOUT, NUM, QUOTE, YEAR, assign_archetypes

_PLACE = re.compile(r"\b(?:in|at|to|near|from|across|inside)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)")
_SPLIT = re.compile(r",|;|\band\b|\bthen\b|\bbecause\b|\bleading to\b|\bwhich\b|\bso\b|\bbut\b", re.I)
_CONTRAST = re.compile(r"\b(while|whereas|but|versus|vs\.?|than|compared to|unlike)\b", re.I)
TITLE_SECONDS = 3.2
INFO = ("stat", "timeline", "quote", "title", "chart", "split", "doc", "flow")


def estimate_duration(text: str, minimum: float = 2.2) -> float:
    return min(14.0, max(minimum, len(text.split()) / 2.6 + 0.8))


def segment(scenes, max_words: int = 14):
    """Break scenes into timed phrase segments; each inherits story metadata, keeps `parent` scene index."""
    out = []
    for p, sc in enumerate(scenes):
        phrases = []
        for sent in re.split(r"(?<=[.!?])\s+", str(sc["text"]).strip()):
            if len(sent.split()) <= max_words:
                phrases.append(sent)
                continue
            buf = ""
            for part in re.split(r"(?<=,)\s+|\s+(?=(?:but|while|and then|because|which)\b)", sent):
                if buf and len((buf + " " + part).split()) > max_words:
                    phrases.append(buf)
                    buf = part
                else:
                    buf = (buf + " " + part).strip()
            if buf:
                phrases.append(buf)
        merged: list[str] = []
        for ph in phrases:
            if merged and len(ph.split()) < 4:
                merged[-1] += " " + ph
            else:
                merged.append(ph)
        for k, ph in enumerate(merged):
            out.append({**sc, "text": ph, "parent": p, "first_in_parent": k == 0,
                        "location_changed": bool(sc.get("location_changed")) and k == 0})
    return out


_STOPS = {"to", "of", "at", "from", "by", "in", "and", "the", "a", "an", "while", "with", "for", "than", "it", "had", "was", "were", "is"}


def _trim(words, n=6, tail=False):
    w = [x.strip(".,;:") for x in words if x.strip(".,;:")]
    while w and w[-1].lower() in _STOPS:
        w.pop()
    while w and w[0].lower() in _STOPS:
        w.pop(0)
    return " ".join(w[-n:] if tail else w[:n])


def _extras(arch, text, years, flat, nums, rng):
    vals = [float(m.group(1).replace(",", "")) for m in nums]
    if arch == "metric_counter":
        m = nums[0]
        return {"stat": {"value": vals[0], "unit": m.group(2) or "", "label": " ".join(flat[m.end():].split()[:6]) or text[:60],
                         "bars": [.25, .4, .55, .75, 1.0]}}
    if arch == "animated_chart":
        if len(vals) >= 3:
            series = vals[:6]
        elif len(vals) == 2:
            series = [vals[0] + (vals[1] - vals[0]) * k / 4 for k in range(5)]
        else:
            series = [vals[0] * f for f in (.35, .5, .62, .78, .9, 1.0)]
        labels = [str(y) for y in years[:len(series)]] if len(years) == len(series) else [""] * len(series)
        title = _trim(flat[:nums[0].start()].split(), 7, True) or _trim(flat[nums[0].end():].split(), 7) or "Trend"
        return {"chart": {"kind": rng.choice(("line", "bar", "area")), "values": series, "labels": labels, "title": title}}
    if arch == "historical_timeline":
        return {"years": years[:5]}
    if arch == "split_comparison":
        if len(nums) >= 2:
            lt, rt = flat[:nums[0].start()].split(), flat[nums[0].end():nums[1].start()].split()
            return {"left": {"label": _trim(lt, 5, True) or "Before", "value": vals[0]},
                    "right": {"label": _trim(rt, 5, True) or "After", "value": vals[1]}}
        else:
            # A split-comparison archetype can be selected by the variety engine
            # for words such as "compared" or "instead", which are not all covered
            # by this module's contrast regex. Never assume a contrast match exists.
            m = _CONTRAST.search(text)
            if m:
                left, right = text[:m.start()], text[m.end():]
            else:
                words = text.split()
                midpoint = max(1, len(words) // 2)
                left, right = " ".join(words[:midpoint]), " ".join(words[midpoint:])
        left_label = _trim(left.split(), 8, True) or "Context"
        right_label = _trim(right.split(), 8) or "Comparison"
        return {"left": {"label": left_label, "value": None}, "right": {"label": right_label, "value": None}}
    if arch == "kinetic_quote":
        q = QUOTE.search(text)
        return {"quote": q.group(1) if q else text, "is_quote": bool(q)}
    if arch == "document_zoom":
        hl = nums[0].group(0).strip() if nums else max(text.split(), key=len).strip(".,")
        tag = str(years[0]) if years else "FILE"
        return {"doc": {"title": f"Official record \u00b7 {tag}", "text": text, "hl": hl}}
    if arch == "concept_flow":
        chunks = [c.strip() for c in _SPLIT.split(text) if len(c.split()) >= 1]
        if len(chunks) < 3:
            w = text.split()
            k = max(1, len(w) // 3)
            chunks = [" ".join(w[i:i + k]) for i in range(0, len(w), k)][:4]
        return {"nodes": [_trim(c.split(), 4) or c for c in chunks[:4]]}
    return {}


def _camera(layout, role, emotion, intensity, action, i):
    d = 1 if i % 2 == 0 else -1
    if role == "establishing" or layout == "map":
        return {"zoom": (1.16, 1.0), "pan": (.05 * d, -.05 * d), "drift": 0.0}
    if layout == "timeline":
        return {"zoom": (1.0, 1.1), "pan": (-.1 * d, .1 * d), "drift": 0.0}
    if layout in INFO:
        return {"zoom": (1.0, 1.08), "pan": (0, .02 * d), "drift": 0.0}
    if action in ("run", "walk"):
        return {"zoom": (1.04, 1.12), "pan": (-.07 * d, .07 * d), "drift": 0.0}
    if emotion in ("fear", "anger") or intensity >= .7:
        return {"zoom": (1.0, 1.22), "pan": (0, .03 * d), "drift": -.02}
    if emotion == "sadness":
        return {"zoom": (1.14, 1.0), "pan": (0, 0), "drift": .02}
    if emotion == "curiosity":
        return {"zoom": (1.0, 1.15), "pan": (.03 * d, -.03 * d), "drift": 0.0}
    return {"zoom": (1.03, 1.1), "pan": (-.03 * d, .03 * d), "drift": 0.0}


def _plate(media_dir, i):
    if media_dir:
        for ext in ("jpg", "jpeg", "png", "webp"):
            p = Path(media_dir) / f"scene_{i + 1:03d}.{ext}"
            if p.is_file():
                return str(p)
    return None


def build_shots(scenes, bible, title, roles=None, media_dir=None, archetypes=None, seed=0):
    roles, rng = roles or {}, random.Random(seed)
    archetypes = archetypes or assign_archetypes([s["text"] for s in scenes], rng)
    first = scenes[0] if scenes else {}
    shots = [{"id": "s000", "scene_index": -1, "parent": -1, "role": "title", "layout": "title", "archetype": None,
              "text": title, "share": 1.0, "location": first.get("location", "landscape"),
              "time_of_day": first.get("time_of_day", "dusk"), "emotion": "determined", "characters": [], "subject": None,
              "action": "observe", "direction": 1, "fx": [], "camera": _camera("title", "title", "determined", 0, "observe", 0),
              "tag": None, "scene_est": TITLE_SECONDS}]
    seen: set[str] = set()
    for i, sc in enumerate(scenes):
        d = direct_scene(sc, i)
        text, arch = d["text"], archetypes[i]
        years = sorted({int(y) for y in YEAR.findall(text)})
        flat = YEAR.sub(" ", text)
        nums = list(NUM.finditer(flat))
        pm = _PLACE.search(text)
        place = pm.group(1) if pm and pm.group(1) not in (d.get("characters") or []) else None
        layout, extra = LAYOUT[arch], _extras(arch, text, years, flat, nums, rng)
        dur = estimate_duration(text, 2.2 if layout == "hero" else 3.0)
        tag = place or (str(years[0]) if len(years) == 1 else None)
        chips = [c for c in ([nums[0].group(0).strip()] if nums else []) + [str(y) for y in years[:1]] if c][:2]
        parent = sc.get("parent", i)
        lt, subj = None, d.get("subject")
        if (subj and subj != "Protagonist" and subj not in seen and sc.get("first_in_parent", True)
                and bible["characters"].get(subj, {}).get("first_scene") == parent):
            lt = {"name": subj, "role": roles.get(subj, "")}
            seen.add(subj)
        plan = [("action", 1.0, layout)]
        if layout == "hero" and place and d.get("location_changed") and dur >= 4.5:
            plan = [("establishing", .3, "map"), ("action", .7, "hero")]
        for k, (role, share, lay) in enumerate(plan):
            shots.append({
                "id": f"s{i + 1:03d}_{k + 1}", "scene_index": i, "parent": parent, "role": role, "layout": lay,
                "archetype": arch, "text": text, "share": share, "location": d["location"],
                "time_of_day": d["time_of_day"], "emotion": d["emotion"], "intensity": d["emotion_intensity"],
                "characters": d["characters"], "subject": subj, "action": d["action"], "shot_type": d["shot_type"],
                "direction": -1 if i % 2 else 1, "fx": d.get("fx", []),
                "camera": _camera(lay, role, d["emotion"], d["emotion_intensity"], d["action"], i),
                "tag": tag, "chips": chips if lay == "hero" else [], "lower_third": lt if lay == "hero" else None,
                "plate": _plate(media_dir, parent), "scene_est": dur, **(extra if lay != "map" else {})})
    return shots


def retime(shots, scene_durations, fps):
    """scene_durations: {segment_index: seconds}. Frame-exact start/duration per shot."""
    out, frame = [], 0
    groups: dict[int, list] = {}
    for s in shots:
        groups.setdefault(s["scene_index"], []).append(s)
    for idx, grp in groups.items():
        dur = TITLE_SECONDS if idx < 0 else scene_durations.get(idx, grp[0]["scene_est"])
        total, cum, prev, t0 = max(len(grp), round(dur * fps)), 0.0, 0, 0.0
        for s in grp:
            cum += s["share"]
            edge = round(total * cum / sum(g["share"] for g in grp))
            n = max(1, edge - prev)
            prev += n
            out.append({**s, "frames": n, "frame_start": frame, "start": frame / fps, "duration": n / fps,
                        "scene_t0": t0, "scene_dur": total / fps})
            frame += n
            t0 += n / fps
    return out
