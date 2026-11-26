"""Deterministic, offline shot and action planning for the procedural animation backend.

This is deliberately rule-based: it adds useful direction without requiring a paid
API, a network call, or a local LLM to be loaded for every scene.
"""
from __future__ import annotations

import re
from typing import Any

_WORD = re.compile(r"[a-z0-9']+")

def _has(text: str, *terms: str) -> bool:
    return any(term in text for term in terms)

def direct_scene(scene: dict[str, Any], index: int = 0) -> dict[str, Any]:
    """Return a copy of a scene enriched with grounded shot/action metadata."""
    result = dict(scene)
    narration = str(scene.get("text") or "")
    text = " ".join(_WORD.findall(narration.lower()))

    if _has(text, "runs", "run", "running", "chases", "chase", "escapes", "escape", "rushes", "rush"):
        action, camera, shot, pace = "run", "tracking", "medium_wide", "fast"
    elif _has(text, "walks", "walk", "walking", "approaches", "approach", "travels", "travels", "marches", "march"):
        action, camera, shot, pace = "walk", "tracking", "wide", "steady"
    elif _has(text, "turns", "turn", "looks", "look", "notices", "notice", "sees", "see", "hears", "hear", "discovers", "discover"):
        action, camera, shot, pace = "react", "push_in", "close_up", "slow"
    elif _has(text, "speaks", "speak", "says", "said", "asks", "ask", "shouts", "shout", "tells", "tell"):
        action, camera, shot, pace = "speak", "push_in", "medium_close", "steady"
    elif _has(text, "falls", "fall", "dies", "die", "collapses", "collapse", "surrenders", "surrender"):
        action, camera, shot, pace = "fall", "pull_back", "wide", "slow"
    else:
        action, camera, shot, pace = "observe", "slow_pan", "medium", "slow"

    if _has(text, "afraid", "fear", "terrified", "danger", "threat", "enemy", "attacks", "attack"):
        mood = "fear"
    elif _has(text, "happy", "smiles", "smile", "celebrates", "celebrate", "joy"):
        mood = "joy"
    elif _has(text, "sad", "grief", "cries", "cry", "mourning", "loss"):
        mood = "sadness"
    elif _has(text, "angry", "anger", "furious", "rage"):
        mood = "anger"
    elif _has(text, "discovers", "discover", "notices", "notice", "mystery", "strange", "smoke"):
        mood = "curiosity"
    else:
        mood = "determined"

    if _has(text, "forest", "woods", "trees", "jungle"):
        environment = "forest"
    elif _has(text, "village", "hut", "houses", "market", "street"):
        environment = "village"
    elif _has(text, "battle", "war", "soldier", "army", "weapon", "tank"):
        environment = "battlefield"
    elif _has(text, "room", "house", "inside", "hall", "door"):
        environment = "interior"
    elif _has(text, "river", "sea", "ocean", "lake", "shore"):
        environment = "water"
    elif _has(text, "mountain", "hill", "cliff"):
        environment = "mountain"
    else:
        environment = "landscape"

    # Respect explicit values supplied by a user-authored plan.
    result.setdefault("action", action)
    result.setdefault("camera_move", camera)
    result.setdefault("shot_type", shot)
    result.setdefault("pace", pace)
    result.setdefault("mood", mood)
    result.setdefault("environment", environment)
    result.setdefault("shot_index", index)
    return result

def direct_plan(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enrich all scenes while retaining their order and existing metadata."""
    return [direct_scene(scene, index) for index, scene in enumerate(scenes)]
