# AI-Cinema-Engine

A Python-based hybrid cinema pipeline with an offline procedural animation backend by default, plus separate LEGO and legacy realistic documentary renderers.

## Current architecture

- `cinema.py`: unified command-line entry point and renderer selection.
- `core/contracts.py`: shared validation/inspection for the existing LEGO and modern storyboard JSON formats.
- `core/runner.py`: launches the preserved renderer as a subprocess, isolates its working directory and reports failures.
- `lego_boost.py` / `lego_ai.py` / `lego_director.py` / `lego_engine_v2.py`: existing LEGO pipeline (preserved).
- `lego_modern.py`: realistic archive-photo documentary renderer with local cinematic editing and licence provenance.

The orchestration layer deliberately delegates to the existing renderers instead of importing and patching their internal modules. This avoids the current legacy import chain leaking into the new entry point.

## Quick start (Windows PowerShell)

Install Python dependencies:

```powershell
python -m pip install -r requirements-cinema.txt
winget install Gyan.FFmpeg
```

For a zero-paid-service workflow, reuse a storyboard with --plan plan.json, or run a local Ollama model for planning with --provider ollama. The renderer's image downloader does not use Gemini, Pexels, Pollinations or paid video-generation APIs.

### Realistic film mode (free-asset workflow)

The realistic renderer uses **free, licence-filtered still images by default**. It does not call paid image or video-generation APIs.

- realistic_director.py derives scene-specific archive queries from the narration, selects shot sizes/camera direction, rejects unsupported named cast and writes period-aware prompts.
- The visual search order is: your own numbered files in media/ → Wikimedia Commons → Openverse.
- The automatic downloader accepts only Public Domain/PDM, CC0 and CC BY images. It deliberately rejects non-commercial, no-derivatives and share-alike licences in the default workflow.
- Every downloaded image records its title, creator, licence, licence URL and original source URL. The renderer writes both output_credits.txt (for your YouTube description) and output_assets.json (a machine-readable provenance record).
- Your own images and videos are not automatically assumed to be copyright-safe: only add assets you created or have permission/licence to use.
- If no acceptable image is found, rendering stops rather than silently downloading a random copyrighted image. Use --allow-cards only if you want a locally designed original graphic as fallback.
- The renderer applies local crop/resize, colour grading, cinematic movement, captions, transitions, sound effects, music and voiceover with Python/Pillow/FFmpeg.

#### Offline-first asset preparation (recommended)

The engine does **not** search image websites while encoding the final film. It prepares the full image set first and stores it in a persistent folder named after the script and its content hash. If a source website rate-limits or the internet disconnects halfway through, completed scene images and their licence records remain saved. Rerunning the same command resumes the missing scenes; the final render does not begin until every required scene has an image.

1. Prepare the entire image set and stop before video rendering:

```powershell
python cinema.py myscript.txt output.mp4 --style realistic --plan plan.json --content-style history --prepare-assets-only
```

2. Open the printed asset folder under assets/ and inspect contact_sheet.jpg. Each image is scene_001.jpg, scene_002.jpg, etc. Replace a scene image with another image you have the right to use if you prefer a different visual. If you replace an image, edit that scene's credit_and_source entry in asset_manifest.json to preserve the correct creator, licence and source URL. Do not claim an image is CC0/CC BY unless its original source confirms it.

3. Once the entire image set is approved, render with no image-site requests:

```powershell
python cinema.py myscript.txt output.mp4 --style realistic --plan plan.json --content-style history --offline
```

The same library is automatically reused for future renders of the same script and storyboard. If you change the script or a scene's visual query, the affected scene is marked stale and must be prepared again. To use a different local library location, pass --asset-library D:\\CinemaAssets.

You can also use --offline from the start when you have already populated the scene_NNN.jpg files and manifest. Missing assets cause a clear error; the renderer never silently substitutes a different image mid-film.

- You can add your own properly licensed moving clips in media/videos/scene_001.mp4, scene_002.mp4, etc. Their audio is ignored; the engine mixes its own narration/music/SFX.

Install Python dependencies and FFmpeg:

```powershell
python -m pip install -r requirements-cinema.txt
winget install Gyan.FFmpeg
```

Use an existing storyboard:

```powershell
python cinema.py myscript.txt output_realistic.mp4 --style realistic --plan plan.json --content-style history --source auto
```

Run a low-resolution test first:

```powershell
python cinema.py myscript.txt realistic_preview.mp4 --style realistic --plan plan.json --content-style history --preview --silent --nomusic
```

Render 1080p (default) or 720p:

```powershell
python cinema.py myscript.txt output_realistic_1080p.mp4 --style realistic --plan plan.json --content-style history --resolution 1080p
```

Intel graphics: --encoder auto tests whether FFmpeg can initialize Intel Quick Sync (H.264 QSV). It selects QSV only if the runtime test succeeds; otherwise it falls back to CPU libx264. To require QSV, use --encoder h264_qsv. To force CPU encoding, use --encoder libx264.

#### Copyright and YouTube safety

A transformation (crop, filter, colour grade, pan/zoom, captions or narration) does **not** make an unlicensed image yours. Use the original licence terms, preserve the attribution and keep the generated assets manifest. Openverse is a discovery index, not a legal warranty: verify the original source page and licence before publishing. YouTube states that even public-domain/Creative Commons/fair-use routes do not guarantee freedom from Content ID claims or copyright strikes. If a claim appears, use the original source page and saved provenance to review or dispute it only when you have a valid basis.

The default licence filter is intentionally conservative: Public Domain/PDM, CC0 and CC BY only. CC BY requires attribution. CC BY-SA, NC and ND are excluded until their additional conditions can be handled explicitly.

The Openverse API is free to access subject to its terms and rate limits; Openverse may change its terms, so review them before large-scale/commercial API use. No API key is required for ordinary anonymous queries at the time of writing.


### Fully local procedural animation mode (default)

The default renderer is now the local Blender animation backend. It does not request images or footage from websites, and it does not call external image/video-generation APIs:

```powershell
winget install BlenderFoundation.Blender
python cinema.py myscript.txt output_animation.mp4
```

You can also reuse a storyboard:
```powershell
python cinema.py myscript.txt output_animation.mp4 --style animation --plan plan.json
```

The animation backend is fully offline. Its deterministic `cinematic_director.py` reads each scene and assigns a basic action, mood, environment, shot size and camera move without loading an LLM or calling an API. Blender uses reusable low-complexity environment kits (forest, village, battlefield, water and mountains), shot-specific camera framing, simple character travel/gestures and reduced render defaults (960x540 at 15 fps; preview is 640x360). These changes reduce unnecessary work and make scene composition respond to the script. This remains an early procedural animation prototype—not photorealistic character animation: detailed rigging, convincing gait, nuanced facial acting, lip-sync, multiple interacting characters and advanced effects remain future work. It saves a companion .blend project beside the MP4. Set `BLENDER_EXE` if Blender is not on PATH.

LEGO mode remains available with `--style lego`. The old archive-photo workflow is now opt-in only with `--style realistic`; it is not used by the default animation mode. The animation backend does not require online LLM planning; without `--plan`, it splits the supplied script into scene beats locally.

### LEGO mode

```powershell
python cinema.py myscript.txt output.mp4 --style lego
```

The unified entry point delegates to `lego_boost.py`, which enables its improved narration fallback and scene/background upgrades while preserving the existing LEGO engine.

Use a saved LEGO plan:

```powershell
python cinema.py myscript.txt output.mp4 --style lego --plan plan.json
```

Use the faster LEGO rendering setting:

```powershell
python cinema.py myscript.txt output.mp4 --style lego --fast
```

## Plan validation and tests

The shared validator checks the common minimum contract (`title` and non-empty `scenes[].text`) without rewriting renderer-specific scene fields.

Run tests:

```powershell
python -m unittest discover -s tests -v
```

## Realistic-renderer scope and limitations

The free pipeline is image-first: it retrieves licence-filtered archival stills and turns them into cinematic sequences with local movement, grading, transitions, narration, music and sound design. It does not currently generate photorealistic moving footage locally. User-supplied moving clips are supported when their rights are clear. A future local video model would need to be evaluated for Intel hardware before it can be added without cloud fees.

Intel QSV is an optional H.264 encoding acceleration only. It does not generate images or video. Intel QSV is selected only after a real FFmpeg runtime probe; CPU encoding remains the fallback.


## Visual candidate selection

The realistic renderer supports multiple licensed image candidates per scene, a comparison contact sheet, a persistent manual selection file, and offline rendering. See [VISUAL_SELECTION.md](VISUAL_SELECTION.md) for the complete workflow.

## Cinematic documentary pipeline (`--style cinematic`)

Story-driven pipeline: **story intelligence -> cinematic director -> documentary compositor -> audio -> MP4**.
No Blender or GPU needed (Pillow + NumPy + FFmpeg).

```
pip install -r requirements-cinematic.txt
python cinema.py script.txt out.mp4 --style cinematic --cinematic-res 720p
python cinematic_pipeline.py script.txt out.mp4 --resolution 1080p   # direct CLI
```
- `pipeline/story.py`: characters, pronoun/location/time/emotion continuity, events.
- `pipeline/director.py`: layout per scene (hero, stat count-up, timeline, quote, map), shots, camera moves, frame-exact timing.
- `pipeline/docu.py`: parallax landscapes, rim-lit actors, particles, lower-thirds, karaoke captions, filmic grade, dissolves.
- `pipeline/audio.py`: edge-tts narration (synced durations), generative score, SFX, ducked mix, SRT + muxed MP4.
- Put photos at `media/scene_001.jpg` ... to use Ken-Burns photo plates instead of procedural art.
- Work files (shot plan, story bible, audio) are written to `cinema_work/<script>/`.
