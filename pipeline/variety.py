"""Anti-repetition engine (theme_seed + history.json) and strict scene variety (8 archetypes)."""
from __future__ import annotations

import json
import random
import re
import secrets
import time
from pathlib import Path

NUM = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(%|percent|million|billion|thousand|trillion|km|kilometers|miles|years?|days?|people|soldiers|countries)?", re.I)
YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
QUOTE = re.compile(r"[\"\u201c]([^\"\u201d]{12,}?)[\"\u201d]")
_CONTRAST = re.compile(r"\b(while|whereas|but|versus|vs\.?|than|compared|unlike|instead)\b", re.I)
_DOC = re.compile(r"\b(report|study|according|document|law|treaty|record|records|letter|newspaper|article|census|survey|archive|declaration)\b", re.I)
_FLOW = re.compile(r"\b(because|causes?|caused|led|leads|leading|then|process|system|step|chain|result|resulted|therefore|so)\b", re.I)
_TREND = re.compile(r"\b(grew|rose|fell|increase[sd]?|decline[sd]?|doubled|tripled|dropped|surged|growth)\b", re.I)

ARCHETYPES = ("animated_chart", "metric_counter", "historical_timeline", "split_comparison",
              "kinetic_quote", "document_zoom", "concept_flow", "ken_burns_visual")
LAYOUT = {"animated_chart": "chart", "metric_counter": "stat", "historical_timeline": "timeline",
          "split_comparison": "split", "kinetic_quote": "quote", "document_zoom": "doc",
          "concept_flow": "flow", "ken_burns_visual": "hero"}

# name: (accent, accent2, shadow tint, highlight tint)
PALETTES = {
    "ember": ((255, 140, 50), (255, 215, 120), (-.02, .01, .05), (.06, .02, -.04)),
    "ocean": ((64, 200, 220), (120, 160, 255), (-.03, .02, .06), (.02, .04, .04)),
    "royal": ((170, 120, 255), (255, 120, 200), (.02, -.02, .06), (.05, 0, .03)),
    "forest": ((110, 220, 120), (230, 230, 110), (-.02, .04, .02), (.04, .04, -.03)),
    "crimson": ((235, 64, 80), (255, 170, 120), (.03, -.02, 0), (.06, .01, -.02)),
    "mono": ((235, 235, 240), (150, 160, 175), (0, 0, .02), (.03, .03, .03)),
    "gold": ((245, 196, 66), (255, 240, 180), (0, -.01, .04), (.07, .04, -.05)),
    "mint": ((90, 235, 190), (80, 170, 255), (-.03, .03, .03), (.02, .05, .02)),
}
_DJ, _LB, _WF = "/usr/share/fonts/truetype/dejavu/DejaVu", "/usr/share/fonts/truetype/liberation/Liberation", "C:/Windows/Fonts/"
FONTS = {
    "classic": ([_WF + "georgiab.ttf", _DJ + "Serif-Bold.ttf"], [_WF + "calibri.ttf", _DJ + "Sans.ttf"]),
    "modern": ([_WF + "segoeuib.ttf", _DJ + "Sans-Bold.ttf"], [_WF + "segoeui.ttf", _DJ + "Sans.ttf"]),
    "impact": ([_WF + "impact.ttf", _WF + "arialbd.ttf", _LB + "Sans-Bold.ttf"], [_WF + "arial.ttf", _LB + "Sans-Regular.ttf"]),
    "mono": ([_WF + "consolab.ttf", _DJ + "SansMono-Bold.ttf"], [_WF + "consola.ttf", _DJ + "SansMono.ttf"]),
    "editorial": ([_WF + "timesbd.ttf", _LB + "Serif-Bold.ttf"], [_WF + "verdana.ttf", _LB + "Sans-Regular.ttf"]),
    "tech": ([_WF + "bahnschrift.ttf", _WF + "trebucbd.ttf", _DJ + "Sans-Bold.ttf"], [_WF + "trebuc.ttf", _DJ + "Sans.ttf"]),
}
TEXTURES = ("paper", "grid", "halftone", "scanlines", "dust", "blueprint")
TRANSITIONS = ("dissolve", "wipe", "slide", "zoom", "flash")


def load_history(path) -> list[dict]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def new_theme(history_path, seed: int | None = None) -> dict:
    """Random theme whose palette, font pairing, texture and transition all differ from the previous run."""
    hist = load_history(history_path)
    last = hist[-1]["theme"] if hist else {}
    recent = {h["theme"]["signature"] for h in hist[-10:]}
    seed = secrets.randbits(32) if seed is None else int(seed)
    for k in range(200):
        rng = random.Random(seed + k)
        pick = lambda opts, key: rng.choice([o for o in opts if o != last.get(key)] or list(opts))
        th = {"palette": pick(PALETTES, "palette"), "fonts": pick(FONTS, "fonts"),
              "texture": pick(TEXTURES, "texture"), "transition": pick(TRANSITIONS, "transition")}
        th["signature"] = "|".join(th.values())
        if th["signature"] not in recent:
            break
    a, a2, sh, hi = PALETTES[th["palette"]]
    return {"seed": seed, **th, "accent": a, "accent2": a2, "shadow": sh, "highlight": hi,
            "font_head": FONTS[th["fonts"]][0], "font_body": FONTS[th["fonts"]][1]}


def features(text: str) -> dict:
    flat = YEAR.sub(" ", text)
    return {"nums": len(NUM.findall(flat)), "years": len(YEAR.findall(text)), "quote": bool(QUOTE.search(text)),
            "contrast": bool(_CONTRAST.search(text)), "doc": bool(_DOC.search(text)), "flow": bool(_FLOW.search(text)),
            "trend": bool(_TREND.search(text)), "pct": "%" in text or "percent" in text.lower(), "words": len(text.split())}


def assign_archetypes(texts: list[str], rng: random.Random, prev_seq=None) -> list[str]:
    seq: list[str] = []
    for t in texts:
        f = features(t)
        s = {a: rng.random() * .4 for a in ARCHETYPES}
        s["ken_burns_visual"] += 1.0
        s["animated_chart"] += (2 if f["nums"] >= 2 else 0) + (1.2 if f["trend"] else 0) - (5 if f["nums"] < 1 else 0)
        s["metric_counter"] += (2 if f["nums"] == 1 or f["pct"] else .8) - (5 if f["nums"] < 1 else 0)
        s["historical_timeline"] += 2.5 - (5 if f["years"] < 1 else 0)
        s["split_comparison"] += (1.5 if f["nums"] >= 2 else 0) + (1.2 if f["contrast"] else 0) + (1 if f["contrast"] and f["nums"] >= 2 else 0) - (5 if not (f["nums"] >= 2 or f["contrast"]) else 0)
        s["kinetic_quote"] += (3 if f["quote"] else 0) + (.6 if f["words"] <= 9 else 0)
        s["document_zoom"] += 2 if f["doc"] else 0
        s["concept_flow"] += (2 if f["flow"] else 0) + (.4 if f["words"] >= 10 else 0)
        for a in s:
            s[a] -= .8 * seq[-3:].count(a)
        if seq:
            s[seq[-1]] = -99
        elif prev_seq:
            s[prev_seq[0]] -= 1.2
        seq.append(max(s, key=s.get))
    return seq


def record_run(history_path, theme: dict, shots: list[dict]) -> None:
    hist = load_history(history_path)
    hist.append({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "theme": theme,
                 "archetypes": [s["archetype"] for s in shots if s.get("archetype")],
                 "structure": [(s["archetype"], round(s["duration"], 1)) for s in shots if s.get("archetype")]})
    Path(history_path).parent.mkdir(parents=True, exist_ok=True)
    Path(history_path).write_text(json.dumps(hist[-50:], indent=1), encoding="utf-8")
