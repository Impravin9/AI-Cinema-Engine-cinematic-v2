"""Word-level audio sync with faster-whisper (runs locally): visuals change on the exact spoken word."""
from __future__ import annotations

import json
import re
from pathlib import Path

_MODELS: dict = {}


def _norm(w: str) -> str:
    return re.sub(r"[^\w]", "", w.lower())


def transcribe(path, cache_dir, size: str = "base"):
    """Return [(word, start, end)] or None when faster-whisper/model is unavailable."""
    cache = Path(cache_dir) / f"{Path(path).stem}.{size}.words.json"
    if cache.exists():
        return [tuple(x) for x in json.loads(cache.read_text())]
    try:
        from faster_whisper import WhisperModel
        model = _MODELS.get(size) or _MODELS.setdefault(size, WhisperModel(size, device="auto", compute_type="int8"))
        segs, _ = model.transcribe(str(path), word_timestamps=True)
        words = [(w.word.strip(), float(w.start), float(w.end)) for s in segs for w in (s.words or [])]
    except Exception:
        return None
    cache.write_text(json.dumps(words))
    return words


def proportional(phrases: list[str], total: float) -> list[float]:
    n = [max(1, len(p.split())) for p in phrases]
    return [total * k / sum(n) for k in n]


def align(phrases: list[str], words, total: float, lead: float = .08) -> list[float]:
    """Segment durations whose boundaries sit on the spoken first word of each phrase (falls back to proportional)."""
    counts = [len([t for t in map(_norm, p.split()) if t]) for p in phrases]
    if not words or abs(len(words) - sum(counts)) > max(3, .25 * sum(counts)):
        return proportional(phrases, total)
    starts, ptr = [], 0
    for c in counts:
        starts.append(max(0.0, words[min(ptr, len(words) - 1)][1] - lead))
        ptr += c
    starts[0] = 0.0
    ends = starts[1:] + [total]
    return [max(.6, e - s) for s, e in zip(starts, ends)]
