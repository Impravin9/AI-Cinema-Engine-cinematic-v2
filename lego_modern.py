#!/usr/bin/env python3
"""
lego_modern.py - realistic documentary renderer (licensed archive stills + cinematic editing + banners + narration). No 2D cartoon.
Same folder as lego_boost.py, lego_ai.py, lego_director.py, lego_engine_v2.py (reuses their LLM + DSP code, edits nothing).
  pip install edge-tts requests ; ffmpeg in PATH
  python lego_modern.py script.txt out.mp4                    # use --plan for a saved storyboard or --provider ollama for local planning -> fetch licensed visuals -> render
  python lego_modern.py script.txt --prompt-only              # export a prompt; or use --plan with a saved storyboard
  python lego_modern.py script.txt out.mp4 --plan modern_plan.json     # (your old plan.json also works)
  flags: --voice en-US-AndrewMultilingualNeural|en-US-AriaNeural|en-GB-RyanNeural|en-IN-PrabhatNeural  --rate +0%  --pitch -2Hz
         --source auto|photo|gen   --media media/  --music music/   --preview (640x360 12fps)   --silent   --endcard   --style history|mythology|news|science|animals|story
Visual sources per scene: your own numbered media/<n>.jpg|png -> Wikimedia Commons -> Openverse.
Only Public Domain/PDM, CC0 and CC BY assets are accepted; attribution is saved.
No paid image/video generation APIs are called by this renderer.
Music: drop royalty-free mp3/wav into music/ named epic_*.mp3 tense_*.mp3 sad_*.mp3 calm_*.mp3 up_*.mp3 (else a built-in cinematic score is synthesised).
Output: out.mp4 + out_credits.txt (paste in YouTube description: licence attribution) + out_pack.txt (title, chapters).
"""
import os, re, sys, io, json, math, time, base64, shutil, hashlib, argparse, subprocess, tempfile, urllib.request, urllib.parse, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
import lego_boost as B
from asset_licensing import lic_ok
from asset_library import (open_library, save_manifest, scene_asset_path, valid_scene_asset, register_scene_asset, candidate_asset_path, register_scene_candidates, select_scene_candidate, load_selection_file)
from realistic_director import prepare_plan
A = B.A; E = B.E
clamp = lambda v, a, b: max(a, min(b, v))
SR = E.SR
UA = {'User-Agent': 'LegoModernDoc/1.0 (documentary tool; ' + os.environ.get('LEGO_CONTACT', 'set env LEGO_CONTACT to your email') + ')'}
ACC = dict(history=(232, 177, 60), mythology=(245, 140, 50), news=(225, 50, 50), science=(60, 170, 235), animals=(90, 200, 120), story=(180, 120, 240))
MOODS = ('epic', 'tense', 'sad', 'up', 'calm')
OK_LIC = ('public domain', 'pd', 'cc0', 'cc by', 'cc-by', 'attribution', 'free art', 'gfdl', 'copyrighted free use', 'no restrictions')

# ================================================================ planning
SYSTEM = """You are a professional documentary film director, historical researcher and cinematographer.
Return ONLY valid JSON, no prose or code fences.
Schema: {"title":str,"style":"history|mythology|news|science|animals|story","scenes":[{"text":str,"visual":"photo|gen","queries":[str,str,str],"gen_prompt":str,"motion":"zoom_in|zoom_out|pan_left|pan_right|push_up","transition":"cut|fade|dip|whip|flash","mood":"epic|tense|sad|up|calm","banner":{"kind":"location|name|date|stat|quote|none","text":str,"sub":str},"chapter":str|null,"sfx":[str]}]}
DIRECTOR RULES:
1. Preserve every word of the supplied narration in original order across scenes. Do not summarize, omit, reorder or invent facts. Each scene covers one visual beat, usually 12-30 words and 4-9 seconds.
2. The supplied script is the source of truth. Never introduce an unrelated celebrity, politician, athlete, fictional character or modern public figure. A person may appear only if named in the script and relevant to that exact scene. If not named, show appropriate anonymous people, vehicles, places or objects.
3. Historical scenes must match the narrated year, country, uniforms, weapons, vehicles, architecture, flags and technology. Never insert modern clothing, modern cars, modern politicians, football players or present-day equipment into a historical scene.
4. Direct what the camera should show, not merely what the narrator mentions. If narration describes a battle, show the battle. If it describes a letter, show the letter. If it describes a city under siege, establish the city and civilians. A mentioned person who is not physically present must not be inserted into the shot.
5. For real historical events and existing people/places, choose visual="photo" and provide precise archive-search queries using event + person/place + year. For unphotographable events, reconstructions, concepts or mythology, use visual="gen" with a specific photorealistic reconstruction prompt.
6. Every gen_prompt describes one coherent cinematic frame: subject, action, period, setting, composition, shot size, lens, lighting, atmosphere and realistic materials. Include no text, no watermark, no collage.
7. Vary shot sizes: establishing wide, aerial wide, ground-level wide, medium, close-up, insert detail. Avoid repetitive Ken Burns motion. Motion must be slow and motivated.
8. Use only script-supported dates, names, statistics and quotes in banners. No invented captions or claims. Use banners sparingly, never two consecutive scenes.
9. Make visual narrative progress: establish geography, show action, show consequences, then transition to the next event. Avoid repeating the same image or subject in adjacent scenes.
10. Return a complete valid plan. Never leave a scene with empty text, queries or gen_prompt."""
STOP = set('in the and but a an on at of to for with as by from after before when while during then this that it he she they we his her its their one two three some many most each every how why what who where which if so yet nor or not no there here also only just over under into than'.split())
def toks_caps(t):
    out = []
    for m in re.finditer(r"[A-Z][a-zA-Z'\-]+(?:\s+(?:[A-Z][a-zA-Z'\-]+|of|the|II|III|IV))*", t):
        ws = m.group(0).split()
        while ws and ws[0].lower() in STOP: ws = ws[1:]
        while ws and ws[-1].lower() in STOP: ws = ws[:-1]
        if ws and len(' '.join(ws)) > 2: out.append(' '.join(ws))
    return list(dict.fromkeys(out))[:3]
GENERIC = ('narrator', 'soldier', 'civilian', 'anchor', 'crowd')
def jn(parts):
    o = ''
    for x in parts:
        if x and x.lower() not in o.lower() and o.lower() not in x.lower(): o = (o + ' ' + x).strip()
        elif x and len(x) > len(o): o = x
    return o
def adapt(plan, style):
    """accept old lego plan.json and fill missing modern fields"""
    title = plan.get('title') or 'Documentary'; style = plan.get('style') or style or {'doc': 'history', 'news': 'news', 'sports': 'news'}.get(plan.get('genre'), 'story'); out = []
    for i, s in enumerate(plan['scenes']):
        txt = s['text'].strip(); names = [a['name'] for a in s.get('actors', []) if not any(g in a['name'].lower() for g in GENERIC)]
        if not s.get('queries'):
            caps = toks_caps(txt); core = title.split(':')[0].strip(); pr = [p['name'] if isinstance(p, dict) else p for p in s.get('props', [])]
            s['queries'] = list(dict.fromkeys(q for q in [jn(names[:1] + [core]), jn(caps[:1] + [core]), jn(pr[:1] + [core]), jn(caps[:2])] if q)) or [core]
        s.setdefault('gen_prompt', f"cinematic photorealistic documentary still, {txt[:160]}, dramatic natural lighting, 35mm, shallow depth of field, 16:9")
        s.setdefault('visual', 'gen' if style == 'mythology' else 'photo')
        s['mood'] = s['mood'] if s.get('mood') in MOODS else {'tense': 'tense', 'epic': 'epic', 'sad': 'sad', 'up': 'up'}.get(s.get('music'), 'epic' if s.get('mood') in ('action', 'joy') else 'tense' if s.get('mood') in ('fear', 'mystery') else 'calm')
        s.setdefault('motion', ['zoom_in', 'pan_right', 'zoom_out', 'pan_left', 'push_up'][i % 5]); s['transition'] = s.get('transition') if s.get('transition') in ('cut', 'fade', 'dip', 'whip', 'flash') else ('fade' if i % 3 else 'dip')
        b = s.get('banner') or {}
        if not b.get('kind'):
            if names and i % 4 == 1: b = dict(kind='name', text=names[0].upper(), sub='')
            elif i % 5 == 3 and toks_caps(txt): b = dict(kind='location', text=toks_caps(txt)[0].upper(), sub='')
            else: b = dict(kind='none')
        s['banner'] = b; s.setdefault('chapter', None); s['sfx'] = [x for x in (s.get('sfx') or []) if isinstance(x, str)]; out.append(s)
    return dict(title=title, style=style, scenes=out)
def ask_plan(script, a):
    ch = choose_llm(a)
    if not ch: return None
    fn, mdl, key = ch; plan = None; known = ''
    for k, part in enumerate(A.chunks(script, 600)):
        user = (f'Continue the same documentary. Title so far: {plan["title"]}. Style: {plan["style"]}.\n\n' if plan else '') + 'SCRIPT PART ' + str(k + 1) + ':\n' + part
        for att in range(2):
            try: p = A.parse_json(fn(SYSTEM, user if not att else user + '\nReturn ONLY valid JSON.', mdl, key)); assert p.get('scenes'); break
            except Exception as e:
                if att: raise SystemExit(f'plan parse failed: {e}')
        if plan is None: plan = p
        else: plan['scenes'] += p['scenes']
    return plan
def choose_llm(a): return A.choose(a.provider, a.model)

# ================================================================ visuals
import ssl
def why(e):
    s = str(getattr(e, 'reason', e)); u = s.upper()
    if isinstance(e, urllib.error.HTTPError): return f'HTTP {e.code} {e.reason}' + (' (rate limited, slowing down)' if e.code == 429 else ' (blocked: set LEGO_CONTACT=your@email.com)' if e.code == 403 else '')
    if 'CERTIFICATE' in u or 'SSL' in u: return 'SSL certificate error (antivirus/proxy/old Windows certs). Fix: pip install -U certifi truststore'
    if 'GETADDRINFO' in u or 'NAME OR SERVICE' in u: return 'DNS failed: no internet, or VPN/firewall blocks it. Test https://commons.wikimedia.org in your browser'
    if 'TIMED OUT' in u or 'TIMEOUT' in u: return 'timed out (slow or blocked network)'
    if '10061' in u or 'REFUSED' in u: return 'connection refused (proxy/firewall)'
    return f'{type(e).__name__}: {s[:120]}'
class Net:
    off = set(); fails = {}; said = set(); ctxs = None
    @classmethod
    def ok(c, k): return k not in c.off
    @classmethod
    def good(c, k): c.fails[k] = 0
    @classmethod
    def bad(c, k, e):
        m = why(e); c.fails[k] = c.fails.get(k, 0) + 1
        if m not in c.said: c.said.add(m); print(f'  [{k}] {m}', flush=True)
        if c.fails[k] >= 4: c.off.add(k); print(f'  [{k}] disabled for this run after repeated failures -> other sources used', flush=True)
    @classmethod
    def contexts(c):
        if c.ctxs is None:
            c.ctxs = [None]
            try: import certifi; c.ctxs.append(ssl.create_default_context(cafile=certifi.where()))
            except Exception: pass
            try: import truststore; c.ctxs.append(truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
            except Exception: pass
        return c.ctxs
def http(url, hdr=None, timeout=25, tries=3, retry429=True):
    rq = urllib.request.Request(url, headers=dict(UA, **(hdr or {}))); last = None
    for k in range(tries):
        for ctx in list(Net.contexts()):
            try:
                r = urllib.request.urlopen(rq, timeout=timeout, context=ctx).read()
                if ctx is not None and Net.ctxs[0] is None: Net.ctxs.remove(ctx); Net.ctxs.insert(0, ctx)  # remember the context that works
                return r
            except urllib.error.HTTPError as e:
                last = e
                if e.code in (429, 503) and retry429: time.sleep(int(e.headers.get('Retry-After', 4 * (k + 1)) or 4)); break
                raise
            except Exception as e:
                last = e
                if 'CERTIFICATE' in str(getattr(e, 'reason', e)).upper(): continue
                break
        time.sleep(1.2 * (k + 1))
    raise last
def net_check():
    try: http('https://commons.wikimedia.org/w/api.php?action=query&meta=siteinfo&format=json', timeout=15, tries=1); print('network: Wikimedia OK', flush=True)
    except Exception as e: Net.off.add('commons'); print(f'network: Wikimedia unreachable -> {why(e)}\n  Openverse and user-supplied local assets remain available as fallback', flush=True)
def strip_html(s): return re.sub(r'<[^>]+>', '', s or '').strip()[:80]
def src_local(i, d):
    for ext in ('jpg', 'jpeg', 'png', 'webp'):
        p = os.path.join(d, f'{i + 1}.{ext}')
        if os.path.exists(p): return Image.open(p), 'local file ' + p
def src_commons(qs, used):
    if not Net.ok('commons'): return
    qs = list(dict.fromkeys(qs + [' '.join(q.split()[:3]) for q in qs if len(q.split()) > 3]))
    for q in qs:
        try:
            u = 'https://commons.wikimedia.org/w/api.php?' + urllib.parse.urlencode(dict(action='query', generator='search', gsrsearch=q + ' filetype:bitmap', gsrnamespace=6, gsrlimit=12, prop='imageinfo', iiprop='url|size|mime|extmetadata', iiurlwidth=1920, format='json'))
            pg = json.loads(http(u, timeout=20)).get('query', {}).get('pages', {}); Net.good('commons')
            for p in sorted(pg.values(), key=lambda x: x.get('index', 99)):
                ii = (p.get('imageinfo') or [{}])[0]; em = ii.get('extmetadata', {}); lic = em.get('LicenseShortName', {}).get('value', '')
                if ii.get('mime') not in ('image/jpeg', 'image/png') or ii.get('width', 0) < 1000 or ii.get('width', 0) < ii.get('height', 1) * .9 or not lic_ok(lic) or ii['url'] in used: continue
                try: im = Image.open(io.BytesIO(http(ii.get('thumburl') or ii['url'], timeout=40)))
                except Exception as e: Net.bad('commons', e); continue
                used.add(ii['url']); return im, f"Wikimedia Commons | title: {strip_html(p.get('title'))} | creator: {strip_html(em.get('Artist', {}).get('value')) or 'Creator not stated'} | licence: {lic} | licence terms: {strip_html(em.get('LicenseUrl', {}).get('value'))} | original source: {ii.get('descriptionurl')}"
        except Exception as e:
            Net.bad('commons', e)
            if not Net.ok('commons'): return
def src_openverse(qs, used):
    """Search Openverse for CC0, PDM and CC BY landscape images."""
    if not Net.ok('openverse'):
        return
    for q in qs:
        try:
            params = {
                'q': q, 'license': 'cc0,pdm,by',
                'license_type': 'commercial,modification',
                'extension': 'jpg,jpeg,png', 'aspect_ratio': 'wide',
                'size': 'large', 'page_size': 20, 'mature': 'false',
                'filter_dead': 'true',
            }
            endpoint = 'https://api.openverse.org/v1/images/?' + urllib.parse.urlencode(params)
            results = json.loads(http(endpoint, timeout=25)).get('results', [])
            Net.good('openverse')
            for item in results:
                lic = str(item.get('license') or '').lower()
                if lic not in {'cc0', 'pdm', 'by'}:
                    continue
                if int(item.get('width') or 0) < 1000 or int(item.get('height') or 0) < 500:
                    continue
                source_url = item.get('url') or item.get('thumbnail')
                if not source_url or source_url in used:
                    continue
                try:
                    im = Image.open(io.BytesIO(http(source_url, timeout=40)))
                except Exception:
                    thumb = item.get('thumbnail')
                    if not thumb or thumb == source_url:
                        continue
                    try:
                        im = Image.open(io.BytesIO(http(thumb, timeout=40)))
                    except Exception as e:
                        Net.bad('openverse', e)
                        continue
                used.add(source_url)
                title = strip_html(item.get('title') or 'Untitled')
                creator = strip_html(item.get('creator') or 'Creator not stated')
                licence = ('CC0 ' + str(item.get('license_version') or '1.0')) if lic == 'cc0' else ('Public Domain Mark' if lic == 'pdm' else 'CC BY ' + str(item.get('license_version') or '4.0'))
                credit = (
                    f"Openverse | title: {title} | creator: {creator} | "
                    f"licence: {licence} | licence terms: {item.get('license_url') or ''} | "
                    f"original source: {item.get('foreign_landing_url') or ''} | "
                    f"creator page: {item.get('creator_url') or ''}"
                )
                return im, credit
        except Exception as e:
            Net.bad('openverse', e)
            if not Net.ok('openverse'):
                return

def card(text, acc, W=1920, H=1080):
    im = Image.new('RGB', (W, H)); a = np.linspace(0, 1, H)[:, None, None]; arr = (np.array((14, 18, 30)) * (1 - a) + np.array(acc) * .35 * a).astype(np.uint8); im = Image.fromarray(np.repeat(arr, W, 1))
    d = ImageDraw.Draw(im); f = E.font(90); words = text.split(); lines = []; cur = ''
    for w in words:
        if d.textlength(cur + ' ' + w, font=f) > W * .7 and cur: lines.append(cur); cur = w
        else: cur = (cur + ' ' + w).strip()
    lines.append(cur)
    for j, l in enumerate(lines[:4]): d.text((W // 2, H // 2 + (j - len(lines[:4]) / 2 + .5) * 110), l, font=f, fill=(240, 240, 245), anchor='mm')
    return im
def fetch(i, s, a, style, used, cache):
    """Resolve a scene using local assets and openly licensed still images only."""
    key = hashlib.md5(('free-license-v2|' + str(i) + str(s.get('queries')) + s.get('gen_prompt', '') + str(a.source)).encode()).hexdigest()[:12]
    cp = os.path.join(cache, key + '.jpg')
    mp = cp + '.txt'
    if os.path.exists(cp) and os.path.exists(mp):
        cached_credit = open(mp, encoding='utf-8').read()
        cache_allowed = cached_credit.startswith('LOCAL USER ASSET |')
        if cached_credit.startswith(('Wikimedia Commons |', 'Openverse |')):
            match = re.search(r'licence:\s*([^|]+)', cached_credit, re.IGNORECASE)
            cache_allowed = bool(match and lic_ok(match.group(1).strip()))
        if cached_credit.startswith('designed card |'):
            cache_allowed = bool(a.allow_cards)
        if cache_allowed:
            return Image.open(cp).convert('RGB'), cached_credit

    local = src_local(i, a.media)
    if local:
        result = (local[0], local[1] + ' | rights: user must confirm ownership or licence')
    else:
        queries = s.get('queries') or [s.get('text', '')[:100]]
        result = src_commons(queries, used) or src_openverse(queries, used)

    if not result:
        if not a.allow_cards:
            raise RuntimeError(
                f"No licence-approved image found for scene {i + 1}: {s['text'][:100]!r}. "
                "Add a properly licensed image to media/<scene-number>.jpg, "
                "or rerun with --allow-cards to use an original locally designed card. "
                "Paid image APIs are not used by this free-assets workflow."
            )
        result = (card(re.sub(r'\s+', ' ', s['text'])[:90], ACC.get(style, ACC['history'])), 'designed card | original local graphic')
    im = result[0].convert('RGB')
    im.save(cp, quality=93)
    with open(mp, 'w', encoding='utf-8') as handle:
        handle.write(result[1])
    return im, result[1]
def fetch_candidates(i, s, a, style, used, limit):
    """Collect several distinct licence-approved candidates for one scene."""
    local = src_local(i, a.media)
    if local:
        image, credit = local
        return [{"id": "c01", "image": image.convert("RGB"),
                 "credit_and_source": credit + " | rights: user must confirm ownership or licence"}]
    queries = s.get("queries") or [s.get("text", "")[:100]]
    candidates = []
    for _ in range(max(1, min(int(limit), 8))):
        result = src_commons(queries, used) or src_openverse(queries, used)
        if not result:
            break
        image, credit = result
        candidates.append({"id": f"c{len(candidates) + 1:02d}",
                           "image": image.convert("RGB"),
                           "credit_and_source": credit})
    if not candidates and a.allow_cards:
        candidates.append({"id": "c01",
                           "image": card(re.sub(r"\s+", " ", s["text"])[:90], ACC.get(style, ACC["history"])),
                           "credit_and_source": "designed card | original local graphic"})
    if not candidates:
        raise RuntimeError(
            f"No licence-approved image candidates found for scene {i + 1}: {s['text'][:100]!r}. "
            "Add a properly licensed image to media/<scene-number> or retry later. "
            "Paid image APIs are not used."
        )
    return candidates


def locate_scene_video(index, folder):
    """Find an optional moving scene clip using a predictable 1-based filename."""
    names = (f"scene_{index + 1:03d}.mp4", f"scene_{index + 1}.mp4",
             f"{index + 1:03d}.mp4", f"{index + 1}.mp4")
    for name in names:
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            return path
    return None

def extract_scene_video(path, cache, W, H, FPS):
    """Decode a scene clip into cached frames so it can share the existing edit timeline."""
    stat = os.stat(path)
    key = hashlib.sha1(f"{os.path.abspath(path)}|{stat.st_size}|{stat.st_mtime_ns}|{W}|{H}|{FPS}".encode()).hexdigest()[:16]
    folder = os.path.join(cache, 'video_frames', key)
    os.makedirs(folder, exist_ok=True)
    existing = sorted(
        os.path.join(folder, name) for name in os.listdir(folder)
        if name.lower().endswith('.jpg') and name.startswith('frame_')
    )
    if existing:
        return existing
    pattern = os.path.join(folder, 'frame_%06d.jpg')
    vf = f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    result = subprocess.run(
        ['ffmpeg', '-y', '-v', 'error', '-i', path, '-an', '-vf', vf,
         '-q:v', '2', pattern],
        capture_output=True, text=True
    )
    frames = sorted(
        os.path.join(folder, name) for name in os.listdir(folder)
        if name.lower().endswith('.jpg') and name.startswith('frame_')
    )
    if result.returncode != 0 or not frames:
        raise RuntimeError(f"Could not decode scene video {path}: {(result.stderr or 'no frames produced')[-500:]}")
    return frames

def compose(im, W=1920, H=1080):
    """cover-crop if aspect ok, else blurred-fill background + contained sharp image"""
    ar = im.width / im.height
    if im.width < W: im = im.resize((W, int(W / ar)) if ar >= W / H else (int(H * ar), H), Image.LANCZOS) if im.width < W * .98 and ar >= W / H * .9 else im
    if .8 * W / H <= ar <= 1.35 * W / H:
        sc = max(W / im.width, H / im.height); r = im.resize((int(im.width * sc) + 1, int(im.height * sc) + 1), Image.LANCZOS); x = (r.width - W) // 2; y = (r.height - H) // 2; return r.crop((x, y, x + W, y + H))
    sc = max(W / im.width, H / im.height); bg = im.resize((int(im.width * sc) + 1, int(im.height * sc) + 1), Image.BILINEAR); x = (bg.width - W) // 2; y = (bg.height - H) // 2
    bg = bg.crop((x, y, x + W, y + H)).filter(ImageFilter.GaussianBlur(38)); bg = ImageEnhance.Brightness(bg).enhance(.55); sc = min(W / im.width, H / im.height) * (1.0 if ar < 1 else 1.0)
    fg = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.LANCZOS); sh = Image.new('RGBA', bg.size, (0, 0, 0, 0)); px = (W - fg.width) // 2; py = (H - fg.height) // 2
    ImageDraw.Draw(sh).rectangle([px + 10, py + 14, px + fg.width + 10, py + fg.height + 14], fill=(0, 0, 0, 150)); sh = sh.filter(ImageFilter.GaussianBlur(18)); bg = Image.alpha_composite(bg.convert('RGBA'), sh).convert('RGB'); bg.paste(fg, (px, py)); return bg
GRADE = dict(epic=(1.14, 1.06, 1.0), tense=(1.12, .8, .96), sad=(1.05, .7, .94), up=(1.06, 1.15, 1.06), calm=(1.03, 1.0, 1.04))
def grade(im, mood):
    c, s, b = GRADE.get(mood, GRADE['epic']); im = ImageEnhance.Brightness(ImageEnhance.Color(ImageEnhance.Contrast(im).enhance(c)).enhance(s)).enhance(b)
    x = np.asarray(im, np.float32); l = (x @ np.array([.299, .587, .114], np.float32) / 255)[..., None]
    x = x + (1 - l) ** 2 * np.array([-7, 2, 10], np.float32) + l ** 2 * np.array([10, 4, -8], np.float32)
    return Image.fromarray(np.clip(x, 0, 255).astype(np.uint8))

# ================================================================ audio
def tts_scene(a, rate_by_mood):
    caches = {}; tmp = tempfile.gettempdir()
    def f(s, i, mood):
        rate = rate_by_mood.get(mood, a.rate)
        if rate not in caches: caches[rate] = B.tts_auto(a.voice, rate)
        return caches[rate](s, 1000 + i)
    return f
def read_wav(p):
    with wave.open(p) as q: return np.frombuffer(q.readframes(q.getnframes()), np.int16).astype(np.float32) / 32768
def synth_music(scenes, total):
    n = int((total + 2) * SR); mus = np.zeros((n, 2), np.float32); P = dict(epic=[(110, 165, 220), (87.3, 130.8, 174.6), (130.8, 196, 261.6), (98, 146.8, 196)], tense=[(73.4, 110, 146.8)] * 4, sad=[(110, 164.8, 220), (87.3, 130.8, 174.6)] * 2, up=[(130.8, 196, 261.6), (98, 146.8, 196), (110, 164.8, 220), (87.3, 130.8, 174.6)], calm=[(130.8, 196, 246.9)] * 4)
    for sc in scenes:
        m = sc['mood']; ch = P[m]; t = sc['t0']; bar = 0
        while t < sc['t0'] + sc['dur'] - .5:
            tp = E.Tt(4.2); notes = ch[bar % len(ch)]; pad = sum(E.lp(E.saw(f + 0 * tp) + E.saw(f * 1.006 + 0 * tp), 900 if m != 'calm' else 600) for f in notes) / 3
            env = np.clip(tp / 1.2, 0, 1) * np.clip((4.2 - tp) / 1.4, 0, 1); E.place(mus, pad * env * .5, t, 1.0, 0)
            if m in ('epic', 'tense'):
                for k in range(4): E.place(mus, E.sine(55 + 0 * E.Tt(.5)) * E.ad(E.Tt(.5), .005, .2) * (.5 if m == 'epic' else .35), t + k * (1.0 if m == 'tense' else .5 * 2), 1.0, 0)
            t += 4.0; bar += 1
    return mus * .55
def load_music(d, scenes, total):
    if not os.path.isdir(d): return None
    fs = [f for f in os.listdir(d) if f.lower().endswith(('.mp3', '.wav', '.m4a', '.ogg'))]
    if not fs: return None
    n = int((total + 2) * SR); mus = np.zeros((n, 2), np.float32)
    for sc in scenes:
        c = [f for f in fs if f.lower().startswith(sc['mood'])] or fs; f = c[int(hashlib.md5((sc['mood'] + str(sc['si'] // 12)).encode()).hexdigest(), 16) % len(c)]
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', os.path.join(d, f), '-ar', str(SR), '-ac', '2', '-f', 'f32le', '-'], capture_output=True).stdout; x = np.frombuffer(raw, np.float32).reshape(-1, 2)
        if len(x) < SR: continue
        o = int(sc['t0'] * SR); L = int(sc['dur'] * SR); off = (sc['si'] * 7 * SR) % max(1, len(x)); seg = np.take(x, np.arange(off, off + L) % len(x), axis=0)
        fd = min(int(.8 * SR), L // 2); seg = seg.copy(); seg[:fd] *= np.linspace(0, 1, fd)[:, None]; seg[-fd:] *= np.linspace(1, 0, fd)[:, None]; mus[o:o + L] += seg[:max(0, n - o)]
    return mus * .8
def build_audio(scenes, total, a, path):
    n = int((total + 2) * SR); nar = np.zeros(n, np.float32); fg = np.zeros((n, 2), np.float32)
    for sc in scenes:
        if sc.get('wav'): x = read_wav(sc['wav']); o = int((sc['t0'] + .15) * SR); x = x[:max(0, n - o)]; nar[o:o + len(x)] += x
        for j, nm in enumerate(sc.get('sfx_at', [])):
            if nm[1] in E.SFX: E.place(fg, E.SFX[nm[1]](), nm[0], .5, 0)
    mus = (load_music(a.music, scenes, total) if not a.nomusic else None); mus = synth_music(scenes, total) if mus is None and not a.nomusic else (mus if mus is not None else np.zeros((n, 2), np.float32))
    blk = np.pad(np.abs(nar), (0, 441 - len(nar) % 441)).reshape(-1, 441).max(1); kw = 25; env = np.convolve(np.pad(blk, (kw, kw), mode='edge'), np.ones(kw) / kw, 'same')[kw:-kw]
    duck = np.interp(np.arange(n) / SR, np.arange(len(env)) * .01, 1 - .62 * np.clip(env * 4, 0, 1)).astype(np.float32)
    x = nar * 1.0; x = x - .0 * x; mix = np.stack([x, x], 1) * 1.0 + mus * duck[:, None] * a.musicvol + fg
    f1, f2 = int(.4 * SR), int(1.6 * SR); mix[:f1] *= np.linspace(0, 1, f1)[:, None]; mix[-f2:] *= np.linspace(1, 0, f2)[:, None]
    mix = np.tanh(mix * 1.1) / np.tanh(1.1); mix *= .9 / max(np.abs(mix).max(), 1e-6)
    with wave.open(path, 'wb') as w: w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((mix * 32767).astype(np.int16).tobytes())

# ================================================================ rendering
ease = lambda p: p * p * (3 - 2 * p)
def kb(sc, u, t):
    m = sc['motion']; u = ease(clamp(u, 0, 1)); z = 1.0 + .2 * u if m == 'zoom_in' else 1.2 - .2 * u if m == 'zoom_out' else 1.15 if m in ('pan_left', 'pan_right') else 1.13
    cx = .5 + (.07 * (u - .5) * 2 if m == 'pan_right' else -.07 * (u - .5) * 2 if m == 'pan_left' else 0); cy = .5 - (.06 * (u - .5) * 2 if m == 'push_up' else 0)
    cx += .0015 * math.sin(t * 1.3); cy += .0015 * math.sin(t * 1.7 + 1); return z, cx, cy
class Ren:
    def __init__(s, W, H, FPS, acc, style):
        s.W, s.H, s.FPS, s.acc, s.style = W, H, FPS, acc, style; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
        s.vig = (1 - .38 * np.clip(d - .55, 0, 1) ** 1.4)[..., None].astype(np.float32); s.rng = np.random.default_rng(5); s.sh = H / 720; s.cc = {}
    def F(s, sz): return E.font(sz * s.sh)
    def base(s, sc, t):
        if sc.get('video_frames'):
            frames = sc['video_frames']
            frame_index = min(len(frames) - 1, max(0, int(t * s.FPS)))
            return s.patch(('video', sc['si'], frame_index),
                           lambda: Image.open(frames[frame_index]).convert('RGB').resize((s.W, s.H), Image.LANCZOS))
        u = t / max(sc['dur'], .1); z, cx, cy = kb(sc, u, t); B_ = sc['img']; w = B_.width / z; h = B_.height / z; x0 = clamp(cx * B_.width - w / 2, 0, B_.width - w); y0 = clamp(cy * B_.height - h / 2, 0, B_.height - h)
        return B_.resize((s.W, s.H), Image.BICUBIC, box=(x0, y0, x0 + w, y0 + h))
    def trans(s, a, b, kind, p):
        p = ease(p)
        if kind == 'dip': return Image.blend(a, Image.new('RGB', a.size), p * 2) if p < .5 else Image.blend(Image.new('RGB', a.size), b, (p - .5) * 2)
        if kind == 'flash': w = Image.new('RGB', a.size, (255, 255, 255)); return Image.blend(a, w, p * 2) if p < .5 else Image.blend(w, b, (p - .5) * 2)
        if kind == 'whip':
            cv = Image.new('RGB', a.size); cv.paste(a, (-int(p * s.W), 0)); cv.paste(b, (int((1 - p) * s.W), 0)); bl = int(70 * math.sin(p * math.pi)); r = Image.blend(Image.fromarray(np.roll(np.asarray(cv), bl, 1)), Image.fromarray(np.roll(np.asarray(cv), -bl, 1)), .5); return Image.blend(r, cv, .3)
        return Image.blend(a, b, p)
    def patch(s, key, fn):
        if key not in s.cc:
            if len(s.cc) > 400: s.cc.clear()
            s.cc[key] = fn()
        return s.cc[key]
    def panel(s, w, h, fill, rad):
        im = Image.new('RGBA', (int(w), int(h)), (0, 0, 0, 0)); ImageDraw.Draw(im).rounded_rectangle([0, 0, w - 1, h - 1], rad, fill=fill); return im
    def lower(s, fr, b, t, T):
        if b['kind'] in ('none', 'stat', 'quote') or not b.get('text'): return
        ts, te = .7, min(T - .4, 4.8)
        if te - ts < 1.2: return
        a_in = ease(clamp((t - ts) / .5, 0, 1)); a_out = ease(clamp((te - t) / .45, 0, 1)); k = min(a_in, a_out)
        if k <= 0: return
        def mk():
            ft, fs = s.F(36), s.F(22); main = b['text'].upper()[:34]; sub = (b.get('sub') or ('LOCATION' if b['kind'] == 'location' else '')).upper()[:48]; d0 = ImageDraw.Draw(Image.new('RGB', (4, 4)))
            wd = max(d0.textlength(main, font=ft), d0.textlength(sub, font=fs)) + 70 * s.sh; hh = (96 if sub else 66) * s.sh; im = s.panel(wd, hh, (10, 12, 18, 215), 8 * s.sh); d = ImageDraw.Draw(im)
            d.rounded_rectangle([0, 0, 9 * s.sh, hh - 1], 4, fill=s.acc + (255,)); d.text((34 * s.sh, 12 * s.sh), main, font=ft, fill=(255, 255, 255)); d.text((34 * s.sh, 58 * s.sh), sub, font=fs, fill=s.acc) if sub else None
            return im
        im = s.patch(('lt', b['text'], b.get('sub')), mk); x = int(-im.width + (im.width + 60 * s.sh) * k); fr.paste(im, (x, int(s.H * .62)), im)
    def bigbanner(s, fr, b, t, T):
        if b['kind'] not in ('stat', 'quote') or not b.get('text'): return fr
        ts, te = .6, min(T - .3, 5.2)
        if te - ts < 1.4: return fr
        k = min(ease(clamp((t - ts) / .55, 0, 1)), ease(clamp((te - t) / .45, 0, 1)))
        if k <= 0: return fr
        sh = Image.new('RGBA', fr.size, (0, 0, 0, int(150 * k))); fr = Image.alpha_composite(fr.convert('RGBA'), sh); d = ImageDraw.Draw(fr)
        if b['kind'] == 'stat':
            f1, f2 = s.F(120), s.F(34); x = int(s.W * .08 - (1 - k) * 60); d.rectangle([x, int(s.H * .30), x + int(8 * s.sh), int(s.H * .30) + int(200 * s.sh)], fill=s.acc + (int(255 * k),))
            d.text((x + 30 * s.sh, s.H * .30 - 6), b['text'].upper(), font=f1, fill=s.acc + (int(255 * k),)); d.text((x + 34 * s.sh, s.H * .30 + 150 * s.sh), (b.get('sub') or '').upper(), font=f2, fill=(240, 240, 240, int(255 * k)))
        else:
            f1, f2 = s.F(46), s.F(26); words = b['text'].split(); lines = []; cur = ''
            for w in words:
                if d.textlength(cur + ' ' + w, font=f1) > s.W * .68 and cur: lines.append(cur); cur = w
                else: cur = (cur + ' ' + w).strip()
            lines.append(cur); y = s.H * .5 - len(lines) * 30 * s.sh; d.text((s.W * .5, y - 90 * s.sh), '\u201c', font=s.F(150), fill=s.acc + (int(255 * k),), anchor='mm')
            for j, l in enumerate(lines): d.text((s.W * .5, y + j * 58 * s.sh), l, font=f1, fill=(255, 255, 255, int(255 * k)), anchor='mm')
            if b.get('sub'): d.text((s.W * .5, y + len(lines) * 58 * s.sh + 20 * s.sh), '\u2014 ' + b['sub'].upper(), font=f2, fill=s.acc + (int(255 * k),), anchor='mm')
        return fr.convert('RGB')
    def chapter(s, fr, ch, t, T):
        if not ch: return
        k = min(ease(clamp((t - .2) / .5, 0, 1)), ease(clamp((3.2 - t) / .4, 0, 1)))
        if k <= 0: return
        def mk():
            f = s.F(24); txt = ch.upper()[:44]; wd = ImageDraw.Draw(Image.new('RGB', (4, 4))).textlength(txt, font=f) + 44 * s.sh; im = s.panel(wd, 48 * s.sh, s.acc + (235,), 24 * s.sh); ImageDraw.Draw(im).text((22 * s.sh, 11 * s.sh), txt, font=f, fill=(15, 15, 20)); return im
        im = s.patch(('ch', ch), mk); fr.paste(im, (int(34 * s.sh - (1 - k) * 200), int(34 * s.sh)), im)
    def title(s, fr, title, sub, t):
        if t > 3.6: return fr
        k = min(ease(clamp(t / .9, 0, 1)), ease(clamp((3.6 - t) / .7, 0, 1)))
        fr = Image.alpha_composite(fr.convert('RGBA'), Image.new('RGBA', fr.size, (0, 0, 0, int(150 * k)))); d = ImageDraw.Draw(fr); f = s.F(78); words = title.upper().split(); lines = []; cur = ''
        for w in words:
            if d.textlength(cur + ' ' + w, font=f) > s.W * .8 and cur: lines.append(cur); cur = w
            else: cur = (cur + ' ' + w).strip()
        lines.append(cur); y = s.H * .5 - (len(lines) - 1) * 48 * s.sh
        for j, l in enumerate(lines): d.text((s.W / 2, y + j * 96 * s.sh + (1 - k) * 18), l, font=f, fill=(255, 255, 255, int(255 * k)), anchor='mm')
        lw = int(s.W * .22 * ease(clamp(t / 1.2, 0, 1))); yl = y + len(lines) * 96 * s.sh - 30 * s.sh; d.rectangle([s.W / 2 - lw, yl, s.W / 2 + lw, yl + 5 * s.sh], fill=s.acc + (int(255 * k),))
        if sub: d.text((s.W / 2, yl + 44 * s.sh), sub.upper(), font=s.F(28), fill=s.acc + (int(255 * k),), anchor='mm')
        return fr.convert('RGB')
    def caption(s, fr, sc, t):
        ws = sc['kar']; tt = t - .15
        for ci, (c0, c1, words) in enumerate(ws):
            if c0 - .05 <= tt < c1 + .05:
                act = next((i for i, (w, a0, a1) in enumerate(words) if a0 <= tt < a1), len(words) - 1 if tt >= words[-1][2] else 0)
                def mk():
                    f = s.F(34); d0 = ImageDraw.Draw(Image.new('RGB', (4, 4))); txt = [w for w, _, _ in words]; wid = [d0.textlength(w + ' ', font=f) for w in txt]; maxw = s.W * .8; rows = [[]]; cw = 0
                    for i, w in enumerate(txt):
                        if cw + wid[i] > maxw and rows[-1]: rows.append([]); cw = 0
                        rows[-1].append(i); cw += wid[i]
                    rw = [sum(wid[i] for i in r) for r in rows]; lh = int(46 * s.sh); im = s.panel(max(rw) + 44 * s.sh, lh * len(rows) + 22 * s.sh, (8, 10, 16, 165), 14 * s.sh); d = ImageDraw.Draw(im)
                    for ri, r in enumerate(rows):
                        x = (im.width - rw[ri]) / 2
                        for i in r: d.text((x, 11 * s.sh + ri * lh), txt[i], font=f, fill=s.acc if i == act else (250, 250, 250)); x += wid[i]
                    return im
                im = s.patch(('cap', sc['si'], ci, act), mk); fr.paste(im, (int((s.W - im.width) / 2), int(s.H - im.height - 38 * s.sh)), im); return
    def end(s, fr, t, T):
        if T - t > 3.5: return
        k = ease(clamp((3.5 - (T - t)) / .6, 0, 1)); d = ImageDraw.Draw(fr, 'RGBA'); f = s.F(40); w, h = 330 * s.sh, 76 * s.sh; x, y = s.W / 2 - w / 2, s.H * .42
        d.rounded_rectangle([x, y, x + w, y + h], 14 * s.sh, fill=(210, 30, 30, int(255 * k))); d.text((s.W / 2, y + h / 2), 'SUBSCRIBE', font=f, fill=(255, 255, 255, int(255 * k)), anchor='mm'); d.text((s.W / 2, y - 40 * s.sh), 'THANKS FOR WATCHING', font=s.F(34), fill=(255, 255, 255, int(255 * k)), anchor='mm')
    def frame(s, scenes, T, a, title):
        i = next((k for k, sc in enumerate(scenes) if T < sc['t0'] + sc['dur']), len(scenes) - 1); sc = scenes[i]; tr = sc['tr']; t = T - sc['t0']
        if i > 0 and tr > 0 and T < sc['t0'] + tr / 2: p = (T - (sc['t0'] - tr / 2)) / tr; pv = scenes[i - 1]; fr = s.trans(s.base(pv, T - pv['t0']), s.base(sc, max(0, t)), sc['kind'], p)
        elif i > 0 and tr == 0 and False: fr = s.base(sc, t)
        elif i < len(scenes) - 1 and scenes[i + 1]['tr'] > 0 and T > sc['t0'] + sc['dur'] - scenes[i + 1]['tr'] / 2: nx = scenes[i + 1]; p = (T - (nx['t0'] - nx['tr'] / 2)) / nx['tr']; fr = s.trans(s.base(sc, t), s.base(nx, max(0, T - nx['t0'])), nx['kind'], p)
        else: fr = s.base(sc, t)
        x = np.asarray(fr, np.float32) * s.vig; x += s.rng.standard_normal((s.H, s.W, 1)).astype(np.float32) * 1.6; fr = Image.fromarray(np.clip(x, 0, 255).astype(np.uint8))
        if sc['si'] == 0: fr = s.title(fr, title, sc.get('subtitle', ''), t)
        off = 3.6 if sc['si'] == 0 else 0; fr = s.bigbanner(fr, sc['banner'], t - off, sc['dur'] - off); s.lower(fr, sc['banner'], t - off, sc['dur'] - off); s.chapter(fr, sc.get('chapter'), t, sc['dur'])
        if not (sc['si'] == 0 and t < 3.4): s.caption(fr, sc, t)
        if a.endcard and sc['si'] == len(scenes) - 1: s.end(fr, t, sc['dur'])
        return fr
def kar(text, d, speech):
    words = text.split(); chunks = [words[i:i + 8] for i in range(0, len(words), 8)]; tot = sum(len(w) + 2 for w in words); tt = 0; out = []
    for c in chunks:
        ws = []
        for w in c: dt = (len(w) + 2) / tot * speech; ws.append((w, tt, tt + dt)); tt += dt
        out.append((ws[0][1], ws[-1][2], ws))
    return out

# ================================================================ main
def select_video_encoder(requested):
    """Use Intel Quick Sync only when the installed FFmpeg can actually initialize it."""
    if requested == 'libx264':
        return 'libx264'
    try:
        probe = subprocess.run(
            ['ffmpeg', '-hide_banner', '-v', 'error', '-f', 'lavfi', '-i',
             'color=c=black:s=64x64:d=0.1', '-frames:v', '1', '-c:v', 'h264_qsv', '-f', 'null', '-'],
            capture_output=True, text=True, timeout=20
        )
        if probe.returncode == 0:
            print('video encoder: Intel Quick Sync (h264_qsv)', flush=True)
            return 'h264_qsv'
        reason = (probe.stderr or probe.stdout or 'QSV initialization failed').strip().splitlines()[-1]
    except Exception as exc:
        reason = str(exc)
    if requested == 'h264_qsv':
        raise SystemExit('Intel Quick Sync was requested but is unavailable: ' + reason)
    print('video encoder: Intel QSV unavailable -> CPU libx264 fallback (' + reason[:180] + ')', flush=True)
    return 'libx264'

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('script'); ap.add_argument('out', nargs='?', default='modern.mp4'); ap.add_argument('--plan'); ap.add_argument('--prompt-only', action='store_true'); ap.add_argument('--voice', default='en-US-AndrewMultilingualNeural'); ap.add_argument('--rate', default='+0%')
    ap.add_argument('--source', default='auto', choices=['auto', 'photo', 'gen'], help='Compatibility flag; downloaded stills always use free, licence-filtered sources.'); ap.add_argument('--media', default='media'); ap.add_argument('--video-dir', default='media/videos', help='Optional user-supplied moving clips: scene_001.mp4, scene_002.mp4, etc.'); ap.add_argument('--music', default='music'); ap.add_argument('--preview', action='store_true'); ap.add_argument('--silent', action='store_true'); ap.add_argument('--endcard', action='store_true')
    ap.add_argument('--style', default=None); ap.add_argument('--provider', default='auto'); ap.add_argument('--model', default=os.environ.get('LEGO_MODEL')); ap.add_argument('--nomusic', action='store_true'); ap.add_argument('--musicvol', type=float, default=.55); ap.add_argument('--cache', default='cache'); ap.add_argument('--asset-library', default='assets', help='Persistent per-script local image library.'); ap.add_argument('--candidates-per-scene', type=int, default=3, help='Distinct licensed image candidates to collect per scene (1-8).'); ap.add_argument('--offline', action='store_true', help='Never contact image websites; require a complete local asset library.'); ap.add_argument('--prepare-assets-only', action='store_true', help='Download/cache every scene image, create a contact sheet, then stop before rendering.'); ap.add_argument('--save-plan', default='modern_plan.json'); ap.add_argument('--allow-cards', action='store_true', help='Allow designed text cards when no visual provider succeeds.'); ap.add_argument('--encoder', choices=['auto', 'libx264', 'h264_qsv'], default='auto'); ap.add_argument('--resolution', choices=['720p', '1080p'], default='1080p'); a = ap.parse_args()
    script = open(a.script, encoding='utf-8').read()
    if a.prompt_only: open('modern_prompt.txt', 'w', encoding='utf-8').write(SYSTEM + '\n\nSCRIPT:\n' + script); return print('Wrote modern_prompt.txt -> paste into Claude.ai, save the JSON reply as modern_plan.json, run with --plan modern_plan.json')
    if not a.prepare_assets_only and shutil.which('ffmpeg') is None: raise SystemExit('ffmpeg not in PATH (winget install ffmpeg)')
    if a.plan: plan = json.load(open(a.plan, encoding='utf-8'))
    else:
        plan = ask_plan(script, a)
        if not plan: raise SystemExit('No planning provider available. For a no-paid-service workflow, start local Ollama and rerun with --provider ollama, or supply an existing storyboard with --plan modern_plan.json.')
        json.dump(plan, open(a.save_plan, 'w', encoding='utf-8'), indent=1); print('plan saved', a.save_plan, flush=True)
    plan = prepare_plan(plan, script, a.style)
    plan = adapt(plan, a.style); style = plan['style']; W, H, FPS = (640, 360, 12) if a.preview else ((1920, 1080, 24) if a.resolution == '1080p' else (1280, 720, 24)); os.makedirs(a.cache, exist_ok=True); used = set(); scenes = []; credits = []
    library_dir, asset_manifest = open_library(a.asset_library, a.script, script)
    if not 1 <= a.candidates_per_scene <= 8:
        raise SystemExit('--candidates-per-scene must be between 1 and 8')
    selections = load_selection_file(library_dir)
    prepared_assets = {}
    if not a.offline:
        net_check()
    print(f'asset library: {library_dir} | offline={a.offline}', flush=True)
    total_assets = len(plan['scenes'])
    # Preflight every scene before TTS or video rendering. A partial download is saved
    # scene-by-scene so a later run resumes without re-downloading completed scenes.
    for asset_i, asset_scene in enumerate(plan['scenes']):
        if locate_scene_video(asset_i, a.video_dir):
            continue
        scene_record = asset_manifest.get("scenes", {}).get(str(asset_i + 1), {})
        existing_candidates = list(scene_record.get("candidates") or [])
        if selections.get(str(asset_i + 1)):
            try:
                select_scene_candidate(library_dir, asset_manifest, asset_i, selections[str(asset_i + 1)])
            except (ValueError, FileNotFoundError) as exc:
                raise SystemExit(f"Invalid selection for scene {asset_i + 1}: {exc}")
            scene_record = asset_manifest["scenes"][str(asset_i + 1)]
            existing_candidates = list(scene_record.get("candidates") or [])
        saved = valid_scene_asset(library_dir, asset_manifest, asset_i, asset_scene)
        local_only = any(str(x.get("credit_and_source", "")).startswith("local file ") for x in existing_candidates)
        if saved and (len(existing_candidates) >= a.candidates_per_scene or local_only):
            asset_path, record = saved
            try:
                prepared_assets[asset_i] = (Image.open(asset_path).convert('RGB'), record.get('credit_and_source', 'Local project asset'))
                print(f'asset {asset_i + 1}/{total_assets}: reused {len(existing_candidates)} saved candidates ({record.get("selected_candidate", "selected")})', flush=True)
                continue
            except Exception:
                pass
        if a.offline:
            if saved:
                asset_path, record = saved
                prepared_assets[asset_i] = (Image.open(asset_path).convert('RGB'), record.get('credit_and_source', 'Local project asset'))
                print(f'asset {asset_i + 1}/{total_assets}: offline reuse ({len(existing_candidates)} candidates)', flush=True)
                continue
            raise SystemExit(f'Missing scene asset {asset_i + 1}. Offline mode will not download. Prepare candidates first or add a licensed image.')
        try:
            candidates = existing_candidates
            start_number = len(candidates) + 1
            try:
                fresh = fetch_candidates(asset_i, asset_scene, a, style, used, a.candidates_per_scene - len(candidates))
            except RuntimeError:
                if candidates:
                    fresh = []
                else:
                    raise
            for candidate in fresh:
                candidate_number = start_number
                candidate["id"] = f"c{candidate_number:02d}"
                target = candidate_asset_path(library_dir, asset_i, candidate["id"])
                target.parent.mkdir(parents=True, exist_ok=True)
                candidate["image"].save(target, quality=94)
                candidate["file"] = str(target.relative_to(library_dir)).replace("\\\\", "/")
                candidates.append({k: v for k, v in candidate.items() if k != "image"})
                start_number += 1
                register_scene_candidates(library_dir, asset_manifest, asset_i, asset_scene, candidates)
            if not candidates:
                raise RuntimeError("No candidates were saved.")
            selected_id = selections.get(str(asset_i + 1))
            if selected_id:
                asset_path, record = select_scene_candidate(library_dir, asset_manifest, asset_i, selected_id)
            else:
                saved = valid_scene_asset(library_dir, asset_manifest, asset_i, asset_scene)
                if not saved:
                    raise RuntimeError("Saved candidate set has no readable selected image.")
                asset_path, record = saved
            prepared_assets[asset_i] = (Image.open(asset_path).convert('RGB'), record.get('credit_and_source', 'Local project asset'))
            print(f'asset {asset_i + 1}/{total_assets}: {len(candidates)} candidates saved; selected {record.get("selected_candidate", "first")}', flush=True)
        except Exception as exc:
            save_manifest(library_dir, asset_manifest)
            raise SystemExit(f'Asset preparation stopped at scene {asset_i + 1}/{total_assets}: {exc}\\nCompleted candidates are saved in {library_dir}. Run the same command later to resume; existing candidates are retained.')
    # One comparison sheet shows every candidate, its ID, and the current selection.
    thumbs = []
    selection_template = {}
    for asset_i in range(total_assets):
        record = asset_manifest.get("scenes", {}).get(str(asset_i + 1), {})
        candidates = record.get("candidates") or []
        selected_id = str(record.get("selected_candidate") or (candidates[0].get("id") if candidates else ""))
        if selected_id:
            selection_template[str(asset_i + 1)] = selected_id
        for candidate in candidates:
            candidate_path = library_dir / str(candidate.get("file", ""))
            if not candidate_path.is_file():
                continue
            thumb = Image.open(candidate_path).convert("RGB")
            thumb.thumbnail((320, 180))
            tile = Image.new('RGB', (340, 220), (24, 28, 38))
            tile.paste(thumb, ((340-thumb.width)//2, 8))
            label = f'SCENE {asset_i + 1:03d}  {candidate.get("id", "?")}'
            if str(candidate.get("id")) == selected_id:
                label += '  [SELECTED]'
            ImageDraw.Draw(tile).text((12, 192), label, fill=(245,245,245))
            thumbs.append(tile)
    if thumbs:
        cols = 3; rows = (len(thumbs) + cols - 1) // cols
        sheet = Image.new('RGB', (cols * 340, rows * 220), (12, 14, 20))
        for tile_i, tile in enumerate(thumbs):
            sheet.paste(tile, ((tile_i % cols) * 340, (tile_i // cols) * 220))
        sheet.save(library_dir / 'contact_sheet.jpg', quality=88)
    template_path = library_dir / 'asset_selections.example.json'
    template_path.write_text(json.dumps(selection_template, indent=2), encoding='utf-8')
    if a.prepare_assets_only:
        print(f'ASSETS READY/RESUMABLE: {library_dir}\\nReview contact_sheet.jpg. Copy asset_selections.example.json to asset_selections.json and change scene values to candidate IDs (for example c02), then rerun with --offline.')
        return
    rate = {'tense': '-4%', 'sad': '-6%', 'calm': '-2%', 'epic': '+0%', 'up': '+5%'}; tts = None if a.silent else tts_scene(a, rate); t0 = 0.0
    for i, s in enumerate(plan['scenes']):
        print(f'scene {i + 1}/{len(plan["scenes"])}: {s["text"][:60]}', flush=True)
        video_path = locate_scene_video(i, a.video_dir)
        video_frames = None
        if video_path:
            video_frames = extract_scene_video(video_path, a.cache, W, H, FPS)
            im = Image.open(video_frames[0]).convert('RGB')
            cr = 'USER-SUPPLIED MOVING FOOTAGE | ' + os.path.abspath(video_path) + ' | rights: user must confirm ownership or licence'
            print('   -> moving footage:', os.path.basename(video_path), flush=True)
        else:
            im, cr = prepared_assets[i]
            print('   ->', cr.split(' | ')[0], flush=True)
        credits.append(f'{i + 1}. {cr}')
        wav, vd = (tts(s['text'], i, s['mood']) if tts else (None, max(2.8, len(s['text'].split()) / 2.6)))
        d = max(3.0, vd + .5); tr = 0 if i == 0 or s['transition'] == 'cut' else .55 if s['transition'] != 'whip' else .45
        sc = dict(s, si=i, t0=t0, dur=d, img=grade(compose(im), s['mood']), video_frames=video_frames, wav=wav, tr=tr, kind=s['transition'], kar=kar(s['text'], d, vd), subtitle=plan.get('subtitle', 'A DOCUMENTARY' if style != 'news' else 'SPECIAL REPORT'))
        sa = []
        if tr and sc['kind'] in ('whip', 'flash', 'fade', 'dip'): sa.append((t0 - .2, 'whoosh'))
        if s['banner'].get('kind') in ('stat', 'quote'): sa.append((t0 + .6, 'thud'))
        elif s['banner'].get('kind') != 'none': sa.append((t0 + .7, 'ding'))
        sa += [(t0 + .3 + j * .5, x) for j, x in enumerate(s['sfx'][:2])]; sc['sfx_at'] = [(t_, n_) for t_, n_ in sa if t_ >= 0]; scenes.append(sc); t0 += d
    total = t0; print(f'duration {total:.1f}s scenes {len(scenes)}', flush=True); wavp = a.out.rsplit('.', 1)[0] + '_audio.wav'; build_audio(scenes, total, a, wavp)
    R = Ren(W, H, FPS, ACC.get(style, ACC['history']), style); nf = int(total * FPS)
    encoder = select_video_encoder(a.encoder)
    video_args = ['-c:v', encoder, '-pix_fmt', 'yuv420p']
    video_args += (['-preset', 'medium', '-global_quality', '23'] if encoder == 'h264_qsv'
                   else ['-preset', 'medium', '-crf', '19'])
    pr = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-i', wavp, *video_args, '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', a.out], stdin=subprocess.PIPE)
    for k in range(nf):
        pr.stdin.write(R.frame(scenes, k / FPS, a, plan['title']).tobytes())
        if k % (FPS * 10) == 0: print(f'  frame {k}/{nf}', flush=True)
    try:
        pr.stdin.close()
    except BrokenPipeError:
        pass
    return_code = pr.wait()
    if return_code != 0:
        raise SystemExit(f"FFmpeg encoding failed with exit code {return_code}. Check the FFmpeg/Intel driver output above.")
    base = a.out.rsplit('.', 1)[0]
    open(base + '_credits.txt', 'w', encoding='utf-8').write('VISUAL CREDITS (paste in YouTube description)\n' + '\n'.join(credits) + '\n')
    json.dump([{'scene': i + 1, 'credit_and_provenance': item} for i, item in enumerate(credits)], open(base + '_assets.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    ch = [(sc['t0'], sc['chapter']) for sc in scenes if sc.get('chapter')] or [(0, plan['title'])]; mm = lambda x: f'{int(x // 60)}:{int(x % 60):02d}'
    open(base + '_pack.txt', 'w', encoding='utf-8').write(f"TITLE: {plan['title']}\n\nCHAPTERS\n0:00 Intro\n" + '\n'.join(f'{mm(t)} {c}' for t, c in ch if t > 0) + '\n')
    print('DONE', a.out, '| credits:', base + '_credits.txt', '| asset manifest:', base + '_assets.json')
if __name__ == '__main__': main()
