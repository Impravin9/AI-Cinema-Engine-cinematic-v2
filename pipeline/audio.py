"""Stage 5 - Audio: narration (edge-tts), generative score, SFX/ambience, ducked mix, SRT."""
from __future__ import annotations

import asyncio
import hashlib
import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 44100
CHORDS = {"determined": (110.0, 164.81, 220.0, 329.63), "fear": (98.0, 103.83, 146.83, 155.56),
          "joy": (130.81, 196.0, 261.63, 329.63), "sadness": (110.0, 130.81, 164.81, 196.0),
          "anger": (73.42, 110.0, 146.83, 155.56), "curiosity": (123.47, 174.61, 220.0, 277.18)}
AMBIENCE = {"forest": (60, .05), "water": (25, .07), "battlefield": (90, .07), "mountain": (70, .06),
            "village": (40, .02), "interior": (120, .02), "landscape": (60, .04)}


def probe_duration(path) -> float | None:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                           capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _windows_sapi_narrate(text: str, output: Path) -> bool:
    """Offline Windows speech fallback; writes a WAV without requiring internet."""
    import base64
    import os
    if os.name != "nt":
        return False
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.SetOutputToWaveFile($args[0]); "
        "$t = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($args[1])); "
        "$s.Speak($t); $s.Dispose()"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-Command", script, str(output), encoded],
            check=True, capture_output=True, text=True, timeout=90,
        )
        return output.exists() and output.stat().st_size > 1024
    except (OSError, subprocess.SubprocessError):
        return False


def narrate(scenes, workdir: Path, voice: str, rate: str, log=print) -> dict[int, Path]:
    """Generate cached narration; fall back to offline Windows speech if Edge TTS stalls."""
    try:
        import edge_tts
    except ImportError:
        edge_tts = None

    d = Path(workdir) / "narration"
    d.mkdir(parents=True, exist_ok=True)
    out: dict[int, Path] = {}
    for i, sc in enumerate(scenes):
        text = str(sc.get("text", "")).strip()
        if not text:
            continue
        key = hashlib.sha1(f"{voice}|{rate}|{text}".encode()).hexdigest()[:10]
        mp3 = d / f"n{i:03d}_{key}.mp3"
        wav = d / f"n{i:03d}_{key}_offline.wav"

        if mp3.exists() and mp3.stat().st_size > 1024:
            out[i] = mp3
            continue
        if wav.exists() and wav.stat().st_size > 1024:
            out[i] = wav
            continue

        # Edge TTS can hang while waiting for its online websocket service.
        if edge_tts is not None:
            try:
                async def _save_with_timeout():
                    await asyncio.wait_for(
                        edge_tts.Communicate(text, voice, rate=rate).save(str(mp3)),
                        timeout=30,
                    )
                asyncio.run(_save_with_timeout())
                if mp3.exists() and mp3.stat().st_size > 1024:
                    out[i] = mp3
                    log(f"[cinematic] narration {i + 1}/{len(scenes)}: online voice")
                    continue
            except (Exception, asyncio.CancelledError) as exc:
                log(f"[cinematic] online TTS unavailable for scene {i + 1} ({type(exc).__name__}); trying offline voice")
                mp3.unlink(missing_ok=True)
            finally:
                if mp3.exists() and mp3.stat().st_size <= 1024:
                    mp3.unlink(missing_ok=True)

        if _windows_sapi_narrate(text, wav):
            out[i] = wav
            log(f"[cinematic] narration {i + 1}/{len(scenes)}: offline Windows voice")
        else:
            log(f"[cinematic] narration unavailable for scene {i + 1}; continuing with music and sound design")

    if not out:
        log("[cinematic] WARNING: no narration clips were generated")
    elif len(out) < len([s for s in scenes if str(s.get("text", "")).strip()]):
        log(f"[cinematic] WARNING: narration generated for {len(out)} of {len(scenes)} scenes")
    return out

def _wav(path, x):
    x = np.clip(x, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


def make_music(path, total, shots):
    n, buf = int(total * SR), None
    buf = np.zeros(int(total * SR), np.float32)
    segs: list[list] = []
    for s in shots:
        if segs and segs[-1][2] == s["emotion"]:
            segs[-1][1] = s["start"] + s["duration"]
        else:
            segs.append([s["start"], s["start"] + s["duration"], s["emotion"]])
    for a, b, emo in segs:
        a0, b0 = max(0, a - .6), min(total, b + .6)
        t = np.arange(int((b0 - a0) * SR)) / SR
        env = np.minimum(1, np.minimum(t / .9, (t[-1] - t) / .9)) ** 2 if len(t) else t
        y = sum(np.sin(2 * np.pi * f * t + k) + .5 * np.sin(2 * np.pi * f * 1.004 * t) for k, f in enumerate(CHORDS.get(emo, CHORDS["determined"])))
        y = y * (.75 + .25 * np.sin(2 * np.pi * .2 * t)) * env * .06
        i0 = int(a0 * SR)
        buf[i0:i0 + len(y)] += y[:len(buf) - i0].astype(np.float32)
    _wav(path, buf / max(1e-6, np.abs(buf).max()) * .5)


def make_sfx(path, total, shots):
    rng = np.random.default_rng(7)
    buf = np.zeros(int(total * SR), np.float32)

    def put(t0, y):
        i = int(t0 * SR)
        if i < len(buf):
            buf[i:i + len(y)] += y[:len(buf) - i]

    prev = None
    for s in shots:
        a, dur = s["start"], s["duration"]
        k, amp = AMBIENCE.get(s["location"], AMBIENCE["landscape"])
        if not prev or prev["location"] != s["location"] or prev["scene_index"] != s["scene_index"]:
            n = rng.normal(0, 1, int(dur * SR)).astype(np.float32)
            n = np.convolve(n, np.ones(k) / k, "same") * amp * 6
            f = int(min(len(n) // 2, .4 * SR))
            n[:f] *= np.linspace(0, 1, f); n[-f:] *= np.linspace(1, 0, f)
            put(a, n)
        if prev and prev["scene_index"] != s["scene_index"]:  # whoosh
            t = np.linspace(0, 1, int(.55 * SR))
            w = rng.normal(0, 1, len(t)) * np.sin(np.pi * t) ** 2
            put(max(0, a - .25), (w - np.convolve(w, np.ones(30) / 30, "same")).astype(np.float32) * .12)
        if s["layout"] in ("stat", "timeline", "title"):  # impact
            t = np.arange(int(.9 * SR)) / SR
            put(a + .05, (np.sin(2 * np.pi * (55 - 25 * t) * t) * np.exp(-t * 5) * .5).astype(np.float32))
        if s["action"] in ("walk", "run") and s["layout"] == "hero":
            step = .55 if s["action"] == "walk" else .3
            for q in np.arange(.2, dur - .1, step):
                t = np.arange(int(.12 * SR)) / SR
                put(a + q, (np.sin(2 * np.pi * 70 * t) * np.exp(-t * 35) * .3).astype(np.float32))
        prev = s
    _wav(path, buf)


def _amix_ok(ffmpeg):
    r = subprocess.run([ffmpeg, "-hide_banner", "-h", "filter=amix"], capture_output=True, text=True)
    return "normalize" in (r.stdout + r.stderr)


def build_mix_filter(offsets_ms, music_vol, total, norm_ok=True):
    fmt = "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo"
    nrm = ":normalize=0" if norm_ok else ""
    f = [f"[0:a]{fmt},volume={music_vol}[m]", f"[1:a]{fmt},volume=0.8[x]"]
    if offsets_ms:
        for k, ms in enumerate(offsets_ms):
            f.append(f"[{2 + k}:a]{fmt},volume=1.5,adelay={ms}|{ms}[n{k}]")
        labs = "".join(f"[n{k}]" for k in range(len(offsets_ms)))
        f.append(f"{labs}amix=inputs={len(offsets_ms)}{nrm}:duration=longest[narr]" if len(offsets_ms) > 1 else "[n0]anull[narr]")
        f += ["[narr]asplit=2[na][nb]", "[m][na]sidechaincompress=threshold=0.04:ratio=9:attack=15:release=350[md]",
              f"[md][x][nb]amix=inputs=3{nrm}:duration=longest[mx]"]
    else:
        f.append(f"[m][x]amix=inputs=2{nrm}:duration=longest[mx]")
    f.append(f"[mx]alimiter=limit=0.95,apad=whole_dur={total:.3f}[out]")
    return ";".join(f)


def mix(out_wav, total, music, sfx, narration, music_vol=.35, ffmpeg="ffmpeg"):
    """narration: list[(Path, start_seconds)]"""
    ok = _amix_ok(ffmpeg)
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", str(music), "-i", str(sfx)]
    for p, _ in narration:
        cmd += ["-i", str(p)]
    cmd += ["-filter_complex", build_mix_filter([int(t * 1000) for _, t in narration], music_vol, total, ok),
            "-map", "[out]", "-t", f"{total:.3f}", "-ar", "44100", str(out_wav)]
    subprocess.run(cmd, check=True)


def _ts(t):
    h, r = divmod(int(t * 1000), 3600000)
    m, r = divmod(r, 60000)
    return f"{h:02}:{m:02}:{r // 1000:02},{r % 1000:03}"


def write_srt(path, shots):
    seen, rows = set(), []
    for s in shots:
        if s["scene_index"] >= 0 and s["scene_index"] not in seen:
            seen.add(s["scene_index"])
            rows.append(f"{len(rows) + 1}\n{_ts(s['start'])} --> {_ts(s['start'] + s['scene_dur'])}\n{s['text']}\n")
    Path(path).write_text("\n".join(rows), encoding="utf-8")


def assemble(video, audio, srt, out, ffmpeg="ffmpeg"):
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", str(video), "-i", str(audio)]
    if srt and Path(srt).stat().st_size:
        cmd += ["-i", str(srt)]
    cmd += ["-map", "0:v", "-map", "1:a"] + (["-map", "2:s", "-c:s", "mov_text"] if len(cmd) > 9 else [])
    cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
