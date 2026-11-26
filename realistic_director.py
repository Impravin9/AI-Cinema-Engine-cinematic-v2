"""Story-grounded shot direction for the realistic documentary renderer.

This module upgrades legacy LEGO storyboard plans into a realistic visual brief.
It does not create facts or historical details that are absent from the narration.
"""
from __future__ import annotations

import re
from typing import Any

STOP = {
    "the", "and", "but", "for", "with", "from", "into", "over", "under",
    "when", "while", "after", "before", "then", "this", "that", "they",
    "them", "their", "there", "where", "which", "who", "what", "how",
    "why", "was", "were", "are", "is", "his", "her", "its", "our",
    "you", "your", "had", "has", "have", "been", "being", "will", "would",
    "could", "should", "not", "but", "all", "any", "one", "two", "three",
    "more", "most", "some", "many", "much", "very", "just", "only",
    "also", "than", "about", "around", "across", "through", "because",
    "while", "during", "onto", "upon", "each", "both", "such", "like",
}
GENERIC_CAST = {
    "soldier", "soldiers", "civilian", "civilians", "pilot", "pilots",
    "sailor", "sailors", "commander", "commanders", "general", "generals",
    "officer", "officers", "crew", "army", "troops", "crowd", "people",
    "narrator", "anchor", "reporter", "doctor", "nurse", "worker", "workers",
}
GENERIC_ADJECTIVES = {"german", "british", "soviet", "japanese", "american", "allied",
                      "french", "italian", "russian", "polish", "chinese", "nazi", "civilian"}

def _generic_group(name: str) -> bool:
    words = _norm(name).split()
    return bool(words) and (words[-1] in GENERIC_CAST or (len(words) == 1 and words[0] in GENERIC_CAST))
EVENTS = (
    (("battle of britain", "raf", "luftwaffe"), "Battle of Britain"),
    (("pearl harbor", "pearl harbour"), "Attack on Pearl Harbor"),
    (("operation barbarossa", "june 22 1941", "soviet union"), "Operation Barbarossa"),
    (("leningrad", "lake ladoga", "road of life"), "Siege of Leningrad"),
    (("stalingrad", "sixth army"), "Battle of Stalingrad"),
    (("midway", "japanese carriers"), "Battle of Midway"),
    (("normandy", "d day", "june 6 1944"), "Normandy landings"),
    (("hiroshima", "nagasaki"), "Atomic bombings of Hiroshima and Nagasaki"),
    (("operation fortitude", "rubber tank", "phantom army"), "Operation Fortitude deception"),
)

def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(text or "").lower()))

def _script_mentions(name: str, script_norm: str) -> bool:
    tokens = _norm(name).split()
    if not tokens:
        return False
    if len(tokens) == 1:
        return len(tokens[0]) > 2 and re.search(r"\b" + re.escape(tokens[0]) + r"\b", script_norm) is not None
    full = " ".join(tokens)
    return full in script_norm or (
        len(tokens[-1]) > 2 and re.search(r"\b" + re.escape(tokens[-1]) + r"\b", script_norm) is not None
    )

def _proper_phrases(text: str) -> list[str]:
    pattern = r"\b[A-Z][a-zA-ZÀ-ÿ.'’-]*(?:\s+(?:[A-Z][a-zA-ZÀ-ÿ.'’-]*|of|the|II|III|IV)){0,4}"
    found = []
    for match in re.finditer(pattern, text):
        phrase = match.group(0).strip(" .,-")
        words = phrase.split()
        while words and words[0].lower() in STOP:
            words.pop(0)
        phrase = " ".join(words)
        if phrase and len(phrase) > 2 and phrase.lower() not in STOP:
            found.append(phrase)
    return list(dict.fromkeys(found))

def _event_terms(text: str) -> list[str]:
    low = _norm(text)
    found = []
    for terms, label in EVENTS:
        if any(_norm(term) in low for term in terms):
            found.append(label)
    return found

def _queries(scene_text: str, script: str, title: str) -> list[str]:
    """Build archive-friendly searches from this scene, not the whole film title."""
    phrases = _proper_phrases(scene_text)
    event_terms = _event_terms(scene_text)
    # Prefer concrete named entities and event names actually present in this scene.
    candidates = []
    candidates.extend(event_terms)
    candidates.extend(phrases)
    # Date and place context from the narration is useful for archive searches.
    dates = re.findall(r"\b(?:17|18|19|20)\d{2}\b", scene_text)
    candidates.extend(dates)
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", scene_text)
             if w.lower() not in STOP]
    # Build one compact subject phrase, avoiding a generic query made from the film title.
    if words:
        candidates.append(" ".join(words[:7]))
    out = []
    for item in candidates:
        q = re.sub(r"\s+", " ", item).strip()
        if q and q.lower() not in {x.lower() for x in out}:
            out.append(q)
    return out[:4] or [re.sub(r"\s+", " ", scene_text).strip()[:100]]

def _shot(text: str, index: int) -> tuple[str, str]:
    low = _norm(text)
    if any(x in low for x in ("map", "route", "front line", "across europe", "army groups")):
        return "aerial_wide", "slow_push_in"
    if any(x in low for x in ("thousands", "millions", "army", "troops", "fleet", "convoy", "crowd")):
        return "extreme_wide", "slow_track"
    if any(x in low for x in ("said", "told", "speech", "announced", "ordered", "declared")):
        return "medium_close_up", "subtle_push_in"
    if any(x in low for x in ("letter", "document", "code", "message", "signature", "photograph")):
        return "insert_close_up", "slow_rack_focus"
    if any(x in low for x in ("died", "dead", "hunger", "starve", "surrender", "prisoner", "casualties")):
        return "intimate_wide", "slow_pull_back"
    choices = [
        ("establishing_wide", "slow_push_in"),
        ("ground_level_medium", "slow_track"),
        ("overhead_detail", "slow_pan"),
        ("telephoto_wide", "subtle_push_in"),
    ]
    return choices[index % len(choices)]

def _prompt(scene: dict[str, Any], style: str, title: str, shot: str, camera: str) -> str:
    narration = re.sub(r"\s+", " ", str(scene.get("text") or "")).strip()
    entities = _proper_phrases(narration)
    event = _event_terms(narration)
    subject = ", ".join((event + entities)[:6]) or title
    historical = style in {"history", "news"}
    period_rules = (
        "Historically faithful period reconstruction: correct uniforms, insignia, weapons, "
        "vehicles, architecture, geography, weather and technology for the exact year. "
        "No modern objects, no contemporary politicians, no sports players, no fantasy props. "
        if historical else ""
    )
    return (
        "Create one coherent photorealistic cinematic film frame, not an illustration, "
        "not LEGO, not a collage. "
        f"Film subject: {subject}. Exact story beat: {narration}. "
        f"Shot design: {shot}; camera: {camera}; widescreen 16:9. "
        "Naturalistic cinematography, physically plausible lighting, realistic materials, "
        "authentic environments, restrained film grain, detailed composition, documentary realism. "
        + period_rules
        + "Only depict people who belong in this exact narrated event. Do not add unrelated "
        "famous people, celebrities, politicians or fictional characters. Do not add readable "
        "text, subtitles, logos, watermarks, UI, borders or poster layouts."
    )

def prepare_plan(plan: dict[str, Any], script: str, requested_style: str | None = None) -> dict[str, Any]:
    """Add grounded shot direction and remove unsupported named people from old LEGO plans."""
    if not isinstance(plan, dict) or not isinstance(plan.get("scenes"), list) or not plan["scenes"]:
        raise ValueError("Realistic director requires a plan with a non-empty scenes array.")
    script_norm = _norm(script)
    title = str(plan.get("title") or "Documentary")
    style = str(plan.get("style") or requested_style or "history").lower()
    if style not in {"history", "mythology", "news", "science", "animals", "story"}:
        style = requested_style or "history"

    # Create a verified named-person list from the user's actual script.
    cast = []
    for character in plan.get("characters") or []:
        if not isinstance(character, dict):
            continue
        name = str(character.get("name") or "").strip()
        role = str(character.get("role") or "").lower()
        if name and (_script_mentions(name, script_norm) or _generic_group(name)):
            cast.append(character)
    plan["characters"] = cast

    for i, scene in enumerate(plan["scenes"]):
        if not isinstance(scene, dict):
            raise ValueError(f"Scene {i + 1} must be a JSON object.")
        text = str(scene.get("text") or "").strip()
        if not text:
            raise ValueError(f"Scene {i + 1} has no narration text.")

        # Remove invented named actors inherited from LEGO plans. Realistic stills
        # are directed from the narration, not from old minifigure action labels.
        verified_actors = []
        for actor in scene.get("actors") or []:
            if not isinstance(actor, dict):
                continue
            name = str(actor.get("name") or "").strip()
            if not name:
                continue
            if _generic_group(name) or _script_mentions(name, _norm(text)):
                verified_actors.append(actor)
        scene["actors"] = verified_actors
        scene["named_characters"] = [
            str(character.get("name"))
            for character in cast
            if _script_mentions(str(character.get("name") or ""), _norm(text))
            and not _generic_group(str(character.get("name") or ""))
        ]

        queries = _queries(text, script, title)
        scene["queries"] = queries
        shot, camera = _shot(text, i)
        scene["shot_type"] = shot
        scene["camera_direction"] = camera
        scene["visual"] = scene.get("visual") if scene.get("visual") in {"photo", "gen"} else (
            "gen" if style == "mythology" else "photo"
        )
        scene["gen_prompt"] = _prompt(scene, style, title, shot, camera)
        scene["director_version"] = 1

        # Preserve authored motion when valid; otherwise choose restrained motion.
        if scene.get("motion") not in {"zoom_in", "zoom_out", "pan_left", "pan_right", "push_up"}:
            scene["motion"] = "zoom_in" if i % 3 == 0 else "pan_right" if i % 3 == 1 else "zoom_out"

        # A name banner is allowed only if the person is explicitly in this scene's text.
        banner = scene.get("banner") or {"kind": "none"}
        if banner.get("kind") == "name":
            banner_name = str(banner.get("text") or "")
            if not _script_mentions(banner_name, script_norm) or not _script_mentions(banner_name, _norm(text)):
                banner = {"kind": "none"}
        scene["banner"] = banner
        scene.setdefault("chapter", None)
        scene["sfx"] = [x for x in (scene.get("sfx") or []) if isinstance(x, str)]

    plan["style"] = style
    plan["director_version"] = 1
    plan["character_bible"] = [
        {"name": c["name"], "role": c.get("role"), "continuity": "Use only in scenes where the narration explicitly places this person."}
        for c in cast
    ]
    return plan
