#!/usr/bin/env python3
"""
LEGO AI DIRECTOR - an LLM (Claude) reads your script like a human director and plans every scene; the engine renders it.
  python lego_ai.py script.txt out.mp4                 # auto-uses any key set: GEMINI_API_KEY (FREE tier), GROQ_API_KEY, OPENROUTER_API_KEY, ANTHROPIC_API_KEY, or --provider ollama (free, local)
  python lego_ai.py script.txt --prompt-only           # no key: writes ai_prompt.txt -> paste into Claude.ai/ChatGPT, save reply as plan.json
  python lego_ai.py script.txt out.mp4 --plan plan.json
  flags: --fast  --tts edge  --voice-name en-US-GuyNeural  --voice narr.wav  --model claude-sonnet-5-5
Files needed in same folder: lego_engine_v2.py, lego_director.py
"""
import os, re, sys, json, argparse, urllib.request, urllib.error
import lego_director as D
E = D.E
clamp = E.clamp
ACTIONS = ['auto', 'run', 'walk', 'idle', 'kick', 'header', 'jump', 'celebrate', 'cheer', 'sad', 'shock', 'angry', 'talk', 'point', 'fall', 'getup', 'dive', 'shrug', 'bow', 'wave', 'namaste', 'dance', 'crouch', 'think']
CAMS = ['follow', 'zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'static', 'shake']
TRS = ['cut', 'fade', 'whip', 'flash']
FXS = ['confetti', 'flash', 'shake', 'speed', 'burst:TEXT', 'title:TEXT', 'sparkle']
LOOKS = "outfit: kit|suit|casual|dress|robe; hair: short|spiky|long|curly|bun|bald|cap|turban|crown; acc: [beard,glasses,tie,headband,gloves,scarf]; skin: light|tan|brown|dark|yellow; shirt/shorts/hat: [r,g,b] or color word; size 0.8-1.1; num (kit shirt number)"

def catalog():
    return (f"backgrounds: {', '.join(E.BGS)}; for bg 'metro' also give city: {', '.join(D.CITIES)}\ntime: sunrise|day|sunset|dusk|night; weather: rain|storm|snow|fog|wind|dust|none\n"
            f"emotion (per scene): {', '.join(D.EM)}; moods: {', '.join(D.MOODS)}\nexpressions (face list, morphs inside the shot): {', '.join(E.EXPR)}\nactions: {', '.join(ACTIONS)}\n"
            f"roles with ready looks: {', '.join(D.ROLES)}\ncharacter look fields -> {LOOKS}\nprops: ANY concrete object or animal word - the renderer draws anything (pool has {len(D.POOL_PROPS)} + unlimited procedural); give optional color and where: left|center|right|fly|move\n"
            f"sfx: {', '.join(sorted(E.SFX))}\nfx: {', '.join(FXS)}; camera: {', '.join(CAMS)}; transition: {', '.join(TRS)}; music: up|tense|sad|epic|off")
SYSTEM = """You are the director of an animated LEGO-style video. Read the script like a human film director and return ONLY valid JSON (no prose, no code fences).
Schema: {"title":str,"genre":"story|sports|news|doc","characters":[{"name":str,"role":str|null,"look":{...}}],
"scenes":[{"text":str,"bg":str,"city":str|null,"time":str,"weather":str,"emotion":str,"mood":str,
"actors":[{"name":str,"action":str,"face":[expr,...],"speaks":bool,"pos":"left|center|right"}],
"props":[{"name":str,"color":str|null,"where":str}],"camera":str,"transition":str,"music":str,"sfx":[str|{"t":sec,"name":str}],"fx":[str],"tag":str|null,"hud":null|{"a":str,"b":str,"sa":int,"sb":int,"clock":str}}]}
Rules:
1. SCENES BY MEANING, not punctuation: start a new scene whenever place, time, weather, mood, participants or the main action changes, or a new beat of the story begins. Each scene 8-26 words (4-10 s).
2. "text" fields must be the script's own words, in order, covering the WHOLE script with nothing added or dropped (they are shown as narration captions).
3. Infer what is implied, not just literal words: atmosphere, era, culture, location, time of day, weather, characters' ages/genders/jobs, feelings ("the silence felt heavy" => suspense mood). Pick looks that fit the person (e.g. an elderly Indian farmer, a young queen).
4. Characters: define each recurring person once with a consistent look; scenes reference them by name. Use only those present in that scene (max 3 actors per scene).
5. Actions must physically show the sentence (run, kick, wave, cry...). "face" is a list of 1-3 expressions showing the emotional arc INSIDE the scene.
6. props: up to 3 concrete visible things per scene, any word allowed. Do not use abstract nouns.
7. Vary camera and transitions; use fx sparingly for big moments (confetti on victory, shake on shocks, title:TEXT for big words). Use sports hud only for real matches.
8. Use only values from the catalog below for enumerated fields.
CATALOG:
""" + catalog()

def call_llm(system, user, model, key):
    body = json.dumps(dict(model=model, max_tokens=12000, system=system, messages=[dict(role='user', content=user)])).encode()
    rq = urllib.request.Request('https://api.anthropic.com/v1/messages', body, {'x-api-key': key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
    try: r = json.load(urllib.request.urlopen(rq, timeout=300))
    except urllib.error.HTTPError as e: raise SystemExit(f'API error {e.code}: {e.read().decode()[:300]}')
    return ''.join(b.get('text', '') for b in r['content'])
def _post(url, body, headers):
    rq = urllib.request.Request(url, json.dumps(body).encode(), dict({'content-type': 'application/json'}, **headers))
    try: return json.load(urllib.request.urlopen(rq, timeout=300))
    except urllib.error.HTTPError as e: raise SystemExit(f'API error {e.code}: {e.read().decode()[:400]}')
def pick_gemini_model(key):
    try:
        r = json.load(urllib.request.urlopen(f'https://generativelanguage.googleapis.com/v1beta/models?key={key}&pageSize=200', timeout=60))
        c = [m['name'].split('/')[-1] for m in r.get('models', []) if 'generateContent' in m.get('supportedGenerationMethods', []) and 'flash' in m['name'] and not re.search(r'lite|image|tts|live|audio|thinking|exp|preview-\d|embed|8b', m['name'])]
        ver = lambda n: [float(x) for x in re.findall(r'\d+(?:\.\d+)?', n)] or [0]
        if c: return max(c, key=ver)
    except Exception: pass
    return 'gemini-2.5-flash'
def call_gemini(system, user, model, key):
    r = _post(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}', dict(systemInstruction=dict(parts=[dict(text=system)]), contents=[dict(role='user', parts=[dict(text=user)])],
              generationConfig=dict(responseMimeType='application/json', temperature=.4, maxOutputTokens=16000)), {})
    try: return ''.join(p.get('text', '') for p in r['candidates'][0]['content']['parts'])
    except (KeyError, IndexError): raise ValueError('empty Gemini reply: ' + json.dumps(r)[:200])
PROV = dict(groq=('https://api.groq.com/openai/v1/chat/completions', 'llama-3.3-70b-versatile', 'GROQ_API_KEY'), openrouter=('https://openrouter.ai/api/v1/chat/completions', 'meta-llama/llama-3.3-70b-instruct:free', 'OPENROUTER_API_KEY'),
            ollama=('http://localhost:11434/v1/chat/completions', 'qwen2.5:14b', None))
def call_openai(base):
    def f(system, user, model, key):
        r = _post(base, dict(model=model, temperature=.4, messages=[dict(role='system', content=system), dict(role='user', content=user)]), {'Authorization': f'Bearer {key}'} if key else {})
        try: return r['choices'][0]['message']['content']
        except (KeyError, IndexError): raise ValueError('empty reply: ' + json.dumps(r)[:200])
    return f
def choose(provider, model):
    env = os.environ; order = [('anthropic', 'ANTHROPIC_API_KEY'), ('gemini', 'GEMINI_API_KEY'), ('gemini', 'GOOGLE_API_KEY'), ('groq', 'GROQ_API_KEY'), ('openrouter', 'OPENROUTER_API_KEY')]
    if provider == 'auto':
        hit = next(((p, k) for p, k in order if env.get(k)), None)
        if not hit: return None
        provider = hit[0]
    if provider == 'anthropic': return call_llm, model or 'claude-sonnet-5-5', env.get('ANTHROPIC_API_KEY')
    if provider == 'gemini':
        key = env.get('GEMINI_API_KEY') or env.get('GOOGLE_API_KEY'); return call_gemini, model or pick_gemini_model(key), key
    base, dm, ev = PROV[provider]; return call_openai(base), model or dm, (env.get(ev) if ev else None)
def parse_json(t):
    t = re.sub(r'^```(?:json)?|```$', '', t.strip(), flags=re.M).strip(); i, j = t.find('{'), t.rfind('}')
    return json.loads(t[i:j + 1])
def chunks(text, n=450):
    paras = [p for p in re.split(r'\n\s*\n', text.strip()) if p.strip()]; out = []; cur = []; c = 0
    for p in paras:
        w = len(p.split())
        if cur and c + w > n: out.append('\n\n'.join(cur)); cur = []; c = 0
        cur.append(p); c += w
    if cur: out.append('\n\n'.join(cur))
    res = []
    for o in out:  # split any oversize paragraph by words
        ws = o.split()
        res += [' '.join(ws[i:i + n * 2]) for i in range(0, len(ws), n * 2)] if len(ws) > n * 2 else [o]
    return res
def ask(script, model, key, llm=call_llm):
    plan = None; known = []
    for k, part in enumerate(chunks(script)):
        user = (f"Characters already defined (reuse these exact names/looks): {json.dumps(known)}\n\n" if known else '') + 'SCRIPT PART ' + str(k + 1) + ':\n' + part
        for attempt in range(2):
            try:
                p = parse_json(llm(SYSTEM, user if attempt == 0 else user + '\n\nReturn ONLY valid JSON.', model, key))
                if not p.get('scenes'): raise ValueError('no scenes')
                break
            except (ValueError, KeyError) as e:
                if attempt: raise SystemExit(f'Could not parse AI reply: {e}')
        if plan is None: plan = p
        else:
            names = {c['name'] for c in plan['characters']}; plan['characters'] += [c for c in p.get('characters', []) if c['name'] not in names]; plan['scenes'] += p['scenes']
        known = plan['characters']
    return plan

# ---------------------------------------------------------------- plan -> scenes
def col(v, default=None):
    if v is None: return default
    if isinstance(v, (list, tuple)) and len(v) == 3: return tuple(int(x) for x in v)
    if isinstance(v, str):
        if v.lower() in D.COLW: return D.COLW[v.lower()]
        if re.fullmatch(r'#?[0-9a-fA-F]{6}', v): v = v.lstrip('#'); return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    return default
def register(c):
    name = c['name']; role = (c.get('role') or '').lower() or None; lk = c.get('look') or {}; D.make_char(name, role if role in D.ROLES else None); ch = E.CAST[name]
    for k in ('shirt', 'shorts', 'hat', 'trim', 'socks'):
        v = col(lk.get(k)); 
        if v: ch[k] = v
    if lk.get('skin'): ch['skin'] = E.SKIN.get(lk['skin']) or col(lk['skin'], ch['skin'])
    if lk.get('hair') in ('short', 'spiky', 'long', 'curly', 'bun', 'bald', 'cap', 'turban', 'crown'): ch['hair'] = lk['hair']
    if lk.get('hair_color'): ch['hc'] = col(lk['hair_color'], ch['hc'])
    if lk.get('outfit') in ('kit', 'suit', 'casual', 'dress', 'robe'): ch['outfit'] = lk['outfit']
    if isinstance(lk.get('acc'), list): ch['acc'] = [a for a in lk['acc'] if a in ('beard', 'glasses', 'tie', 'headband', 'gloves', 'scarf')]
    if lk.get('size'): ch['size'] = clamp(float(lk['size']), .7, 1.15)
    if 'num' in lk: ch['num'] = lk['num']
    if ch['outfit'] == 'kit' and ch.get('num') is None: ch['num'] = D.hsh(name) % 98 + 1
def prop_kind(name):
    toks = re.findall(r"[a-z']+", name.lower())
    for t in reversed(toks):
        for s in D.stems(t):
            if s in D.PROPL: return D.PROPL[s]
    r = D.find_objs(toks)
    if r: return r[0][0]
    w = D.sing(toks[-1]) if toks else 'thing'; return 'gen:' + w
SFXMAP = dict(thunder='thud', door='thud', knock='thud', crash='sting', explosion='sting', bell='ding', clap='applause', cheer='cheer_s', crowd='cheer_s', cry='sigh', laugh='laugh_s', scream='gasp_s', roar='roar', birds='chirp', whistle='whistle', horn='horn')
def kar(words, d, em):
    ch = [words[i:i + 8] for i in range(0, len(words), 8)]; tot = sum(len(w) + 2 for w in words); tt = .2; out = []
    for c in ch:
        ws = []
        for w in c: dt = (len(w) + 2) / tot * (d - .45); ws.append((w, tt, tt + dt)); tt += dt
        out.append([ws[0][1] - .05, ws[-1][2] + .08, ws, em])
    for k in range(len(out) - 1): out[k][1] = out[k + 1][0]
    out[-1][1] = d - .05; return [tuple(o) for o in out]
def build_scenes(plan, tts=None):
    title = plan.get('title') or ' '.join(plan['scenes'][0]['text'].split()[:6]); genre = plan.get('genre', 'story')
    for c in plan.get('characters', []): register(c)
    D.make_char('Anchor', 'anchor'); out = []; seenbg = None; INT = ('stadium', 'locker', 'tunnel', 'hall', 'studio', 'office', 'home'); NAT = ('city', 'metro', 'village'); n = len(plan['scenes'])
    for si, s in enumerate(plan['scenes']):
        text = s['text'].strip(); words = text.split(); d = clamp(len(words) / 2.5 + .6, 2.6, 7.0); voice = None
        if tts: voice, vd = tts(text, si); d = max(2.6, vd + .45)
        bg = s.get('bg', 'village'); bg = bg if bg in E.BGS else 'village'; tod = s.get('time'); tod = None if tod in (None, 'day', 'none', 'clear') else tod
        wx = s.get('weather'); wx = wx if wx in ('rain', 'storm', 'snow', 'fog', 'wind', 'dust') else None
        bo = {}
        if bg in NAT: bo['time'] = {'night': 'night', 'sunset': 'dusk', 'dusk': 'dusk', 'sunrise': 'dusk'}.get(tod, 'day')
        if bg == 'stadium' and tod == 'night': bo['night'] = True
        if bg == 'metro': bo['city'] = s.get('city') if s.get('city') in D.CITIES else 'paris'
        if bg == 'village' and s.get('temple'): bo['temple'] = True
        tint = None if (bg in INT) or (bg in NAT and tod in ('night', 'sunset', 'dusk')) else tod
        if bg in NAT and tod == 'sunrise': tint = 'sunrise'
        emo = s.get('emotion') if s.get('emotion') in D.EM else 'neutral'; f0, f1, act0, sfx0, em, mus0 = D.EM[emo]
        mk = s.get('mood') if s.get('mood') in D.MOODS else D.EMOOD[emo]; music = s.get('music') if s.get('music') in ('up', 'tense', 'sad', 'epic', 'off') else (mus0 or D.MOODS[mk][6] or {'sports': 'up', 'news': 'up'}.get(genre, 'sad'))
        A = [a for a in (s.get('actors') or []) if a.get('name')][:3]
        for a in A:
            if a['name'] not in E.CAST: register(dict(name=a['name'], role=None))
        k = len(A); xs = {1: [640], 2: [470, 810], 3: [380, 640, 900]}.get(k, []); P = {'left': 380, 'center': 640, 'right': 900}; actors = []; ps = []
        for i, a in enumerate(A):
            x = P.get(a.get('pos'), xs[i]); sd = 1 if x <= 640 else -1; y = 560 + (i % 2) * 26; act = a.get('action') if a.get('action') in ACTIONS else 'auto'
            if act == 'auto': act = act0 if (i == 0 and act0 not in ('run', 'walk') and False) else 'auto'
            if act == 'run': path = [(0, 150 if sd > 0 else 1130, y), (d, 1130 if sd > 0 else 150, y)]
            elif act == 'walk': path = [(0, x - sd * 260, y), (d * .7, x, y), (d, x + sd * 26, y)]
            else: path = [(0, x - sd * 150, y), (d * .4, x, y), (d, x + sd * 30, y)]
            fl = [f for f in (a.get('face') or []) if f in E.EXPR] or [f0, f1]; fc = [(d * j / len(fl) * (0.9 if j else 0), f) for j, f in enumerate(fl)]
            acts = [] if act in ('auto', 'run', 'walk', 'idle') else [(d * .35, act)] if act in E.ONE else [(.5, act)]
            sp = a.get('speaks') or act == 'talk'
            actors.append(E.actor(a['name'], path, act=acts, face=fc, say=[(.3, d - .3)] if sp else [], fdir=[(d * .4, sd)])); ps.append(x)
        pr = []; used = set()
        for pj in (s.get('props') or [])[:3]:
            nm = pj if isinstance(pj, str) else pj.get('name', ''); c_ = None if isinstance(pj, str) else col(pj.get('color'), None); wh = None if isinstance(pj, str) else pj.get('where')
            if not nm: continue
            kind = prop_kind(nm)
            if kind in used: continue
            used.add(kind); cc = c_ or D.PAL[D.hsh(nm + text) % 10]; fh, mv, sz = D.ginfo(kind); j = len(pr)
            if wh == 'fly' and not fh: fh = 120
            if wh == 'move': mv = True
            if fh: pr.append(E.prop(kind, path=[(0, 100, 540, fh), (d, 1180, 540, fh + 40)], size=sz, col=cc, txt='R'))
            elif mv:
                dr = 1 if j % 2 == 0 else -1; yy = 520 + 40 * (j % 3); pr.append(E.prop(kind, path=[(0, 120 if dr > 0 else 1160, yy, 0), (d, 1160 if dr > 0 else 120, yy, 0)], size=sz, col=cc, txt=('R' if dr > 0 else 'L') + ' walk'))
            else:
                x = {'left': 190, 'right': 1090, 'center': 640}.get(wh, [160, 1100, 330, 960][j]); pr.append(E.prop(kind, path=[(0, x, 480 + 30 * j, 0)], size=sz, col=cc))
        if mk == 'joy' and len(pr) < 3 and 'balloon' not in used: pr += [E.prop('balloon', path=[(0, 260 + 640 * q, 560, 60), (d, 270 + 640 * q, 560, 170)], col=D.PAL[(si + q) % 10]) for q in (0, 1)]
        sf = []
        for j, q in enumerate(s.get('sfx') or []):
            nm, t_ = (q, .4 + j * .6) if isinstance(q, str) else (q.get('name', ''), float(q.get('t', .4)))
            nm = nm if nm in E.SFX else SFXMAP.get(nm.lower()); 
            if nm: sf.append((min(t_, d - .3), nm, .8))
        if sfx0 and not sf: sf.append((.5, sfx0, .7))
        if mk == 'fear': sf += [(.3 + q * .9, 'thud', .35) for q in range(int(d / .9))]
        fxs = []
        for f in (s.get('fx') or []):
            kd, _, arg = f.partition(':')
            if kd == 'confetti': fxs.append(E.fx(d * .4, 'confetti', d=3.0))
            elif kd == 'flash': fxs.append(E.fx(.3, 'flash', a=.7))
            elif kd == 'shake': fxs.append(E.fx(.3, 'shake', amp=12))
            elif kd == 'speed': fxs.append(E.fx(.3, 'speed', d=min(1.2, d - .4)))
            elif kd == 'sparkle': fxs.append(E.fx(.5, 'sparkle', x=640, y=420))
            elif kd == 'burst': fxs.append(E.fx(d * .4, 'burst', text=arg or '!', x=640, y=200))
            elif kd == 'title': fxs.append(E.fx(.4, 'title', text=(arg or '').upper(), d=min(2.0, d - 1.0), size=int(min(100, 1500 / max(len(arg or 'x'), 1))), y=250))
        if mk == 'action' and not any(f.startswith('speed') for f in (s.get('fx') or [])): fxs.append(E.fx(.3, 'speed', d=min(1.2, d - .4)))
        if si == 0: fxs.append(E.fx(.4, 'title', text=title.upper(), d=min(2.2, d - 1.0), size=int(min(100, 1500 / max(len(title), 1))), y=250))
        if si == n - 1: fxs.append(E.fx(max(.5, d - 2.0), 'title', text='THE END', d=1.6, size=100, y=300))
        a0 = A[0]['name'] if A else None; cm = s.get('camera'); ci = si % 4
        cam = dict(follow=a0, z=(1.05, 1.3), lead=40) if (cm == 'follow' or (not cm and ci == 0)) and a0 else dict(z=(1.0, 1.3)) if cm == 'zoom_in' else dict(z=(1.3, 1.0)) if cm == 'zoom_out' else dict(x=(720, 560), z=1.08) if cm == 'pan_left' else dict(x=(560, 720), z=1.08) if cm == 'pan_right' else dict(z=1.05) if cm == 'static' else dict(x=(560, 720), z=1.08) if ci == 1 else dict(z=(1.3, 1.0)) if ci == 2 else dict(x=(720, 560), z=(1.0, 1.12))
        if cm == 'shake': cam = dict(z=1.1, shake=6)
        tr = s.get('transition') if s.get('transition') in TRS else ('fade' if bg != seenbg else 'cut'); tr = 'cut' if si == 0 else tr
        hd = None
        if s.get('hud'): h = s['hud']; hd = E.hud(str(h.get('a', 'RED'))[:3].upper(), str(h.get('b', 'BLU'))[:3].upper(), int(h.get('sa', 0)), int(h.get('sb', 0)), str(h.get('clock', "1'")))
        sc = E.scene(d, bg, bo, actors, pr, cam, fxs, sf, None, em, (.5, .8) if genre == 'sports' else ((.3, .9) if emo == 'joy' else (.25, .35)), music, tr, hd)
        sc.update(tod=tint, wx=wx, mood=mk, voice=voice, letter=genre in ('story', 'doc'), em=emo, text=text, kar=kar(words, d, em))
        if s.get('tag') or bg != seenbg: sc['tag'] = (s.get('tag') or (bo.get('city', bg)).upper()).upper()
        seenbg = bg; out.append(sc)
    best = max(range(n), key=lambda i: ({'joy': 3, 'shock': 3, 'panic': 2, 'angry': 2}.get(out[i]['em'], 0), -i)); th = plan.get('thumb') or {}
    out[best]['thumb'] = (str(th.get('text') or ' '.join(title.split()[:2]).upper() + '!'), out[best]['dur'] * .55)
    return out, genre, title

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('script'); ap.add_argument('out', nargs='?', default='output.mp4'); ap.add_argument('--plan'); ap.add_argument('--prompt-only', action='store_true'); ap.add_argument('--fast', action='store_true')
    ap.add_argument('--tts'); ap.add_argument('--voice-name', default='en-US-GuyNeural'); ap.add_argument('--voice'); ap.add_argument('--model', default=os.environ.get('LEGO_MODEL')); ap.add_argument('--provider', default='auto', choices=['auto', 'anthropic', 'gemini', 'groq', 'openrouter', 'ollama']); ap.add_argument('--save-plan', default='plan.json'); a = ap.parse_args()
    script = open(a.script, encoding='utf-8').read()
    if a.prompt_only:
        open('ai_prompt.txt', 'w', encoding='utf-8').write(SYSTEM + '\n\nSCRIPT:\n' + script); return print('Wrote ai_prompt.txt - paste it into Claude.ai (or any chat AI), save the JSON reply as plan.json, then run with --plan plan.json')
    if a.fast: E.K = 1.0
    if a.plan:
        try: plan = json.load(open(a.plan, encoding='utf-8'))
        except (ValueError, OSError) as e: raise SystemExit(f'plan file {a.plan} is not valid JSON ({e}). Paste the AI reply again and keep only the JSON, from the first brace to the last brace.')
        if not isinstance(plan, dict) or not isinstance(plan.get('scenes'), list) or not plan['scenes']:
            raise SystemExit(f"plan file {a.plan} has no 'scenes' list. Expected JSON starting with {{\"title\": ..., \"scenes\": [...]}}. Keys found: {list(plan)[:8] if isinstance(plan, dict) else type(plan).__name__}")
    elif choose(a.provider, a.model):
        fn, mdl, key = choose(a.provider, a.model); print('AI provider model:', mdl, flush=True); plan = ask(script, mdl, key, fn); json.dump(plan, open(a.save_plan, 'w'), indent=1); print('AI plan saved to', a.save_plan, flush=True)
    else: plan = None; print('No AI key set (ANTHROPIC/GEMINI/GROQ/OPENROUTER) and no --plan: using the basic offline planner (less intelligent). Use --prompt-only for the AI route.')
    tts = D.tts_edge(a.voice_name) if a.tts == 'edge' else None; sc, g, ti = build_scenes(plan, tts) if plan else D.plan(script, None, None, tts)
    if a.voice:
        import subprocess, wave; wv = '/tmp/_voice.wav'; subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', a.voice, '-ar', str(E.SR), '-ac', '1', wv], check=True)
        with wave.open(wv) as q: vd = q.getnframes() / q.getframerate()
        f = (vd + 1.0) / sum(s['dur'] for s in sc)
        for s in sc: s['dur'] *= f; s['kar'] = tuple((x0 * f, x1 * f, [(w, w0 * f, w1 * f) for w, w0, w1 in ws], em) for x0, x1, ws, em in s['kar'])
        sc[0]['voice'] = wv
    print(f'genre={g} scenes={len(sc)} duration={sum(s["dur"] for s in sc):.1f}s', flush=True); D.pack(sc, g, ti, a.out); E.make(sc, a.out)
if __name__ == '__main__': main()
