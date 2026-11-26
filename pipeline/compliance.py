"""Originality / repetitiveness self-audit written next to every render (not a policy guarantee)."""
from __future__ import annotations


def audit(shots: list[dict], theme: dict, prev: dict | None = None) -> dict:
    seq = [s["archetype"] for s in shots if s.get("archetype")]
    moving = all(s["camera"]["zoom"][0] != s["camera"]["zoom"][1] or s["camera"]["pan"][0] != s["camera"]["pan"][1] for s in shots)
    rep = {k: seq.count(k) for k in set(seq)}
    rep_ok = all(a != b for a, b in zip(seq, seq[1:]))
    prev_theme = (prev or {}).get("theme", {})
    diff = {k: theme.get(k) != prev_theme.get(k) for k in ("palette", "fonts", "texture", "transition")} if prev_theme else {}
    same_struct = bool(prev and prev.get("archetypes") == seq)
    rep_report = {
        "segments": len(seq), "archetype_counts": rep, "no_consecutive_repeat": rep_ok,
        "distinct_archetypes": len(rep), "every_shot_has_camera_motion": moving,
        "max_segment_seconds": round(max((s["duration"] for s in shots), default=0), 1),
        "theme_differs_from_previous": diff, "structure_identical_to_previous": same_struct,
    }
    rep_report["pass"] = rep_ok and moving and not same_struct and rep_report["max_segment_seconds"] <= 12 and all(diff.values())
    return rep_report
