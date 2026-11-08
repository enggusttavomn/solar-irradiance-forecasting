"""Render three final-setting stills, then wait for the local visual-QA gate.

This gate is an internal agent review checkpoint, not a user permission flow.
The same Blender process then renders the movie, retaining compiled shaders.
"""
import hashlib
import json
from pathlib import Path
import time
import bpy

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'documentacao/relatorio_final_ea019/video/revisao_00_40_v6'

scene=bpy.context.scene
blend=Path(bpy.data.filepath)
digest=hashlib.sha256(blend.read_bytes()).hexdigest()
folder=OUT/'qa_ultima_conferencia';folder.mkdir(exist_ok=True)
raw=scene.render.filepath
scene.render.image_settings.file_format='PNG'
for second in [1,14.5,20.5]:
    scene.frame_set(round(second*30)+1)
    scene.render.filepath=str(folder/f't_{second:g}.png')
    bpy.ops.render.render(write_still=True)
(OUT/'qa_gate_esperando.json').write_text(json.dumps({'blend_sha256':digest,'stills':[1,14.5,20.5]}),encoding='utf-8')
print('V6_QA_GATE_READY',flush=True)
gate=OUT/'qa_render_aprovado_v6.json'
while True:
    if gate.is_file():
        data=json.loads(gate.read_text(encoding='utf-8'))
        if data.get('blend_sha256')==digest and data.get('approved') is True:
            break
    time.sleep(1)
print('V6_QA_GATE_PASSED',flush=True)
scene.render.image_settings.file_format='FFMPEG'
scene.render.filepath=raw
scene.frame_set(1)
bpy.ops.render.render(animation=True)
