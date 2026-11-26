#!/usr/bin/env python3
"""Offline procedural 3D animation renderer. All visuals are generated locally in Blender."""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, tempfile, re
from pathlib import Path

from cinematic_director import direct_plan

def split_script(text):
    parts = [x.strip() for x in re.split(r'(?<=[.!?])\s+', text) if x.strip()]
    if not parts:
        parts = [text.strip()]
    return [{"text": p, "visual": "cinematic_character", "mood": "determined"} for p in parts]

BLENDER_SOURCE = r'''
import bpy, sys, json, math, os
from mathutils import Vector
args = sys.argv[sys.argv.index("--")+1:]
plan_path, output, fps, seconds, preview = args[0], args[1], int(args[2]), float(args[3]), args[4] == "1"
plan=json.load(open(plan_path,encoding="utf-8"))
scenes=plan.get("scenes") or [{"text":plan.get("title","A cinematic moment")}]
bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete(use_global=False)
s=bpy.context.scene
# Blender renamed/removed Eevee engine identifiers across major versions.
engine_ids = {item.identifier for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
if "BLENDER_EEVEE_NEXT" in engine_ids:
    s.render.engine = "BLENDER_EEVEE_NEXT"
elif "BLENDER_EEVEE" in engine_ids:
    s.render.engine = "BLENDER_EEVEE"
else:
    raise RuntimeError("No Eevee render engine is available in this Blender build. Available engines: " + ", ".join(sorted(engine_ids)))
s.render.resolution_x=640 if preview else 960; s.render.resolution_y=360 if preview else 540; s.render.resolution_percentage=100
s.render.fps=fps
s.render.use_persistent_data=True
s.render.threads_mode='FIXED'; s.render.threads=2 if preview else 4
if hasattr(s, 'eevee') and hasattr(s.eevee, 'taa_render_samples'):
 s.eevee.taa_render_samples=8 if preview else 16
# Blender 5.x separates the media type from the image/video format.
s.render.image_settings.media_type = "VIDEO"
s.render.image_settings.file_format = "FFMPEG"
s.render.ffmpeg.format = "MPEG4"
s.render.ffmpeg.codec = "H264"
s.render.ffmpeg.constant_rate_factor = "MEDIUM"
s.render.filepath=output
s.world.color=(0.025,0.025,0.025)
s.view_settings.view_transform="AgX"
def mat(name,color,metal=0,rough=.55):
 m=bpy.data.materials.new(name); m.diffuse_color=(*color,1); m.use_nodes=True
 p=m.node_tree.nodes.get("Principled BSDF"); p.inputs["Base Color"].default_value=(*color,1); p.inputs["Metallic"].default_value=metal; p.inputs["Roughness"].default_value=rough
 return m
skin=mat("warm natural skin",(0.56,.31,.19)); shirt=mat("deep teal fabric",(.025,.20,.23)); pants=mat("charcoal trousers",(.055,.075,.095)); hair=mat("dark hair",(.035,.022,.018)); white=mat("eye whites",(.82,.82,.76)); iris=mat("dark irises",(.06,.035,.02)); gold=mat("warm practical light",(.8,.39,.09),.2)
def uv(name,loc,scale,material):
 bpy.ops.mesh.primitive_uv_sphere_add(segments=24,ring_count=16,location=loc); o=bpy.context.object; o.name=name; o.scale=scale; o.data.materials.append(material); bpy.ops.object.shade_smooth(); return o
def cyl(name,a,b,r,material):
 mid=(Vector(a)+Vector(b))/2; d=Vector(b)-Vector(a)
 bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=r, depth=d.length, location=mid)
 o=bpy.context.object; o.name=name; o.rotation_mode="QUATERNION"; o.rotation_quaternion=d.to_track_quat("Z","Y"); o.data.materials.append(material); bpy.ops.object.shade_smooth(); bevel=o.modifiers.new("soft edges","BEVEL"); bevel.width=.06; bevel.segments=3; o.modifiers.new("weighted normals","WEIGHTED_NORMAL"); return o
# Ground and layered atmospheric backdrop
floor_mat=mat("matte stage",(.035,.055,.07))
bpy.ops.mesh.primitive_plane_add(size=200, location=(0,0,-.08)); bpy.context.object.data.materials.append(floor_mat)
for x in (-5,-3,3,5):
 bpy.ops.mesh.primitive_cube_add(size=1, location=(x,2,1.1)); o=bpy.context.object; o.scale=(1.1,.6,1.2+(abs(x)%2)*.5); o.data.materials.append(mat("architectural shadow "+str(x),(.045+.01*abs(x),.07,.09)))
# Reusable lightweight environment kits. Visibility is switched per directed scene.
wood=mat("environment wood",(.19,.095,.045)); leaves=mat("forest foliage",(.055,.19,.075)); wall=mat("village plaster",(.48,.32,.19)); roof=mat("thatch roof",(.16,.075,.035)); smoke_mat=mat("smoke grey",(.34,.36,.37))
environment_objects={"forest":[],"village":[],"battlefield":[],"water":[],"mountain":[],"smoke":[]}
for i,x in enumerate((-4.2,-2.8,2.8,4.2)):
 trunk=cyl("forest tree trunk",(x,1.2,0),(x,1.2,1.45),.13,wood); environment_objects["forest"].append(trunk)
 crown=uv("forest canopy",(x,1.2,1.85),(.72,.62,.88),leaves); environment_objects["forest"].append(crown)
for i,x in enumerate((-3.4,0,3.4)):
 bpy.ops.mesh.primitive_cube_add(size=1,location=(x,2.1,.72)); hut=bpy.context.object; hut.name="village hut"; hut.scale=(1.25,1.0,.9); hut.data.materials.append(wall); environment_objects["village"].append(hut)
 bpy.ops.mesh.primitive_cone_add(vertices=4,radius1=1.05,radius2=0,depth=1.0,location=(x,2.1,1.65),rotation=(0,0,math.radians(45))); thatch=bpy.context.object; thatch.name="village thatch roof"; thatch.data.materials.append(roof); environment_objects["village"].append(thatch)
for x in (-3.2,0,3.2):
 bpy.ops.mesh.primitive_cube_add(size=1,location=(x,1.8,.35)); barricade=bpy.context.object; barricade.name="battlefield debris"; barricade.scale=(1.1,.35,.45); barricade.rotation_euler[1]=math.radians(12); barricade.data.materials.append(wood); environment_objects["battlefield"].append(barricade)
bpy.ops.mesh.primitive_plane_add(size=30,location=(0,1,-.015)); water=bpy.context.object; water.name="water environment"; water.data.materials.append(mat("water surface",(.025,.12,.19),.15,.22)); environment_objects["water"].append(water)
for x in (-4,0,4):
 bpy.ops.mesh.primitive_cone_add(vertices=8,radius1=2.2,radius2=0,depth=4,location=(x,3,1.9)); peak=bpy.context.object; peak.name="distant mountain"; peak.data.materials.append(mat("mountain stone",(.12,.15,.17))); environment_objects["mountain"].append(peak)
for i in range(4):
 cloud=uv("forest smoke",(2.0+i*.13,1.1,1.1+i*.34),(.38+i*.08,.32+i*.08,.45+i*.09),smoke_mat); environment_objects["smoke"].append(cloud)
# Character assembled as separate expressive parts; keyframes animate posture, gaze and gestures.
root=bpy.data.objects.new("CHARACTER_ROOT",None); s.collection.objects.link(root)
def part(o):
 o.parent=root; return o
torso=part(uv("torso",(0,0,1.22),(.39,.24,.57),shirt))
neck=part(uv("neck",(0,0,1.83),(.13,.13,.18),skin))
head=part(uv("face",(0,0,2.16),(.34,.29,.43),skin))
part(uv("hair cap",(0,.015,2.48),(.35,.30,.20),hair))
# ears
for x in (-.34,.34): part(uv("ear",(x,0,2.17),(.075,.09,.12),skin))
# Eyes, eyelids and brows face camera at y=-1
for x in (-.13,.13):
 part(uv("eye white",(x,-.265,2.22),(.075,.035,.052),white))
 part(uv("iris",(x,-.299,2.22),(.027,.016,.032),iris))
 brow=part(cyl("expressive brow",(x-.07,-.275,2.32),(x+.07,-.275,2.34),.025,hair))
# Nose and mouth; mouth shape is changed per shot by scale/keyframes
part(uv("nose",(0,-.30,2.13),(.055,.07,.10),skin))
mouth=part(uv("mouth",(0,-.277,2.00),(.105,.025,.025),hair))
# arms and legs as segmented articulated-looking forms
limbs=[]
for side in (-1,1):
 shoulder=part(uv("shoulder",(side*.40,0,1.55),(.18,.19,.20),shirt))
 upper=part(cyl("upper arm",(side*.42,0,1.48),(side*.53,0,1.05),.105,shirt))
 fore=part(cyl("forearm",(side*.53,0,1.05),(side*.48,-.04,.70),.085,skin))
 hand=part(uv("hand",(side*.48,-.04,.67),(.09,.075,.11),skin))
 thigh=part(cyl("thigh",(side*.16,0,.82),(side*.18,0,.42),.13,pants))
 shin=part(cyl("shin",(side*.18,0,.42),(side*.18,-.03,.08),.095,pants))
 foot=part(uv("shoe",(side*.18,-.12,.06),(.14,.25,.08),hair))
 limbs += [upper,fore,thigh,shin]
# Stage props, key light and cinematic camera
def area(name,loc,power,color,size,target):
 bpy.ops.object.light_add(type="AREA", location=loc); l=bpy.context.object; l.name=name; l.data.energy=power; l.data.color=color; l.data.shape="DISK"; l.data.size=size; l.rotation_euler=(Vector(target)-l.location).to_track_quat("-Z","Y").to_euler()
area("warm key",(-3,-4,6),950,(1,.72,.48),5,(0,0,1.4))
area("cool fill",(4,-2,3),600,(.35,.58,1),4,(0,0,1.4))
area("rim",(0,3,4),1100,(1,.35,.12),3,(0,0,1.5))
bpy.ops.object.camera_add(location=(3.2,-7.8,2.9)); cam=bpy.context.object; cam.rotation_euler=(Vector((0,0,1.35))-cam.location).to_track_quat("-Z","Y").to_euler(); cam.data.lens=48; s.camera=cam
# A restrained title-card-free scene: no external textures, images, fonts or footage.
caption_curve=bpy.data.curves.new("scene caption","FONT"); caption_curve.body=""; caption_curve.size=.25
caption=bpy.data.objects.new("caption",caption_curve); s.collection.objects.link(caption); caption.location=(-2.3,-.2,.15); caption.rotation_euler=(math.radians(90),0,0); caption.data.materials.append(mat("caption ivory",(.9,.78,.54)))
# Animate all scenes in one continuous film; character acts are varied by semantic cues.
frame=1
for idx,scn in enumerate(scenes):
 text=str(scn.get("text","")); low=text.lower()
 start=frame; end=frame+max(1,int(seconds*fps))-1
 env=str(scn.get("environment","landscape"))
 for env_name, env_objects in environment_objects.items():
  for env_obj in env_objects:
   visible=(env_name == env) if env_name != "smoke" else any(w in low for w in ("smoke","fire","burning","burns","flames"))
   env_obj.hide_render=not visible
   env_obj.keyframe_insert(data_path="hide_render",frame=start)
   env_obj.keyframe_insert(data_path="hide_render",frame=end)
 caption.data.body=text[:105]
 # Motivate character travel and acting from the director's scene metadata.
 action=str(scn.get('action','observe')); mood=str(scn.get('mood','determined'))
 travel={'walk':0.85,'run':1.45,'fall':0.18}.get(action,0.22)
 direction=-1 if idx%2 else 1
 root.location=(-travel*.5*direction,0,0); root.rotation_euler=(0,0,0)
 root.keyframe_insert("location",frame=start); root.keyframe_insert("rotation_euler",frame=start)
 root.location=(travel*.5*direction,0,0); root.rotation_euler[2]=math.radians(-12 if mood in ('fear','sadness') else 10)
 root.keyframe_insert("location",frame=end); root.keyframe_insert("rotation_euler",frame=end)
 # Arm gestures plus alternating leg swings for walk/run beats.
 for j,obj in enumerate(limbs):
  obj.keyframe_insert("rotation_euler",frame=start)
  if action in ('walk','run') and j in (2,3,6,7):
   phase=1 if j in (2,7) else -1
   amount=22 if action=='run' else 12
   obj.rotation_euler[1]=math.radians(phase*amount)
  elif j in (0,1):
   obj.rotation_euler[1]=math.radians((-18 if j==0 else 18) if action=='speak' else (10 if j==0 else -10))
  obj.keyframe_insert("rotation_euler",frame=start+int((end-start)*.45))
  obj.rotation_euler[1]=0; obj.keyframe_insert("rotation_euler",frame=end)
 # Mouth opens subtly for speech; brows/eyes are intentionally understated.
 mouth.scale=(.105,.025,.045 if any(w in low for w in ("said","speak","speech","shout")) else .018); mouth.keyframe_insert("scale",frame=start); mouth.keyframe_insert("scale",frame=end)
 shot=str(scn.get('shot_type','medium'))
 profiles={
  'wide':((3.8,-9.5,3.1),35,(0,0,1.2)),
  'medium_wide':((3.0,-8.0,2.8),40,(0,0,1.35)),
  'medium':((2.5,-6.8,2.65),50,(0,0,1.4)),
  'medium_close':((1.2,-5.2,2.45),65,(0,0,1.85)),
  'close_up':((0.6,-4.2,2.35),75,(0,0,2.1)),
 }
 base,lens,target=profiles.get(shot,profiles['medium'])
 cam.data.lens=lens
 base_v=Vector(base); target_v=Vector(target)
 move=str(scn.get('camera_move','slow_pan'))
 if move=='push_in': cam.location=base_v+(base_v-target_v)*0.10
 elif move=='pull_back': cam.location=base_v
 elif move=='tracking': cam.location=base_v+Vector((-0.45*direction,0,0))
 else: cam.location=base_v+Vector((0.12 if idx%2 else -0.12,0,0))
 cam.rotation_euler=(target_v-cam.location).to_track_quat("-Z","Y").to_euler()
 cam.keyframe_insert("location",frame=start); cam.keyframe_insert("rotation_euler",frame=start)
 if move=='push_in': cam.location=base_v
 elif move=='pull_back': cam.location=base_v+(base_v-target_v)*0.12
 elif move=='tracking': cam.location=base_v+Vector((0.45*direction,0,0))
 else: cam.location=base_v+Vector((-0.12 if idx%2 else 0.12,0,0))
 cam.rotation_euler=(target_v-cam.location).to_track_quat("-Z","Y").to_euler()
 cam.keyframe_insert("location",frame=end); cam.keyframe_insert("rotation_euler",frame=end)
 frame=end+1
s.frame_start=1; s.frame_end=frame-1; s.render.filepath=output
s.render.image_settings.color_mode="RGB"
bpy.ops.wm.save_as_mainfile(filepath=output+".blend")
bpy.ops.render.render(animation=True)
'''

def main():
    p=argparse.ArgumentParser(description="Fully local procedural 3D animation renderer (no image websites or online assets).")
    p.add_argument("script"); p.add_argument("out"); p.add_argument("--plan"); p.add_argument("--blender")
    p.add_argument("--fps",type=int,default=15); p.add_argument("--seconds",type=float,default=6.0); p.add_argument("--max-scenes",type=int,help="Render only the first N scenes."); p.add_argument("--preview",action="store_true",help="Use 640x360 and a short low-frame-rate test render."); p.add_argument("--silent",action="store_true")
    a=p.parse_args()
    source=Path(a.script).read_text(encoding="utf-8")
    if a.plan:
        plan=json.loads(Path(a.plan).read_text(encoding="utf-8"))
        if not isinstance(plan.get("scenes"),list) or not plan["scenes"]: raise ValueError("Plan must contain a non-empty scenes array.")
    else:
        plan={"title":Path(a.script).stem,"scenes":split_script(source)}
    if not plan["scenes"]: raise ValueError("No scenes found in script.")
    plan["scenes"] = direct_plan(plan["scenes"])
    print("[animation] Director: offline shot/action planning enabled.", flush=True)
    if a.max_scenes is not None:
        if a.max_scenes < 1: raise ValueError("--max-scenes must be at least 1.")
        plan["scenes"] = plan["scenes"][:a.max_scenes]
        print(f"[animation] Limited render to first {len(plan['scenes'])} scene(s).", flush=True)
    blender=a.blender or os.environ.get("BLENDER_EXE") or shutil.which("blender")
    if not blender: raise RuntimeError("Blender was not found. Install the free Blender desktop application and add blender.exe to PATH, or set BLENDER_EXE.")
    out=Path(a.out).resolve(); out.parent.mkdir(parents=True,exist_ok=True)
    # Catch syntax errors in the embedded Blender program before launching Blender.
    try:
        compile(BLENDER_SOURCE, "<embedded_blender_scene>", "exec")
    except SyntaxError as exc:
        raise RuntimeError(f"Embedded Blender scene script has a syntax error at line {exc.lineno}: {exc.msg}") from exc
    with tempfile.TemporaryDirectory(prefix="ai_cinema_animation_") as td:
        plan_path=Path(td)/"plan.json"; py_path=Path(td)/"render_scene.py"
        plan_path.write_text(json.dumps(plan,ensure_ascii=False),encoding="utf-8"); py_path.write_text(BLENDER_SOURCE,encoding="utf-8")
        fps = max(6, min(12, a.fps)) if a.preview else max(12, min(60, a.fps))
        seconds = max(1.0, min(2.0, a.seconds)) if a.preview else max(2.0, min(20.0, a.seconds))
        cmd=[blender,"-b","-t","2" if a.preview else "4","--python",str(py_path),"--",str(plan_path),str(out),str(fps),str(seconds),"1" if a.preview else "0"]
        print("[animation] Backend: local Blender procedural 3D",flush=True)
        print("[animation] Visual source: generated geometry/materials/lighting only; no external image or footage requests.",flush=True)
        print(f"[animation] Scenes: {len(plan['scenes'])}; target: {out}",flush=True)
        if a.preview: print("[animation] Preview mode: 640x360, maximum 12 fps, maximum 2 seconds per scene.",flush=True)
        result=subprocess.run(cmd)
        if result.returncode: return result.returncode
    if not out.is_file() or out.stat().st_size < 1024:
        size = out.stat().st_size if out.is_file() else 0
        raise RuntimeError(f"Blender did not produce a valid MP4 (output size: {size} bytes). Check the Blender render/FFmpeg messages above.")
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        check = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height", "-show_entries", "format=duration", "-of", "json", str(out)],
            capture_output=True, text=True, check=False,
        )
        if check.returncode != 0:
            raise RuntimeError("The MP4 file failed FFprobe validation: " + (check.stderr.strip() or "unknown container/codec error"))
        try:
            media = json.loads(check.stdout)
            if not media.get("streams") or float(media.get("format", {}).get("duration", 0)) <= 0:
                raise ValueError("missing video stream or zero duration")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"The MP4 file is incomplete or has no playable video stream: {exc}") from exc
    print(f"[animation] Render complete: {out} ({out.stat().st_size:,} bytes)",flush=True)
    return 0

if __name__=="__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        print(f"[animation] ERROR: {exc}",file=sys.stderr); raise SystemExit(2)
