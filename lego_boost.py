#!/usr/bin/env python3
"""
lego_boost.py - add-on for lego_ai.py / lego_director.py / lego_engine_v2.py (NO edits to those files).
Put it in the same folder and run EXACTLY like lego_ai.py:
  python lego_boost.py script.txt out.mp4 --plan plan.json
  python lego_boost.py script.txt --prompt-only            (new prompt -> paste into Claude.ai -> save plan.json)
  python lego_boost.py script.txt out.mp4 --silent         (only if you really want no narration)
What it fixes:
 1. AUDIO: narration TTS is now ON by default (before: only with --tts edge, so videos were silent). Chain: edge-tts -> Windows SAPI -> pyttsx3 -> espeak-ng.
    Windows-safe temp dir (/tmp crashed on Windows). If every engine fails it STOPS with a clear message instead of silently rendering without voice.
 2. VISUALS: 11 new backgrounds (battlefield trench sea sky ruins warroom mountain temple farm cave) and a
    free-text scene resolver: any bg word / bg_desc / scene text is mapped to the best-fitting background, time of day, weather and sfx.
    No more 'everything = city/office/hall'. Same background never repeats 3 scenes in a row.
 3. PLAN QUALITY: unknown actions (sign, sit, salute, smirk...) are mapped to real ones instead of silently ignored; AI prompt upgraded
    (mythology / history / animals / war / any genre rules, new catalog, variety rules).
"""
import os, re, sys, math, json, shutil, tempfile, subprocess
os.makedirs('/tmp', exist_ok=True)  # lego_ai/lego_director hard-code /tmp paths; on Windows this creates <drive>:\tmp
import lego_ai as A
import lego_cinema_fixes as CinemaFix
D = A.D; E = A.E
rnd, sky, clouds, birds, flag_wave, ground = D.rnd, D.sky, D.clouds, D.birds, D.flag_wave, D.ground
sin, cos = math.sin, math.cos

# ============================================================ 1. AUDIO
_state = dict(edge_fail=0)
def _ff(src, wv): subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', src, '-ar', str(E.SR), '-ac', '1', wv], check=True)
def _edge(txt, voice, rate, mp3):
    import asyncio, edge_tts
    asyncio.run(edge_tts.Communicate(txt, voice, rate=rate).save(mp3))
def _sapi(txt, out):
    if os.name != 'nt': return False
    env = dict(os.environ, LEGO_TXT=txt, LEGO_OUT=out)
    ps = "Add-Type -AssemblyName System.Speech;$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;$s.Rate=-1;$s.SetOutputToWaveFile($env:LEGO_OUT);$s.Speak($env:LEGO_TXT);$s.Dispose()"
    return subprocess.run(['powershell', '-NoProfile', '-Command', ps], env=env).returncode == 0 and os.path.exists(out)
def _pyttsx3(txt, out):
    import pyttsx3
    e = pyttsx3.init(); e.setProperty('rate', 165); e.save_to_file(txt, out); e.runAndWait(); return os.path.exists(out)
def _espeak(txt, out):
    ex = shutil.which('espeak-ng') or shutil.which('espeak')
    return bool(ex) and subprocess.run([ex, '-s', '150', '-w', out, txt]).returncode == 0 and os.path.exists(out)
def tts_auto(voice='en-US-GuyNeural', rate='+0%'):
    tmp = tempfile.gettempdir()
    def f(s, i):
        import wave
        txt = re.sub(r'["\u201c\u201d]', '', s); mp3 = os.path.join(tmp, f'_nar{i}.mp3'); raw = os.path.join(tmp, f'_nar{i}_raw.wav'); wv = os.path.join(tmp, f'_nar{i}.wav'); ok = False
        if _state['edge_fail'] < 2:
            for _ in range(3):
                try: _edge(txt, voice, rate, mp3); _ff(mp3, wv); ok = True; break
                except Exception as e: err = e
            if not ok: _state['edge_fail'] += 1; print(f'[audio] edge-tts failed ({type(err).__name__}); trying offline voice. Fix: pip install edge-tts + internet', flush=True)
        if not ok:
            for fn in (_sapi, _pyttsx3, _espeak):
                try:
                    if fn(txt, raw): _ff(raw, wv); ok = True; break
                except Exception: pass
        if not ok: raise SystemExit('NO TTS ENGINE WORKED. Run: pip install edge-tts   (needs internet + ffmpeg in PATH). Or use --silent to render without voice.')
        with wave.open(wv) as q: return wv, q.getnframes() / q.getframerate()
    return f
D.tts_edge = tts_auto

# ============================================================ 2. NEW BACKGROUNDS
def smoke(r, t, n, y0, col, p, big=1.0):
    for i in range(n):
        x = (i * 230 + t * 8 * (1 + rnd(i, 9))) % 1700 - 200; h = (150 + rnd(i, 1) * 150) * big
        for k in range(5): r.ell(x + sin(t * .7 + k + i) * 10, y0 - k * h / 5, 34 + k * 9, 26 + k * 5, tuple(max(20, c - k * 4) for c in col), p)
def flashes(r, t, ys, xs, p=.5):
    for i, x in enumerate(xs):
        ph = (t * .9 + i * .37) % 1.6
        if ph < .5: r.glow(x, ys, 40 + 150 * ph / .5, (255, 190, 80), .8 * (1 - ph / .5), p)
def bg_battlefield(r, t, o):
    sky(r, (70, 62, 70), (214, 140, 86), 470); r.glow(900, 430, 380, (255, 140, 60), .45, .2); smoke(r, t, 7, 440, (62, 58, 62), .25)
    for x in (200, 540, 900):
        c = (46, 50, 46); r.rect(x - 60, 430, x + 60, 452, c, .4); r.rect(x - 30, 414, x + 30, 430, c, .4); r.line([(x + 30, 422), (x + 100, 418)], c, 5, .4); r.ell(x, 452, 66, 9, (30, 32, 30), .4)
    flashes(r, t, 430, (300, 700, 1050)); ground(r, 470, (98, 88, 66), (84, 76, 58), 9)
    for i in range(6): r.ell(120 + i * 215, 520 + (i % 3) * 70, 90, 15, (68, 60, 46))
    for x in (110, 1170):
        r.line([(x - 40, 505), (x + 40, 445)], (50, 50, 55), 6); r.line([(x - 40, 445), (x + 40, 505)], (50, 50, 55), 6); r.line([(x - 55, 475), (x + 55, 475)], (50, 50, 55), 4)
    r.line([(330, 470), (330, 380), (300, 340)], (30, 24, 22), 8, .8); r.line([(330, 420), (368, 392)], (30, 24, 22), 5, .8)
def bg_trench(r, t, o):
    sky(r, (120, 120, 132), (196, 172, 150), 380); smoke(r, t, 5, 360, (110, 106, 108), .2, .8); flashes(r, t, 330, (260, 820), .3)
    r.rect(-900, 330, 2300, 470, (110, 84, 58), .6)
    for j in range(4):
        for i in range(-1, 14): r.ell(i * 100 + (j % 2) * 50, 360 + j * 28, 52, 15, (150 - j * 8, 130 - j * 8, 92 - j * 6), .65)
    for x in range(40, 1300, 190): r.rect(x, 350, x + 14, 470, (92, 66, 44), .8)
    r.line([(-50, 336), (1330, 336)], (50, 50, 55), 3, .8)
    for x in range(-20, 1300, 60): r.line([(x, 326), (x + 30, 346), (x + 60, 326)], (50, 50, 55), 2, .8)
    ground(r, 470, (88, 70, 50), (76, 60, 44), 8)
    for i in range(-1, 14): r.rect(i * 100, 478, i * 100 + 92, 492, (124, 92, 60), .95)
    for x in (300, 980): r.glow(x, 400, 110 + 10 * sin(t * 9 + x), (255, 180, 80), .45, .9); r.ell(x, 404, 8, 12, (255, 200 + int(30 * sin(t * 9)), 80), .9)
def bg_sea(r, t, o):
    sky(r, (110, 170, 230), (232, 242, 252), 400); r.glow(1000, 150, 230, (255, 245, 200), .5, .1); clouds(r, t, .1, 60, 5); birds(r, t, .2, 4, 160)
    r.rect(-900, 390, 2300, 470, (40, 110, 170), .3)
    for x, s in ((260, 1.0), (760, .7)):
        r.poly([(x - 150 * s, 395), (x + 170 * s, 395), (x + 120 * s, 420), (x - 130 * s, 420)], (84, 90, 100), .3); r.rect(x - 60 * s, 365, x + 60 * s, 395, (110, 116, 126), .3); r.rect(x - 14 * s, 335, x + 14 * s, 365, (96, 100, 110), .3); r.line([(x + 60 * s, 380), (x + 140 * s, 376)], (60, 64, 72), 4, .3)
    for i in range(6):
        y = 410 + i * 12; pts = [(x, y + sin(x * .02 + t * 1.5 + i) * 6) for x in range(-100, 1400, 40)]; r.poly(pts + [(1400, 480), (-100, 480)], (30 + i * 6, 100 + i * 8, 160 + i * 5), .45 + i * .05)
    ground(r, 470, (150, 150, 156), (132, 132, 140), 9); r.line([(-50, 500), (1330, 500)], (214, 214, 220), 6, .9)
    for x in range(0, 1300, 160): r.line([(x, 500), (x, 450)], (214, 214, 220), 5, .9)
def bg_sky(r, t, o):
    sky(r, (50, 120, 215), (196, 226, 255), 560); r.glow(1000, 120, 260, (255, 250, 220), .5, .1)
    for p, y, n, c in ((.15, 40, 4, (240, 246, 255)), (.3, 200, 5, (250, 252, 255))): clouds(r, t, p, y, n, c, 10 + p * 40)
    for i in range(3):
        x = (t * (120 + 30 * i) + i * 520) % 1700 - 200; y = 130 + i * 90 + sin(t + i) * 8; c = (60, 70, 60)
        r.line([(x - 260, y + 4), (x - 20, y)], (240, 244, 250), 3, .5); r.ell(x, y, 62, 11, c, .5); r.poly([(x - 10, y), (x - 40, y - 54), (x - 22, y - 54), (x + 22, y)], c, .5); r.poly([(x - 10, y), (x - 40, y + 54), (x - 22, y + 54), (x + 22, y)], c, .5)
        r.poly([(x - 58, y), (x - 84, y - 26), (x - 70, y - 26), (x - 46, y)], c, .5); r.ell(x + 62, y, 4, 24 * abs(sin(t * 40)) + 4, (200, 200, 200), .5)
    clouds(r, t, .9, 500, 6, (248, 250, 255), 14); ground(r, 520, (244, 248, 255), (226, 236, 250), 6)
def bg_ruins(r, t, o):
    sky(r, (90, 90, 100), (210, 170, 140), 470); smoke(r, t, 6, 440, (70, 68, 72), .22, 1.1)
    for i in range(8):
        x = i * 180 - 80; h = 120 + rnd(i, 2) * 200; r.poly([(x, 470), (x, 470 - h), (x + 30, 470 - h + 25), (x + 55, 470 - h - 10), (x + 90, 470 - h + 35), (x + 105, 470 - h + 10), (x + 125, 470)], (86, 80, 84), .45)
        for j in range(int(h // 60)): r.rect(x + 20, 440 - j * 55 - 20, x + 44, 440 - j * 55 + 10, (40, 38, 44), .45)
    for x in (260, 940): r.glow(x, 440, 120 + 15 * sin(t * 7 + x), (255, 150, 60), .55, .5)
    ground(r, 470, (104, 98, 96), (90, 84, 84), 9)
    for i in range(14): x = (i * 97) % 1280; y = 480 + (i * 53) % 190; r.poly([(x, y), (x + 30, y - 18 - rnd(i, 4) * 14), (x + 58, y)], (80 + i % 3 * 10, 74, 74))
def bg_warroom(r, t, o):
    r.rect(-900, 0, 2300, 470, (48, 54, 60), .5); r.rect(300, 60, 980, 300, (196, 178, 130), .5)
    for x in range(300, 981, 68): r.line([(x, 60), (x, 300)], (170, 152, 108), 1, .5)
    for y in range(60, 301, 48): r.line([(300, y), (980, y)], (170, 152, 108), 1, .5)
    r.poly([(360, 240), (420, 140), (520, 120), (560, 190), (500, 260), (420, 280)], (110, 140, 90), .5); r.poly([(640, 270), (720, 160), (860, 130), (930, 220), (840, 280)], (110, 140, 90), .5)
    k = (t * 40) % 160; r.line([(430, 210), (560 + k * .3, 190 - k * .2)], (200, 40, 40), 5, .5); r.ell(560 + k * .3, 190 - k * .2, 9, 9, (220, 50, 50), .5)
    for x, y in ((470, 160), (700, 200), (880, 170)): r.ell(x, y, 7, 7, (40, 90, 200), .5)
    r.line([(640, 0), (640, 40)], (30, 30, 30), 3, .6); r.poly([(600, 70), (680, 70), (660, 40), (620, 40)], (40, 90, 60), .6); r.glow(640, 80, 330, (255, 220, 150), .5, .6)
    ground(r, 470, (70, 52, 40), (60, 44, 34), 8); r.rect(240, 420, 1040, 445, (120, 84, 52), .9); r.rect(280, 410, 1000, 421, (196, 178, 130), .9)
    for x in (270, 1010): r.rect(x, 445, x + 14, 520, (90, 62, 40), .9)
    for x in (450, 640, 820): r.rect(x, 398, x + 14, 410, (60, 70, 160), .9)
def bg_mountain(r, t, o):
    sky(r, (250, 170, 120), (120, 150, 215), 470); r.glow(300, 300, 320, (255, 220, 150), .5, .1); birds(r, t, .2, 3, 120)
    for p, base, h, c in ((.15, 440, 300, (150, 140, 170)), (.3, 460, 260, (120, 116, 150)), (.55, 480, 200, (90, 96, 120))):
        for i in range(-2, 7):
            x = i * 380 + 60 + rnd(i, int(p * 10)) * 60; r.poly([(x - 240, base), (x, base - h), (x + 240, base)], c, p); r.poly([(x - 60, base - h + 85), (x, base - h), (x + 60, base - h + 85), (x, base - h + 60)], (245, 245, 252), p)
    ground(r, 470, (96, 140, 80), (84, 126, 70), 8)
    for i in range(-2, 10): x = i * 170 + rnd(i, 2) * 60; y = 480 + rnd(i, 3) * 40; r.poly([(x - 26, y), (x, y - 100), (x + 26, y)], (36, 100, 70), .9)
def bg_temple(r, t, o):
    sky(r, (60, 40, 110), (250, 170, 110), 470); r.glow(640, 300, 430, (255, 210, 120), .5, .2)
    r.rect(300, 400, 980, 470, (196, 160, 110), .55); r.rect(340, 360, 940, 400, (210, 172, 120), .55)
    for k in range(7): r.poly([(520 + k * 4, 360 - k * 40), (760 - k * 4, 360 - k * 40), (750 - k * 4, 320 - k * 40), (530 + k * 4, 320 - k * 40)], (214 - k * 6, 170 - k * 6, 110), .55)
    r.poly([(600, 80), (680, 80), (640, 20)], (240, 200, 80), .55); flag_wave(r, 640, 20, 70, 36, [(255, 140, 30), (255, 200, 60)], t, .5)
    for x in range(380, 900, 90): r.rect(x, 400, x + 30, 470, (230, 200, 150), .7)
    ground(r, 470, (196, 176, 140), (176, 156, 124), 9)
    for i in range(10):
        x = 90 + i * 122; r.ell(x, 466, 12, 7, (150, 80, 40), .95); r.ell(x, 452 + sin(t * 9 + i) * 2, 5, 10, (255, 190 + int(40 * sin(t * 7 + i)), 60), .95); r.glow(x, 450, 55, (255, 180, 70), .4, .95)
def bg_farm(r, t, o):
    sky(r, (130, 190, 240), (235, 245, 255), 400); r.glow(1100, 110, 220, (255, 245, 200), .5, .1); clouds(r, t, .12, 60, 5); birds(r, t, .2, 3, 150)
    for i in range(-1, 6): r.poly([(i * 340 - 200, 420), (i * 340, 340), (i * 340 + 220, 420)], (110, 170, 100), .2)
    r.rect(180, 300, 340, 430, (170, 50, 45), .5); r.poly([(160, 300), (260, 240), (360, 300)], (120, 36, 36), .5); r.line([(180, 300), (340, 430)], (245, 240, 235), 4, .5); r.line([(340, 300), (180, 430)], (245, 240, 235), 4, .5)
    r.rect(860, 250, 880, 430, (120, 100, 80), .5)
    for b in range(4): a = t * 1.2 + b * math.pi / 2; r.line([(870, 250), (870 + 80 * cos(a), 250 + 80 * sin(a))], (235, 230, 220), 7, .5)
    for j in range(4): r.rect(-900, 400 + j * 18, 2300, 416 + j * 18, (150 - j * 10, 180 - j * 8, 80), .6)
    ground(r, 470, (120, 170, 90), (104, 152, 78), 8)
    for x in range(-20, 1300, 120): r.rect(x, 470, x + 8, 520, (130, 96, 64), .9)
    r.line([(-20, 485), (1300, 485)], (130, 96, 64), 5, .9); r.line([(-20, 505), (1300, 505)], (130, 96, 64), 5, .9)
def bg_cave(r, t, o):
    r.rect(-900, 0, 2300, 470, (26, 22, 30), .3)
    for i in range(-1, 14): x = i * 110 + rnd(i, 1) * 50; h = 80 + rnd(i, 2) * 160; r.poly([(x - 36, 0), (x + 36, 0), (x, h)], (60, 52, 62), .5)
    for x in (140, 1140): r.glow(x, 300, 260 + 20 * sin(t * 8 + x), (255, 160, 70), .5, .6); r.rect(x - 4, 300, x + 4, 400, (90, 60, 40), .8); r.ell(x, 292, 10, 16, (255, 190 + int(40 * sin(t * 10)), 70), .8)
    ground(r, 470, (70, 62, 66), (58, 50, 56), 8)
    for i in range(-1, 12): x = i * 130 + rnd(i, 3) * 60; h = 50 + rnd(i, 4) * 90; r.poly([(x - 30, 470), (x, 470 - h), (x + 30, 470)], (80, 72, 78), .85)
    for i in range(7): x = 180 + i * 150; r.poly([(x, 440), (x + 10, 415 + 4 * sin(t * 3 + i)), (x + 20, 440), (x + 10, 460)], [(120, 200, 255), (180, 140, 255), (120, 255, 200)][i % 3], .9)
NEW = dict(battlefield=bg_battlefield, trench=bg_trench, sea=bg_sea, sky=bg_sky, ruins=bg_ruins, warroom=bg_warroom, mountain=bg_mountain, temple=bg_temple, farm=bg_farm, cave=bg_cave)
E.BGS.update(NEW)
D.AUDIO_ALIAS.update(battlefield='tunnel', trench='tunnel', sea='village', sky='tunnel', ruins='tunnel', warroom='locker', mountain='village', temple='hall', farm='village', cave='tunnel')

# ============================================================ 3. FREE-TEXT RESOLVER
KW = dict(
    battlefield='battle tank panzer invasion invad attack offensive troops army armies assault blitz shell artillery warrior soldier front frontline conquer conquest',
    trench='trench bunker siege defend fortif entrench',
    sea='ship navy naval fleet harbor harbour pearl ocean battleship carrier convoy atlantic pacific sail pirate voyage cruiser',
    sky='plane aircraft airplane bomber airborne paratroop raf luftwaffe flight fly flew dogfight parachute heaven sky aerial',
    ruins='ruin rubble destroy devastat wreck aftermath ash burned bombed collapse',
    warroom='strategy strateg briefing headquarters intelligence codebreak spy command cabinet planning deception secret treaty pact decoded',
    mountain='mountain himalaya peak alps valley cliff hill summit',
    temple='temple god goddess mytholog myth divine shiva vishnu krishna rama ravana zeus olympus ritual prayer mantra sacred deity mahabharata ramayana hanuman',
    farm='farm harvest crop barn cattle wheat plough plow villager',
    cave='cave cavern underground dungeon tomb mine tunnel hidden chamber',
    forest='forest jungle woods wildlife tiger lion deer animal safari bear wolf', desert='desert sand pyramid egypt pharaoh oasis camel', snow='snow winter frozen siberia blizzard ice',
    space='space rocket moon planet galaxy astronaut universe', castle='castle king queen palace throne kingdom knight emperor', beach='beach shore island coast', underwater='underwater coral submarine',
    market='market bazaar trade merchant')
GENERIC = {'city': 1, 'village': 1, 'studio': 1, 'metro': 1, 'office': 2, 'hall': 2, 'home': 2, 'locker': 2}
TOD = ['day', 'sunset', 'dusk']
ACT = dict(sign='think', sit='idle', stand='idle', salute='bow', clap='cheer', cry='sad', laugh='celebrate', fight='angry', march='walk', fly='run', pray='namaste', write='think', hug='celebrate', fire='point', shoot='point', command='point', speak='talk', listen='idle', plan='think', escape='run', hide='crouch', surrender='sad')
SFXK = dict(bomb='explosion', explo='explosion', tank='engine', plane='engine', engine='engine', storm='wind', wind='wind', march='step', crowd='cheer_s', laugh='laugh_s', bell='ding', thunder='thud', sword='sting', shock='sting', secret='drumroll', whisper='drumroll', cheer='cheer_s')
def toks(s): return re.findall(r"[a-z']+", str(s).lower())
def score(field, text):
    out = {}
    for b, ws in KW.items():
        st = ws.split(); n = 0
        for w in field: n += 3 * any(w.startswith(k) for k in st)
        for w in text: n += any(w.startswith(k) for k in st if len(k) >= 3)
        if n: out[b] = n
    return out
def upgrade(plan):
    prev = []; tc = 0
    for s in plan['scenes']:
        txt = s.get('text', ''); tt = toks(txt); raw = str(s.get('bg', '') or '').lower().strip(); ft = toks(raw.replace('_', ' ') + ' ' + str(s.get('bg_desc', '')))
        sc = score(ft, tt); bg = raw.replace(' ', '_')
        if bg not in E.BGS: bg = ''
        if bg == '' or (bg in GENERIC and sc and max(sc.values()) >= GENERIC[bg]): bg = max(sc, key=sc.get) if sc else (bg or 'city')
        if len(prev) >= 2 and prev[-1] == prev[-2] == bg:
            alt = [b for b in sorted(sc, key=sc.get, reverse=True) if b != bg]
            if alt: bg = alt[0]
            else: s['time'] = TOD[(tc := tc + 1) % 3]
        if bg in ('city', 'metro'):
            ct = next((D.CITYL[w] for w in tt + ft if w in D.CITYL), None)
            if ct: bg = 'metro'; s['city'] = ct
        s['bg'] = bg; prev.append(bg)
        if s.get('time') in (None, '', 'day', 'none'):
            x = next((D.TODL[w] for w in tt if w in D.TODL and D.TODL[w] != 'clear'), None)
            if x: s['time'] = x
        if s.get('weather') in (None, '', 'none'):
            x = next((D.WXL[w] for w in tt if w in D.WXL and D.WXL[w] != 'clear'), None)
            if x: s['weather'] = x
        for a in s.get('actors') or []:
            ac = str(a.get('action', 'auto')).lower()
            if ac in E.EXPR: a['face'] = [ac] + [f for f in (a.get('face') or []) if f != ac]; ac = 'talk' if a.get('speaks') else 'idle'
            ac = ACT.get(ac, ac); a['action'] = ac if ac in A.ACTIONS else 'auto'
            a['face'] = [f for f in (a.get('face') or []) if f in E.EXPR]
        if not s.get('sfx'):
            q = [v for k, v in SFXK.items() if any(w.startswith(k) for w in tt) and v in E.SFX][:2]
            if q: s['sfx'] = q
    return plan
_bs = A.build_scenes
A.build_scenes = lambda plan, tts=None: _bs(upgrade(plan), tts)

# ============================================================ 4. UPGRADED AI PROMPT
EXTRA = """9. WORLD-CLASS DIRECTING. The script can be ANY genre: mythology, history, war, animals, science, sports, news, stories. Choose "bg" from the REAL PLACE of each scene. NEVER default to city/office/hall.
   mythology/gods -> temple, castle, mountain, forest, sky, cave; war -> battlefield, trench, sea, sky, ruins, warroom; animals -> forest, farm, beach, underwater, desert, snow; ancient history -> desert, castle, temple, market, sea.
   Also add optional "bg_desc": 3-8 free words describing the exact setting (e.g. "burning Polish village at dawn"); the renderer uses it to pick the closest background.
10. VARIETY: in any 40 scenes use at least 8 different backgrounds, never the same bg 3 scenes in a row, vary time (sunrise/day/sunset/night) and weather, change camera every scene.
11. EVERY scene needs 1-2 sfx that match the action (explosion, engine, step, wind, cheer, thud, ding, sting, drumroll...), props that are concrete objects/animals/vehicles of the era, and 'face' lists that show an emotional arc.
12. Give historical/mythical figures a distinctive 'look' (hair, acc, skin, outfit colors) and keep it identical in every scene.
13. STRICT CASTING: Never invent or insert any named real person, celebrity, politician, athlete, or fictional character who is not explicitly named in the supplied script. In particular, NEVER add modern public figures to historical stories. If the script does not name a person, use historically appropriate ROLE GROUPS such as "German soldier", "British soldier", "Allied soldier", "civilian", "pilot" or "commander"; do not invent a famous identity.
14. HISTORICAL ACCURACY: Match uniforms, vehicles, weapons, flags, architecture and locations to the stated period and country. Do not use modern suits, sports kits, modern cars, football stadiums or contemporary personalities in historical war scenes.
15. ACTION CONTINUITY: Every actor must have a purposeful action tied to the exact scene text. Use "idle" for listening, watching, waiting or standing. Use "walk"/"run" only when the text says movement occurs. Use "talk" for speech, "point" for giving orders or indicating a target, "bow" for saluting, "crouch" for taking cover, and "fall" only when someone falls. Do not make every character walk or run. Keep actors in place when they are not travelling.
16. SCENE CAST: Include only people/groups physically present in that shot. A narrator, leader or named historical person must not appear as an on-screen actor merely because they are mentioned in narration. Use props, maps, vehicles, environments or a separate cutaway when a person is only being discussed.
CATALOG:
"""
A.SYSTEM = A.SYSTEM.split('CATALOG:')[0] + EXTRA + A.catalog()

# ============================================================ MAIN
def main():
    av = sys.argv
    # Capture the original user script so hallucinated named characters can be rejected.
    if len(av) > 1 and not av[1].startswith('-'):
        try:
            with open(av[1], encoding='utf-8-sig') as source_file:
                CinemaFix.set_source_script(source_file.read())
        except OSError as exc:
            raise SystemExit(f"Cannot read input script {av[1]}: {exc}")
    CinemaFix.install()
    if '--silent' in av: av.remove('--silent')
    elif not any(x in av for x in ('--prompt-only', '--tts', '--voice')): av += ['--tts', 'edge']
    if shutil.which('ffmpeg') is None: raise SystemExit('ffmpeg not found in PATH. Install: winget install ffmpeg  (then reopen the terminal)')
    A.main()
if __name__ == '__main__': main()
