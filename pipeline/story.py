"""Stage 1 - Story intelligence: characters, events, emotions, locations, continuity."""
from __future__ import annotations

import re
from typing import Any

from cinematic_director import direct_scene

_TOKEN = re.compile(r"[a-z0-9']+")
_CAP = re.compile(r"\b[A-Z][a-z]{2,}\b")
STOP = frozenset("""The And But For With From Then When While After Before Once Suddenly Meanwhile Later Soon Now
Here There This That These Those His Her Its Our Their They She Him Them Who What Where Why How Not Yet One Two Three
Every Each Some Many Most All Any Another Other Finally Inside Outside Across Under Over Beyond Through""".split())

LOCATIONS = {
    "forest": ("forest", "woods", "trees", "jungle", "grove"),
    "village": ("village", "hut", "huts", "houses", "market", "street", "town"),
    "battlefield": ("battle", "battlefield", "war", "soldier", "soldiers", "army", "weapon", "tank", "trench"),
    "interior": ("room", "house", "inside", "hall", "door", "palace", "office", "kitchen", "castle"),
    "water": ("river", "sea", "ocean", "lake", "shore", "beach", "harbor", "harbour", "ship"),
    "mountain": ("mountain", "mountains", "hill", "hills", "cliff", "peak", "valley"),
}
TIMES = {
    "night": ("night", "midnight", "moonlight", "stars"),
    "dawn": ("dawn", "sunrise", "daybreak"),
    "morning": ("morning",),
    "noon": ("noon", "midday", "afternoon"),
    "dusk": ("dusk", "sunset", "evening", "twilight"),
}
EMOTIONS = {
    "fear": ("afraid", "fear", "terrified", "terror", "scream", "screams", "screamed", "terror", "screams", "scream", "danger", "threat", "enemy", "attack", "attacks", "panic", "dread"),
    "joy": ("happy", "smiles", "smile", "celebrates", "celebrate", "joy", "laughs", "laugh", "victory"),
    "sadness": ("sad", "grief", "cries", "cry", "mourning", "loss", "tears", "died", "dies"),
    "anger": ("angry", "anger", "furious", "rage", "shouts", "fury"),
    "curiosity": ("discovers", "discover", "notices", "notice", "mystery", "strange", "smoke", "wonders"),
}
ACTION_EVENT = {"run": "pursuit", "walk": "journey", "react": "discovery", "speak": "dialogue",
                "fall": "loss", "observe": "observation"}
_SING, _PLUR = {"he", "she", "him", "his", "her", "hers"}, {"they", "them", "their", "theirs"}
_FIRE = {"smoke", "fire", "burning", "burns", "flames"}
PLAN_EMOTION = {"shock": "fear", "sad": "sadness", "think": "curiosity", "angry": "anger", "awe": "curiosity", "proud": "joy",
                "neutral": "determined", "panic": "fear", "joy": "joy"}
GRADE_MOOD = {"fear": "fear", "sadness": "sad", "anger": "anger", "joy": "wonder", "curiosity": "mystery", "determined": "epic"}
TOD_VIS = {"dawn": "sunrise", "morning": "day", "noon": "day", "dusk": "dusk", "night": "night", "sunrise": "sunrise", "sunset": "sunset", "day": "day"}
_LEX = {w for table in (LOCATIONS, TIMES, EMOTIONS) for terms in table.values() for w in terms}
_START = re.compile(r"(?:^|[.!?]\s+)([A-Z][a-z]{2,})\s+([a-z]+)")


def _best(words: list[str], table: dict[str, tuple[str, ...]]) -> tuple[str | None, int]:
    best, score = None, 0
    for key, terms in table.items():
        n = sum(words.count(t) for t in terms)
        if n > score:
            best, score = key, n
    return best, score


_COMMON = frozenset("""rain wind night time fire smoke water light sun moon war people men women soldiers life death
morning evening day sky sea river city world history years peace army battle storm snow dust darkness silence""".split())
_LEX = {w for t in (LOCATIONS, TIMES, EMOTIONS) for ws in t.values() for w in ws}
_AUX = {"is", "was", "has", "had", "can", "will", "must", "did", "does", "stands", "walks"}


def discover_characters(texts: list[str], plan_names=()) -> list[str]:
    names: list[str] = []
    for n in plan_names:
        n = str(n).strip()
        if n and n.lower() not in ("narrator", "narration") and n not in names:
            names.append(n)
    if names:
        return names
    counts: dict[str, int] = {}
    ok: set[str] = set()
    for t in texts:
        for m in _CAP.finditer(t):
            w = m.group(0)
            if w in STOP or w.lower() in _COMMON or w.lower() in _LEX:
                continue
            counts[w] = counts.get(w, 0) + 1
            before = t[:m.start()].rstrip()
            if before and before[-1] not in ".!?\"\u201c":
                ok.add(w)  # capitalised mid-sentence => proper noun
            else:
                nxt = re.match(r"\s+([a-z]+)", t[m.end():])
                if nxt and (nxt.group(1) in _AUX or nxt.group(1).endswith(("s", "ed"))):
                    ok.add(w)  # "Arjun walks", "Meera screamed"
    return [w for w, c in counts.items() if w in ok or c >= 2]


def _aliases(name: str) -> set[str]:
    return {name.lower(), *[t.lower() for t in name.split() if len(t) >= 4]}


def _mentions(text: str, names: list[str]) -> list[str]:
    found = []
    for n in names:
        pos = [m.start() for a in _aliases(n) for m in re.finditer(r"\b" + re.escape(a) + r"\b", text, re.I)]
        if pos:
            found.append((min(pos), n))
    return [n for _, n in sorted(found)]


def analyze(scenes: list[dict[str, Any]], plan_characters=None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return (scenes enriched with story metadata, story bible). Input scenes are not mutated."""
    texts = [str(s.get("text", "")) for s in scenes]
    pnames = [c.get("name") if isinstance(c, dict) else c for c in (plan_characters or [])]
    known = discover_characters(texts, [p for p in pnames if p])
    out: list[dict[str, Any]] = []
    bible: dict[str, Any] = {"characters": {}, "locations": [], "arc": []}
    prev_loc = prev_time = prev_emo = None
    prev_int, present_prev, subject_prev = 0.3, [], None

    for i, (scene, text) in enumerate(zip(scenes, texts)):
        d = dict(scene)
        words = _TOKEN.findall(text.lower())
        wset = set(words)

        loc, _ = _best(words, LOCATIONS)
        loc = scene.get("bg") or loc or prev_loc or "landscape"
        changed = loc != prev_loc
        tod, _ = _best(words, TIMES)
        tod = scene.get("time") or tod or prev_time or "morning"

        explicit = PLAN_EMOTION.get(str(scene.get("emotion", "")).lower(), str(scene.get("emotion", "")).lower())
        emo, score = (explicit, 1) if explicit in EMOTIONS else _best(words, EMOTIONS)
        if emo:
            intensity = min(1.0, 0.4 + 0.3 * score)
        else:
            intensity = prev_int * 0.6
            emo = prev_emo if (prev_emo and intensity >= 0.3) else "determined"
            intensity = max(intensity, 0.3)

        authored = [a.get("name") for a in scene.get("actors", []) if isinstance(a, dict) and a.get("name") in known]
        mentioned = authored or _mentions(text, known)
        if mentioned:
            subject = mentioned[0]
            present = list(mentioned)
            if not changed:  # people already on stage stay there
                present += [p for p in present_prev if p not in present]
        else:
            subject = subject_prev
            present = list(present_prev)
        if not present:
            subject = known[0] if known else "Protagonist"
            present = [subject]
        subject = subject if subject in present else present[0]
        present = present[:3]

        action = direct_scene(scene, i)["action"]
        d.setdefault("action", action)
        d.setdefault("time", TOD_VIS.get(tod, "day"))
        keep_mood = scene.get("mood") if scene.get("mood") in ("suspense", "fear", "mystery", "sad", "epic", "action", "anger", "calm", "wonder") else None
        d.update({
            "characters": present, "subject": subject, "location": loc, "environment": loc,
            "location_changed": changed, "time_of_day": tod, "emotion": emo, "mood": keep_mood or GRADE_MOOD.get(emo, "epic"),
            "emotion_intensity": round(intensity, 2), "event": ACTION_EVENT.get(action, "observation"),
            "fx": ["smoke"] if wset & _FIRE else [],
            "continuity": {"carried_characters": not mentioned, "time_changed": tod != prev_time and i > 0},
        })
        out.append(d)
        for p in present:
            c = bible["characters"].setdefault(p, {"first_scene": i, "scenes": []})
            c["scenes"].append(i)
        if loc not in bible["locations"]:
            bible["locations"].append(loc)
        bible["arc"].append(emo)
        prev_loc, prev_time, prev_emo, prev_int = loc, tod, emo, intensity
        present_prev, subject_prev = present, subject
    return out, bible
