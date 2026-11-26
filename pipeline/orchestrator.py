"""Orchestrator: story -> segment -> variety/theme -> narration+word sync -> render -> audio -> final MP4."""
from __future__ import annotations

import json
import random
import shutil
from pathlib import Path

from . import audio, audio_sync, compliance, director, story, variety
from .docu import DocuRenderer

RES = {"preview": (640, 360, 12), "540p": (960, 540, 24), "720p": (1280, 720, 24), "1080p": (1920, 1080, 24)}


def _load(script, plan_path):
    if plan_path:
        from core.contracts import load_json
        plan = load_json(plan_path)
        roles = {c.get("name"): c.get("role", "") for c in plan.get("characters", []) if isinstance(c, dict)}
        return plan["scenes"], plan.get("characters"), plan.get("title") or Path(script).stem, roles
    from animation_renderer import split_script
    return split_script(Path(script).read_text(encoding="utf-8")), None, Path(script).stem.replace("_", " ").title(), {}


def run(script, out, *, plan_path=None, resolution="720p", max_scenes=None, silent=False, tts=True,
        voice="en-US-AndrewMultilingualNeural", rate="+0%", workdir=None, nomusic=False, musicvol=.35,
        media="media", seed=None, whisper_model="base", history=None, log=print):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required (https://ffmpeg.org). Install it and retry.")
    W, H, fps = RES[resolution]
    scenes, pchars, title, roles = _load(script, plan_path)
    scenes = scenes[:max_scenes] if max_scenes else scenes
    if not scenes:
        raise ValueError("No scenes found in the input script/plan.")
    wd = Path(workdir or Path("cinema_work") / Path(script).stem)
    wd.mkdir(parents=True, exist_ok=True)
    hist_path = Path(history or wd.parent / "history.json")
    hist = variety.load_history(hist_path)

    log("[cinematic] 1/7 story intelligence + segmentation")
    scenes, bible = story.analyze(scenes, pchars)
    segs = director.segment(scenes)
    (wd / "story_bible.json").write_text(json.dumps(bible, indent=2), encoding="utf-8")

    log("[cinematic] 2/7 anti-repetition theme + archetypes")
    theme = variety.new_theme(hist_path, seed)
    arch = variety.assign_archetypes([s["text"] for s in segs], random.Random(theme["seed"]), hist[-1]["archetypes"] if hist else None)
    log(f"[cinematic] theme_seed={theme['seed']} {theme['palette']}/{theme['fonts']}/{theme['texture']}/{theme['transition']}")
    shots = director.build_shots(segs, bible, title, roles, media if Path(media).is_dir() else None, arch, theme["seed"])

    log("[cinematic] 3/7 narration + word-level sync")
    narr = {} if (silent or not tts) else audio.narrate(scenes, wd, voice, rate, log)
    durs: dict[int, float] = {}
    for p, clip in narr.items():
        d = audio.probe_duration(clip)
        if not d:
            continue
        idx = [i for i, s in enumerate(segs) if s["parent"] == p]
        words = audio_sync.transcribe(clip, wd, whisper_model)
        if words is None:
            log("[cinematic] faster-whisper unavailable: using proportional timing (pip install faster-whisper)")
        for i, dd in zip(idx, audio_sync.align([segs[i]["text"] for i in idx], words, d + .6)):
            durs[i] = dd
    shots = director.retime(shots, durs, fps)
    total = (shots[-1]["frame_start"] + shots[-1]["frames"]) / fps
    (wd / "shotplan.json").write_text(json.dumps({"title": title, "fps": fps, "resolution": [W, H], "theme": theme, "shots": shots}, indent=2, default=str), encoding="utf-8")

    rep = compliance.audit(shots, theme, hist[-1] if hist else None)
    (wd / "compliance.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    log(f"[cinematic] variety audit: pass={rep['pass']} distinct_archetypes={rep['distinct_archetypes']} max_segment={rep['max_segment_seconds']}s")

    log(f"[cinematic] 4/7 rendering {len(shots)} shots, {total:.1f}s at {W}x{H}")
    video = wd / "video_silent.mp4"
    DocuRenderer({"shots": shots, "theme": theme}, W, H, fps).render(str(video), ffmpeg, log)

    log("[cinematic] 5/7 audio")
    music, sfx, mixed = wd / "music.wav", wd / "sfx.wav", wd / "mix.wav"
    if nomusic:
        audio._wav(music, __import__("numpy").zeros(int(total * audio.SR), "float32"))
    else:
        audio.make_music(music, total, shots)
    audio.make_sfx(sfx, total, shots)
    starts: dict[int, float] = {}
    for s in shots:
        starts.setdefault(s["parent"], s["start"])
    audio.mix(mixed, total, music, sfx, [(p, starts[i] + .15) for i, p in sorted(narr.items())], musicvol, ffmpeg)

    log("[cinematic] 6/7 final assembly")
    srt = wd / "captions.srt"
    audio.write_srt(srt, shots)
    audio.assemble(video, mixed, srt, out, ffmpeg)

    log("[cinematic] 7/7 history log")
    variety.record_run(hist_path, theme, shots)
    log(f"[cinematic] done -> {out}")
    return Path(out)
