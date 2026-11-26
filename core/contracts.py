"""Validation and inspection for existing and normalized cinema plans.

The legacy LEGO and modern renderers intentionally keep their native schemas.
This module validates the shared minimum contract without rewriting either plan.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PlanValidationError(ValueError):
    """Raised when a storyboard plan cannot be safely passed to a renderer."""


def load_json(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.is_file():
        raise PlanValidationError(f"Plan file not found: {file_path}")
    try:
        data = json.loads(file_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise PlanValidationError(
            f"Invalid JSON in {file_path} at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(data, dict):
        raise PlanValidationError("Plan root must be a JSON object.")
    return validate_plan(data)


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise PlanValidationError("Plan root must be an object.")
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise PlanValidationError("Plan must contain a non-empty 'scenes' array.")

    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            raise PlanValidationError(f"Scene {index} must be an object.")
        text = scene.get("text")
        if not isinstance(text, str) or not text.strip():
            raise PlanValidationError(f"Scene {index} is missing non-empty narration 'text'.")

    # Both current renderers consume title + scenes; their scene detail differs.
    plan.setdefault("title", "Untitled Cinema Project")
    if not isinstance(plan["title"], str) or not plan["title"].strip():
        raise PlanValidationError("'title' must be a non-empty string.")
    return plan


def inspect_plan(path: str | Path) -> dict[str, Any]:
    """Return useful plan diagnostics without modifying the source file."""
    plan = load_json(path)
    scenes = plan["scenes"]
    legacy = sum(1 for scene in scenes if "bg" in scene or "actors" in scene)
    modern = sum(1 for scene in scenes if "visual" in scene or "gen_prompt" in scene)
    return {
        "title": plan["title"],
        "scene_count": len(scenes),
        "legacy_scene_count": legacy,
        "modern_scene_count": modern,
        "mixed_or_unknown_count": len(scenes) - max(legacy, modern),
        "schema": "lego" if legacy and not modern else "modern" if modern and not legacy else "mixed-or-shared",
    }
