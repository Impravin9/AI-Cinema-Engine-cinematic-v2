"""Persistent per-script visual asset library for offline-first rendering."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


def project_key(script_path: str, script_text: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(script_path).stem).strip("_") or "film"
    digest = hashlib.sha256(script_text.encode("utf-8")).hexdigest()[:10]
    return f"{stem}_{digest}"


def scene_signature(scene: dict[str, Any]) -> str:
    stable = {
        "text": scene.get("text", ""),
        "queries": scene.get("queries", []),
        "gen_prompt": scene.get("gen_prompt", ""),
    }
    raw = json.dumps(stable, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def open_library(root: str, script_path: str, script_text: str) -> tuple[Path, dict[str, Any]]:
    folder = Path(root) / project_key(script_path, script_text)
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / "asset_manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
    else:
        manifest = {}
    manifest.setdefault("version", 1)
    manifest.setdefault("project", folder.name)
    manifest.setdefault("scenes", {})
    return folder, manifest


def save_manifest(folder: Path, manifest: dict[str, Any]) -> None:
    target = folder / "asset_manifest.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)


def scene_asset_path(folder: Path, index: int) -> Path:
    return folder / f"scene_{index + 1:03d}.jpg"


def candidate_asset_path(folder: Path, index: int, candidate_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(candidate_id)).strip("_")
    if not safe_id:
        raise ValueError("candidate_id must contain at least one safe character")
    return folder / "candidates" / f"scene_{index + 1:03d}" / f"{safe_id}.jpg"


def register_scene_candidates(
    folder: Path,
    manifest: dict[str, Any],
    index: int,
    scene: dict[str, Any],
    candidates: list[dict[str, Any]],
    selected_candidate: str | None = None,
) -> None:
    """Persist candidate provenance and the selected candidate for one scene."""
    previous = manifest.setdefault("scenes", {}).get(str(index + 1), {})
    ids = {str(item.get("id")) for item in candidates}
    selected = selected_candidate or previous.get("selected_candidate")
    if selected not in ids:
        selected = str(candidates[0]["id"]) if candidates else None
    manifest["scenes"][str(index + 1)] = {
        "signature": scene_signature(scene),
        "candidates": candidates,
        "selected_candidate": selected,
        "selection": "manual" if selected_candidate else ("manual" if previous.get("selection") == "manual" else "automatic"),
        "file": scene_asset_path(folder, index).name,
        "credit_and_source": next((str(x.get("credit_and_source", "")) for x in candidates if str(x.get("id")) == selected), ""),
    }
    save_manifest(folder, manifest)


def select_scene_candidate(
    folder: Path,
    manifest: dict[str, Any],
    index: int,
    candidate_id: str,
) -> tuple[Path, dict[str, Any]]:
    """Select a saved candidate without losing its original source/licence metadata."""
    record = manifest.get("scenes", {}).get(str(index + 1), {})
    for candidate in record.get("candidates", []):
        if str(candidate.get("id")) != str(candidate_id):
            continue
        path = folder / str(candidate.get("file", ""))
        if not path.is_file():
            raise FileNotFoundError(f"Candidate image is missing: {path}")
        record["selected_candidate"] = str(candidate_id)
        record["selection"] = "manual"
        record["credit_and_source"] = str(candidate.get("credit_and_source", ""))
        manifest["scenes"][str(index + 1)] = record
        save_manifest(folder, manifest)
        return path, record
    raise ValueError(f"Unknown candidate {candidate_id!r} for scene {index + 1}")


def valid_scene_asset(folder: Path, manifest: dict[str, Any], index: int, scene: dict[str, Any]) -> tuple[Path, dict[str, Any]] | None:
    record = manifest.get("scenes", {}).get(str(index + 1), {})
    if record.get("signature") != scene_signature(scene):
        return None
    candidates = record.get("candidates") or []
    if candidates:
        selected = str(record.get("selected_candidate") or candidates[0].get("id"))
        for candidate in candidates:
            if str(candidate.get("id")) == selected:
                path = folder / str(candidate.get("file", ""))
                if path.is_file():
                    return path, {**record, "credit_and_source": candidate.get("credit_and_source", record.get("credit_and_source", ""))}
        return None
    path = scene_asset_path(folder, index)
    if not path.is_file():
        return None
    return path, record


def register_scene_asset(
    folder: Path,
    manifest: dict[str, Any],
    index: int,
    scene: dict[str, Any],
    source_credit: str,
) -> Path:
    path = scene_asset_path(folder, index)
    manifest.setdefault("scenes", {})[str(index + 1)] = {
        "file": path.name,
        "signature": scene_signature(scene),
        "credit_and_source": source_credit,
        "selection": "automatic",
    }
    save_manifest(folder, manifest)
    return path



def load_selection_file(folder: Path) -> dict[str, str]:
    """Read optional human-edited asset_selections.json (scene number -> candidate id)."""
    path = folder / "asset_selections.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid selection file {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("asset_selections.json must contain a JSON object mapping scene numbers to candidate IDs")
    return {str(k): str(v) for k, v in raw.items() if str(k).isdigit() and str(v).strip()}
